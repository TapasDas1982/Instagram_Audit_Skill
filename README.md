# Instagram Audit Skill

Audits an Instagram Business or Creator account across seven dimensions and produces a Word (`.docx`) report with a scorecard, findings, and prioritized action plan.

Built for **Twist N Turns** dance studios — multi-location accounts audited monthly, benchmarked against neighborhood peers, integrated with the existing PHP/MySQL studio admin panel.

## The three locked decisions

| Decision | Choice | Why |
|----------|--------|-----|
| **Scope first** | Twist N Turns own studios only | Tightest feedback loop. No app review delay before validating audit logic on data we understand. |
| **Stack** | Python 3.11 | `pandas + matplotlib + python-docx` saves ~1 week vs PHP. Runs alongside the PHP studio app in its own venv. |
| **Storage** | MySQL on the existing studio host, new schema `ig_audit` | Reuses existing MySQL host, fits the existing `config.php` pattern, lets us trend audits over time. |

## Phase status

| Phase | Outcome | Status |
|-------|---------|--------|
| Phase 0 | Setup, structure, schema, Meta App queued for review | ✅ |
| Phase 1 | CSV-import audit producing Word reports | ⬜ |
| Phase 2 | Graph API integration (no manual exports) | ⬜ |
| Phase 3 | Peer benchmarking | ⬜ |
| Phase 4 | Monthly automated email + admin panel page | ⬜ |
| Phase 5 | Productize for the dance teacher hiring platform | ⬜ |

## Audit dimensions

1. **Profile health** — bio, link, highlights, pinned posts
2. **Cadence** — frequency, time-of-day, content mix
3. **Engagement** — ER%, Power 4 (likes/comments/saves/shares), saves-to-likes ratio
4. **Reels** — watch time, retention, replays
5. **Audience** — growth, geo/demo, active hours
6. **Hashtag effectiveness** — tier mix and reach
7. **Competitive benchmarks** (Phase 3) — peer-relative ranks

Weighted overall score (0–100) per [`references/scoring_weights.json`](references/scoring_weights.json).

## Quickstart

```bash
# 1. Clone
git clone https://github.com/TapasDas1982/Instagram_Audit_Skill.git
cd Instagram_Audit_Skill

# 2. Set up Python 3.11 venv
python3.11 -m venv venv
source venv/bin/activate              # Linux/macOS
# .\venv\Scripts\Activate.ps1         # Windows PowerShell
pip install --upgrade pip
pip install -r requirements.txt

# 3. Apply MySQL schema
mysql -u root -p < db/schema.sql
# Then create the application user — see db/schema.sql header.

# 4. Configure
cp config/config.example.py config/config.py
# Edit config/config.py — fill in MYSQL credentials.
# On Linux: chmod 600 config/config.py

# 5. Run an audit (Phase 1, available after sign-off)
python scripts/audit.py \
    --source csv \
    --csv-path tests/fixtures/sample_export.csv \
    --account twistnturns \
    --profile-json tests/fixtures/sample_profile.json
# → output/twistnturns_YYYY-MM-DD.docx
```

## Project structure

```
.
├── config/           # config.example.py committed; config.py gitignored
├── scripts/          # CLI entrypoints (audit.py, ingest_*.py, batch_run.py, ...)
├── lib/              # Library code (normalize, scoring, charts, audit_dimensions/)
├── references/       # Scoring weights, rubric, peer sets, benchmark data
├── templates/        # Word .docx template + section copy
├── tests/            # pytest tests + CSV/API fixtures
├── db/               # schema.sql + migrations
├── deploy/           # Linux deployment artifacts (cron, logrotate, runbooks)
├── cache/            # gitignored — API response cache
└── output/           # gitignored — generated reports
```

## Tapash-side parallel tasks (start now, run in background)

These don't block code but DO block Phase 2 launch — start them while Phase 1 is being built:

- [ ] **Create the Meta App** at https://developers.facebook.com/apps/ (Business type). App review takes 1–3 weeks.
  - Add products: Instagram Graph API, Facebook Login for Business
  - Request scopes: `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`, `pages_show_list`, `business_management`
- [ ] **Publish Privacy Policy + Terms of Service** on `twistnturns.in` — Meta App Review rejects without these. Pages must be live and indexable.
- [ ] **Switch IG accounts to Business or Creator** if any are still Personal. Each must be linked to a Facebook Page Tapash owns.
- [ ] **Provision Hetzner Cloud server** — Ubuntu 22.04+, MySQL 8, Python 3.11. See [`deploy/hetzner_setup.md`](deploy/hetzner_setup.md) when written in Phase 0.

## Deployment target

**Hetzner Cloud** (Linux). The full provisioning runbook is in [`deploy/hetzner_setup.md`](deploy/hetzner_setup.md).

The Python audit tool reads from and writes to the same MySQL database the existing PHP studio admin panel uses. Phase 4 adds a PHP page (`admin/ig-audits.php`) to the existing admin project that surfaces audit data — that PHP file is a separate deliverable to Tapash's PHP repo, not in this repo.

## Contributing

This project is public so other developers can contribute. Before opening a PR, please read:

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — setup, branch conventions, test plan, code style
- **[SECURITY.md](SECURITY.md)** — how to report a vulnerability (privately, not as a public issue)
- **[.githooks/README.md](.githooks/README.md)** — enable the pre-commit hook to catch accidental secret commits

### ⚠️ For all contributors: never commit secrets

This repo is public — every push is permanent. **Do not** commit `config/config.py`, `.env`, real Meta tokens, MySQL passwords, or any other credentials. The `.gitignore` blocks the common patterns and `.githooks/pre-commit` is a safety net, but pay attention to `git status` before every commit.

If you accidentally push a real secret, **rotate the credential immediately** (don't try to remove it from history — it's already cached). See [SECURITY.md](SECURITY.md) for the report flow.

## License

[MIT](LICENSE) — free for any use, including commercial. By contributing, you agree your contributions are licensed under the same terms.
