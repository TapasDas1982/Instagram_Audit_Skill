"""
Engagement dimension.

Engagement rate = (likes + comments + saves + shares) / followers, averaged per post.
Saves-to-likes ratio is the strongest 'this is useful' signal.
Comment-to-like ratio indicates real conversation vs passive likes.
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
    posts = audit_input.posts
    followers = max(1, audit_input.profile.follower_count)
    findings: list[Finding] = []

    if not posts:
        return DimensionResult(
            name="engagement",
            score=0.0,
            metrics={"n_posts": 0, "median_er_pct": 0, "mean_er_pct": 0},
            findings=[Finding(
                severity="critical",
                title="No posts in the audit period — cannot compute engagement",
                evidence="posts list is empty.",
                recommended_action="Post anything. Then audit again.",
                impact="high",
                ease="easy",
            )],
        )

    # Per-post engagement rate (treat None as 0 for fields that may be absent in CSV)
    per_post_er = []
    for p in posts:
        eng = p.total_engagement
        per_post_er.append(eng / followers * 100.0)
    mean_er = statistics.mean(per_post_er)
    median_er = statistics.median(per_post_er)

    # Saves-to-likes ratio (only where saves data is present)
    saves_to_likes_pcts = []
    for p in posts:
        if p.saves is not None and p.likes:
            saves_to_likes_pcts.append(p.saves / p.likes * 100.0)
    mean_s2l = statistics.mean(saves_to_likes_pcts) if saves_to_likes_pcts else None

    # Comment-to-like ratio
    c2l_pcts = []
    for p in posts:
        if p.likes:
            c2l_pcts.append((p.comments or 0) / p.likes * 100.0)
    mean_c2l = statistics.mean(c2l_pcts) if c2l_pcts else 0

    # Subscore: engagement rate
    er_strong = t.get("engagement_rate_strong_pct", 3.0)
    er_weak = t.get("engagement_rate_weak_pct", 1.0)
    if median_er >= er_strong:
        er_score = 100.0
    elif median_er >= er_weak:
        er_score = 50.0 + 50.0 * (median_er - er_weak) / (er_strong - er_weak)
        findings.append(Finding(
            severity="warning",
            title="Engagement rate is moderate",
            evidence=f"Median ER {median_er:.2f}% (mean {mean_er:.2f}%). Target ≥{er_strong:.1f}%.",
            recommended_action=(
                "Lift engagement with: stronger first-frame hooks, comment-bait questions, "
                "and content that triggers saves (tutorials, reference frameworks)."
            ),
            impact="high",
            ease="medium",
        ))
    else:
        er_score = max(0.0, median_er / er_weak * 50.0)
        findings.append(Finding(
            severity="critical",
            title="Engagement rate is weak",
            evidence=f"Median ER {median_er:.2f}% — below the {er_weak:.1f}% threshold.",
            recommended_action=(
                "Audit your top 3 highest-ER posts and replicate their structure. "
                "Stop posting promotional-only content."
            ),
            impact="high",
            ease="medium",
        ))

    # Subscore: saves-to-likes
    s2l_strong = t.get("saves_to_likes_strong_pct", 5.0)
    s2l_weak = t.get("saves_to_likes_weak_pct", 2.0)
    if mean_s2l is None:
        s2l_score = 50.0  # Neutral when saves data isn't in the CSV
        findings.append(Finding(
            severity="info",
            title="Saves data not available in this export",
            evidence="No 'saves' column in the CSV (or all values blank).",
            recommended_action=(
                "Re-export from Meta Business Suite within 7 days of posting — "
                "saves data is dropped on older re-exports."
            ),
            impact="low",
            ease="easy",
        ))
    elif mean_s2l >= s2l_strong:
        s2l_score = 100.0
    elif mean_s2l >= s2l_weak:
        s2l_score = 60.0 + 40.0 * (mean_s2l - s2l_weak) / (s2l_strong - s2l_weak)
    else:
        s2l_score = max(0.0, mean_s2l / s2l_weak * 60.0)
        findings.append(Finding(
            severity="warning",
            title="Low saves-to-likes ratio",
            evidence=f"Mean saves/likes = {mean_s2l:.1f}% (target ≥{s2l_strong:.0f}%).",
            recommended_action=(
                "Saves indicate 'I want to come back to this'. Make at least one "
                "post per week a reference/tutorial that's worth saving."
            ),
            impact="medium",
            ease="medium",
        ))

    # Subscore: comment-to-like
    c2l_strong = t.get("comment_to_like_strong_pct", 2.0)
    if mean_c2l >= c2l_strong:
        c2l_score = 100.0
    else:
        c2l_score = max(40.0, mean_c2l / c2l_strong * 100.0)

    # Top decile / bottom decile
    n = len(posts)
    if n >= 10:
        sorted_er = sorted(per_post_er, reverse=True)
        top10_threshold = sorted_er[max(0, n // 10 - 1)]
        bot10_threshold = sorted_er[max(0, n - n // 10)]
        top_posts = [p for p, er in zip(posts, per_post_er) if er >= top10_threshold]
        if top_posts:
            findings.append(Finding(
                severity="positive",
                title=f"Top-performing posts identified (top 10%)",
                evidence=(
                    f"Top decile ER ≥{top10_threshold:.2f}%. "
                    f"Best post: {top_posts[0].permalink or top_posts[0].post_id}."
                ),
                recommended_action="Reverse-engineer top performers — what hook, format, length, time worked?",
                impact="medium",
                ease="easy",
            ))

    score = (er_score * 0.50 + s2l_score * 0.30 + c2l_score * 0.20)

    return DimensionResult(
        name="engagement",
        score=round(min(score, 100.0), 2),
        metrics={
            "n_posts": n,
            "follower_count": followers,
            "median_er_pct": round(median_er, 2),
            "mean_er_pct": round(mean_er, 2),
            "mean_saves_to_likes_pct": round(mean_s2l, 2) if mean_s2l is not None else None,
            "mean_comment_to_like_pct": round(mean_c2l, 2),
            "subscore_er": round(er_score, 2),
            "subscore_saves_to_likes": round(s2l_score, 2),
            "subscore_comment_to_like": round(c2l_score, 2),
        },
        findings=findings,
    )
