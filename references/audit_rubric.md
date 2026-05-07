# Audit Rubric (human-readable)

This is the human-readable companion to [`scoring_weights.json`](scoring_weights.json). When tuning weights or thresholds, update both files together.

## Why these weights?

| Dimension | Weight | Rationale |
|-----------|-------:|-----------|
| Engagement | 0.25 | Strongest signal of audience health. If people aren't engaging, nothing else matters. |
| Reels | 0.20 | Most-rewarded format in 2026. Underweighting Reels misses the platform's primary growth lever. |
| Cadence | 0.15 | Foundation for all other metrics — irregular posting capsizes engagement and growth. |
| Benchmarks | 0.15 | Context. Winning vs peers matters more than absolute numbers in a saturated category. |
| Profile | 0.10 | Necessary but rarely the bottleneck once basics are in place. |
| Audience | 0.10 | Diagnostic, not actionable on a short timescale — useful for direction-setting. |
| Hashtags | 0.05 | Diminishing returns in 2026 algorithm. Worth flagging excess but small overall lever. |

## Threshold rationale

| Metric | Strong | OK | Weak | Notes |
|--------|:------:|:--:|:----:|-------|
| Engagement rate | ≥3% | 1–3% | <1% | (likes+comments+saves+shares) / followers |
| Saves-to-likes | ≥5% | 2–5% | <2% | Saves are the strongest "this is useful" signal |
| Comment-to-like | ≥2% | — | — | Indicates real conversation vs passive likes |
| Posting frequency | ≥4/wk | 2–4/wk | <2/wk | Below 2/wk and the algorithm de-prioritizes the account |
| Reels share of content | ≥50% | 30–50% | <30% | 2026 algorithm rewards Reels disproportionately |
| Reels retention | ≥50% | 30–50% | <30% | Avg watch / total length |
| Follower growth (30d) | ≥3% | 1–3% | <1% | Linear regression over the audit period |

## Tuning notes

These thresholds are the doc's starting point — tune them against Twist N Turns data after **3 audits**. Dance/lifestyle accounts may push thresholds in either direction:

- Local studios with hyper-engaged audiences often beat 3% ER even with small followings — consider raising the strong threshold to 5%.
- Reels share for service businesses (vs creators) may be lower — 30–40% is realistic.

When you change a value:

1. Update `scoring_weights.json`
2. Update the table in this file
3. Note the date and reason in a `references/changelog.md` entry (create when first tuning happens)
4. Re-run the last 3 audits and compare scores — any dramatic swing means the weight wasn't well-calibrated.

## Score-to-grade mapping

| Score range | Grade | Meaning |
|-------------|:-----:|---------|
| 85–100 | A | Excellent — minor optimizations only |
| 70–84 | B | Good — clear opportunities for improvement |
| 55–69 | C | Average — significant gaps to address |
| 40–54 | D | Below average — major overhaul needed |
| 0–39  | F | Critical — fundamental issues to fix first |
