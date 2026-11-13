# Failed-document applicant guidance report

## Outcome and branch

Implemented on `fix/fail-hides-review`, created from main `1e5004c`. A confirmed FAIL on a document suppresses only that same document's NEEDS_REVIEW findings in applicant upload/list/final-check/status document responses. All FAILs, INFO/reference findings and other grades retain their messages and stable order. Review-only documents retain their existing guidance. Stored findings and officer responses remain complete; identity masking still checks every source finding before suppression.

No verdict, blocker, extractor, engine, database schema or frontend source was changed. No existing test or expectation was modified. No commit, push or merge has been performed; the project workflow's concrete commit approval remains pending.

## Warning origin

`LOW_OCR_CONFIDENCE / NEEDS_REVIEW` is the code behind the quoted automatic-reading/officer-check guidance. Commit **951dec9215e70bd4a8907e939224490e06fa8bfc** (`fix: close OCR review gaps and verify full regression suite`, 2026-11-13 03:36:16 +09:00) introduced the payment-validation-based confidence cap of 0.4. Historical extractor/converter execution on the same authored case-7-shaped input shows confidence 0.9 before this commit and 0.4 after it, with the same failed validations: `monthly_rows_found`, `monthly_amounts_numeric`, `months_continuous`.

Commit **630960243fb4ca46e2455971fbc385a8f0203c3e** then introduced independent billing-period/amount-absence evidence for `MISSING_BILLING_MONTHS / FAIL`. Because independent certainty correctly survives unrelated aggregate uncertainty, both findings remain in the full assessment. The missing piece was applicant projection, not verdict precedence.

This is a generic confidence warning driven by payment validation failures, not a separate per-target-month required-field finding. Monthly extraction absence can therefore be reported alongside a certain billing-month defect. However, changing only the query range in a complete government-form control does not produce those extraction failures or LOW_OCR_CONFIDENCE. The original case 7's exact failed-check set is **unverified**; the user will inspect it locally with the new option. The synthetic fixture also omits header fragments and must not be described as proof of the original document's precise OCR failure. See `research/warning-origin.md` for both historical experiments and controls.

## Changed files

| File | Change |
| --- | --- |
| `demo/backend/api/common.py` | Shared immutable applicant finding projection; preserved full-source identity masking |
| `demo/backend/tools/verify_upload.py` | Additive applicant code/grade output and opt-in failed validation names by slot |
| `demo/backend/tests/test_applicant_failure_findings.py` | 15 new projection/API/officer/reference/case5/7 acceptance cases |
| `demo/backend/tests/test_verify_upload_validations.py` | 37 new validation-name, privacy, default-off, document-association and bounded-family cases |
| `.trellis/spec/backend/failure-filtering.md` | Executable applicant projection and CLI diagnostic contracts |
| `.trellis/tasks/11-13-fail-hides-review/prd.md` | Approved requirements and acceptance results |
| `.trellis/tasks/11-13-fail-hides-review/design.md` | Projection/CLI boundary and compatibility design |
| `.trellis/tasks/11-13-fail-hides-review/implement.md` | Execution and verification record |
| `.trellis/tasks/11-13-fail-hides-review/task.json` | Task metadata, branch and implementation status |
| `.trellis/tasks/11-13-fail-hides-review/implement.jsonl` | Backend/research implementation context |
| `.trellis/tasks/11-13-fail-hides-review/check.jsonl` | Independent review context |
| `.trellis/tasks/11-13-fail-hides-review/research/warning-origin.md` | Warning history, reproduced validation names and limits |
| `.trellis/tasks/11-13-fail-hides-review/report.md` | This report and full verification evidence |

## Tests

| Suite | Requested baseline | Final result | Difference |
| --- | --- | --- | --- |
| `engine_v2/tests` | 1264 passed / 3 skipped | **1264 passed / 3 skipped** | Unchanged |
| `demo/backend/tests` | 1107 passed | **1159 passed** | +52 new tests; no failures or removed tests |
| 17 counting scenarios | 1885 passed / 0 failed | **1885 passed / 0 failed** | Unchanged |
| All scenario modules, including P14 | All exit 0 | **18 modules exit 0** | Unchanged |

Focused implementation regression: **178 passed** (including the 44 existing CLI tests and all 52 new cases). Independent checker: **59 passed** across both new suites and resident-number privacy regression; no findings or code edits. All four changed Python files parsed successfully; static production validation names matched the positive vocabulary. `git diff --check` and Trellis context validation passed. No formatter/typechecker configuration or executable was present; no such check is claimed.

Full-suite logs: `/tmp/fail-hides-review-engine.log` (7 dependency warnings), `/tmp/fail-hides-review-backend.log` (9 dependency/deprecation warnings), `/tmp/fail-hides-review-scenarios-summary.log`, and per-module `/tmp/fail-hides-review-run_p*_scenarios.log`. Independent review log: `/tmp/fail-hides-review-independent-check.log`.

## Synthetic verify_upload applicant reasons

Executed actual authored image PDFs through `verify_upload.main` with `--self-identity --validations` and injected fictitious recognition words, using the unchanged shared upload assessment. Both documents retained status FAIL and blockers O. Complete diagnostic `reason:` lines still included the reading warnings; applicant lines were exactly:

| Case | Applicant-visible code | Grade |
| --- | --- | --- |
| 5 | `MISSING_ADDRESS_DATES` | FAIL |
| 5 | `LOW_IMAGE_QUALITY` | FAIL |
| 7 | `MISSING_BILLING_MONTHS` | FAIL |

Case 7's opt-in failed validations were exactly `monthly_rows_found`, `monthly_amounts_numeric`, `months_continuous`, each associated with `nhis_payment`. Value-free CLI log: `/tmp/fail-hides-review-case5-case7.log`. These are synthetic acceptance results, not native OCR or original-file verification.

## New CLI option and original case 7

Run from the repository root on the user's Mac:

```bash
.venv/bin/python -B -m demo.backend.tools.verify_upload --slot nhis_payment --self-identity --validations "<case-7.pdf>"
```

The option adds `failed_validation: SLOT NAME` only for names stored in failed-validation metadata. No values, source text, successful validations or explanations are output. Known static identifiers and bounded production families (daily copy indices 0–99; payment columns 1–8) are allowed. Unrecognized tokens become `UNKNOWN_VALIDATION`; their original contents are never echoed. Without the option there are no validation lines. It also works with `--income`, preserving payment/qualification/acquisition-loss slot association. `--slots-list --validations` is rejected with fixed ARGUMENT_ERROR.

Existing complete `reason:` diagnostics remain available to inspect officer-level findings. `applicant_reason:` lines show the shared applicant projection. Original files and native OCR success were not inspected or claimed in this implementation.

## Commit plan

One coherent work commit: `fix(demo): hide review guidance for failed applicant documents`, containing all thirteen files listed above. There are no unrecognized dirty files. Await user confirmation before staging or committing, per `.trellis/workflow.md` Phase 3.4. Do not push or merge. After the work commit, `/trellis:finish-work` can handle the separate archive/journal workflow.
