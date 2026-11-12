# Income and age eligibility evidence

## Goal
Prevent false income approval/rejection and enforce inclusive program birth ranges.

## Requirements and acceptance
1. Use only the configured three health-insurance billed months (October–December 2025); retain existing rounded-average formula, exclude care and extra-income columns. Missing or untrusted amounts require review.
2. Preserve the public 1–10 household table; reject no one using a clamped 11+ row. Unknown household size requires review.
3. Extract A (qualification management number) and B (government payment workplace) as 값 있음 / 확실한 공란 / 못 읽음. Blank requires observed bounded labels/cells and complete form structure. Never infer blank from missing fields.
4. Compare integer average with min/max workplace/regional limits. At/below both meets income; above both exceeds; between requires two agreeing A/B sources, or trusted printed legacy category compatibility. No mixed/multi-worker rule is introduced. Explicit category conflicts require review.
5. Certain excess fails with INCOME_OVER_THRESHOLD. Undetermined income always produces final NEEDS_REVIEW and visible reason details; checklist uses the same state. Job package has no income rule.
6. Both programs enforce inclusive birth_range: outside fails, absent/unreadable or identity mismatch requires review. Check identity source and editability.
7. Keep fixtures, old validations and extractor fields; add obviously fictitious coordinate/adapter/review regressions. Preserve tests except explicitly changed obsolete expectations, documenting each.

## Constraints
Branch feat/income-eligibility from e10438a; no main merge, push or PR. Commit each of nine stages. Do not access private data or execute real documents. Masked /tmp layouts are read-only; never copy wholesale. Do not touch docs/audit/. No residence, identifier-retention or unrelated extractor changes. Final task status review, awaiting user confirmation.

## Follow-up confirmed requirements
The user's follow-up supersedes requirements 4–5 where they conflict: definite FAIL from any source wins over NEEDS_REVIEW; final includes engine final plus household/income/age/overlap, while stage2 includes only engine stage2 plus those additional results. Preserve reasons and synchronize stored/payload/action/officer list/detail. Existing overlapping applications retain their own FAIL while officer decisions are reset as before. For rows with mixed limits, above both ordinary limits but at/below mixed is UNDETERMINED / INCOME_MIXED_POSSIBLE; above all available limits is certain excess. No mixed membership selection. One-person behavior and ordinary middle/low rules remain. Five ordered local commits, task review/user-confirmation state retained.
