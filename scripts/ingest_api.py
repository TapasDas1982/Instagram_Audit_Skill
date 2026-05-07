"""
API-based ingestion for the Instagram audit pipeline.

Calls IGClient to fetch profile, media, insights, and audience data for the
configured IG Business account, then normalizes into an AuditInput identical
in shape to what ingest_csv.py produces.

Phase 2 entry point — used by audit.py --source api.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from lib.ig_api import IGClient, IGAPIError  # noqa: F401 (re-exported for callers)
from lib.normalize import AudienceSnapshot, AuditInput, Post, Profile
from scripts.ingest_csv import _extract_hashtags


# Mapping from Meta Graph API media_type values to our internal canonical names
_MEDIA_TYPE_MAP: dict[str, str] = {
    "IMAGE": "image",
    "CAROUSEL_ALBUM": "carousel",
    "VIDEO": "video",
    "REEL": "reel",
}


def _normalize_media_type(raw_type: str) -> str:
    """Return our canonical media_type string for a Graph API media_type value."""
    return _MEDIA_TYPE_MAP.get(raw_type.upper(), "image")


def _build_profile(raw: dict) -> Profile:
    """Construct a Profile dataclass from a raw get_profile() response."""
    website = raw.get("website") or None
    return Profile(
        username=raw.get("username", ""),
        display_name=raw.get("name", raw.get("username", "")),
        bio=raw.get("biography", ""),
        has_link=bool(website),
        follower_count=int(raw.get("followers_count", 0)),
        following_count=int(raw.get("follows_count", 0)),
        media_count=int(raw.get("media_count", 0)),
        highlights_count=None,  # not available via standard Graph API
        is_business=True,        # we only support Business/Creator accounts
        profile_picture_url=raw.get("profile_picture_url"),
        website=website,
    )


def _build_post(raw: dict) -> Post:
    """Construct a Post dataclass from a raw media item (insights already merged)."""
    caption = raw.get("caption") or ""
    hashtags = _extract_hashtags(caption)
    media_type = _normalize_media_type(raw.get("media_type", "IMAGE"))

    # posted_at — the API returns "2024-03-15T12:00:00+0000"
    ts_str: str = raw.get("timestamp", "")
    posted_at: datetime
    if ts_str:
        posted_at = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    else:
        posted_at = datetime.utcnow()

    return Post(
        post_id=raw.get("id", ""),
        posted_at=posted_at,
        media_type=media_type,
        caption=caption,
        hashtags=hashtags,
        likes=int(raw.get("like_count", 0)),
        comments=int(raw.get("comments_count", 0)),
        saves=_opt_int(raw.get("saved")),
        shares=_opt_int(raw.get("shares")),
        reach=_opt_int(raw.get("reach")),
        impressions=_opt_int(raw.get("impressions")),
        plays=_opt_int(raw.get("plays")),
        avg_watch_seconds=_opt_float(raw.get("avg_watch_seconds")),
        video_length_seconds=None,  # not available via insights API
        replays=None,               # not available via standard insights
        permalink=raw.get("permalink") or None,
    )


def _opt_int(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _opt_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_audit_input_from_api(
    meta_config: dict,
    *,
    period_days: int = 30,
    cache_dir: str | Path = "./cache",
    log_path: str | Path | None = None,
) -> AuditInput:
    """Call Meta Graph API and return an AuditInput.

    Args:
        meta_config:  The META dict from config/config.py.
        period_days:  How many days back to include in the audit.
        cache_dir:    Directory for 24-hour JSON response cache.
        log_path:     Optional path for the rotating log file.

    Returns:
        AuditInput with source="api".

    Raises:
        IGAPIError: on hard API failures (auth errors, rate-limit exhaustion).
    """
    ig_user_id: str = meta_config["ig_user_id"]
    access_token: str = meta_config["long_lived_token"]
    api_version: str = meta_config.get("graph_api_version", "v21.0")
    cache_ttl_hours: int = 24

    client = IGClient(
        ig_user_id=ig_user_id,
        access_token=access_token,
        api_version=api_version,
        cache_dir=cache_dir,
        cache_ttl_hours=cache_ttl_hours,
        log_path=log_path,
    )

    # 1. Profile
    raw_profile = client.get_profile()

    # 2. Date window
    period_end: date = date.today()
    period_start: date = period_end - timedelta(days=period_days - 1)

    # 3. Media with insights merged
    raw_media = client.get_media(period_start, period_end)

    # 4. Audience
    raw_audience = client.get_audience_insights()

    # 5. Follower growth
    follower_growth: dict[date, int] = client.get_follower_growth(
        period_start, period_end
    )

    # 6. Build Profile
    api_profile = _build_profile(raw_profile)

    # 7. Build Post list
    posts: list[Post] = [_build_post(item) for item in raw_media]

    # 8. Build AudienceSnapshot
    audience = AudienceSnapshot(
        follower_count_by_day=follower_growth,
        geo=raw_audience.get("geo", {}),
        age_gender=raw_audience.get("age_gender", {}),
        active_hours=raw_audience.get("active_hours", {}),
    )

    # 9. Return
    return AuditInput(
        profile=api_profile,
        posts=posts,
        audience=audience,
        period_start=period_start,
        period_end=period_end,
        source="api",
    )
