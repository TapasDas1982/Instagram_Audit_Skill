# Security Policy

## Reporting a vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

If you discover a security issue — leaked credential in commit history, code that could expose user data, an injection or authentication flaw — report it privately:

1. Open a GitHub Security Advisory: https://github.com/TapasDas1982/Instagram_Audit_Skill/security/advisories/new (preferred — keeps the disclosure thread together)
2. Or email the maintainer directly via the contact on https://twistnturns.in

Please include:

- A clear description of the issue
- Steps to reproduce (or a proof-of-concept)
- The affected file(s), commit(s), or behavior
- Your assessment of impact

I'll acknowledge receipt within 5 business days and aim to fix or mitigate within 30 days, depending on severity.

## What's in scope

| In scope | Out of scope |
|----------|--------------|
| Code in this repository (`scripts/`, `lib/`, `db/`, `config/config.example.py`) | The deployed Twist N Turns infrastructure (twistnturns.in, Hetzner production server) |
| Leaked secrets in commit history | Self-XSS or attacks requiring an attacker-controlled config.py |
| Dependency vulnerabilities flagged by the project's `requirements.txt` | Vulnerabilities in third-party packages (report upstream) |
| Documentation that recommends insecure patterns | UI/UX issues unrelated to security |
| Schema or query patterns that enable SQL injection or data exposure | The Meta Graph API itself (report to Meta) |

## What you'll do for me

If you find a leaked credential — a real Meta token, MySQL password, SMTP password — in this repo's history, **assume it is compromised** and report immediately. I will rotate the credential before merging the fix.

## Hardening checklist

The project follows these practices to reduce the chance of an incident:

- All secrets live in `config/config.py` which is gitignored from commit 1
- `config/config.example.py` (committed) uses `REPLACE_ME` placeholders only
- `.gitignore` covers SSH keys, SSL certs, vendor credential files, DB dumps, and `.env*` files
- `scripts/check_secrets.sh` and `.githooks/pre-commit` block known secret patterns at commit time
- Production deployment guide ([deploy/hetzner_setup.md](deploy/hetzner_setup.md)) instructs `chmod 600 config/config.py`
- GitHub Secret Scanning is enabled (free for public repos) and Dependabot alerts are on
- No real PII (follower lists, audit reports for real accounts) is committed — fixtures must be anonymized

## Thanks

Security is a team sport. If you take the time to report something privately, I appreciate it and will credit you in the fix commit unless you ask otherwise.
