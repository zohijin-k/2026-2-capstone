# Shape-derived follow-up verification — 2026-11-13

Status: **review — awaiting user verification**. Source checkpoint: `a8bac17`. No push, PR, archive, deployment or audit-document changes.

## Step 1 baseline and reproduction
Three strict-xfail acceptance tests reproduced every extractor-level failure recorded in the redacted observations. A read nine history rows but failed name consistency, page names, history cells, numbering and blank marker. B failed name consistency, household rows and subscriber/first-member matching. C failed form recognition, government document-number consistency, birth consistency and number format. The demo-only `성명_required` is added after extraction; the final backend tests verify this separate conversion check. Initial result: 3 xfailed, 0 unexpected failures. All three xfail marks have now been removed and the acceptance tests pass.

Evidence: `engine_v2/tests/test_observed_forms.py:12`, `demo/backend/tests/test_observed_forms.py:57`. Fixtures are newly authored fictitious values; the external shape file was read in place and never copied/staged. Its unavailable original values were not used.

## Causes and implementation evidence

| Area | Cause and correction | Evidence |
|---|---|---|
| Shared comparison | One-character labels require a comparison-only view, with spacing checks; original tokens remain intact. | `engine_v2/extractors/nhis_forms.py:116` |
| Shared columns | Centered header starts are not left edges of body cells. Boundaries come from persistent empty body corridors, mapped to ordered headers; ambiguous corridors fail closed. | `engine_v2/extractors/nhis_forms.py:140` |
| A identity | The side role label is between header/value baselines, and a centered name starts left of its label. Read unique horizontally overlapping values below the name/RRN labels, stopping at the next section. | `engine_v2/extractors/nhis_forms.py:52` |
| A history | Category/employer values start left of the printed header. Use body corridors, reserve observed date words and retain the existing long-employer continuation checks. Number sequence, neighbor dates and blank marker pass. | `engine_v2/extractors/nhis_acquisition_loss.py:244` |
| B members | The split name header and left-aligned member values were excluded by header-start slicing. Use observed columns and preserve Korean JSON keys, complete-list publication and first-member/subscriber validation. | `engine_v2/extractors/nhis_qualification.py:82` |
| B resolution | Pixel-bucket text ordering can shuffle separated glyphs after scaling/jitter. Compare normalized coordinate lines instead. | `engine_v2/extractors/nhis_qualification.py:130` |
| C form/header | The observed output/purpose labels fall outside the old fixed height bands. Recognize relative grid/identity labels and scope issue-date parsing to the observed grid row. This activates existing portal-only 14-digit number handling and excludes government document-number checks. | `engine_v2/extractors/insurance_4.py:114`, `engine_v2/extractors/insurance_4.py:183`, `engine_v2/extractors/insurance_4.py:420` |
| C row dates | Acquisition is above the insurance-label baseline and receipt is below it. Use row-spacing bands and keep separate date occurrences in the date column. | `engine_v2/extractors/insurance_4.py:307` |
| Resident titles | The large main title and separated subtype glyphs are interrupted by right-side notices in reading order; the opening parenthesis may be absent. After legacy classification fails, use large upper-page main-title/subtype coordinates and reject missing/conflicting evidence. | `engine_v2/pipeline/resident_title.py:10`, `demo/backend/ocr/pdftext.py:117` |
| Resident routing | Both image LocalOcr and previously unclassified text PDFs use the same fallback and retain `ra.extract` for fields; classification alone cannot promote incomplete fields to PASS. | `demo/backend/ocr/localocr.py:531`, `demo/backend/ocr/localocr.py:578`, `engine_v2/extractors/resident_abstract.py:352` |

## Final verification

| Suite | Previous | Final passed | Skipped | Failed | Added |
|---|---:|---:|---:|---:|---:|
| engine_v2 pytest | 366 passed / 3 skipped | 499 | 3 | 0 | 133 |
| demo/backend pytest | 61 passed | 139 | 0 | 0 | 78 |
| Existing standalone scenarios | 1,796 reported passes | 1,796 | 0 | 0 | 0 |

New tests total **211**. All 18 scenario modules exited 0. The reported numeric sum comes from 17 modules; P14 separately confirms all 8 form templates. P2 remains 53 passed / 0 failed. Initial full-scope review found four existing regressions; all were fixed in production code, without deleting or weakening existing tests: merged parenthesized name, split text-layer portal section labels/header scoping, and long employer overprinting a date column. A late cleanup removed a still-used local text variable and caused three backend failures; the variable was restored before the final full-backend run. Final failures are zero.

Coverage includes names of 2–4 characters; per-word 2pt jitter; changed workplace lengths and row counts; portal header shifts; increased raster resolution; A/B blank/header-only names; C missing birth/number/header/rows; B subscriber, paired household member, unpaired member and absent applicant; title parenthesis damage, abstract/register discrimination, conflicting subtypes, notices without titles, small/lower-page titles and the prior title shape. Complete A/B/C identity matches produce PASS without findings; incomplete fields/structure produce NEEDS_REVIEW without FAIL.

Evidence: `engine_v2/tests/test_observed_forms.py:25`, `engine_v2/tests/test_observed_forms.py:47`, `engine_v2/tests/test_observed_forms.py:74`, `engine_v2/tests/test_resident_title.py:12`, `demo/backend/tests/test_observed_forms.py:36`, `demo/backend/tests/test_observed_forms.py:75`, `demo/backend/tests/test_resident_title.py:15`. Existing government24, payment, upload and scenario tests remain intact. Added label helpers are form-scoped; the legacy common label matcher is unchanged.

Commands and local logs:
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest engine_v2/tests -q --tb=short` → `/tmp/shape-engine-final.txt`
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest demo/backend/tests -q --tb=short` → `/tmp/shape-backend-final.txt`
- Existing `demo.backend.tests.run_p*_scenarios` modules in independent subprocesses → `/tmp/shape-scenarios-final.json`
- Changed Python AST parsing and `git diff --check`: passed. No configured Python lint/type-check command was found in the package/spec context.

## Remaining assumptions and boundaries
Actual OCR accuracy and unobserved layout/font variants remain **unverified (추정)**. Word-box fixtures verify geometry and routing, not recognition quality. Resident LocalOcr routing tests mock captured word boxes; they do not demonstrate model inference on the user's PDFs. The prior abstract's recorded `history_numbers_sequential` failure remains outside this title-classification task; its cause is **unverified (추정)**, and the existing validation at `engine_v2/extractors/resident_abstract.py:442` is unchanged. New A/B/C multi-page forms still require review. Ambiguous table corridors or damaged required values still require review. Existing deprecation warnings from PyMuPDF/fitz/Starlette dependencies remain outside scope.

## Commit sequence
1. `0bafbb4` — freeze shape-derived A/B/C failures.
2. `84b6cfc` — comparison-only labels and body-gap columns.
3. `5e223cb` — A identity/history.
4. `368d93b` — B household table.
5. `e611f57` — C relative form/grid and dates.
6. `11f2193` — resident title fallback and routing.
7. `a8bac17` — final verdict/geometry tests, legacy regressions and spec update.
8. Final task documentation commit — review status, this evidence and remaining assumptions.

Git boundary: branch `feat/acq-loss-nhis-form`; the pre-existing untracked `docs/audit/` remains excluded. No real document data or external shape file was staged.
