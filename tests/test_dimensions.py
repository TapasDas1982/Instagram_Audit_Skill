"""Per-dimension high-score / low-score tests.

Each dimension test builds two AuditInputs:
  1. a "good" input that should score high
  2. a "bad" input that should score low
and asserts the score lands in the expected range.

These tests are deliberately not exact-match — scoring formulas may be
re-tuned; we want to catch direction-of-travel changes, not lock in
specific point values.
"""

from datetime import datetime, timedelta

import pytest

from lib.audit_dimensions import (
    audience,
    benchmarks,
    cadence,
    engagement,
    hashtags,
    profile,
    reels,
)
from tests.conftest import make_post


# --------- profile ---------

def test_profile_high_score(make_audit_input):
    ai = make_audit_input(
        bio="Multi-style dance studio in Kolkata 🩰 Bharatanatyam · Bollywood · Hip-Hop. Book a trial today via the link below.",
        has_link=True,
        highlights_count=6,
        is_business=True,
    )
    result = profile.evaluate(ai)
    assert result.name == "profile"
    assert result.score >= 80, f"expected high score, got {result.score}"


def test_profile_low_score(make_audit_input):
    ai = make_audit_input(
        bio="",  # essentially empty
        has_link=False,
        highlights_count=0,
        is_business=False,
    )
    result = profile.evaluate(ai)
    assert result.score < 40, f"expected low score, got {result.score}"
    severities = {f.severity for f in result.findings}
    assert "critical" in severities


# --------- cadence ---------

def test_cadence_high_score(make_audit_input):
    base = datetime(2026, 5, 1, 19, 0)
    posts = [
        make_post(
            post_id=f"r{i}", posted_at=base + timedelta(days=i),
            media_type="reel", caption="#foo",
        )
        for i in range(20)  # ~5/week, regular
    ]
    ai = make_audit_input(
        posts=posts,
        active_hours={h: 0.3 for h in range(24)} | {18: 1.0, 19: 0.95},
        period_days=30,
    )
    result = cadence.evaluate(ai)
    assert result.score >= 70, f"expected high cadence score, got {result.score}"


def test_cadence_low_score(make_audit_input):
    posts = [
        make_post(post_id="p1", posted_at=datetime(2026, 5, 1, 12), media_type="image"),
        make_post(post_id="p2", posted_at=datetime(2026, 5, 25, 12), media_type="image"),
    ]  # 2 posts in 30 days, no reels
    ai = make_audit_input(posts=posts, period_days=30)
    result = cadence.evaluate(ai)
    assert result.score < 50, f"expected low cadence score, got {result.score}"


# --------- engagement ---------

def test_engagement_high_score(make_audit_input):
    posts = [
        make_post(
            post_id=f"p{i}", posted_at=datetime(2026, 5, i + 1, 18),
            likes=200, comments=15, saves=20, shares=10,
        )
        for i in range(10)
    ]
    ai = make_audit_input(posts=posts, follower_count=5000)  # ER ~4.9%
    result = engagement.evaluate(ai)
    assert result.score >= 70, f"expected high engagement score, got {result.score}"


def test_engagement_low_score(make_audit_input):
    posts = [
        make_post(
            post_id=f"p{i}", posted_at=datetime(2026, 5, i + 1, 18),
            likes=10, comments=0, saves=0, shares=0,
        )
        for i in range(5)
    ]
    ai = make_audit_input(posts=posts, follower_count=10000)  # ER ~0.1%
    result = engagement.evaluate(ai)
    assert result.score < 50, f"expected low engagement score, got {result.score}"


# --------- reels ---------

def test_reels_high_score(make_audit_input):
    posts = [
        make_post(
            post_id=f"r{i}", posted_at=datetime(2026, 5, i + 1, 18),
            media_type="reel", avg_watch_seconds=18.0, video_length_seconds=20.0,
            plays=2000, reach=1500,
        )
        for i in range(10)  # ~2/week, retention 90%
    ]
    ai = make_audit_input(posts=posts, period_days=30)
    result = reels.evaluate(ai)
    assert result.score >= 70, f"expected high reels score, got {result.score}"


def test_reels_low_score_no_reels(make_audit_input):
    posts = [
        make_post(post_id="p1", posted_at=datetime(2026, 5, 1, 12), media_type="image"),
        make_post(post_id="p2", posted_at=datetime(2026, 5, 5, 12), media_type="carousel"),
    ]
    ai = make_audit_input(posts=posts)
    result = reels.evaluate(ai)
    assert result.score == 0.0


def test_reels_low_retention(make_audit_input):
    posts = [
        make_post(
            post_id=f"r{i}", posted_at=datetime(2026, 5, i + 1, 18),
            media_type="reel", avg_watch_seconds=2.0, video_length_seconds=20.0,
        )
        for i in range(4)  # 10% retention
    ]
    ai = make_audit_input(posts=posts, period_days=30)
    result = reels.evaluate(ai)
    assert result.score < 60, f"expected low reels retention score, got {result.score}"


# --------- audience ---------

def test_audience_high_growth(make_audit_input):
    from datetime import date
    ai = make_audit_input(
        follower_count_by_day={
            date(2026, 4, 8): 5000,
            date(2026, 4, 15): 5050,
            date(2026, 4, 22): 5100,
            date(2026, 4, 30): 5200,  # +4% over period
        },
        active_hours={18: 1.0, 19: 0.9},
    )
    # Manually set geo + age_gender for completeness
    ai.audience.geo = {"Kolkata, IN": 60.0}
    ai.audience.age_gender = {"F.25-34": 40.0}
    result = audience.evaluate(ai)
    assert result.score >= 70, f"expected high audience growth score, got {result.score}"


def test_audience_negative_growth(make_audit_input):
    from datetime import date
    ai = make_audit_input(
        follower_count_by_day={
            date(2026, 4, 8): 5000,
            date(2026, 4, 30): 4900,
        },
    )
    result = audience.evaluate(ai)
    assert result.score < 40, f"expected low audience growth score, got {result.score}"


# --------- hashtags ---------

def test_hashtags_high_score(make_audit_input):
    """Mix of niche tags, varied across posts, no generics."""
    posts = []
    for i in range(8):
        tags_set_a = ["bharatanatyam", "kolkatadance", "twistnturns", "danceeducation", "classicaldance"]
        tags_set_b = ["bollywooddance", "reelsindia", "dancereel", "danceindia", "fyp"]
        tags = tags_set_a if i % 2 == 0 else tags_set_b
        caption = "Test " + " ".join(f"#{t}" for t in tags)
        posts.append(
            make_post(post_id=f"p{i}", posted_at=datetime(2026, 5, i + 1, 18), caption=caption)
        )
    # Patch the hashtags list properly (caption-derived)
    for p in posts:
        p.hashtags = [t.strip("#").lower() for t in p.caption.split() if t.startswith("#")]
    ai = make_audit_input(posts=posts)
    result = hashtags.evaluate(ai)
    assert result.score >= 70, f"expected high hashtag score, got {result.score}"


def test_hashtags_low_score_no_tags(make_audit_input):
    posts = [
        make_post(post_id="p1", posted_at=datetime(2026, 5, 1), caption="No tags here")
    ]
    posts[0].hashtags = []
    ai = make_audit_input(posts=posts)
    result = hashtags.evaluate(ai)
    assert result.score < 40, f"expected low hashtag score, got {result.score}"


def test_hashtags_low_score_generic_overuse(make_audit_input):
    posts = []
    for i in range(5):
        caption = "Test #love #instagood #photooftheday #instadaily #picoftheday"
        posts.append(
            make_post(post_id=f"p{i}", posted_at=datetime(2026, 5, i + 1, 18), caption=caption)
        )
    for p in posts:
        p.hashtags = [t.strip("#").lower() for t in p.caption.split() if t.startswith("#")]
    ai = make_audit_input(posts=posts)
    result = hashtags.evaluate(ai)
    # All-generic + same on every post should drop diversity AND generic subscores
    assert result.score < 60, f"expected low hashtag score, got {result.score}"


# --------- benchmarks ---------

def test_benchmarks_phase1_stub(make_audit_input):
    ai = make_audit_input()
    result = benchmarks.evaluate(ai)
    assert result.score == 50.0
    assert any("Phase 3" in f.evidence for f in result.findings)
