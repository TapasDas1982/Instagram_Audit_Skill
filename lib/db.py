"""
Thin MySQL wrapper for the audit pipeline.

Two responsibilities:
1. `upsert_account(username, **fields)` — get-or-create the accounts row
2. `save_audit(account_id, audit_input, results, overall_score, report_path)` —
   write one audits row and the per-dimension audit_history rows in a transaction

If the database is unreachable (e.g. dev machine without MySQL running),
`save_audit` logs a warning and returns None instead of crashing the audit
run — the .docx report is still produced.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Optional

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:  # pragma: no cover - mysql may not be installed in dev/test
    mysql = None
    MySQLError = Exception

from lib.normalize import AuditInput, DimensionResult


logger = logging.getLogger(__name__)


def _serialize(obj: Any) -> Any:
    """JSON encoder for dataclasses, dates, datetimes."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return str(obj)


@contextmanager
def _connect(mysql_config: Mapping[str, Any]):
    """Yield a MySQL connection. Closes on exit."""
    if mysql is None:
        raise RuntimeError(
            "mysql.connector is not installed. Run: pip install mysql-connector-python"
        )
    conn = mysql.connector.connect(
        host=mysql_config["host"],
        port=mysql_config.get("port", 3306),
        user=mysql_config["user"],
        password=mysql_config["password"],
        database=mysql_config["database"],
    )
    try:
        yield conn
    finally:
        conn.close()


def upsert_account(
    mysql_config: Mapping[str, Any],
    username: str,
    *,
    display_name: str | None = None,
    studio_location: str | None = None,
    account_type: str = "owned",
    ig_user_id: str | None = None,
) -> int:
    """Return the integer accounts.id for `username`, creating the row if needed."""
    with _connect(mysql_config) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM accounts WHERE username = %s", (username,))
        row = cur.fetchone()
        if row:
            return int(row[0])
        cur.execute(
            """
            INSERT INTO accounts
                (ig_user_id, username, display_name, studio_location, account_type)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (ig_user_id, username, display_name, studio_location, account_type),
        )
        conn.commit()
        return int(cur.lastrowid)


def save_audit(
    *,
    mysql_config: Mapping[str, Any] | None,
    audit_input: AuditInput,
    results: Mapping[str, DimensionResult],
    overall_score: float,
    report_path: str | Path,
    studio_location: str | None = None,
) -> Optional[int]:
    """Persist the audit. Returns the inserted audits.id, or None if MySQL is down.

    Designed to be non-fatal — if MySQL isn't available, log a warning and
    move on. The .docx is still saved by the caller.
    """
    if not mysql_config or mysql_config.get("password") in (None, "REPLACE_ME"):
        logger.warning(
            "MySQL config missing or unconfigured; skipping persistence. "
            "(Edit config/config.py to enable.)"
        )
        return None

    try:
        account_id = upsert_account(
            mysql_config,
            audit_input.profile.username,
            display_name=audit_input.profile.display_name,
            studio_location=studio_location,
            account_type="owned",
        )
        with _connect(mysql_config) as conn:
            cur = conn.cursor()
            scores_json = json.dumps(
                {name: r.score for name, r in results.items()}, default=_serialize
            )
            findings_json = json.dumps(
                {
                    name: [
                        {
                            "severity": f.severity,
                            "title": f.title,
                            "evidence": f.evidence,
                            "action": f.recommended_action,
                            "impact": f.impact,
                            "ease": f.ease,
                        }
                        for f in r.findings
                    ]
                    for name, r in results.items()
                },
                default=_serialize,
            )
            raw_data_json = json.dumps(
                {
                    "profile": asdict(audit_input.profile),
                    "audience": asdict(audit_input.audience),
                    "post_count": len(audit_input.posts),
                },
                default=_serialize,
            )
            cur.execute(
                """
                INSERT INTO audits
                    (account_id, audit_date, source, period_start, period_end,
                     overall_score, raw_data_json, scores_json, findings_json,
                     report_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    account_id,
                    date.today(),
                    audit_input.source,
                    audit_input.period_start,
                    audit_input.period_end,
                    round(overall_score, 2),
                    raw_data_json,
                    scores_json,
                    findings_json,
                    str(report_path),
                ),
            )
            audit_id = int(cur.lastrowid)

            # Per-dimension history rows
            for name, r in results.items():
                cur.execute(
                    """
                    INSERT INTO audit_history
                        (account_id, audit_id, dimension, score, metric_name, metric_value)
                    VALUES (%s, %s, %s, %s, NULL, NULL)
                    """,
                    (account_id, audit_id, name, round(r.score, 2)),
                )
                # Numeric metrics for trend tracking
                for metric_name, metric_value in r.metrics.items():
                    if isinstance(metric_value, (int, float)):
                        cur.execute(
                            """
                            INSERT INTO audit_history
                                (account_id, audit_id, dimension, score, metric_name, metric_value)
                            VALUES (%s, %s, %s, NULL, %s, %s)
                            """,
                            (account_id, audit_id, name, metric_name, float(metric_value)),
                        )
            conn.commit()
            return audit_id
    except MySQLError as e:
        logger.warning("MySQL persistence failed: %s. Audit report still saved at %s.", e, report_path)
        return None
    except Exception as e:  # pragma: no cover
        logger.exception("Unexpected error in save_audit: %s", e)
        return None
