"""
Weighted scoring engine.

Reads `references/scoring_weights.json` once, then applies the weights to a
dict of per-dimension scores to produce the overall composite (0–100) and a
letter grade A/B/C/D/F.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


class Scorer:
    """Weighted-average scorer driven by `scoring_weights.json`.

    Example:
        >>> scorer = Scorer("references/scoring_weights.json")
        >>> scorer.overall({"engagement": 80, "reels": 60, ...})
        72.5
        >>> scorer.grade(72.5)
        'B'
    """

    def __init__(self, weights_path: str | Path) -> None:
        path = Path(weights_path)
        with path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.weights: dict[str, float] = cfg["weights"]
        self.thresholds: dict[str, float] = cfg.get("thresholds", {})
        self.grades_cfg: dict[str, list[float]] = cfg.get("grades", {})
        self._validate_weights()

    def _validate_weights(self) -> None:
        total = sum(self.weights.values())
        if not 0.99 <= total <= 1.01:
            raise ValueError(
                f"weights must sum to 1.0, got {total:.4f}: {self.weights}"
            )

    def overall(self, dimension_scores: Mapping[str, float]) -> float:
        """Return the weighted composite score on a 0–100 scale.

        If `dimension_scores` is missing some dimensions defined in the
        weights file, the result re-normalizes against the weights present —
        i.e. you can run a partial audit and still get a meaningful score.
        Missing dimensions are simply not counted.
        """
        if not dimension_scores:
            return 0.0
        present_weight = sum(
            self.weights.get(k, 0.0) for k in dimension_scores
        )
        if present_weight == 0:
            return 0.0
        weighted_sum = sum(
            float(dimension_scores[k]) * self.weights.get(k, 0.0)
            for k in dimension_scores
        )
        return round(weighted_sum / present_weight, 2)

    def grade(self, score: float) -> str:
        """Map a 0–100 score to a letter grade A/B/C/D/F."""
        for letter, bounds in self.grades_cfg.items():
            low, high = bounds
            if low <= score <= high:
                return letter
        # Fallback in case grades_cfg is malformed
        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        if score >= 40:
            return "D"
        return "F"

    def threshold(self, key: str, default: float | None = None) -> float | None:
        """Read a tunable threshold (e.g. `engagement_rate_strong_pct`)."""
        return self.thresholds.get(key, default)
