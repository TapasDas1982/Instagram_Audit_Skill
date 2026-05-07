"""
Profile health dimension.

Scores the static profile elements that don't depend on posts:
bio quality, link in bio, highlights count, display name, website.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.normalize import AuditInput, DimensionResult, Finding


def _load_thresholds(thresholds: dict | None) -> dict:
    if thresholds is not None:
        return thresholds
    weights_path = Path(__file__).resolve().parents[2] / "references" / "scoring_weights.json"
    with weights_path.open("r", encoding="utf-8") as f:
        return json.load(f)["thresholds"]


def evaluate(audit_input: AuditInput, thresholds: dict | None = None) -> DimensionResult:
    t = _load_thresholds(thresholds)
    profile = audit_input.profile
    findings: list[Finding] = []
    points: dict[str, float] = {}

    # Bio length: 80–150 chars is the sweet spot for IG bios
    bio_min = t.get("bio_length_min", 80)
    bio_max = t.get("bio_length_max", 150)
    bio_len = len(profile.bio or "")
    if bio_min <= bio_len <= bio_max:
        points["bio_length"] = 20.0
    elif bio_len >= 30:
        points["bio_length"] = 12.0
        if bio_len < bio_min:
            findings.append(Finding(
                severity="warning",
                title="Bio is too short",
                evidence=f"Bio is {bio_len} chars; aim for {bio_min}–{bio_max}.",
                recommended_action=(
                    "Expand the bio to include: who you serve, what you teach, "
                    "where you're located, and a call-to-action."
                ),
                impact="medium",
                ease="easy",
            ))
        else:
            findings.append(Finding(
                severity="warning",
                title="Bio is too long",
                evidence=f"Bio is {bio_len} chars; the readable cutoff on mobile is {bio_max}.",
                recommended_action="Tighten the bio — the second half gets truncated by 'more'.",
                impact="low",
                ease="easy",
            ))
    else:
        points["bio_length"] = 0.0
        findings.append(Finding(
            severity="critical",
            title="Bio is essentially empty",
            evidence=f"Bio is only {bio_len} chars.",
            recommended_action=(
                "Write 2–3 lines stating: who you teach, what styles, where, "
                "and link to bookings."
            ),
            impact="high",
            ease="easy",
        ))

    # Link in bio
    if profile.has_link or (profile.website and profile.website.strip()):
        points["link"] = 20.0
    else:
        points["link"] = 0.0
        findings.append(Finding(
            severity="critical",
            title="No link in bio",
            evidence="The single tappable link is missing.",
            recommended_action=(
                "Add a Linktree, Beacons, or your booking page. The bio link is "
                "your only path off-platform — every studio account should have one."
            ),
            impact="high",
            ease="easy",
        ))

    # Highlights count
    min_h = t.get("highlights_count_min", 4)
    h_count = profile.highlights_count or 0
    if h_count >= min_h:
        points["highlights"] = 20.0
    elif h_count > 0:
        points["highlights"] = 10.0
        findings.append(Finding(
            severity="warning",
            title=f"Only {h_count} highlight(s) — aim for at least {min_h}",
            evidence=f"Highlights are the persistent shelf above the feed; you have {h_count}.",
            recommended_action=(
                "Add highlights for: classes, schedule, locations, testimonials. "
                "Use branded covers."
            ),
            impact="medium",
            ease="easy",
        ))
    else:
        points["highlights"] = 0.0
        findings.append(Finding(
            severity="critical",
            title="No highlights at all",
            evidence="Highlights = 0.",
            recommended_action="Create at least 4 highlights from existing Stories.",
            impact="high",
            ease="medium",
        ))

    # Display name (separate from username)
    if profile.display_name and profile.display_name.lower() != profile.username.lower():
        points["display_name"] = 15.0
    else:
        points["display_name"] = 5.0
        findings.append(Finding(
            severity="info",
            title="Display name is just the username",
            evidence=f"display_name='{profile.display_name}', username='{profile.username}'",
            recommended_action=(
                "Set the display name to include keywords like 'Dance Studio' "
                "or your city — IG search uses it for discovery."
            ),
            impact="medium",
            ease="easy",
        ))

    # Profile picture present
    if profile.profile_picture_url:
        points["profile_picture"] = 10.0
    else:
        # We may not have this from CSV; treat absence as info, not critical
        points["profile_picture"] = 7.0

    # Account is Business/Creator (gives access to insights)
    if profile.is_business:
        points["business_account"] = 15.0
    else:
        points["business_account"] = 0.0
        findings.append(Finding(
            severity="critical",
            title="Account is not Business or Creator",
            evidence="is_business=False",
            recommended_action=(
                "Switch to Business in Settings → Account type — required for "
                "the Graph API and all insights."
            ),
            impact="high",
            ease="easy",
        ))

    score = sum(points.values())  # max possible: 100
    if not findings:
        findings.append(Finding(
            severity="positive",
            title="Profile is complete",
            evidence="Bio, link, highlights, display name, business account all in place.",
            impact="low",
            ease="easy",
        ))

    return DimensionResult(
        name="profile",
        score=round(min(score, 100.0), 2),
        metrics={
            "bio_length": bio_len,
            "has_link": int(profile.has_link or bool(profile.website)),
            "highlights_count": h_count,
            "follower_count": profile.follower_count,
            "media_count": profile.media_count,
            "is_business": int(profile.is_business),
            **{f"pts_{k}": v for k, v in points.items()},
        },
        findings=findings,
    )
