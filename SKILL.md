---
name: instagram-audit
description: Run a comprehensive audit on an Instagram Business or Creator account and produce a Word report with scorecard, findings, and prioritized action plan. Use this skill whenever the user asks for an Instagram audit, account review, social media analysis, performance review, content review, or wants to understand why their Reels aren't performing — even if they don't explicitly say "audit". Also use when comparing accounts to peers, benchmarking against competitors, or generating a monthly Instagram health check.
---

# Instagram Audit Skill

Audits an Instagram Business or Creator account across seven dimensions and produces a Word (`.docx`) report.

## When this skill is invoked

Decide the data path:

1. **CSV path** — the user has an export from Meta Business Suite. Run:
   ```
   scripts/audit.py --source csv --csv-path <path> --account <username> [--profile-json <path>]
   ```
2. **API path** (Phase 2 onwards) — credentials in `config/config.py`. Run:
   ```
   scripts/audit.py --source api --account <username>
   ```

If unclear, ask which path. Default to CSV when `config/config.py` has no Meta token.

## Dimensions audited

| # | Dimension | Weight | Key signals |
|---|-----------|--------|-------------|
| 1 | Profile health | 0.10 | Bio length, value prop clarity, link in bio, ≥4 highlights, branded display name |
| 2 | Cadence | 0.15 | Posts/week, inter-post variance, content mix, time-of-day vs audience active hours |
| 3 | Engagement | 0.25 | ER% = (likes+comments+saves+shares)/followers, saves-to-likes, comment-to-like |
| 4 | Reels | 0.20 | Avg watch time, retention %, replay rate |
| 5 | Audience | 0.10 | Follower growth slope, geo distribution, age/gender, active hours |
| 6 | Hashtags | 0.05 | Tier mix (large/mid/small), avg reach per tier |
| 7 | Benchmarks | 0.15 | Quartile rank vs curated peer set per location |

**Composite score** = weighted average (0–100), graded A/B/C/D/F.

## Output

Word document in `./output/{username}_{YYYY-MM-DD}.docx` containing:

- Cover with overall score (0–100) and grade
- Per-dimension scorecard with score badges
- Findings with evidence (specific posts, dates, numbers)
- Prioritized action plan (sorted by impact × ease)
- Charts: engagement-over-time, content mix donut, posting heatmap, hashtag tier reach
- Phase 3 onwards: Competitive Position section with peer comparison

A row is also written to the MySQL `audits` table for trend tracking and admin panel display.

## Reference files

- [`references/audit_rubric.md`](references/audit_rubric.md) — human-readable scoring rubric
- [`references/scoring_weights.json`](references/scoring_weights.json) — machine-readable weights and thresholds
- [`references/peer_sets.json`](references/peer_sets.json) — Phase 3 peer lists per location
- [`templates/report_template.docx`](templates/report_template.docx) — Word template with placeholders
- [`templates/report_sections.md`](templates/report_sections.md) — Section copy and tone reference

## Scripts

- [`scripts/ingest_csv.py`](scripts/ingest_csv.py) — parse Meta Business Suite CSV exports
- [`scripts/ingest_api.py`](scripts/ingest_api.py) — pull from Instagram Graph API (Phase 2)
- [`scripts/audit.py`](scripts/audit.py) — orchestrator, the main entry point
- [`scripts/report.py`](scripts/report.py) — generate the Word document
- [`scripts/refresh_token.py`](scripts/refresh_token.py) — refresh Meta long-lived token (Phase 2 cron)
- [`scripts/benchmark_peers.py`](scripts/benchmark_peers.py) — pull peer data via Business Discovery (Phase 3)
- [`scripts/batch_run.py`](scripts/batch_run.py) — monthly multi-account batch (Phase 4)

## Status

This skill is built phase by phase. See [`README.md`](README.md) for current phase status. Phase 0 (setup) is complete; Phase 1 (CSV MVP) is the next deliverable.
