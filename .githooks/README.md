# Git hooks

This directory contains optional Git hooks for contributors. They are NOT run by default — Git looks for hooks in `.git/hooks/` unless you tell it otherwise.

## Enable

```bash
git config core.hooksPath .githooks
```

That's a per-clone setting (stored in `.git/config`), not committed. Each contributor enables it once.

## What's here

| Hook | What it does |
|------|--------------|
| [`pre-commit`](pre-commit) | Blocks commits that stage `config/config.py`, `.env`, SSH keys, or contain Meta/GitHub/AWS/Slack token patterns. Warns on suspicious password-like values. |

## Bypassing

If you have a legitimate reason to bypass the hook (e.g. a test fixture with intentionally-fake tokens that match a pattern):

```bash
git commit --no-verify
```

Document the reason in the commit message. If you're bypassing because the hook has a false positive, please open an issue so we can refine the patterns.

## Windows note

The hook is a bash script. On Windows, it runs under Git Bash (which Git for Windows installs by default). If your environment doesn't have bash, the hook is a no-op — please run `bash .githooks/pre-commit` manually before committing, or use Git Bash.
