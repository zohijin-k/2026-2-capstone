# Stage 7 results

## Behavior

The dedicated `engine_v2/extractors/business_registration.py` reader reads the thirteen requested fields using the observed NTS grid, with typed dates, industry/category lists and a joint-business boolean. `engine_v2/engine.py:45` registers the new proof enum from `engine_v2/schemas/models.py:37`.

`business_registration.py:90` derives the label/value corridor from observed full-label bounds and repeated right-value starts. Justified labels use the shared bounded label view, while values preserve their original words and boxes. Header aliases are deduplicated by contained source-word identity, with duplicated labels still rejected.

`business_registration.py:138` reads all joint rows. A unique explicit no-participant phrase permits the source-shaped oversized two-plus-one-character fragments when they provide no independently plausible name/identifier row. Their original purpose remains 추정. A complete participant, normal partial identity row, numeric residue or conflicting absence phrase keeps the result reviewable. Each observed column is grouped independently, then equal row counts and bounded vertical offsets relative to row pitch establish the pairing. Joint rows one through ten are covered with positive/negative skew and jitter. Equal counts cannot conceal missing first/last rows.

The `_issue_date` helper bounds issuance below confirmation and the current-status notice and above the unique tax-office issuer. It selects the complete aligned date row so text-layer tokenization can split year, month and day. Missing/malformed/competing dates remain incomplete. Additional aligned numeric/date content overlapping the issuer block also invalidates uniqueness, covering rows whose upper edge precedes the issuer while their center overlaps it.

The reader uses the existing `job_common.brn_is_valid` checksum. A valid personal entity code can derive birth from the sanitized identifier prefix. Corporate codes 81–88, unknown codes 80/89, invalid business numbers and explicit corporate taxpayer evidence suppress birth. Corporate taxpayer evidence conflicting with a personal number fails `business_entity_consistent`.

`demo/backend/ocr/localocr.py:216` applies the final required-field guard after shared header safety. Its dedicated converter at line 274 preserves the existing Korean identity/date keys and renders lists as JSON strings. Text-layer and image body classification both route to this converter, independently of filename and expected slot. `demo/backend/ocr/__init__.py:83` reapplies the guard after common filtering.

`demo/backend/rules/doc_check.py:362` gates incomplete proofs and missing/mismatching applicant identity before other rules. Missing reference identity also yields NEEDS_REVIEW. Matching representative name and birth produce no identity warning. The existing wrong-slot type failure remains active. Internal address, industry and category data remain subject to the existing applicant whitelist.

Opening dates can follow issuance because pre-opening registration is permitted. This stage adds no employment inference. Registration and issuance chronology remain document-evidence checks. The source and decision are recorded in `business-plan.md`.

## Verification

- Added 131 tests, comprising 94 engine and 37 backend tests.
- The new engine/backend suites passed 131 tests. The latest combined targeted run including prior PR #27 NHIS/observed-form/portal upload coverage passed 277 tests.
- Actual image-PDF uploads cover eight normal joint/list combinations, corrupted/incomplete proofs, identity mismatch, corporate identifiers and conflicting taxpayer evidence. A normal text-layer proof uses the same field contract.
- Other cases cover two-to-four-character names, scaling/jitter/skew, thirteen missing required values, valid personal-code endpoints, corporate and unknown codes, labels/date ambiguity, one-to-ten participant rows, partial/conflicting joints, future opening metadata and post-filter stale completeness.
- Python compileall and git diff checking passed for the changed modules. Full engine/backend/scenario integration remains the parent task's final gate.

## Files

- Added `engine_v2/extractors/business_registration.py`, `engine_v2/tests/p2_business_samples.py`, `engine_v2/tests/test_business_registration.py` and `demo/backend/tests/test_p2_business_uploads.py`.
- Updated the engine registry/enum, LocalOcr dispatch/converter/guard, common OCR final guard call and the proof completeness/identity branch in `doc_check.py`.
- Updated this stage's research plan and outcome record. No model, training or employment scoring rule was changed.
