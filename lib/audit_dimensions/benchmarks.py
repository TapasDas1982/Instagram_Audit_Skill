"""
Benchmarks dimension.

Phase 1 stub — returns 50.0 with a 'pending peer data' finding.
Phase 3 replaces the body with real peer comparison via Business Discovery.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.normalize import AuditInput, DimensionResult, Finding


def _load_thresholds(thresholds: dict | None) -> dict:
    if thresholds is not None:
        return thresholds
    weights_path = Path(__file__).resolve().parents[2] / "references" / "scoring_weights.json"
    with weights_path.open("r", encoding="utf-8") as f:
        return json.load(f)["thresholds"]


def evaluate(audit_input: AuditInput, thresholds: dict | None = None) -> DimensionResult:
    _ = _load_thresholds(thresholds)
    return DimensionResult(
        name="benchmarks",
        score=50.0,
        metrics={
            "phase": 1,
            "peer_count": 0,
            "rank": None,
        },
        findings=[Finding(
            severity="info",
            title="Peer benchmarking not yet enabled",
            evidence=(
                "Phase 3 will populate this dimension with peer comparison "
                "via Meta's Business Discovery API. Until then, score is a "
                "neutral 50/100 placeholder."
            ),
            recommended_action=(
                "Curate 8–12 peer accounts per studio location in references/peer_sets.json "
                "(3–5 same-neighborhood, 3–5 city-wide aspirational, 2–3 national)."
            ),
            impact="medium",
            ease="medium",
        )],
    )
