# Applicant finding projection

## Boundary

The behavior gap is in serialization: `document_dict()` currently publishes every stored finding. Keep assessment, persistence and officer serialization intact. Add a small shared applicant-findings projection in `demo/backend/api/common.py`, used by `document_dict()` and the explicit-upload verification CLI.

The projection accepts stored findings, ignores non-dictionary entries as today, and returns fresh dictionaries containing only the existing public keys (`code`, `message`, `how_to_fix`, `link`, `severity`). If any finding is FAIL, omit findings with severity NEEDS_REVIEW. Preserve other findings and their stable order. Treat missing severity on historical findings consistently with the existing document-blocker default of FAIL; do not infer failure from code names or message text. Do not recompute or mutate document status.

Identity mismatch masking must continue to inspect the complete source findings before suppression. Hiding a downgraded identity warning must not expose a previously masked name or birth date. No stored mapping/list may be mutated.

## Consumers and compatibility

`api/documents.py` upload/list responses, `api/review.py` final-check and status already call `document_dict()`; their route logic need not change. `api/officer.py:_document_view` must continue to return all stored findings including internal detail. `document_fact`, `check_document`, `document_blockers`, eligibility and submit remain unchanged.

`tools/verify_upload.py` currently prints complete diagnostic `reason:` lines from the assessment. Preserve them. Add value-free `applicant_reason: CODE GRADE` lines for explicit-upload mode through the same applicant projection. This makes verification of the visible response concrete without discarding officer diagnostics or printing messages/values. Add opt-in `--validations` in explicit-upload and income-bundle modes. Emit each failed validation name with its static slot key for document association. Read existing `판독검증실패` metadata only; never rerun/change extractors. Map names to a reviewed fixed production vocabulary (including bounded production name families), drop or safely mark unknown names without echoing them, deduplicate in stable order, and emit no values, evidence or successful validations. Reject `--validations` with `--slots-list` as incompatible modes. Keep default output unchanged apart from the approved additive applicant reasons.

## Expected files

- `demo/backend/api/common.py`: shared applicant finding projection and serializer integration, with full-source identity masking preserved.
- `demo/backend/tools/verify_upload.py`: additive applicant code/grade output for explicit-upload verification.
- `demo/backend/tests/test_applicant_failure_findings.py` (new): projection, API, officer and CLI acceptance regressions using fictitious findings/files, including FAIL + INFO + NEEDS_REVIEW and validation output privacy/document association.
- `.trellis/spec/backend/failure-filtering.md`: document the approved response contract after implementation and validation.
- This task's planning/research/report files.

No engine, verdict/blocking, database schema or frontend edits. No existing expectation changes are planned. If a baseline test requires one, first present its exact diff and rationale before editing it.

## Verification design

Cover FAIL plus INFO/reference warnings plus multiple reviews, multiple FAILs, review-only, PASS, historical message-only FAILs, malformed entries, stable order and source immutability. Preserve unknown non-NEEDS_REVIEW reference grades as well; do not implement a non-FAIL denylist. Include full-source identity masking and a NEEDS_REVIEW finding using the same code as another FAIL, proving the decision follows severity rather than a review-code denylist.

Use isolated database/API fixtures for upload response, list and final-check, compare with stored findings and officer representation, and confirm unchanged blockers/status/submit rejection. Use actual synthetic image files with authored recognition words for case 5/7 combinations; run `verify_upload` under its existing no-DB/value-free/audit checks and assert both complete diagnostic and applicant code lists. Never claim native OCR or original-file success from injected recognition.

Rollback is limited to the projection and additive CLI lines; no data migration is necessary.
