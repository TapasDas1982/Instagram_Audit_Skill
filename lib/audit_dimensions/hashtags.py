"""
Hashtag effectiveness dimension.

Phase 1 (CSV) doesn't have per-hashtag reach, so this dimension scores:
- Average hashtags per post (sweet spot 5–15 for Instagram)
- Hashtag diversity (unique tags / total tag uses)
- Top recurring tags
- Misuse signals (banned, too generic, all-the-same-on-every-post)

Phase 3 will add per-tag reach analysis via the Graph API hashtag endpoints.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

from lib.normalize import AuditInput, DimensionResult, Finding


# Hashtags that are too generic / saturated to drive discovery
GENERIC_TAGS = {
    "instagood", "love", "photooftheday", "instadaily", "picoftheday",
    "follow", "followme", "like4like", "likeforlike", "followforfollow",
    "f4f", "l4l", "instalike", "tagsforlikes", "amazing", "smile",
}


def _load_thresholds(thresholds: dict | None) -> dict:
    if thresholds is not None:
        return thresholds
    weights_path = Path(__file__).resolve().parents[2] / "references" / "scoring_weights.json"
    with weights_path.open("r", encoding="utf-8") as f:
        return json.load(f)["thresholds"]


def evaluate(audit_input: AuditInput, thresholds: dict | None = None) -> DimensionResult:
    _ = _load_thresholds(thresholds)  # reserved for future thresholds
    posts = audit_input.posts
    findings: list[Finding] = []

    if not posts:
        return DimensionResult(
            name="hashtags",
            score=0.0,
            metrics={"n_posts": 0, "avg_hashtags_per_post": 0},
            findings=[Finding(
                severity="info",
                title="No posts to analyze hashtag usage",
                evidence="posts list is empty.",
                impact="low",
                ease="easy",
            )],
        )

    counts_per_post = [len(p.hashtags) for p in posts]
    avg_per_post = statistics.mean(counts_per_post)
    n_posts_with_tags = sum(1 for c in counts_per_post if c > 0)

    all_tags = [tag for p in posts for tag in p.hashtags]
    if all_tags:
        unique_tags = len(set(all_tags))
        diversity = unique_tags / len(all_tags)
        most_common = Counter(all_tags).most_common(10)
    else:
        unique_tags = 0
        diversity = 0
        most_common = []

    generic_overuse = (
        sum(1 for t in all_tags if t.lower() in GENERIC_TAGS) / max(1, len(all_tags))
    )

    # Subscore: count per post (sweet spot 5–15)
    if 5 <= avg_per_post <= 15:
        count_score = 100.0
    elif avg_per_post < 1:
        count_score = 0.0
        findings.append(Finding(
            severity="critical",
            title="Posts have essentially no hashtags",
            evidence=f"Avg {avg_per_post:.1f} hashtags/post.",
            recommended_action=(
                "Add 5–10 niche hashtags to every post. Mix neighborhood tags "
                "(#kolkatadance), style tags (#bharatanatyam), and brand tag (#twistnturns)."
            ),
            impact="medium",
            ease="easy",
        ))
    elif avg_per_post < 5:
        count_score = avg_per_post / 5 * 100.0
        findings.append(Finding(
            severity="warning",
            title="Hashtag count below the sweet spot",
            evidence=f"Avg {avg_per_post:.1f} tags/post; aim for 5–15.",
            recommended_action="Add 3–5 more relevant niche tags per post.",
            impact="low",
            ease="easy",
        ))
    elif avg_per_post > 25:
        count_score = max(40.0, 100.0 - (avg_per_post - 25) * 4)
        findings.append(Finding(
            severity="warning",
            title="Hashtag stuffing detected",
            evidence=f"Avg {avg_per_post:.1f} tags/post — IG penalizes 30+.",
            recommended_action="Cap at 15. More tags ≠ more reach in 2026.",
            impact="medium",
            ease="easy",
        ))
    else:  # 15 < avg <= 25
        count_score = 80.0

    # Subscore: diversity
    if diversity >= 0.5:
        diversity_score = 100.0
    elif diversity >= 0.3:
        diversity_score = 70.0
    elif diversity >= 0.1:
        diversity_score = 40.0
    else:
        diversity_score = 20.0
        findings.append(Finding(
            severity="warning",
            title="Same hashtags on every post",
            evidence=(
                f"Diversity ratio {diversity:.2f} (unique/total). "
                "IG suppresses repeated hashtag blocks."
            ),
            recommended_action=(
                "Build 3–4 hashtag sets and rotate them. Each post should swap "
                "at least 5 tags from the previous one."
            ),
            impact="medium",
            ease="easy",
        ))

    # Subscore: generic-tag overuse — gradient penalty so 100% overuse → 0,
    # 50% → 25, 20% → 70. Linear with multiplier 1.5 and clamped at 0.
    generic_score = max(0.0, 100.0 - generic_overuse * 100.0 * 1.5)
    if generic_overuse >= 0.20:
        findings.append(Finding(
            severity="warning",
            title=f"{generic_overuse * 100:.0f}% of tags are generic",
            evidence="Tags like #instagood, #love, #photooftheday don't drive reach.",
            recommended_action=(
                "Replace generic tags with niche ones — '#bollywooddanceindia' "
                "beats '#dance' for any small account."
            ),
            impact="medium",
            ease="easy",
        ))

    if most_common and not any(f.severity == "warning" for f in findings):
        findings.append(Finding(
            severity="info",
            title="Most-used hashtags",
            evidence=", ".join(f"#{tag} ({count})" for tag, count in most_common[:5]),
            impact="low",
            ease="easy",
        ))

    score = count_score * 0.40 + diversity_score * 0.40 + generic_score * 0.20

    return DimensionResult(
        name="hashtags",
        score=round(min(score, 100.0), 2),
        metrics={
            "n_posts": len(posts),
            "n_posts_with_tags": n_posts_with_tags,
            "avg_hashtags_per_post": round(avg_per_post, 2),
            "unique_tag_count": unique_tags,
            "tag_diversity_ratio": round(diversity, 3),
            "generic_overuse_ratio": round(generic_overuse, 3),
            "subscore_count": round(count_score, 2),
            "subscore_diversity": round(diversity_score, 2),
            "subscore_generic": round(generic_score, 2),
            "top_tags": ", ".join(f"#{t}({c})" for t, c in most_common[:5]),
        },
        findings=findings,
    )
