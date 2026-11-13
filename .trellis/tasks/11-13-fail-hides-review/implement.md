# Implementation and verification plan

Status: implemented and verified on 2026-11-13; awaiting work-commit approval. `--validations` and explicit INFO/reference preservation are included. No existing tests or expectations changed.

1. After approval, activate this task with curated backend/research context and load Trellis development guidelines.
2. Add the shared applicant finding projection in `api/common.py`. Keep full-source identity masking and all stored/officer facts intact.
3. Add explicit-upload `applicant_reason:` code/grade output to `verify_upload`; preserve all existing `reason:` diagnostics and privacy/audit behavior. Add opt-in `--validations` with failed-name-only per-slot output in single-document and income modes; test known/unknown/malicious names, passed-name exclusion and no default output.
4. Add standalone synthetic acceptance tests for mixed findings, review-only behavior, multiple FAILs with preserved INFO/reference warnings, historical severity defaults, immutable storage, identity privacy, upload/list/final-check, officer output, unchanged blockers and case 5/7 CLI results.
5. Run focused acceptance and existing guidance/quality/verify_upload/privacy regressions. Before changing any existing expectation, present the exact proposed diff and reason to the user.
6. Run `.venv/bin/python -B -m pytest engine_v2/tests -q` and `.venv/bin/python -B -m pytest demo/backend/tests -q`, logging results under `/tmp/fail-hides-review-*`. Compare against 1264 passed/3 skipped and 1107 passed. Run every `demo.backend.tests.run_p*_scenarios` sequentially to avoid shared DB collisions; compare 1885 passed/0 failed and P14 exit 0.
7. Review the entire diff against backend specs, update the response contract, validate task context and run `git diff --check`. Record counts, changed files, limitations and value-free case 5/7 applicant lists in the task report.
8. Present the concrete commit grouping for user approval per project workflow; do not push or merge. Original-file verification requires explicitly identified files and must be distinguished from synthetic acceptance.

## Completed verification

- Engine: 1264 passed /3 skipped; backend:1159 passed (1107 baseline +52 new); 18 scenario modules exit0, counting1885 passed/0 failed.
- Focused regression178 passed; independent review59 passed, no findings and no edits.
- Four changed Python files AST parse; all literal validation identifiers covered; git diff --check and task context validation pass.
- Synthetic verify_upload case5 applicant codes: MISSING_ADDRESS_DATES FAIL, LOW_IMAGE_QUALITY FAIL. Case7: MISSING_BILLING_MONTHS FAIL. Full officer diagnostics retained. Original case7 will be verified by the user on their Mac.
- Contract updated in failure-filtering.md; full evidence and concrete thirteen-file commit plan in report.md. No commit, push, merge, archive or journal mutation performed.
