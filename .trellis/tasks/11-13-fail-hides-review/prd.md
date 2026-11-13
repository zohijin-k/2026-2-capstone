# Hide review guidance for confirmed failures

## Goal

Prevent contradictory applicant guidance: a document that requires reupload must not also tell its applicant that an officer will check it if submitted as is.

## Background

- Main baseline: `1e5004c`; requested branch: `fix/fail-hides-review`, created from main.
- Applicant uploads, document lists, final-check and status share `api.common.document_dict`. Officer `_document_view` reads stored findings separately.
- The case-7-shaped synthetic fixture reproduces `LOW_OCR_CONFIDENCE / NEEDS_REVIEW` alongside `MISSING_BILLING_MONTHS / FAIL`. The confidence cap was added in `951dec9`; independent billing-period FAIL evidence followed in `6309602`. See `research/warning-origin.md` for evidence and limits.

## Requirements

- R1: Trace the warning's introducing commit, code and validation path, distinguishing synthetic reproduction from original-document verification.
- R2: In applicant upload cards and final-check, hide review-only findings whenever that same document has at least one confirmed FAIL finding. Preserve every FAIL finding, message and order.
- R3: Keep stored findings and officer responses complete. Preserve identity masking, public-field allowlists and applicant privacy.
- R4: Documents without confirmed FAIL retain their existing review guidance.
- R5: Do not change verdict precedence, submission blocking, engine extractors or frontend structure.
- R6: Report an existing test's proposed expectation diff and reason before modifying that expectation.

- R7: Preserve reference/INFO warnings even alongside FAIL; suppression is by exact NEEDS_REVIEW severity, never by warning text or code.
- R8: Add opt-in `--validations` to verify_upload, emitting only failed validation names per document, never values, source text or arbitrary OCR strings. Original case 7 will be verified by the user on their Mac.

## Acceptance Criteria

- [x] FAIL plus review warnings: applicant response preserves all FAILs and reference/INFO findings, omitting NEEDS_REVIEW only; stored/officer findings retain both classes.
- [x] Review-only: existing officer-check guidance remains and status/submission behavior is unchanged.
- [x] Authored case 7: `MISSING_BILLING_MONTHS` plus reading warning.
- [x] Authored case 5: `MISSING_ADDRESS_DATES` plus `LOW_IMAGE_QUALITY` plus reading warning.
- [x] Explicit-upload `verify_upload` reports applicant-visible codes/grades through the shared projection while preserving its existing complete diagnostic reasons and value-free output.
- [x] Run full engine_v2/backend pytest and all scenario modules; compare with 1264 passed/3 skipped, 1107 passed, and 1885 scenario checks passed/0 failed, respectively. Include P14's successful exit.
- [x] Report origin commit/code, changed files, test counts and applicant-visible case 5/7 code/grade lists, labeling synthetic versus original verification accurately.

## Constraints and approval

The user approved the final implementation plan on 2026-11-13, including opt-in failed-validation output and explicit preservation of reference/INFO warnings. Task creation was explicitly approved earlier that day. No original case 5/7 upload paths were supplied in this request; original-file verification cannot be claimed from authored fixtures. The existing value-free CLI remains the only planned original-file verification path if those files become available.
