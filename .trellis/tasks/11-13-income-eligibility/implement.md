# Ordered implementation
1. [x] Commit reviewed planning artifacts.
2. [x] Implement A qualification evidence and focused tests; commit.
3. [x] Implement B payment evidence and focused tests; commit.
4. [x] Remove category fallback and expose trusted three-month/evidence facts; commit.
5. [x] Implement integer income outcomes and official household coverage; commit.
6. [x] Propagate income outcome through adapter/review/checklist; commit.
7. [x] Enforce shared age eligibility, identity mismatch and checklist; commit.
8. [x] Complete regression matrix, document changed existing expectations; commit.
9. [x] Full-scope Trellis check, tests and spec review; record results and mark task review awaiting user; commit.

No push, merge, PR or archive. Preserve unrelated dirty files. Use python3 (python unavailable); locate environment with pytest/dependencies before checks.

## Follow-up: status precedence and possible mixed interval
1. [x] Inventory every review status write and commit the follow-up design first (0c0b33b).
2. [x] Merge FAIL > NEEDS_REVIEW > PASS for new and reopened reviews, retaining reasons and stage separation (1a03895).
3. [x] Require INCOME_MIXED_POSSIBLE review above ordinary bounds through mixed equality; reject above all bounds (03b6a53).
4. [x] Add131 cases, update policy-obsolete expectations with reasons, verify officer list/detail/action and checklist (3184d68).
5. [x] Complete full-suite comparison: engine1172/3 skipped, backend735, scenarios1857/0 plus normal P14; update design, expectations and backend spec; commit verification.

Task remains review and awaiting user confirmation. No push, PR or archive. Pre-existing untracked audit files are excluded.
