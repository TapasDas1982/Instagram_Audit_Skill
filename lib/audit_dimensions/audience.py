"""
Audience dimension.

Follower growth slope, top geos, primary age-gender, active hour peaks.
CSV exports often lack audience demographics — Phase 2 (Graph API) fills those.
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


def _linear_growth_pct(followers_by_day: dict) -> float | None:
    """Return growth as a percentage of the period-start follower count.

    Uses simple endpoint-to-endpoint delta — robust to noise on small accounts
    and easier to explain than full linear regression.
    """
    if len(followers_by_day) < 2:
        return None
    days = sorted(followers_by_day.keys())
    start = followers_by_day[days[0]]
    end = followers_by_day[days[-1]]
    if start <= 0:
        return None
    return (end - start) / start * 100.0


def evaluate(audit_input: AuditInput, thresholds: dict | None = None) -> DimensionResult:
    t = _load_thresholds(thresholds)
    aud = audit_input.audience
    findings: list[Finding] = []

    growth_pct = _linear_growth_pct(aud.follower_count_by_day)
    has_geo = bool(aud.geo)
    has_demo = bool(aud.age_gender)
    has_active = bool(aud.active_hours)

    # Subscore: growth
    g_strong = t.get("follower_growth_30d_strong_pct", 3.0)
    g_weak = t.get("follower_growth_30d_weak_pct", 1.0)
    if growth_pct is None:
        growth_score = 50.0
        findings.append(Finding(
            severity="info",
            title="Follower growth not tracked in this dataset",
            evidence="follower_count_by_day is empty or has <2 points.",
            recommended_action=(
                "Phase 2 (Graph API) will track daily follower count. "
                "For now, capture follower_count manually before each audit."
            ),
            impact="low",
            ease="easy",
        ))
    elif growth_pct >= g_strong:
        growth_score = 100.0
        findings.append(Finding(
            severity="positive",
            title="Healthy follower growth",
            evidence=f"+{growth_pct:.1f}% over the audit period.",
            impact="low",
            ease="easy",
        ))
    elif growth_pct >= g_weak:
        growth_score = 50.0 + 50.0 * (growth_pct - g_weak) / (g_strong - g_weak)
    elif growth_pct > 0:
        growth_score = max(0.0, growth_pct / g_weak * 50.0)
        findings.append(Finding(
            severity="warning",
            title="Growth is below 1%/period",
            evidence=f"Only +{growth_pct:.2f}% follower change.",
            recommended_action=(
                "Growth comes from Reels reach, collabs, and clear positioning. "
                "Audit which posts brought new followers and double down."
            ),
            impact="high",
            ease="medium",
        ))
    else:
        growth_score = 0.0
        findings.append(Finding(
            severity="critical",
            title="Negative or flat follower growth",
            evidence=f"{growth_pct:.2f}% — losing audience.",
            recommended_action=(
                "Sudden churn often follows a posting-style change. Compare the last 5 posts "
                "to the previous 5 — what shifted?"
            ),
            impact="high",
            ease="medium",
        ))

    # Subscore: completeness of audience signals
    completeness_components = (has_geo, has_demo, has_active)
    completeness_score = sum(completeness_components) / 3 * 100.0
    if completeness_score < 100:
        findings.append(Finding(
            severity="info",
            title="Audience demographics are partial",
            evidence=(
                f"geo={'✓' if has_geo else '✗'}, "
                f"age/gender={'✓' if has_demo else '✗'}, "
                f"active_hours={'✓' if has_active else '✗'}"
            ),
            recommended_action="Phase 2 Graph API integration will populate these.",
            impact="low",
            ease="easy",
        ))

    # Top 3 geos (informational)
    top_geo = None
    if has_geo:
        sorted_geo = sorted(aud.geo.items(), key=lambda kv: kv[1], reverse=True)
        top_geo = sorted_geo[0][0] if sorted_geo else None
        if sorted_geo:
            findings.append(Finding(
                severity="info",
                title="Top audience locations",
                evidence=", ".join(f"{loc} {pct:.0f}%" for loc, pct in sorted_geo[:3]),
                impact="low",
                ease="easy",
            ))

    # Primary age-gender (informational)
    primary_demo = None
    if has_demo:
        primary_demo = max(aud.age_gender.items(), key=lambda kv: kv[1])[0]

    # Active hour peak (informational)
    peak_hour = None
    if has_active:
        peak_hour = max(aud.active_hours.items(), key=lambda kv: kv[1])[0]

    score = growth_score * 0.70 + completeness_score * 0.30

    return DimensionResult(
        name="audience",
        score=round(min(score, 100.0), 2),
        metrics={
            "follower_growth_pct": round(growth_pct, 2) if growth_pct is not None else None,
            "top_geo": top_geo,
            "primary_demographic": primary_demo,
            "peak_active_hour": peak_hour,
            "subscore_growth": round(growth_score, 2),
            "subscore_completeness": round(completeness_score, 2),
        },
        findings=findings,
    )
