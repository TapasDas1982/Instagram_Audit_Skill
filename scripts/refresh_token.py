"""
Meta long-lived token refresh.

Meta long-lived User tokens expire after 60 days. This script refreshes the
token 14 days before expiry and atomically rewrites config/config.py.

Run from cron (see deploy/cron/refresh_token.cron):
    python scripts/refresh_token.py [--force]

--force: refresh even if token isn't close to expiry (for testing).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Bootstrap: make project root importable when invoked as a script
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.py"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("refresh_token")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_meta_config() -> dict:
    """Load and return the META dict from config/config.py.

    Raises SystemExit with a helpful message on any failure.
    """
    if not _CONFIG_PATH.exists():
        log.error(
            "config/config.py not found. "
            "Copy config/config.example.py to config/config.py and fill in values."
        )
        sys.exit(1)

    try:
        config_dir = str(_CONFIG_PATH.parent)
        if config_dir not in sys.path:
            sys.path.insert(0, config_dir)
        import config  # type: ignore  # noqa: PLC0415
        meta = getattr(config, "META", None)
    except Exception as exc:
        log.error("Failed to import config/config.py: %s", exc)
        sys.exit(1)

    if meta is None:
        log.error("META dict not found in config/config.py.")
        sys.exit(1)

    return meta  # type: ignore[return-value]


def _validate_meta_config(meta: dict) -> None:
    """Exit with error if required fields are missing or still placeholder."""
    _PLACEHOLDER = (None, "REPLACE_ME", "", "None")

    for key in ("app_id", "app_secret", "long_lived_token"):
        val = meta.get(key)
        if val in _PLACEHOLDER:
            log.error(
                "META['%s'] is not configured. "
                "Set a real value in config/config.py before refreshing.",
                key,
            )
            sys.exit(1)


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def _token_needs_refresh(meta: dict, *, force: bool) -> bool:
    """Return True if the token should be refreshed now."""
    if force:
        return True

    expires_at_raw = meta.get("token_expires_at")
    if not expires_at_raw:
        log.info("token_expires_at not set; refreshing to be safe.")
        return True

    try:
        expires_at = datetime.fromisoformat(str(expires_at_raw))
    except ValueError:
        log.warning("Could not parse token_expires_at=%r; refreshing.", expires_at_raw)
        return True

    # Make timezone-aware if naive (assume UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    now = datetime.now(tz=timezone.utc)
    days_left = (expires_at - now).days

    if days_left > 14:
        log.info(
            "Token is fresh — expires in %d days (%s). Nothing to do.",
            days_left,
            expires_at.date().isoformat(),
        )
        return False

    log.info(
        "Token expires in %d days (%s) — within the 14-day refresh window.",
        days_left,
        expires_at.date().isoformat(),
    )
    return True


def _exchange_token(meta: dict) -> tuple[str, datetime]:
    """Call the Meta token exchange endpoint and return (new_token, new_expiry).

    NEVER logs app_secret or the token values.
    """
    api_version = meta.get("graph_api_version", "v21.0")
    url = f"https://graph.facebook.com/{api_version}/oauth/access_token"

    log.info("Requesting token refresh from Meta Graph API ...")

    try:
        resp = requests.get(
            url,
            params={
                "grant_type": "fb_exchange_token",
                "client_id": meta["app_id"],
                "client_secret": meta["app_secret"],
                "fb_exchange_token": meta["long_lived_token"],
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        log.error("Network error during token refresh: %s", type(exc).__name__)
        sys.exit(1)

    if resp.status_code != 200:
        # Log status and error message only — never the full URL (contains secret)
        try:
            err = resp.json().get("error", {})
            log.error(
                "Token refresh failed: HTTP %d — %s (code %s)",
                resp.status_code,
                err.get("message", "unknown error"),
                err.get("code", "?"),
            )
        except Exception:
            log.error("Token refresh failed: HTTP %d", resp.status_code)
        sys.exit(1)

    data = resp.json()
    new_token: str = data["access_token"]
    new_expiry = datetime.now(tz=timezone.utc) + timedelta(days=60)

    return new_token, new_expiry


# ---------------------------------------------------------------------------
# Atomic config rewrite
# ---------------------------------------------------------------------------

def _rewrite_config(new_token: str, new_expiry: datetime) -> None:
    """Atomically update long_lived_token and token_expires_at in config.py.

    Strategy:
      1. Read current config.py as text.
      2. Replace the relevant value lines with regex.
      3. Write to config.py.tmp.
      4. os.replace() — atomic on Linux (same filesystem).
    """
    config_text = _CONFIG_PATH.read_text(encoding="utf-8")

    expiry_iso = new_expiry.strftime("%Y-%m-%dT%H:%M:%S")

    # Replace long_lived_token line — handles both None and existing string values
    config_text = re.sub(
        r'("long_lived_token"\s*:\s*)(?:None|"[^"]*")',
        lambda m: f'{m.group(1)}"{new_token}"',
        config_text,
    )

    # Replace token_expires_at line
    config_text = re.sub(
        r'("token_expires_at"\s*:\s*)(?:None|"[^"]*")',
        lambda m: f'{m.group(1)}"{expiry_iso}"',
        config_text,
    )

    tmp_path = _CONFIG_PATH.with_suffix(".py.tmp")
    tmp_path.write_text(config_text, encoding="utf-8")
    os.replace(str(tmp_path), str(_CONFIG_PATH))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the Meta long-lived user token in config/config.py."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh even if the token is not close to expiry (useful for testing).",
    )
    args = parser.parse_args()

    meta = _load_meta_config()
    _validate_meta_config(meta)

    if not _token_needs_refresh(meta, force=args.force):
        return 0

    new_token, new_expiry = _exchange_token(meta)
    _rewrite_config(new_token, new_expiry)

    # Log expiry date only — never the token value
    log.info(
        "Token refreshed successfully. New expiry: %s.",
        new_expiry.date().isoformat(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
