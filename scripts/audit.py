"""
Audit orchestrator — the main CLI entry point.

Usage:
    python scripts/audit.py --source csv \
        --csv-path tests/fixtures/sample_export.csv \
        --account twistnturns \
        --profile-json tests/fixtures/sample_profile.json

Phase 2 will add `--source api` (no CSV required, pulls from Graph API).

Run from the project root so relative paths work, OR from anywhere by ensuring
the project root is on PYTHONPATH (the script does this automatically).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


# Make the project root importable when run as `python scripts/audit.py`
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from lib.audit_dimensions import (  # noqa: E402
    audience,
    benchmarks,
    cadence,
    engagement,
    hashtags,
    profile,
    reels,
)
from lib.db import save_audit  # noqa: E402
from lib.scoring import Scorer  # noqa: E402
from scripts.ingest_csv import build_audit_input_from_csv  # noqa: E402
from scripts.report import generate_report  # noqa: E402


DIMENSION_EVALUATORS = {
    "profile": profile.evaluate,
    "cadence": cadence.evaluate,
    "engagement": engagement.evaluate,
    "reels": reels.evaluate,
    "audience": audience.evaluate,
    "hashtags": hashtags.evaluate,
    "benchmarks": benchmarks.evaluate,
}


def _load_mysql_config() -> dict | None:
    """Load MYSQL config from config/config.py if it exists; else return None."""
    try:
        sys.path.insert(0, str(_PROJECT_ROOT / "config"))
        import config  # type: ignore
        return getattr(config, "MYSQL", None)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an Instagram audit and produce a Word report.")
    parser.add_argument("--source", choices=["csv", "api"], required=True)
    parser.add_argument("--csv-path", help="Path to a Meta Business Suite CSV export (required when --source csv)")
    parser.add_argument("--profile-json", help="Path to the profile sidecar JSON (recommended for CSV runs)")
    parser.add_argument("--account", required=True, help="Account username (used for output filename)")
    parser.add_argument("--period-days", type=int, default=30, help="Audit window length in days (default: 30)")
    parser.add_argument("--output-dir", default=str(_PROJECT_ROOT / "output"))
    parser.add_argument("--weights", default=str(_PROJECT_ROOT / "references" / "scoring_weights.json"))
    parser.add_argument("--studio-location", default=None, help="Studio location tag (e.g. 'ballygunge')")
    parser.add_argument("--no-db", action="store_true", help="Skip MySQL persistence even if config is present")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("audit")

    # ---- Build AuditInput ----
    if args.source == "csv":
        if not args.csv_path:
            parser.error("--csv-path is required when --source csv")
        audit_input = build_audit_input_from_csv(
            csv_path=args.csv_path,
            profile_json_path=args.profile_json,
            period_days=args.period_days,
        )
    else:
        log.error("--source api lands in Phase 2. Use --source csv for now.")
        return 2

    log.info(
        "Loaded %d posts for @%s (%s → %s, source=%s)",
        len(audit_input.posts),
        audit_input.profile.username,
        audit_input.period_start,
        audit_input.period_end,
        audit_input.source,
    )

    # ---- Score ----
    scorer = Scorer(args.weights)
    results = {}
    for name, evaluate in DIMENSION_EVALUATORS.items():
        log.debug("Evaluating dimension: %s", name)
        results[name] = evaluate(audit_input, thresholds=scorer.thresholds)

    dim_scores = {name: r.score for name, r in results.items()}
    overall = scorer.overall(dim_scores)
    grade = scorer.grade(overall)

    # ---- Generate Word report ----
    template_path = _PROJECT_ROOT / "templates" / "report_template.docx"
    report_path = generate_report(
        account=args.account,
        audit_input=audit_input,
        results=results,
        overall_score=overall,
        grade=grade,
        weights=scorer.weights,
        output_dir=args.output_dir,
        template_path=template_path if template_path.exists() else None,
    )
    log.info("Report saved: %s", report_path)

    # ---- Persist to MySQL ----
    if not args.no_db:
        mysql_config = _load_mysql_config()
        audit_id = save_audit(
            mysql_config=mysql_config,
            audit_input=audit_input,
            results=results,
            overall_score=overall,
            report_path=report_path,
            studio_location=args.studio_location,
        )
        if audit_id:
            log.info("Audit persisted to MySQL: audits.id=%d", audit_id)

    # ---- Terminal summary ----
    # Use ASCII bars (#/.) instead of Unicode block chars — Windows console
    # default cp1252 encoding can't render U+2588/U+2591.
    print()
    print("=" * 60)
    print(f"  Instagram Audit -- @{audit_input.profile.username}")
    print(f"  Overall Score: {overall:.1f}/100  (Grade: {grade})")
    print("=" * 60)
    for name in DIMENSION_EVALUATORS:
        score = dim_scores[name]
        bar_len = int(score / 5)
        bar = "#" * bar_len + "." * (20 - bar_len)
        print(f"  {name.title():<13} {bar} {score:5.1f}/100")
    print("=" * 60)
    print(f"  Report: {report_path}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
