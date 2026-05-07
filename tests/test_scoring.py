"""Tests for lib/scoring.py."""

import json

import pytest

from lib.scoring import Scorer


def test_weights_must_sum_to_one(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "weights": {"profile": 0.5, "cadence": 0.3},  # sums to 0.8
        "thresholds": {},
        "grades": {"A": [85, 100], "F": [0, 84.99]},
    }))
    with pytest.raises(ValueError, match="weights must sum"):
        Scorer(bad)


def test_overall_weighted_average(weights_path):
    scorer = Scorer(weights_path)
    # Per references/scoring_weights.json:
    # engagement 0.25, reels 0.20, cadence 0.15, benchmarks 0.15,
    # profile 0.10, audience 0.10, hashtags 0.05
    scores = {
        "profile": 80,
        "cadence": 60,
        "engagement": 50,
        "reels": 70,
        "audience": 90,
        "hashtags": 100,
        "benchmarks": 50,
    }
    expected = (
        80 * 0.10 + 60 * 0.15 + 50 * 0.25 + 70 * 0.20
        + 90 * 0.10 + 100 * 0.05 + 50 * 0.15
    )
    assert scorer.overall(scores) == round(expected, 2)


def test_overall_with_partial_dimensions(weights_path):
    """Missing dimensions should re-normalize, not zero-fill."""
    scorer = Scorer(weights_path)
    # Engagement (0.25) and reels (0.20) only → present_weight 0.45
    scores = {"engagement": 80, "reels": 60}
    expected = (80 * 0.25 + 60 * 0.20) / 0.45
    assert scorer.overall(scores) == round(expected, 2)


def test_overall_empty_returns_zero(weights_path):
    scorer = Scorer(weights_path)
    assert scorer.overall({}) == 0.0


def test_grade_mapping(weights_path):
    scorer = Scorer(weights_path)
    assert scorer.grade(95) == "A"
    assert scorer.grade(85) == "A"
    assert scorer.grade(75) == "B"
    assert scorer.grade(60) == "C"
    assert scorer.grade(45) == "D"
    assert scorer.grade(20) == "F"
    assert scorer.grade(0) == "F"


def test_threshold_lookup(weights_path):
    scorer = Scorer(weights_path)
    # Defined in scoring_weights.json
    assert scorer.threshold("engagement_rate_strong_pct") == 3.0
    # Missing key returns default
    assert scorer.threshold("nonexistent_key", default=42.0) == 42.0
