<!-- Thanks for contributing! Please fill this out so review is fast. -->

## Summary

<!-- 1-2 sentences. What does this PR change and why? -->

## Phase

<!-- Phase 1, 2, 3, 4, or 5? Or out-of-phase (docs/fix/style)? -->

## Changes

<!-- Bullet list of the substantive changes -->

-
-

## Linked issue

<!-- Fixes #123 / Refs #456 -->

## Test plan

<!-- How did you verify this works? Include commands and expected output. -->

- [ ] `pytest -v` passes locally
- [ ] If touching the audit dimensions: added high-score and low-score test fixtures
- [ ] If touching report generation: opened the generated `.docx` and confirmed it renders
- [ ] If touching schema: tested migration applies cleanly to a fresh DB

## ⚠️ Secret check

- [ ] No `config/config.py`, `.env`, or other gitignored file is staged (`git status` confirms)
- [ ] No real Meta tokens, MySQL passwords, or production server IPs in the diff
- [ ] Pre-commit hook is enabled (`git config core.hooksPath .githooks`) and ran clean — OR I have manually verified the diff is safe

## Notes for the reviewer

<!-- Anything else? Trade-offs, alternatives, follow-ups, screenshots? -->
