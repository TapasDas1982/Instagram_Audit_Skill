"""
CSV ingestor for Meta Business Suite exports.

Meta's CSV format varies — column names change by language, account type,
and export date. The CSV_COLUMN_MAP below maps our internal field names to
the candidate column headers we've seen. Add new variants as you encounter
them.

Use:
    audit_input = build_audit_input_from_csv(
        csv_path="export.csv",
        profile_json_path="profile.json",
        period_days=30,
    )
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from lib.normalize import AudienceSnapshot, AuditInput, Post, Profile


CSV_COLUMN_MAP: dict[str, list[str]] = {
    "post_id":      ["Post ID", "Permalink", "id", "Post id"],
    "posted_at":    ["Publish time", "Posted", "Timestamp", "Date", "Publish Time"],
    "media_type":   ["Post type", "Media product type", "Media type", "Type"],
    "caption":      ["Description", "Caption", "Post caption"],
    "likes":        ["Likes", "Reactions", "Like count"],
    "comments":     ["Comments", "Comment count"],
    "saves":        ["Saves", "Saved", "Save count"],
    "shares":       ["Shares", "Share count"],
    "reach":        ["Reach", "Accounts reached"],
    "impressions":  ["Impressions"],
    "plays":        ["Plays", "Video plays", "Reel plays"],
    "avg_watch":    ["Average watch time", "Average video watch time", "Avg watch time"],
    "video_length": ["Duration", "Video length", "Length"],
    "permalink":    ["Permalink", "URL", "Post URL"],
}

# Post-type values we've seen in the wild → our internal media_type
MEDIA_TYPE_NORMALIZATION: dict[str, str] = {
    "reel": "reel",
    "reels": "reel",
    "ig_reel": "reel",
    "video": "video",
    "ig_video": "video",
    "carousel": "carousel",
    "carousel_album": "carousel",
    "album": "carousel",
    "image": "image",
    "photo": "image",
    "ig_image": "image",
}


def _resolve(df: pd.DataFrame, key: str) -> str | None:
    """Return the actual column name in `df` for our internal `key`, or None."""
    for candidate in CSV_COLUMN_MAP.get(key, []):
        if candidate in df.columns:
            return candidate
    # Case-insensitive fallback
    lowered = {c.lower(): c for c in df.columns}
    for candidate in CSV_COLUMN_MAP.get(key, []):
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _safe_int(v: Any) -> int | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, str):
        v = v.strip().replace(",", "")
        if not v:
            return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _safe_float(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, str):
        v = v.strip().replace(",", "")
        if not v:
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_hashtags(caption: str) -> list[str]:
    """Extract lowercase hashtag tokens from a caption (without the '#')."""
    if not caption:
        return []
    return [tag.lower() for tag in re.findall(r"#(\w+)", caption)]


def _classify_media_type(row: pd.Series, media_col: str | None, caption: str) -> str:
    """Decide a row's media_type. Falls back to 'image' if unclear."""
    if media_col:
        raw = str(row.get(media_col, "")).strip().lower()
        if raw in MEDIA_TYPE_NORMALIZATION:
            return MEDIA_TYPE_NORMALIZATION[raw]
        # Substring matches
        for key, mapped in MEDIA_TYPE_NORMALIZATION.items():
            if key in raw:
                return mapped
    # Caption hint
    if "#reel" in (caption or "").lower():
        return "reel"
    return "image"


def _parse_meta_csv(path: str | Path) -> list[Post]:
    df = pd.read_csv(path)
    if df.empty:
        return []

    post_id_col = _resolve(df, "post_id")
    posted_col = _resolve(df, "posted_at")
    media_col = _resolve(df, "media_type")
    caption_col = _resolve(df, "caption")
    likes_col = _resolve(df, "likes")
    comments_col = _resolve(df, "comments")
    saves_col = _resolve(df, "saves")
    shares_col = _resolve(df, "shares")
    reach_col = _resolve(df, "reach")
    impressions_col = _resolve(df, "impressions")
    plays_col = _resolve(df, "plays")
    avg_watch_col = _resolve(df, "avg_watch")
    video_length_col = _resolve(df, "video_length")
    permalink_col = _resolve(df, "permalink")

    if not posted_col:
        raise ValueError(
            f"Could not find a 'posted at' column in CSV. Tried: {CSV_COLUMN_MAP['posted_at']}. "
            f"Columns present: {list(df.columns)}"
        )

    posts: list[Post] = []
    seen_permalinks: set[str] = set()
    for _, row in df.iterrows():
        permalink = str(row.get(permalink_col, "")).strip() if permalink_col else ""
        # Dedupe carousel rows that share a permalink
        if permalink and permalink in seen_permalinks:
            continue
        if permalink:
            seen_permalinks.add(permalink)

        try:
            posted_at = pd.to_datetime(row[posted_col]).to_pydatetime()
        except Exception:
            continue  # skip rows we can't parse a date from

        post_id_raw = str(row.get(post_id_col, "")).strip() if post_id_col else ""
        post_id = post_id_raw or permalink or f"row_{len(posts)}"

        caption = str(row.get(caption_col, "") or "") if caption_col else ""
        hashtags = _extract_hashtags(caption)
        media_type = _classify_media_type(row, media_col, caption)

        likes = _safe_int(row.get(likes_col)) if likes_col else None
        comments = _safe_int(row.get(comments_col)) if comments_col else None

        posts.append(Post(
            post_id=post_id,
            posted_at=posted_at,
            media_type=media_type,
            caption=caption,
            hashtags=hashtags,
            likes=int(likes or 0),
            comments=int(comments or 0),
            saves=_safe_int(row.get(saves_col)) if saves_col else None,
            shares=_safe_int(row.get(shares_col)) if shares_col else None,
            reach=_safe_int(row.get(reach_col)) if reach_col else None,
            impressions=_safe_int(row.get(impressions_col)) if impressions_col else None,
            plays=_safe_int(row.get(plays_col)) if plays_col else None,
            avg_watch_seconds=_safe_float(row.get(avg_watch_col)) if avg_watch_col else None,
            video_length_seconds=_safe_float(row.get(video_length_col)) if video_length_col else None,
            permalink=permalink or None,
        ))

    return posts


def _load_profile_json(path: str | Path) -> Profile:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Profile(
        username=data["username"],
        display_name=data.get("display_name", data["username"]),
        bio=data.get("bio", ""),
        has_link=bool(data.get("has_link", False)),
        follower_count=int(data.get("follower_count", 0)),
        following_count=int(data.get("following_count", 0)),
        media_count=int(data.get("media_count", 0)),
        highlights_count=data.get("highlights_count"),
        is_business=bool(data.get("is_business", True)),
        profile_picture_url=data.get("profile_picture_url"),
        website=data.get("website"),
    )


def _load_audience_json(profile_data: dict) -> AudienceSnapshot:
    """Optional 'audience' block inside the profile JSON."""
    aud = profile_data.get("audience", {}) or {}
    follower_by_day_raw = aud.get("follower_count_by_day", {}) or {}
    follower_by_day = {
        date.fromisoformat(k): int(v) for k, v in follower_by_day_raw.items()
    }
    active_hours_raw = aud.get("active_hours", {}) or {}
    active_hours = {int(k): float(v) for k, v in active_hours_raw.items()}
    return AudienceSnapshot(
        follower_count_by_day=follower_by_day,
        geo=aud.get("geo", {}) or {},
        age_gender=aud.get("age_gender", {}) or {},
        active_hours=active_hours,
    )


def build_audit_input_from_csv(
    csv_path: str | Path,
    profile_json_path: str | Path | None,
    period_days: int = 30,
) -> AuditInput:
    """End-to-end: read CSV + profile JSON → AuditInput."""
    posts = _parse_meta_csv(csv_path)
    if profile_json_path:
        with open(profile_json_path, "r", encoding="utf-8") as f:
            profile_data = json.load(f)
        profile = _load_profile_json(profile_json_path)
        audience = _load_audience_json(profile_data)
    else:
        # Minimal placeholder profile if no JSON sidecar
        profile = Profile(
            username="unknown",
            display_name="Unknown Account",
            bio="",
            has_link=False,
            follower_count=1,
            following_count=0,
            media_count=len(posts),
            highlights_count=0,
            is_business=True,
        )
        audience = AudienceSnapshot()

    if posts:
        period_end = max(p.posted_at.date() for p in posts)
    else:
        period_end = datetime.utcnow().date()
    period_start = period_end - timedelta(days=period_days - 1)

    return AuditInput(
        profile=profile,
        posts=posts,
        audience=audience,
        period_start=period_start,
        period_end=period_end,
        source="csv",
    )
