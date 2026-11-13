# Review warning origin and response boundary

## Confirmed repository evidence

- `engine/reason_messages.py:16` maps `LOW_OCR_CONFIDENCE` to the quoted automatic-reading/officer-check message. `rules/doc_check.py:66,88` adds the existing submit-as-is guidance. This is distinct from `REQUIRED_FIELD_UNREADABLE`.
- Commit `951dec9215e70bd4a8907e939224490e06fa8bfc` (2026-11-13 03:36:16 +09:00), `fix: close OCR review gaps and verify full regression suite`, adds `nhis_payment.REVIEW_VALIDATIONS`, `has_failed_payment_validation`, and `_from_nhis`'s confidence cap of 0.4 when critical payment validations fail.
- `demo/backend/ocr/localocr.py:398-405` retains that cap. The single-document engine check (`engine/stage1_document_check.py:73-76`) emits LOW_OCR_CONFIDENCE below its unchanged threshold; the demo keeps that finding NEEDS_REVIEW.
- Commit `630960243fb4ca46e2455971fbc385a8f0203c3e` adds independent printed-period/absence evidence and a certain `MISSING_BILLING_MONTHS` FAIL. That proof is deliberately independent of aggregate OCR confidence, so it coexists with the warning.
- `api/common.py:218` serializes all stored findings for applicants without mixed-FAIL suppression. Upload/list/final-check/status reuse it. `api/officer.py:654-669` independently projects complete findings from storage. Final-check `_warnings` counts documents whose status is NEEDS_REVIEW, so a FAIL document does not add that aggregate warning; the contradiction originates in its per-document findings.

## Read-only synthetic reproduction

Executed `.venv/bin/python -B` with `fail_case_samples.missing_payment_months()`, current `nhis_payment.extract`, and historical `_from_nhis` functions extracted with AST from `git show` into isolated namespaces. No source edits or historical checkout were performed, and no document values were printed.

The same extracted case-7-shaped input has no `월별고지금액` field and fails `monthly_rows_found`, `monthly_amounts_numeric`, `months_continuous`.

| Converter revision | Confidence | LOW_OCR_CONFIDENCE |
| --- | --- | --- |
| `951dec9^` | 0.9 | absent |
| `951dec9` | 0.4 | NEEDS_REVIEW |
| `HEAD` | 0.4 | NEEDS_REVIEW |

Current complete findings: `LOW_OCR_CONFIDENCE NEEDS_REVIEW`, `MISSING_BILLING_MONTHS FAIL`.

Historical converters do not add the independent `고지월검증자료` field introduced later in 6309602. With today's checker their billing result is therefore NEEDS_REVIEW; this experiment isolates the warning/confidence change, not an end-to-end historical verdict.

A second read-only experiment loaded each revision's complete `engine_v2/extractors/nhis_payment.py` into a temporary module namespace (relative imports retained), then used that revision's `_from_nhis` on the same fictitious pages. `951dec9^`, `951dec9`, `6309602` and HEAD all reported the same three failed validation names. Confidence was respectively 0.9, 0.4, 0.4 and 0.4. This confirms the confidence-cap origin without relying solely on today's payment extractor.

## What the duplicate means, and the limit

The duplicate is a broad payment-validation confidence warning, not a separate required-field check for each missing target month. Absence of the monthly map/rows can trigger those validations and thus generic LOW_OCR_CONFIDENCE even when independent evidence establishes a certain billing defect. Hiding it belongs in applicant projection, not in the extractor or severity policy.

Do not overstate why the original case 7 failed its monthly validations. The authored fixture also removes header fragments to follow the generic legacy payment reader. A control retaining the normal government form and changing only the query period fails no extraction validations and stays confidence 0.95; it acquires no LOW_OCR_CONFIDENCE. Thus a missing target range alone does not universally imply that warning. Original files have not been supplied or executed in this task; the original document's exact failed-check set remains unverified.

## CLI and existing expectation boundary

`verify_upload.py:265-266` prints complete assessment findings; changing its `reason:` lines to applicant-only findings would erase diagnostic coverage. Preserve them and add applicant-visible code/grade lines through the shared projection. Existing tests need no planned expectation rewrites. `tests/test_verify_upload.py:36` checks privacy by forbidden values rather than an exact prefix schema; additive value-free lines fit that contract.

## Approved refinements

The user approved implementation with two refinements on 2026-11-13: preserve all reference/INFO findings (hide exact NEEDS_REVIEW only), and expose opt-in `--validations` containing failed names per document, never values/source text. Original case 7 will be run by the user on their Mac. Existing daily insurance-mark reference text is retained in OCR `판독경고` metadata and is not currently a standalone CheckFinding; do not invent a new finding, grade or frontend path for it.
