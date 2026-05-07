"""
Cadence dimension.

Posts/week, regularity, content mix, time-of-day vs audience active hours.
"""

from __future__ import annotations

import json
import statistics
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
    posts = sorted(audit_input.posts, key=lambda p: p.posted_at)
    period_days = max(1, (audit_input.period_end - audit_input.period_start).days + 1)
    findings: list[Finding] = []

    # Posts per week
    n = len(posts)
    posts_per_week = (n / period_days) * 7.0 if period_days else 0
    strong = t.get("posting_frequency_strong_per_week", 4)
    weak = t.get("posting_frequency_weak_per_week", 2)

    if posts_per_week >= strong:
        cadence_freq_score = 100.0
    elif posts_per_week >= weak:
        cadence_freq_score = 50.0 + 50.0 * (posts_per_week - weak) / (strong - weak)
        findings.append(Finding(
            severity="warning",
            title="Posting cadence below the strong threshold",
            evidence=f"{posts_per_week:.1f} posts/week over {period_days} days; target ≥{strong}.",
            recommended_action=(
                f"Plan {strong}+ posts/week — the algorithm down-weights inactive accounts. "
                "Batch-shoot Reels weekly to make this sustainable."
            ),
            impact="high",
            ease="medium",
        ))
    else:
        cadence_freq_score = max(0.0, posts_per_week / weak * 50.0)
        findings.append(Finding(
            severity="critical",
            title="Posting cadence is too low",
            evidence=f"Only {posts_per_week:.1f} posts/week (n={n} in {period_days}d).",
            recommended_action=(
                f"Post at least {weak}/week immediately, ramp to {strong}/week. "
                "Inconsistency is the #1 reason small accounts plateau."
            ),
            impact="high",
            ease="medium",
        ))

    # Regularity (std dev of inter-post gaps in days)
    if n >= 3:
        gaps = [
            (posts[i].posted_at - posts[i - 1].posted_at).total_seconds() / 86400.0
            for i in range(1, n)
        ]
        mean_gap = statistics.mean(gaps)
        stdev_gap = statistics.stdev(gaps) if len(gaps) >= 2 else 0
        # Lower stdev relative to mean = more regular
        cv = (stdev_gap / mean_gap) if mean_gap > 0 else 0
        if cv <= 0.5:
            regularity_score = 100.0
        elif cv <= 1.0:
            regularity_score = 70.0
        elif cv <= 1.5:
            regularity_score = 40.0
        else:
            regularity_score = 20.0
            findings.append(Finding(
                severity="warning",
                title="Posting is irregular",
                evidence=(
                    f"Inter-post gaps: mean {mean_gap:.1f}d, stdev {stdev_gap:.1f}d "
                    f"(coefficient of variation {cv:.2f})."
                ),
                recommended_action=(
                    "Pick 3 fixed posting slots per week (e.g. Tue/Thu/Sat 6 PM). "
                    "Predictability lifts the algorithm's confidence."
                ),
                impact="medium",
                ease="easy",
            ))
    else:
        regularity_score = 50.0
        findings.append(Finding(
            severity="info",
            title="Not enough posts to assess regularity",
            evidence=f"Only {n} posts in the period.",
            impact="low",
            ease="easy",
        ))

    # Content mix — Reels share
    reel_count = sum(1 for p in posts if p.is_reel)
    reel_share = (reel_count / n * 100.0) if n else 0
    reel_strong = t.get("reels_share_strong_pct", 50.0)
    reel_weak = t.get("reels_share_weak_pct", 30.0)
    if reel_share >= reel_strong:
        mix_score = 100.0
    elif reel_share >= reel_weak:
        mix_score = 60.0 + 40.0 * (reel_share - reel_weak) / (reel_strong - reel_weak)
        findings.append(Finding(
            severity="warning",
            title="Reels share below 50% — leaving reach on the table",
            evidence=f"Reels are {reel_share:.0f}% of content; target ≥{reel_strong:.0f}%.",
            recommended_action=(
                "In 2026 the algorithm rewards Reels disproportionately. "
                "Convert one carousel/week into a 15–30s Reel."
            ),
            impact="high",
            ease="medium",
        ))
    else:
        mix_score = max(0.0, reel_share / reel_weak * 60.0)
        findings.append(Finding(
            severity="critical",
            title="Almost no Reels in the content mix",
            evidence=f"Only {reel_share:.0f}% Reels (n={reel_count}/{n}).",
            recommended_action=(
                "Reels are the highest-reach format right now. Aim for 50%+ "
                "of weekly output to be Reels."
            ),
            impact="high",
            ease="medium",
        ))

    # Time-of-day vs audience active hours overlap
    if audit_input.audience.active_hours and posts:
        post_hours = [p.posted_at.hour for p in posts]
        peak_audience_hour = max(audit_input.audience.active_hours.items(), key=lambda kv: kv[1])[0]
        # How many posts hit within ±2 hours of audience peak?
        hits = sum(1 for h in post_hours if abs(h - peak_audience_hour) <= 2)
        overlap_pct = hits / len(post_hours) * 100.0
        if overlap_pct >= 60:
            timing_score = 100.0
        elif overlap_pct >= 30:
            timing_score = 70.0
        else:
            timing_score = 40.0
            findings.append(Finding(
                severity="warning",
                title="Posting times miss the audience's active window",
                evidence=(
                    f"Audience peaks at {peak_audience_hour}:00; "
                    f"only {overlap_pct:.0f}% of posts land within ±2h of that."
                ),
                recommended_action=(
                    f"Schedule posts between {max(0, peak_audience_hour - 2):02d}:00 "
                    f"and {min(23, peak_audience_hour + 2):02d}:00."
                ),
                impact="medium",
                ease="easy",
            ))
    else:
        timing_score = 60.0  # Neutral when audience data isn't available

    # Composite cadence score: weighted within the dimension
    score = (
        cadence_freq_score * 0.40
        + regularity_score * 0.20
        + mix_score * 0.30
        + timing_score * 0.10
    )

    return DimensionResult(
        name="cadence",
        score=round(min(score, 100.0), 2),
        metrics={
            "n_posts": n,
            "period_days": period_days,
            "posts_per_week": round(posts_per_week, 2),
            "reel_count": reel_count,
            "reel_share_pct": round(reel_share, 2),
            "subscore_frequency": round(cadence_freq_score, 2),
            "subscore_regularity": round(regularity_score, 2),
            "subscore_mix": round(mix_score, 2),
            "subscore_timing": round(timing_score, 2),
        },
        findings=findings,
    )
