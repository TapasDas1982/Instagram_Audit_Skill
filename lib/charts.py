"""
matplotlib chart renderers.

All renderers write a PNG to disk and return its path. The Word report
generator inserts these PNGs at fixed locations rather than embedding
matplotlib output directly — easier to debug and faster to iterate on
the visual design.

We use the 'Agg' backend so charts render in headless environments
(cron jobs, CI, the Hetzner box).
"""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")  # headless — must come before pyplot import
import matplotlib.pyplot as plt  # noqa: E402

from lib.normalize import AuditInput, Post  # noqa: E402


PALETTE = {
    "primary": "#2E5BBA",
    "accent": "#F5A623",
    "good": "#4CAF50",
    "warn": "#FF9800",
    "bad": "#E53935",
    "neutral": "#9E9E9E",
    "bg": "#F7F7F7",
}


def _setup_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_facecolor(PALETTE["bg"])


def render_engagement_over_time(
    posts: Iterable[Post],
    follower_count: int,
    output_path: str | Path,
) -> Path:
    """Line chart: ER per post over time."""
    posts_sorted = sorted(posts, key=lambda p: p.posted_at)
    if not posts_sorted:
        return _render_empty(output_path, "No posts in the audit period")

    dates = [p.posted_at for p in posts_sorted]
    er_values = [
        (p.total_engagement / max(1, follower_count)) * 100.0 for p in posts_sorted
    ]

    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.plot(dates, er_values, marker="o", color=PALETTE["primary"], linewidth=2)
    ax.fill_between(dates, er_values, alpha=0.15, color=PALETTE["primary"])
    ax.set_ylabel("Engagement Rate (%)")
    ax.set_title("Engagement Rate by Post", loc="left", fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    fig.autofmt_xdate()
    _setup_axes(ax)
    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def render_content_mix_donut(posts: Iterable[Post], output_path: str | Path) -> Path:
    """Donut: post count by media_type."""
    counts = Counter(p.media_type for p in posts)
    if not counts:
        return _render_empty(output_path, "No posts to chart content mix")

    labels = list(counts.keys())
    values = list(counts.values())
    colors = {
        "reel": PALETTE["accent"],
        "carousel": PALETTE["primary"],
        "image": PALETTE["good"],
        "video": PALETTE["warn"],
    }
    color_list = [colors.get(label, PALETTE["neutral"]) for label in labels]

    fig, ax = plt.subplots(figsize=(5, 5))
    wedges, texts, autotexts = ax.pie(
        values,
        labels=[label.title() for label in labels],
        colors=color_list,
        autopct="%1.0f%%",
        startangle=90,
        wedgeprops=dict(width=0.4),
        pctdistance=0.80,
    )
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontweight("bold")
    ax.set_title("Content Mix", loc="left", fontweight="bold")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def render_posting_heatmap(posts: Iterable[Post], output_path: str | Path) -> Path:
    """Heatmap: post count by day-of-week × hour-of-day."""
    grid: dict[tuple[int, int], int] = defaultdict(int)
    posts_list = list(posts)
    for p in posts_list:
        grid[(p.posted_at.weekday(), p.posted_at.hour)] += 1

    if not grid:
        return _render_empty(output_path, "No posts to chart heatmap")

    matrix = [[grid.get((dow, h), 0) for h in range(24)] for dow in range(7)]
    fig, ax = plt.subplots(figsize=(9, 3.5))
    im = ax.imshow(matrix, aspect="auto", cmap="Blues", interpolation="nearest")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_yticks(range(7))
    ax.set_yticklabels([calendar.day_abbr[d] for d in range(7)])
    ax.set_xlabel("Hour of day")
    ax.set_title("Posting Heatmap (when you post)", loc="left", fontweight="bold")
    fig.colorbar(im, ax=ax, label="Post count")
    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def render_hashtag_top_n(
    posts: Iterable[Post], output_path: str | Path, top_n: int = 10
) -> Path:
    """Horizontal bar chart: top N most-used hashtags."""
    all_tags = [tag for p in posts for tag in p.hashtags]
    if not all_tags:
        return _render_empty(output_path, "No hashtags found in posts")

    most_common = Counter(all_tags).most_common(top_n)
    labels = [f"#{tag}" for tag, _ in most_common][::-1]
    counts = [c for _, c in most_common][::-1]

    fig, ax = plt.subplots(figsize=(7, max(3.5, len(labels) * 0.35)))
    ax.barh(labels, counts, color=PALETTE["primary"])
    ax.set_xlabel("Posts using this tag")
    ax.set_title(f"Top {top_n} Hashtags", loc="left", fontweight="bold")
    _setup_axes(ax)
    for i, c in enumerate(counts):
        ax.text(c + 0.05, i, str(c), va="center", fontsize=9)
    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def render_score_radar(scores: dict[str, float], output_path: str | Path) -> Path:
    """Radar chart: per-dimension scores 0–100."""
    import math

    if not scores:
        return _render_empty(output_path, "No dimension scores to plot")

    labels = list(scores.keys())
    values = [scores[k] for k in labels]
    n = len(labels)
    angles = [i / float(n) * 2 * math.pi for i in range(n)]
    angles += angles[:1]
    values += values[:1]

    fig, ax = plt.subplots(figsize=(5.5, 5.5), subplot_kw=dict(polar=True))
    ax.plot(angles, values, color=PALETTE["primary"], linewidth=2)
    ax.fill(angles, values, color=PALETTE["primary"], alpha=0.20)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([k.title() for k in labels])
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_title("Dimension Scorecard", y=1.08, fontweight="bold")
    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def _render_empty(output_path: str | Path, message: str) -> Path:
    """Generate a placeholder chart when there's no data."""
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=11, color=PALETTE["neutral"])
    ax.set_axis_off()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out


def render_peer_comparison(
    subject_username: str,
    subject_followers: int,
    peer_data: list[dict],  # [{"username": str, "followers_count": int}, ...]
    output_path: str | Path,
) -> Path:
    """Horizontal bar chart: subject vs top 5 peers by follower count.

    Returns `output_path` unchanged (without writing) if peer_data is empty.
    """
    output_path = Path(output_path)
    if not peer_data:
        return output_path  # nothing to render — caller checks for file existence

    # Sort peers by followers desc, take top 5
    top_peers = sorted(
        peer_data, key=lambda p: p.get("followers_count", 0), reverse=True
    )[:5]

    names = [f"@{p['username']}" for p in top_peers] + [f"@{subject_username} (you)"]
    values = [p.get("followers_count", 0) for p in top_peers] + [subject_followers]
    colors = [PALETTE["neutral"]] * len(top_peers) + [PALETTE["primary"]]

    max_val = max(values) if values else 1

    fig, ax = plt.subplots(figsize=(8, max(3.0, len(names) * 0.7)))
    bars = ax.barh(names, values, color=colors)
    ax.set_xlabel("Followers")
    ax.set_title("Follower Count vs Peers", loc="left", fontweight="bold")
    _setup_axes(ax)
    for bar in bars:
        ax.text(
            bar.get_width() + max_val * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{int(bar.get_width()):,}",
            va="center",
            fontsize=9,
        )

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_all(audit_input: AuditInput, scores: dict[str, float], output_dir: str | Path) -> dict[str, Path]:
    """Render every chart used in the report. Returns a name → Path map."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "engagement_over_time": render_engagement_over_time(
            audit_input.posts, audit_input.profile.follower_count,
            out_dir / "engagement_over_time.png",
        ),
        "content_mix": render_content_mix_donut(
            audit_input.posts, out_dir / "content_mix.png"
        ),
        "posting_heatmap": render_posting_heatmap(
            audit_input.posts, out_dir / "posting_heatmap.png"
        ),
        "hashtag_top": render_hashtag_top_n(
            audit_input.posts, out_dir / "hashtag_top.png"
        ),
        "score_radar": render_score_radar(scores, out_dir / "score_radar.png"),
        # peer_comparison is rendered by the benchmarks dimension (or benchmark_peers.py)
        # when live peer data is available via Business Discovery.  Not rendered here
        # because render_all does not have access to peer_data from the API response.
    }
