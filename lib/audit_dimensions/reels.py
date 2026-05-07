"""
Reels dimension.

Average watch time, retention (avg watch / video length), replay rate.
Phase 1 CSV exports may not include retention; we degrade gracefully.
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
    reels = [p for p in audit_input.posts if p.is_reel]
    findings: list[Finding] = []

    if not reels:
        return DimensionResult(
            name="reels",
            score=0.0,
            metrics={"n_reels": 0},
            findings=[Finding(
                severity="critical",
                title="No Reels in the audit period",
                evidence="reel_count=0",
                recommended_action=(
                    "Reels are the algorithm's preferred format. Even one Reel/week "
                    "outperforms three carousels for new-account discovery."
                ),
                impact="high",
                ease="medium",
            )],
        )

    n = len(reels)

    # Retention = avg_watch_seconds / video_length_seconds (per Reel where both known)
    retentions = []
    for r in reels:
        if r.avg_watch_seconds and r.video_length_seconds and r.video_length_seconds > 0:
            retentions.append(r.avg_watch_seconds / r.video_length_seconds * 100.0)
    has_retention_data = bool(retentions)
    median_retention = statistics.median(retentions) if retentions else None

    # Plays normalized by reach (engagement-equivalent for Reels)
    plays_per_reach = []
    for r in reels:
        if r.plays and r.reach:
            plays_per_reach.append(r.plays / r.reach)
    mean_plays_per_reach = statistics.mean(plays_per_reach) if plays_per_reach else None

    # Average watch seconds (when we have it but not video length)
    avg_watch_secs = [r.avg_watch_seconds for r in reels if r.avg_watch_seconds]
    mean_watch = statistics.mean(avg_watch_secs) if avg_watch_secs else None

    # Subscore: retention
    r_strong = t.get("reel_retention_strong_pct", 50.0)
    r_weak = t.get("reel_retention_weak_pct", 30.0)
    if has_retention_data:
        if median_retention >= r_strong:
            retention_score = 100.0
            findings.append(Finding(
                severity="positive",
                title="Strong Reel retention",
                evidence=f"Median retention {median_retention:.0f}% — algorithm-friendly.",
                recommended_action="Find the top 3 Reels by retention and copy their structure.",
                impact="medium",
                ease="easy",
            ))
        elif median_retention >= r_weak:
            retention_score = 50.0 + 50.0 * (median_retention - r_weak) / (r_strong - r_weak)
            findings.append(Finding(
                severity="warning",
                title="Reel retention is mediocre",
                evidence=f"Median retention {median_retention:.0f}% (target ≥{r_strong:.0f}%).",
                recommended_action=(
                    "Tighten the first 1.5 seconds — that's where most viewers drop. "
                    "Lead with motion, a question, or a result — not a logo or title card."
                ),
                impact="high",
                ease="medium",
            ))
        else:
            retention_score = max(0.0, median_retention / r_weak * 50.0)
            findings.append(Finding(
                severity="critical",
                title="Reel retention is low",
                evidence=f"Median retention {median_retention:.0f}% — below {r_weak:.0f}%.",
                recommended_action=(
                    "Most viewers leave in <3 seconds. Audit your hooks: are you starting "
                    "with the payoff or with setup?"
                ),
                impact="high",
                ease="medium",
            ))
    else:
        retention_score = 50.0
        findings.append(Finding(
            severity="info",
            title="Reel retention data unavailable in this CSV",
            evidence="avg_watch_seconds and/or video_length_seconds missing.",
            recommended_action=(
                "Phase 2 (Graph API) will fetch retention via ig_reels_avg_watch_time. "
                "For now, score is partial."
            ),
            impact="low",
            ease="easy",
        ))

    # Subscore: plays-per-reach (signal of organic re-watches and shares)
    if mean_plays_per_reach is not None:
        if mean_plays_per_reach >= 1.5:
            plays_score = 100.0
        elif mean_plays_per_reach >= 1.1:
            plays_score = 70.0
        else:
            plays_score = 40.0
    else:
        plays_score = 60.0  # neutral

    # Subscore: how many Reels (within Reels dimension) — at least one weekly
    period_days = max(1, (audit_input.period_end - audit_input.period_start).days + 1)
    reels_per_week = n / period_days * 7.0
    if reels_per_week >= 2:
        volume_score = 100.0
    elif reels_per_week >= 1:
        volume_score = 70.0
    else:
        volume_score = 40.0
        findings.append(Finding(
            severity="warning",
            title="Reel cadence is below 1/week",
            evidence=f"{reels_per_week:.1f} Reels/week.",
            recommended_action="Commit to one Reel per week as a baseline.",
            impact="medium",
            ease="medium",
        ))

    score = retention_score * 0.50 + plays_score * 0.20 + volume_score * 0.30

    return DimensionResult(
        name="reels",
        score=round(min(score, 100.0), 2),
        metrics={
            "n_reels": n,
            "reels_per_week": round(reels_per_week, 2),
            "median_retention_pct": round(median_retention, 2) if median_retention is not None else None,
            "mean_avg_watch_seconds": round(mean_watch, 2) if mean_watch is not None else None,
            "mean_plays_per_reach": round(mean_plays_per_reach, 3) if mean_plays_per_reach is not None else None,
            "subscore_retention": round(retention_score, 2),
            "subscore_plays": round(plays_score, 2),
            "subscore_volume": round(volume_score, 2),
        },
        findings=findings,
    )
