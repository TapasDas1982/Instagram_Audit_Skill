"""Tests for the data model in lib/normalize.py."""

from datetime import date, datetime

import pytest

from lib.normalize import (
    AudienceSnapshot,
    AuditInput,
    DimensionResult,
    Finding,
    Post,
    Profile,
)


def test_post_validates_media_type():
    with pytest.raises(ValueError, match="media_type"):
        Post(
            post_id="x",
            posted_at=datetime(2026, 5, 1),
            media_type="video_essay",  # invalid
            caption="",
            hashtags=[],
            likes=0,
            comments=0,
        )


def test_post_total_engagement_treats_none_as_zero():
    p = Post(
        post_id="x",
        posted_at=datetime(2026, 5, 1),
        media_type="image",
        caption="",
        hashtags=[],
        likes=10,
        comments=2,
        saves=None,
        shares=None,
    )
    assert p.total_engagement == 12


def test_post_total_engagement_full():
    p = Post(
        post_id="x", posted_at=datetime(2026, 5, 1), media_type="reel",
        caption="", hashtags=[], likes=100, comments=20, saves=15, shares=5,
    )
    assert p.total_engagement == 140
    assert p.is_reel is True


def test_audit_input_validates_source():
    with pytest.raises(ValueError, match="source"):
        AuditInput(
            profile=Profile(
                username="x", display_name="x", bio="", has_link=False,
                follower_count=1, following_count=1, media_count=1,
            ),
            posts=[],
            audience=AudienceSnapshot(),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            source="manual",  # invalid
        )


def test_audit_input_validates_period():
    with pytest.raises(ValueError, match="period_end"):
        AuditInput(
            profile=Profile(
                username="x", display_name="x", bio="", has_link=False,
                follower_count=1, following_count=1, media_count=1,
            ),
            posts=[],
            audience=AudienceSnapshot(),
            period_start=date(2026, 5, 7),
            period_end=date(2026, 5, 1),  # before start
            source="csv",
        )


def test_finding_validates_severity():
    with pytest.raises(ValueError, match="severity"):
        Finding(severity="urgent", title="t", evidence="e")


def test_finding_priority_score():
    high_easy = Finding(severity="warning", title="t", evidence="e", impact="high", ease="easy")
    low_hard = Finding(severity="warning", title="t", evidence="e", impact="low", ease="hard")
    assert high_easy.priority_score > low_hard.priority_score
    assert high_easy.priority_score == 9  # 3 * 3
    assert low_hard.priority_score == 1  # 1 * 1


def test_dimension_result_score_must_be_0_to_100():
    with pytest.raises(ValueError, match="score"):
        DimensionResult(name="profile", score=150.0, metrics={})
    with pytest.raises(ValueError, match="score"):
        DimensionResult(name="profile", score=-5.0, metrics={})


def test_dimension_result_accepts_valid():
    r = DimensionResult(name="profile", score=72.5, metrics={"x": 1})
    assert r.score == 72.5
    assert r.findings == []
