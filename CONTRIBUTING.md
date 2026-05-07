# Contributing to Instagram Audit Skill

Thanks for your interest in contributing. This is a public project — please read this whole file before opening a PR.

## ⚠️ The most important rule: never commit secrets

This repo is public. **Every push is permanent — even force-pushed history is recoverable from cached PRs and forks.** A leaked credential in any commit, even one later "removed", must be rotated immediately.

### Things that MUST NEVER be committed

| File / pattern | Why |
|----------------|-----|
| `config/config.py` | Contains MySQL password, Meta App Secret, long-lived tokens, Brevo SMTP password |
| `.env`, `.env.local`, `.env.production` | Same risk |
| `*.pem`, `*.key`, `id_rsa`, `id_ed25519` | SSH and SSL private keys |
| `*.token`, `*.secret`, `credentials*.json` | Vendor credential files |
| Real Meta App ID, App Secret, access tokens | Even in code comments, READMEs, or test fixtures |
| Real database passwords | Even in deploy docs — use `STRONG_PASSWORD_HERE` style placeholders |
| Real follower/user data with personal info | Anonymize fixtures before committing |
| Production server IP addresses | Use `$IG_HOST` style placeholders in docs |

The [`.gitignore`](.gitignore) blocks the most common patterns, but **belt-and-braces**:

1. Run `git status` before every commit — confirm nothing sensitive is staged
2. Run `git check-ignore <file>` to verify a file is properly ignored
3. Enable the optional pre-commit hook (see below)

### If you accidentally commit a secret

1. **Stop pushing.** Don't `git push` if you haven't yet.
2. If you've already pushed: **rotate the credential immediately** (Meta token, MySQL password, etc.). Removing the commit doesn't help — assume the value is compromised.
3. Open an issue at the repo with `[security]` in the title (or email — see [SECURITY.md](SECURITY.md)).

## Setup for development

```bash
# 1. Fork & clone
git clone https://github.com/YOUR_FORK/Instagram_Audit_Skill.git
cd Instagram_Audit_Skill

# 2. Python 3.11 venv
python3.11 -m venv venv
source venv/bin/activate              # Linux/macOS
# .\venv\Scripts\Activate.ps1         # Windows PowerShell
pip install --upgrade pip
pip install -r requirements.txt

# 3. Configure (this file is gitignored)
cp config/config.example.py config/config.py
# Edit config/config.py — fill in YOUR OWN local MySQL test credentials.
# On Linux/macOS:
chmod 600 config/config.py

# 4. Verify gitignore is working
git check-ignore config/config.py     # should print: config/config.py

# 5. (Recommended) Enable the pre-commit hook
git config core.hooksPath .githooks
```

## Running tests

```bash
pytest -v
```

All tests must pass before submitting a PR.

## Pre-commit hook

The [`.githooks/pre-commit`](.githooks/pre-commit) script blocks commits that:

- Stage `config/config.py`, `.env`, or other sensitive files
- Contain Meta access tokens (`EAA…` pattern), GitHub PATs (`ghp_…`), AWS keys (`AKIA…`), or Slack tokens (`xox…`)
- Contain non-placeholder strings that look like passwords (`password = "abc123…"`)

Enable it once per clone:

```bash
git config core.hooksPath .githooks
```

It's a safety net — not a replacement for paying attention.

## Branch and PR conventions

- **Branches** off `main`: `phase-N/short-description`, `fix/short-description`, `docs/short-description`
- **Commits**: imperative mood, one focused change per commit. Reference issues with `Fixes #N` or `Refs #N`.
- **PRs**: explain *what* changed and *why*. Link the issue. Include before/after screenshots if it touches reports or charts.
- **Tests**: every new dimension or scoring rule needs a test. See `tests/test_dimensions.py` for the high-score / low-score fixture pattern.

## Style

- Python: PEP 8 with 100-char lines. Docstrings on public functions only — keep comments to non-obvious *why*.
- Cross-platform paths: use `pathlib.Path`, never hardcode `/` or `\`.
- No new dependencies without discussion (open an issue first).
- Don't add features outside the current phase scope. The [README](README.md) tracks phase status; out-of-phase work is welcome but goes in a separate PR with a phase-N+1 branch name.

## Scope of contributions welcomed

- Bug fixes, especially in CSV parsing across Meta export variants
- New audit dimensions or refinements (with rubric updates and tests)
- Documentation improvements
- Cross-platform fixes (Windows, macOS, Linux)
- Translations of report copy
- Performance improvements that don't add dependencies

Out of scope without prior discussion (open an issue first):

- Major architectural changes
- New external service integrations beyond Meta Graph API
- Anything Phase 5 (productization) — that's design-stage and depends on Phase 1–4 learnings

## Code of conduct

Be kind. Disagree on substance, not on people. The maintainer reserves the right to close PRs and issues that don't meet this bar.

## License

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE).
