"""
Unified data model for the audit pipeline.

Both CSV ingestion (`scripts/ingest_csv.py`) and Graph API ingestion (Phase 2,
`scripts/ingest_api.py`) produce instances of `AuditInput`. Every dimension
evaluator and the report generator consume `AuditInput`. Changing the shape
here ripples through both ingest paths — keep additions backward-compatible
where possible (default values on new fields).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


MEDIA_TYPES = ("image", "carousel", "video", "reel")


@dataclass
class Post:
    """One post on an Instagram account."""

    post_id: str
    posted_at: datetime
    media_type: str                          # one of MEDIA_TYPES
    caption: str
    hashtags: list[str]                      # lowercase, no '#' prefix
    likes: int
    comments: int
    saves: Optional[int] = None
    shares: Optional[int] = None
    reach: Optional[int] = None
    impressions: Optional[int] = None
    # Reels-specific
    plays: Optional[int] = None
    avg_watch_seconds: Optional[float] = None
    video_length_seconds: Optional[float] = None
    replays: Optional[int] = None
    permalink: Optional[str] = None

    def __post_init__(self) -> None:
        if self.media_type not in MEDIA_TYPES:
            raise ValueError(
                f"media_type must be one of {MEDIA_TYPES}, got {self.media_type!r}"
            )

    @property
    def total_engagement(self) -> int:
        """Sum of likes + comments + saves + shares (treats None as 0)."""
        return (
            (self.likes or 0)
            + (self.comments or 0)
            + (self.saves or 0)
            + (self.shares or 0)
        )

    @property
    def is_reel(self) -> bool:
        return self.media_type == "reel"


@dataclass
class Profile:
    """Account-level profile data not derivable from individual posts."""

    username: str
    display_name: str
    bio: str
    has_link: bool
    follower_count: int
    following_count: int
    media_count: int
    highlights_count: Optional[int] = None
    is_business: bool = True
    profile_picture_url: Optional[str] = None
    website: Optional[str] = None


@dataclass
class AudienceSnapshot:
    """Audience-level metrics for the audit period.

    Empty dicts are valid — Phase 1 CSV ingestion may have very limited
    audience data; the audience dimension falls back to a 'data unavailable'
    finding rather than crashing.
    """

    follower_count_by_day: dict[date, int] = field(default_factory=dict)
    geo: dict[str, float] = field(default_factory=dict)         # 'country/city' → percentage
    age_gender: dict[str, float] = field(default_factory=dict)  # 'M.25-34' style → percentage
    active_hours: dict[int, float] = field(default_factory=dict)  # hour 0-23 → relative score


@dataclass
class AuditInput:
    """Everything one audit run needs. Source-agnostic."""

    profile: Profile
    posts: list[Post]
    audience: AudienceSnapshot
    period_start: date
    period_end: date
    source: str                             # 'csv' | 'api'

    def __post_init__(self) -> None:
        if self.source not in ("csv", "api"):
            raise ValueError(
                f"source must be 'csv' or 'api', got {self.source!r}"
            )
        if self.period_end < self.period_start:
            raise ValueError("period_end must be >= period_start")


@dataclass
class Finding:
    """One specific observation produced by a dimension evaluator.

    `severity` drives ordering and color in the report.
    `evidence` is human-readable supporting data (e.g. "8 posts in 30 days,
    median ER 0.8%"). Keep it specific — generic findings are noise.
    """

    severity: str                            # 'critical' | 'warning' | 'info' | 'positive'
    title: str
    evidence: str
    recommended_action: Optional[str] = None
    impact: str = "medium"                   # 'high' | 'medium' | 'low'
    ease: str = "medium"                     # 'easy' | 'medium' | 'hard'

    def __post_init__(self) -> None:
        if self.severity not in ("critical", "warning", "info", "positive"):
            raise ValueError(f"invalid severity: {self.severity!r}")
        if self.impact not in ("high", "medium", "low"):
            raise ValueError(f"invalid impact: {self.impact!r}")
        if self.ease not in ("easy", "medium", "hard"):
            raise ValueError(f"invalid ease: {self.ease!r}")

    @property
    def priority_score(self) -> int:
        """Higher = address sooner. impact × (inverse-ease) on a 1–9 scale."""
        impact_w = {"high": 3, "medium": 2, "low": 1}[self.impact]
        ease_w = {"easy": 3, "medium": 2, "hard": 1}[self.ease]
        return impact_w * ease_w


@dataclass
class DimensionResult:
    """The unified return value of every `evaluate(audit_input)` function."""

    name: str                                # 'profile', 'cadence', etc.
    score: float                             # 0.0 to 100.0
    metrics: dict[str, float | int | str | None]
    findings: list[Finding] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 100.0:
            raise ValueError(
                f"score must be 0–100, got {self.score} for dimension {self.name!r}"
            )
