"""
Peer benchmark data refresher.

Pre-fetches and displays Business Discovery data for all peer accounts
defined in references/peer_sets.json.  Run before batch audits to verify
peer accounts are queryable, or on a separate schedule to monitor peer
follower growth.

Only Business and Creator type Instagram accounts can be queried via the
Business Discovery API.  Personal accounts return None and are reported
as skipped.

Usage:
    python scripts/benchmark_peers.py
    python scripts/benchmark_peers.py --location ballygunge
    python scripts/benchmark_peers.py --all
    python scripts/benchmark_peers.py --verbose

Run from the project root, or set PYTHONPATH to the project root.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path


# ---- Ensure project root is importable ----
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from lib.ig_api import IGClient, IGAPIError  # noqa: E402


_PEER_SETS_PATH = _PROJECT_ROOT / "references" / "peer_sets.json"


def _is_placeholder(username: str) -> bool:
    """Return True if the username is a template placeholder."""
    return bool(re.match(r"^(peer|top|national)_", username))


def _load_peer_sets() -> dict:
    """Load and return the full peer_sets.json data."""
    if not _PEER_SETS_PATH.exists():
        raise FileNotFoundError(
            f"peer_sets.json not found at {_PEER_SETS_PATH}. "
            "Create it by copying the structure from references/peer_sets.json."
        )
    with _PEER_SETS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _peers_for_location(location_data: dict) -> list[tuple[str, str]]:
    """Return list of (username, tier) pairs for a location dict.

    Filters out placeholder entries.
    """
    result: list[tuple[str, str]] = []
    for tier in ("primary_peers", "aspirational_peers", "national_best"):
        for username in location_data.get(tier, []):
            if not _is_placeholder(username):
                result.append((username, tier))
    return result


def _load_meta_config() -> dict | None:
    """Load META config from config/config.py; return None if not present."""
    try:
        sys.path.insert(0, str(_PROJECT_ROOT / "config"))
        import config  # type: ignore
        return getattr(config, "META", None)
    except Exception:
        return None


def _build_client(meta_cfg: dict) -> IGClient:
    """Construct an IGClient from the META config dict."""
    return IGClient(
        ig_user_id=str(meta_cfg["ig_user_id"]),
        access_token=str(meta_cfg["long_lived_token"]),
        api_version=meta_cfg.get("graph_api_version", "v21.0"),
        cache_dir=_PROJECT_ROOT / "cache",
    )


def _run_location(
    client: IGClient,
    location_key: str,
    location_data: dict,
    log: logging.Logger,
) -> tuple[int, int, int]:
    """Fetch and print peer data for one location.

    Returns (fetched, skipped_placeholder, errors).
    """
    peers = _peers_for_location(location_data)
    if not peers:
        log.info("  %s: no real peer accounts configured (all placeholders)", location_key)
        return 0, 0, 0

    fetched = 0
    skipped = 0
    errors = 0

    for username, tier in peers:
        try:
            profile = client.discover_peer(username)
            if profile is None:
                print(
                    f"  @{username:<40} [{tier}] SKIPPED "
                    "(personal account or not found)"
                )
                skipped += 1
            else:
                followers = profile.get("followers_count", "?")
                media = profile.get("media_count", "?")
                print(
                    f"  @{username:<40} [{tier}] "
                    f"{followers:>8,} followers · {media:>5} posts"
                    if isinstance(followers, int)
                    else f"  @{username:<40} [{tier}] {followers} followers · {media} posts"
                )
                fetched += 1
        except IGAPIError as exc:
            print(f"  @{username:<40} [{tier}] ERROR: {exc}")
            errors += 1
        except Exception as exc:  # noqa: BLE001
            log.debug("Unexpected error for @%s: %s", username, exc)
            print(f"  @{username:<40} [{tier}] ERROR (unexpected): {exc}")
            errors += 1

    return fetched, skipped, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh peer benchmark data via Business Discovery API."
    )
    parser.add_argument(
        "--location",
        metavar="LOCATION",
        default=None,
        help=(
            "Only process this location key (e.g. 'ballygunge'). "
            "Omit to process all defined locations."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_locations",
        help="Process all locations including 'default'. Equivalent to omitting --location.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("benchmark_peers")

    # ---- Config ----
    meta_cfg = _load_meta_config()
    if not meta_cfg:
        print(
            "ERROR: META config not found in config/config.py. "
            "Copy config/config.example.py to config/config.py and fill in your "
            "Meta App credentials before running this script."
        )
        return 1
    if not meta_cfg.get("long_lived_token"):
        print(
            "ERROR: META['long_lived_token'] is not set in config/config.py. "
            "Complete Meta App setup (Phase 2) before running peer benchmarks."
        )
        return 1

    # ---- Load peer sets ----
    try:
        peer_sets = _load_peer_sets()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    locations: dict = peer_sets.get("locations", {})

    # Filter to requested location if --location was given
    if args.location:
        loc_key = args.location.lower().replace(" ", "_")
        if loc_key not in locations:
            print(
                f"ERROR: location '{loc_key}' not found in peer_sets.json. "
                f"Available: {', '.join(locations.keys())}"
            )
            return 1
        locations = {loc_key: locations[loc_key]}
    elif not args.all_locations:
        # Default: skip 'default' location (has no real peers typically)
        locations = {k: v for k, v in locations.items() if k != "default"}

    if not locations:
        print("No locations to process. Use --all to include 'default'.")
        return 0

    # ---- Build client ----
    try:
        client = _build_client(meta_cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Could not build IGClient: {exc}")
        return 1

    # ---- Run ----
    total_fetched = 0
    total_skipped = 0
    total_errors = 0

    print()
    print("=" * 72)
    print("  Instagram Audit Skill — Peer Benchmark Refresher")
    print("=" * 72)

    for loc_key, loc_data in locations.items():
        if isinstance(loc_data, dict) and "_comment" in loc_data and len(loc_data) <= 2:
            # Meta-only dict (e.g. the 'default' entry with just _comment)
            continue
        print(f"\nLocation: {loc_key}")
        f, s, e = _run_location(client, loc_key, loc_data, log)
        total_fetched += f
        total_skipped += s
        total_errors += e

    print()
    print("=" * 72)
    print(
        f"  Summary: {total_fetched} fetched · "
        f"{total_skipped} skipped (personal/not found) · "
        f"{total_errors} errors"
    )
    print("=" * 72)
    print()

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
