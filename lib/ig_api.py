"""
Meta Graph API v21.0 client.

Handles: authentication via long-lived user token, 24-hour JSON response
cache, exponential backoff on 429/5xx, per-call logging.

DO NOT log app_secret or long_lived_token.
"""

from __future__ import annotations

import hashlib
import json
import logging
import logging.handlers
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests


class IGAPIError(Exception):
    """Raised on non-retryable API errors (HTTP 400, auth failures, etc.)."""

    def __init__(
        self,
        message: str,
        code: int | None = None,
        subcode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.subcode = subcode

    def __repr__(self) -> str:  # pragma: no cover
        return f"IGAPIError({self.args[0]!r}, code={self.code}, subcode={self.subcode})"


# Module-level logger — handlers added in IGClient.__init__ when log_path given
log = logging.getLogger("ig_api")


class IGClient:
    """Thin client for the Meta Graph API (Instagram Business endpoints).

    Caches all GET responses as JSON files keyed by request hash.
    Retries 429 / 5xx up to 3 times with exponential backoff.
    Never logs access_token or app_secret.
    """

    BASE_URL = "https://graph.facebook.com"

    def __init__(
        self,
        ig_user_id: str,
        access_token: str,
        api_version: str = "v21.0",
        cache_dir: Path | str = "./cache",
        cache_ttl_hours: int = 24,
        log_path: Path | str | None = None,
    ) -> None:
        self._ig_user_id = ig_user_id
        self._access_token = access_token
        self._api_version = api_version
        self._cache_dir = Path(cache_dir)
        self._cache_ttl_seconds = cache_ttl_hours * 3600

        self._cache_dir.mkdir(parents=True, exist_ok=True)

        if log_path is not None:
            _attach_file_handler(log, Path(log_path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_url(self, endpoint: str) -> str:
        return f"{self.BASE_URL}/{self._api_version}/{endpoint}"

    def _cache_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.json"

    def _is_cache_valid(self, path: Path) -> bool:
        if not path.exists():
            return False
        age = time.time() - path.stat().st_mtime
        return age < self._cache_ttl_seconds

    @staticmethod
    def _make_cache_key(url: str, params: dict[str, Any]) -> str:
        # Exclude access_token from the cache key (it's sensitive and
        # the cache directory itself is gitignored)
        safe_params = {k: v for k, v in params.items() if k != "access_token"}
        payload = url + json.dumps(sorted(safe_params.items()), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _cached_get(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        cache_key: str | None = None,
    ) -> dict:
        """Perform a GET with caching and retry logic.

        Raises:
            IGAPIError: on HTTP 400 or other non-retryable client errors.
        """
        url = self._build_url(endpoint)
        request_params = {**params, "access_token": self._access_token}

        if cache_key is None:
            cache_key = self._make_cache_key(url, params)
        cache_file = self._cache_path(cache_key)

        if self._is_cache_valid(cache_file):
            log.debug("CACHE HIT  endpoint=%s", endpoint)
            with cache_file.open("r", encoding="utf-8") as fh:
                return json.load(fh)

        # --- HTTP fetch with retry ---
        max_attempts = 4  # 1 initial + 3 retries
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            t0 = time.monotonic()
            try:
                resp = requests.get(url, params=request_params, timeout=30)
            except requests.RequestException as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000
                log.warning(
                    "REQUEST ERROR endpoint=%s attempt=%d elapsed_ms=%.0f error=%s",
                    endpoint,
                    attempt,
                    elapsed_ms,
                    type(exc).__name__,
                )
                last_exc = exc
                _backoff(attempt)
                continue

            elapsed_ms = (time.monotonic() - t0) * 1000
            status = resp.status_code

            log.info(
                "API CALL   endpoint=%s status=%d attempt=%d cache=MISS elapsed_ms=%.0f",
                endpoint,
                status,
                attempt,
                elapsed_ms,
            )

            if status == 200:
                data: dict = resp.json()
                with cache_file.open("w", encoding="utf-8") as fh:
                    json.dump(data, fh)
                return data

            if status == 400:
                _raise_api_error(resp)

            if status == 429 or status in (500, 502, 503):
                log.warning(
                    "RETRYABLE  endpoint=%s status=%d attempt=%d",
                    endpoint,
                    status,
                    attempt,
                )
                last_exc = IGAPIError(f"HTTP {status}", code=status)
                _backoff(attempt)
                continue

            # Any other 4xx or unexpected status — raise immediately
            _raise_api_error(resp)

        raise IGAPIError(
            f"Max retries exceeded for endpoint {endpoint!r}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_profile(self) -> dict:
        """Fetch account-level profile fields.

        Returns the raw API dict.
        """
        fields = (
            "id,name,biography,website,"
            "followers_count,follows_count,media_count,"
            "profile_picture_url,username"
        )
        return self._cached_get(
            self._ig_user_id,
            {"fields": fields},
        )

    def get_media(self, since: date, until: date) -> list[dict]:
        """Fetch all media in [since, until] with insights merged.

        Paginates until there are no more pages OR the oldest post predates
        `since`. Each item has basic fields + flattened insights.
        """
        fields = (
            "id,caption,media_type,timestamp,"
            "permalink,like_count,comments_count"
        )
        params: dict[str, Any] = {
            "fields": fields,
            "limit": 50,
        }

        endpoint = f"{self._ig_user_id}/media"
        results: list[dict] = []
        page_url: str | None = None  # None → use standard endpoint; str → use raw URL

        while True:
            if page_url is not None:
                # Pagination: use the raw next URL directly (already has token baked in)
                t0 = time.monotonic()
                try:
                    resp = requests.get(page_url, timeout=30)
                except requests.RequestException as exc:
                    log.warning("Pagination request failed: %s", type(exc).__name__)
                    break
                elapsed_ms = (time.monotonic() - t0) * 1000
                log.info(
                    "API CALL   endpoint=%s/page status=%d cache=MISS elapsed_ms=%.0f",
                    endpoint,
                    resp.status_code,
                    elapsed_ms,
                )
                if resp.status_code != 200:
                    break
                page_data = resp.json()
            else:
                page_data = self._cached_get(endpoint, params)

            items: list[dict] = page_data.get("data", [])
            stop_early = False

            for item in items:
                ts_str = item.get("timestamp", "")
                if ts_str:
                    post_date = _parse_iso_date(ts_str)
                    if post_date < since:
                        stop_early = True
                        break
                    if post_date > until:
                        continue

                # Merge insights into the item dict
                insights = self.get_media_insights(
                    item["id"],
                    item.get("media_type", "IMAGE"),
                )
                results.append({**item, **insights})

            paging = page_data.get("paging", {})
            next_url = paging.get("next")
            if stop_early or not next_url:
                break
            page_url = next_url

        return results

    def get_media_insights(self, media_id: str, media_type: str) -> dict:
        """Fetch per-post insight metrics.

        Returns a flattened dict like:
            {"impressions": 1234, "reach": 800, "saved": 55, ...}

        On 403/permission error: logs a warning and returns {}.
        """
        media_type_upper = media_type.upper()
        if media_type_upper in ("VIDEO", "REEL"):
            metric = (
                "impressions,reach,saved,shares,"
                "plays,ig_reels_avg_watch_time,ig_reels_video_view_total_time"
            )
        else:
            metric = "impressions,reach,saved,shares"

        endpoint = f"{media_id}/insights"
        try:
            raw = self._cached_get(endpoint, {"metric": metric})
        except IGAPIError as exc:
            # Permission or availability issues are common for older posts
            log.warning(
                "Insights unavailable for media_id=%s: %s", media_id, exc
            )
            return {}

        flat: dict[str, Any] = {}
        for item in raw.get("data", []):
            name: str = item.get("name", "")
            value = item.get("values", [{}])[0].get("value") if "values" in item else item.get("value")

            if name == "ig_reels_avg_watch_time":
                # API returns milliseconds — convert to seconds
                flat["avg_watch_seconds"] = float(value) / 1000.0 if value is not None else None
            elif name == "ig_reels_video_view_total_time":
                # Total watch time in ms; used as fallback only — skip storing raw
                flat["_total_watch_time_ms"] = value
            elif name == "saved":
                flat["saved"] = value
            else:
                flat[name] = value

        # If avg_watch_seconds not yet set but we have total + plays, derive it
        if flat.get("avg_watch_seconds") is None:
            total_ms = flat.pop("_total_watch_time_ms", None)
            plays = flat.get("plays")
            if total_ms and plays and int(plays) > 0:
                flat["avg_watch_seconds"] = float(total_ms) / 1000.0 / int(plays)
        else:
            flat.pop("_total_watch_time_ms", None)

        return flat

    def get_audience_insights(self) -> dict:
        """Fetch audience demographics and active-hours data.

        Returns a normalized dict:
            {
                "geo":          {"Mumbai": 15.2, ...},
                "age_gender":   {"M.25-34": 8.1, ...},
                "active_hours": {0: 0.3, ...},
            }

        On permission errors: logs warning with account ID (never token) and
        returns empty dict.
        """
        result: dict[str, dict] = {"geo": {}, "age_gender": {}, "active_hours": {}}

        # --- Demographics ---
        try:
            demo_data = self._cached_get(
                f"{self._ig_user_id}/insights",
                {
                    "metric": "follower_demographics,reached_audience_demographics",
                    "period": "lifetime",
                    "breakdown": "age,gender,city",
                },
            )
            result["geo"], result["age_gender"] = _parse_demographics(demo_data)
        except IGAPIError as exc:
            log.warning(
                "Audience demographics unavailable for ig_user_id=%s: %s",
                self._ig_user_id,
                exc,
            )

        # --- Active hours ---
        try:
            online_data = self._cached_get(
                f"{self._ig_user_id}/insights",
                {
                    "metric": "online_followers",
                    "period": "day",
                },
            )
            result["active_hours"] = _parse_active_hours(online_data)
        except IGAPIError as exc:
            log.warning(
                "Active-hours data unavailable for ig_user_id=%s: %s",
                self._ig_user_id,
                exc,
            )

        return result

    def get_follower_growth(self, since: date, until: date) -> dict[date, int]:
        """Fetch daily follower counts for the given date range.

        Returns a dict mapping date → follower_count.
        On any error, returns {}.
        """
        try:
            raw = self._cached_get(
                f"{self._ig_user_id}/insights",
                {
                    "metric": "follower_count",
                    "period": "day",
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                },
            )
        except IGAPIError as exc:
            log.warning(
                "Follower growth unavailable for ig_user_id=%s: %s",
                self._ig_user_id,
                exc,
            )
            return {}

        growth: dict[date, int] = {}
        for item in raw.get("data", []):
            if item.get("name") != "follower_count":
                continue
            for entry in item.get("values", []):
                try:
                    end_time = _parse_iso_date(entry["end_time"])
                    value = int(entry["value"])
                    growth[end_time] = value
                except (KeyError, ValueError, TypeError):
                    continue

        return growth

    def discover_peer(self, peer_username: str) -> dict | None:
        """Look up a public Business/Creator account by username.

        Uses the Business Discovery API — requires the current IG user to be
        a Business account connected to a Facebook Page.

        Returns the peer's profile dict, or None if unavailable (personal
        accounts return HTTP 400 — handled silently at DEBUG level).
        """
        fields = (
            f"business_discovery.fields("
            f"id,name,biography,website,"
            f"followers_count,follows_count,media_count,username"
            f")"
        )
        try:
            raw = self._cached_get(
                self._ig_user_id,
                {
                    "fields": fields,
                    "username": peer_username,
                },
            )
            return raw.get("business_discovery")
        except IGAPIError as exc:
            log.debug(
                "Business discovery failed for username=%s: %s",
                peer_username,
                exc,
            )
            return None


# ------------------------------------------------------------------
# Module-level helpers (not part of the public API)
# ------------------------------------------------------------------

def _attach_file_handler(logger: logging.Logger, log_path: Path) -> None:
    """Add a rotating file handler to `logger` if not already present."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Avoid duplicate handlers on re-import / re-instantiation
    for handler in logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            if getattr(handler, "baseFilename", None) == str(log_path.resolve()):
                return
    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    if not logger.level:
        logger.setLevel(logging.DEBUG)


def _backoff(attempt: int) -> None:
    """Sleep for 2^(attempt+1) seconds: 2s, 4s, 8s."""
    delay = 2 ** (attempt + 1)
    log.debug("Backoff: sleeping %ds before retry", delay)
    time.sleep(delay)


def _raise_api_error(resp: requests.Response) -> None:
    """Parse the Graph API error envelope and raise IGAPIError."""
    try:
        body = resp.json()
        err = body.get("error", {})
        message = err.get("message", resp.text)
        code = err.get("code")
        subcode = err.get("error_subcode")
    except Exception:
        message = resp.text
        code = None
        subcode = None
    raise IGAPIError(message, code=code, subcode=subcode)


def _parse_iso_date(ts: str) -> date:
    """Parse an ISO-8601 timestamp string to a date object."""
    # Handles "2024-03-15T12:00:00+0000", "2024-03-15T12:00:00Z", etc.
    ts_clean = ts.replace("Z", "+00:00")
    # Strip timezone suffix for fromisoformat on Python 3.11
    if "+" in ts_clean[10:]:
        ts_clean = ts_clean[: ts_clean.rindex("+", 10)]
    elif ts_clean.endswith("-00:00"):
        ts_clean = ts_clean[:-6]
    try:
        return date.fromisoformat(ts_clean[:10])
    except ValueError:
        from datetime import datetime  # local import to avoid top-level cycle
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).date()


def _parse_demographics(raw: dict) -> tuple[dict[str, float], dict[str, float]]:
    """Extract geo and age_gender breakdowns from a demographics response."""
    geo: dict[str, float] = {}
    age_gender: dict[str, float] = {}

    for item in raw.get("data", []):
        name = item.get("name", "")
        # Breakdowns live under total_value.breakdowns
        total_val = item.get("total_value", {})
        breakdowns = total_val.get("breakdowns", [])
        for bd in breakdowns:
            dimension_keys = bd.get("dimension_keys", [])
            results = bd.get("results", [])
            for entry in results:
                dims = entry.get("dimension_values", [])
                pct = float(entry.get("value", 0))
                if not dims:
                    continue
                if "city" in dimension_keys and len(dims) >= dimension_keys.index("city") + 1:
                    city_idx = dimension_keys.index("city")
                    city = dims[city_idx]
                    geo[city] = geo.get(city, 0.0) + pct
                if "age" in dimension_keys and "gender" in dimension_keys:
                    age_idx = dimension_keys.index("age")
                    gender_idx = dimension_keys.index("gender")
                    if len(dims) > max(age_idx, gender_idx):
                        key = f"{dims[gender_idx]}.{dims[age_idx]}"
                        age_gender[key] = age_gender.get(key, 0.0) + pct

    return geo, age_gender


def _parse_active_hours(raw: dict) -> dict[int, float]:
    """Extract hour → relative-activity mapping from online_followers response."""
    active: dict[int, float] = {}
    for item in raw.get("data", []):
        if item.get("name") != "online_followers":
            continue
        for entry in item.get("values", []):
            hourly: dict = entry.get("value", {})
            for hour_str, count in hourly.items():
                try:
                    active[int(hour_str)] = float(count)
                except (ValueError, TypeError):
                    continue

    # Normalise to a 0-1 relative scale
    if active:
        max_val = max(active.values())
        if max_val > 0:
            active = {h: v / max_val for h, v in active.items()}

    return active
