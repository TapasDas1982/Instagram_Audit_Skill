"""
Competitive benchmark dimension — Phase 3.

Compares the audited account against a curated peer set using Business Discovery.
Peer sets are defined in references/peer_sets.json.

Scoring method: two observable peer metrics plus an industry ER benchmark:
  1. follower_quartile (30 %): quartile rank of subject's follower_count vs peers
  2. activity_quartile (30 %): quartile rank of subject's media_count vs peers
  3. er_benchmark    (40 %): score vs dance-studio industry ER thresholds
                             (ER% > 3 → 100, 1–3 → 70, 0.5–1 → 40, < 0.5 → 20)

Note: Business Discovery API returns profile metrics only (followers, media_count)
— per-post insights are not available for peer accounts. Observable engagement
rate (ER) can therefore only be measured for the subject account, not peers.

Falls back to score=50 with a "data unavailable" finding if:
  - No peer set defined for the account's studio_location
  - ig_client is None (CSV source or no API configured)
  - All peer accounts returned None from discover_peer (all personal accounts)
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from lib.normalize import AuditInput, DimensionResult, Finding

if TYPE_CHECKING:
    pass  # IGClient imported lazily inside evaluate to avoid hard dependency


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Industry benchmark thresholds (dance studios, 2025/2026)
# ---------------------------------------------------------------------------

_ER_TIERS: list[tuple[float, float, str]] = [
    # (min_er_pct, score, label)
    (3.0, 100.0, "strong (> 3 %)"),
    (1.0,  70.0, "average (1–3 %)"),
    (0.5,  40.0, "below average (0.5–1 %)"),
    (0.0,  20.0, "weak (< 0.5 %)"),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_placeholder(username: str) -> bool:
    """Return True if the username is a placeholder entry from the template."""
    return bool(re.match(r"^(peer|top|national)_", username))


def _load_peer_set(studio_location: str | None) -> list[str]:
    """Load peer usernames for the given studio location.

    Returns only real (non-placeholder) usernames.  Returns [] if the file
    doesn't exist, the location isn't found, or all entries are placeholders.
    """
    peer_sets_path = (
        Path(__file__).resolve().parents[2] / "references" / "peer_sets.json"
    )
    if not peer_sets_path.exists():
        return []
    with peer_sets_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    loc = (studio_location or "").lower().replace(" ", "_")
    location_data = (
        data["locations"].get(loc)
        or data["locations"].get("default", {})
    )
    peers = (
        location_data.get("primary_peers", [])
        + location_data.get("aspirational_peers", [])
    )
    return [p for p in peers if not _is_placeholder(p)]


def _compute_subject_metrics(
    posts: list,
    follower_count: int,
    period_days: int,
) -> dict:
    """Compute observable metrics for the subject account from post data."""
    if not posts or follower_count == 0:
        return {
            "observable_er": 0.0,
            "reels_share": 0.0,
            "posts_per_week": 0.0,
            "top_tags": set(),
        }

    total_likes = sum(p.likes for p in posts)
    total_comments = sum(p.comments for p in posts)
    observable_er = (total_likes + total_comments) / (len(posts) * follower_count) * 100.0

    reel_count = sum(1 for p in posts if p.is_reel)
    reels_share = reel_count / len(posts) * 100.0

    posts_per_week = len(posts) / max(1, period_days / 7)

    all_tags = [tag for p in posts for tag in p.hashtags]
    top_tags: set[str] = {t for t, _ in Counter(all_tags).most_common(20)}

    return {
        "observable_er": round(observable_er, 2),
        "reels_share": round(reels_share, 1),
        "posts_per_week": round(posts_per_week, 2),
        "top_tags": top_tags,
    }


def _er_benchmark_score(observable_er: float) -> tuple[float, str]:
    """Score the subject's ER against industry thresholds. Returns (score, label)."""
    for min_er, score, label in _ER_TIERS:
        if observable_er >= min_er:
            return score, label
    return 20.0, "weak (< 0.5 %)"


def _quartile_score(subject_val: float, peer_vals: list[float]) -> float:
    """Return 100/75/50/25 based on subject's quartile rank among peers.

    Uses a simple sorted-position approach; returns 50.0 for empty peer lists.
    """
    if not peer_vals:
        return 50.0
    sorted_peers = sorted(peer_vals)
    n = len(sorted_peers)
    # Quartile boundaries — fallback to first/last element for tiny lists
    q1 = sorted_peers[max(0, n // 4)]
    q3 = sorted_peers[min(n - 1, (3 * n) // 4)]
    median = sorted_peers[n // 2]

    if subject_val >= q3:
        return 100.0
    if subject_val >= median:
        return 75.0
    if subject_val >= q1:
        return 50.0
    return 25.0


def _fetch_peer_profiles(ig_client, peer_usernames: list[str]) -> list[dict]:
    """Fetch profile metrics for each peer via Business Discovery.

    Returns a list of dicts with at least 'username', 'followers_count',
    'media_count'.  Skips peers that return None (personal accounts or errors).
    """
    peer_data: list[dict] = []
    for username in peer_usernames:
        try:
            profile = ig_client.discover_peer(username)
            if profile is None:
                log.debug("Peer @%s skipped — personal account or not found", username)
                continue
            peer_data.append({
                "username": username,
                "followers_count": int(profile.get("followers_count", 0)),
                "media_count": int(profile.get("media_count", 0)),
            })
        except Exception as exc:
            log.debug("Could not fetch peer @%s: %s", username, exc)
    return peer_data


# ---------------------------------------------------------------------------
# Main evaluate function
# ---------------------------------------------------------------------------

def evaluate(
    audit_input: AuditInput,
    thresholds: dict | None = None,  # noqa: ARG001 — reserved for future config
    *,
    ig_client=None,           # IGClient instance, optional
    studio_location: str | None = None,
) -> DimensionResult:
    """Evaluate the benchmarks dimension with real peer comparison (Phase 3).

    Args:
        audit_input:      The full audit payload.
        thresholds:       Pass-through from Scorer; reserved for future config.
        ig_client:        IGClient instance.  Pass None for CSV-only runs.
        studio_location:  Location tag matching a key in peer_sets.json
                          (e.g. 'ballygunge').  Used to select the peer set.

    Returns:
        DimensionResult with name='benchmarks', score 0–100.
    """
    posts = audit_input.posts
    period_days = (audit_input.period_end - audit_input.period_start).days + 1
    follower_count = audit_input.profile.follower_count
    findings: list[Finding] = []

    # ---- Subject metrics ----
    subject_metrics = _compute_subject_metrics(posts, follower_count, period_days)
    observable_er: float = subject_metrics["observable_er"]
    er_score, er_label = _er_benchmark_score(observable_er)

    # ---- ER finding (always generated, even without peer data) ----
    if observable_er >= 3.0:
        findings.append(Finding(
            severity="positive",
            title=f"Strong engagement rate vs dance studio benchmark: {observable_er:.2f} %",
            evidence=(
                f"Observable ER (likes + comments / followers per post) is {observable_er:.2f} %, "
                f"which is {er_label}. Dance studios typically target 2–3 %."
            ),
            impact="high",
            ease="easy",
        ))
    elif observable_er < 1.0:
        findings.append(Finding(
            severity="warning",
            title=f"Engagement rate below industry benchmark: {observable_er:.2f} %",
            evidence=(
                f"Observable ER is {observable_er:.2f} % ({er_label}). "
                "Dance studio accounts typically achieve 2–3 % on Reels-heavy feeds."
            ),
            recommended_action=(
                "Prioritize Reels (target 60 %+ of content), post 1 × day vs "
                "current cadence, and add a call-to-action in every caption."
            ),
            impact="high",
            ease="medium",
        ))
    else:
        findings.append(Finding(
            severity="info",
            title=f"Engagement rate at industry average: {observable_er:.2f} %",
            evidence=(
                f"Observable ER is {observable_er:.2f} % ({er_label}). "
                "Good baseline; increasing Reels volume typically pushes this above 3 %."
            ),
            recommended_action="Increase Reels share to > 60 % of posts to lift ER.",
            impact="medium",
            ease="medium",
        ))

    # ---- Load peer set ----
    peer_usernames = _load_peer_set(studio_location)

    if not peer_usernames:
        # No peers configured or all were placeholders
        findings.append(Finding(
            severity="info",
            title="Peer benchmarking not yet active",
            evidence=(
                "No real peer account usernames are configured for location "
                f"'{studio_location or 'default'}'. "
                "Edit references/peer_sets.json to add Business/Creator accounts."
            ),
            recommended_action=(
                "Add 3–5 same-neighborhood and 2–3 aspirational peer Instagram "
                "handles (Business or Creator type) to references/peer_sets.json."
            ),
            impact="medium",
            ease="easy",
        ))
        return DimensionResult(
            name="benchmarks",
            score=round(er_score, 2),
            metrics={
                "peer_count": 0,
                "subject_followers": follower_count,
                "peer_median_followers": None,
                "follower_quartile_score": None,
                "activity_quartile_score": None,
                "er_benchmark_score": round(er_score, 2),
                "observable_er_pct": observable_er,
            },
            findings=findings,
        )

    # ---- Fetch peer profiles ----
    if ig_client is None:
        findings.append(Finding(
            severity="info",
            title="Peer comparison unavailable — running from CSV",
            evidence=(
                f"{len(peer_usernames)} peer account(s) are configured but "
                "Business Discovery requires API mode (--source api)."
            ),
            recommended_action=(
                "Re-run with --source api once the Meta App is configured "
                "to get live peer comparison data."
            ),
            impact="medium",
            ease="medium",
        ))
        return DimensionResult(
            name="benchmarks",
            score=round(er_score, 2),
            metrics={
                "peer_count": 0,
                "subject_followers": follower_count,
                "peer_median_followers": None,
                "follower_quartile_score": None,
                "activity_quartile_score": None,
                "er_benchmark_score": round(er_score, 2),
                "observable_er_pct": observable_er,
            },
            findings=findings,
        )

    peer_data = _fetch_peer_profiles(ig_client, peer_usernames)

    if not peer_data:
        findings.append(Finding(
            severity="warning",
            title="All configured peer accounts are Personal type or unavailable",
            evidence=(
                "Business Discovery API returned no data for any peer. "
                "Only Business and Creator accounts can be queried."
            ),
            recommended_action=(
                "Verify each username in peer_sets.json is a Business or Creator "
                "account.  Personal accounts return null from Business Discovery."
            ),
            impact="medium",
            ease="medium",
        ))
        return DimensionResult(
            name="benchmarks",
            score=round(er_score, 2),
            metrics={
                "peer_count": 0,
                "subject_followers": follower_count,
                "peer_median_followers": None,
                "follower_quartile_score": None,
                "activity_quartile_score": None,
                "er_benchmark_score": round(er_score, 2),
                "observable_er_pct": observable_er,
            },
            findings=findings,
        )

    # ---- Peer comparison scoring ----
    peer_follower_vals = [float(p["followers_count"]) for p in peer_data]
    peer_activity_vals = [float(p["media_count"]) for p in peer_data]

    follower_q_score = _quartile_score(float(follower_count), peer_follower_vals)
    activity_q_score = _quartile_score(
        float(audit_input.profile.media_count), peer_activity_vals
    )

    # Compute median peer followers for display
    sorted_follower_vals = sorted(peer_follower_vals)
    n = len(sorted_follower_vals)
    peer_median_followers = int(sorted_follower_vals[n // 2])

    # ---- Peer comparison findings ----
    if follower_count >= peer_median_followers:
        findings.append(Finding(
            severity="positive",
            title=(
                f"Follower count ({follower_count:,}) exceeds peer median "
                f"({peer_median_followers:,})"
            ),
            evidence=(
                f"Compared against {len(peer_data)} peer account(s). "
                f"You are above the median peer on follower count."
            ),
            impact="medium",
            ease="easy",
        ))
    else:
        gap = peer_median_followers - follower_count
        findings.append(Finding(
            severity="warning",
            title=(
                f"{sum(1 for v in peer_follower_vals if v > follower_count)} of "
                f"{len(peer_data)} peers have more followers than you "
                f"(gap: {gap:,})"
            ),
            evidence=(
                f"Your follower count: {follower_count:,}. "
                f"Peer median: {peer_median_followers:,}. "
                f"Closing the gap typically takes 3–6 months of consistent Reels."
            ),
            recommended_action=(
                "Post 1 Reel per day for 30 days, targeting local discovery "
                "hashtags to accelerate organic follower growth."
            ),
            impact="medium",
            ease="hard",
        ))

    # Top peer callout
    if peer_data:
        top_peer = max(peer_data, key=lambda p: p["followers_count"])
        if top_peer["followers_count"] > follower_count:
            ratio = top_peer["followers_count"] / max(1, follower_count)
            findings.append(Finding(
                severity="info",
                title=(
                    f"Top peer @{top_peer['username']} has "
                    f"{top_peer['followers_count']:,} followers "
                    f"({ratio:.1f}x yours)"
                ),
                evidence=(
                    f"Studying @{top_peer['username']}'s content mix, posting "
                    "frequency, and hashtag strategy can reveal replicable tactics."
                ),
                recommended_action=(
                    f"Audit @{top_peer['username']} — note their top Reels formats, "
                    "posting cadence, and bio link structure."
                ),
                impact="medium",
                ease="easy",
            ))

    # ---- Final score ----
    final_score = (
        0.30 * follower_q_score
        + 0.30 * activity_q_score
        + 0.40 * er_score
    )
    final_score = round(min(final_score, 100.0), 2)

    return DimensionResult(
        name="benchmarks",
        score=final_score,
        metrics={
            "peer_count": len(peer_data),
            "subject_followers": follower_count,
            "peer_median_followers": peer_median_followers,
            "follower_quartile_score": round(follower_q_score, 1),
            "activity_quartile_score": round(activity_q_score, 1),
            "er_benchmark_score": round(er_score, 1),
            "observable_er_pct": observable_er,
        },
        findings=findings,
    )
