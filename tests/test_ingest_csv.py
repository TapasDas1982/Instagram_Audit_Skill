"""Tests for the CSV ingestor."""

import csv

import pytest

from scripts.ingest_csv import (
    _classify_media_type,
    _extract_hashtags,
    _resolve,
    _safe_float,
    _safe_int,
    build_audit_input_from_csv,
)


def test_extract_hashtags_basic():
    caption = "Class today was great! #twistnturns #danceindia #BharataNatyam"
    tags = _extract_hashtags(caption)
    assert tags == ["twistnturns", "danceindia", "bharatanatyam"]


def test_extract_hashtags_empty():
    assert _extract_hashtags("") == []
    assert _extract_hashtags(None) == []


def test_extract_hashtags_no_tags():
    assert _extract_hashtags("Just a caption with no tags") == []


def test_safe_int_handles_strings_with_commas():
    assert _safe_int("1,234") == 1234
    assert _safe_int("  42  ") == 42
    assert _safe_int("") is None
    assert _safe_int(None) is None
    assert _safe_int("not a number") is None


def test_safe_float_handles_decimals():
    assert _safe_float("12.5") == 12.5
    assert _safe_float("1,000.5") == 1000.5
    assert _safe_float(None) is None


def test_classify_media_type():
    import pandas as pd
    row = pd.Series({"Post type": "Reel"})
    assert _classify_media_type(row, "Post type", "") == "reel"
    row = pd.Series({"Post type": "Carousel"})
    assert _classify_media_type(row, "Post type", "") == "carousel"
    row = pd.Series({"Post type": "Image"})
    assert _classify_media_type(row, "Post type", "") == "image"
    # Unknown post type → fallback
    row = pd.Series({"Post type": "Story"})
    assert _classify_media_type(row, "Post type", "") == "image"
    # No media column, but #reel in caption
    assert _classify_media_type(pd.Series({}), None, "Class #reel today") == "reel"


def test_resolve_finds_known_columns(tmp_path):
    """Verify _resolve handles common Meta CSV column-name variants."""
    csv_a = tmp_path / "variant_a.csv"
    with csv_a.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Post ID", "Publish time", "Likes", "Comments"])
        w.writerow(["1", "2026-05-01 18:00", "100", "10"])

    import pandas as pd
    df = pd.read_csv(csv_a)
    assert _resolve(df, "post_id") == "Post ID"
    assert _resolve(df, "posted_at") == "Publish time"
    assert _resolve(df, "likes") == "Likes"


def test_resolve_handles_alternate_column_names(tmp_path):
    csv_b = tmp_path / "variant_b.csv"
    with csv_b.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Permalink", "Posted", "Reactions"])
        w.writerow(["http://...", "2026-05-01 18:00", "100"])

    import pandas as pd
    df = pd.read_csv(csv_b)
    assert _resolve(df, "post_id") == "Permalink"
    assert _resolve(df, "posted_at") == "Posted"
    assert _resolve(df, "likes") == "Reactions"


def test_resolve_returns_none_for_missing(tmp_path):
    csv_p = tmp_path / "minimal.csv"
    csv_p.write_text("foo,bar\n1,2\n")
    import pandas as pd
    df = pd.read_csv(csv_p)
    assert _resolve(df, "post_id") is None


def test_build_audit_input_from_sample_csv(sample_csv_path, sample_profile_path):
    ai = build_audit_input_from_csv(
        csv_path=sample_csv_path,
        profile_json_path=sample_profile_path,
        period_days=30,
    )
    assert ai.profile.username == "twistnturns"
    assert ai.profile.follower_count == 5400
    assert ai.profile.has_link is True
    assert ai.source == "csv"
    assert len(ai.posts) >= 15
    # Mix of media types
    media_types = {p.media_type for p in ai.posts}
    assert "reel" in media_types
    assert "carousel" in media_types
    # Hashtags extracted
    assert any("twistnturns" in p.hashtags for p in ai.posts)
    # Audience data populated from JSON sidecar
    assert ai.audience.active_hours
    assert ai.audience.geo
    assert ai.audience.follower_count_by_day


def test_carousel_dedup_by_permalink(tmp_path):
    """Two rows sharing a permalink should collapse to one Post."""
    csv_p = tmp_path / "carousel_dup.csv"
    with csv_p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Post ID", "Permalink", "Publish time", "Post type", "Description", "Likes", "Comments"])
        w.writerow(["1", "http://x/p/abc", "2026-05-01 18:00", "Carousel", "test #foo", "100", "10"])
        w.writerow(["2", "http://x/p/abc", "2026-05-01 18:00", "Carousel", "test #foo", "100", "10"])
        w.writerow(["3", "http://x/p/def", "2026-05-02 18:00", "Reel", "test #bar", "200", "20"])
    ai = build_audit_input_from_csv(csv_path=csv_p, profile_json_path=None, period_days=30)
    assert len(ai.posts) == 2
