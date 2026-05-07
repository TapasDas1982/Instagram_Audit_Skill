"""Pytest fixtures and path setup."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest


# Make the project root importable
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture
def project_root() -> Path:
    return _PROJECT_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def weights_path(project_root: Path) -> Path:
    return project_root / "references" / "scoring_weights.json"


@pytest.fixture
def sample_csv_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_export.csv"


@pytest.fixture
def sample_profile_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_profile.json"


def make_post(
    *,
    post_id: str = "p1",
    posted_at: datetime | None = None,
    media_type: str = "reel",
    caption: str = "Test caption #foo #bar",
    likes: int = 100,
    comments: int = 10,
    saves: int | None = 5,
    shares: int | None = 3,
    reach: int | None = 1000,
    plays: int | None = 1500,
    avg_watch_seconds: float | None = 12.0,
    video_length_seconds: float | None = 20.0,
):
    """Build a Post with sensible defaults for tests."""
    from lib.normalize import Post

    return Post(
        post_id=post_id,
        posted_at=posted_at or datetime(2026, 5, 1, 18, 0, 0),
        media_type=media_type,
        caption=caption,
        hashtags=[t.strip("#").lower() for t in caption.split() if t.startswith("#")],
        likes=likes,
        comments=comments,
        saves=saves,
        shares=shares,
        reach=reach,
        plays=plays,
        avg_watch_seconds=avg_watch_seconds,
        video_length_seconds=video_length_seconds,
    )


@pytest.fixture
def make_audit_input():
    """Factory: build an AuditInput with overridable bits."""
    from lib.normalize import AudienceSnapshot, AuditInput, Profile

    def _factory(
        *,
        posts=None,
        bio: str = "Multi-style dance studios in Kolkata. Bharatanatyam, Bollywood, Hip-Hop. Book a trial.",
        has_link: bool = True,
        follower_count: int = 5000,
        highlights_count: int = 5,
        is_business: bool = True,
        active_hours: dict | None = None,
        follower_count_by_day: dict | None = None,
        period_days: int = 30,
    ) -> AuditInput:
        if posts is None:
            posts = [make_post()]
        period_end = max((p.posted_at.date() for p in posts), default=date(2026, 5, 7))
        period_start = period_end - timedelta(days=period_days - 1)
        return AuditInput(
            profile=Profile(
                username="testaccount",
                display_name="Test Account",
                bio=bio,
                has_link=has_link,
                follower_count=follower_count,
                following_count=300,
                media_count=200,
                highlights_count=highlights_count,
                is_business=is_business,
            ),
            posts=posts,
            audience=AudienceSnapshot(
                follower_count_by_day=follower_count_by_day or {},
                active_hours=active_hours or {},
            ),
            period_start=period_start,
            period_end=period_end,
            source="csv",
        )

    return _factory
