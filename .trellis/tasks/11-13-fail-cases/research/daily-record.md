# Daily-work record reader research

## Observed masked shape

The read-only structure evidence describes two insurance copies, each consisting of a table page followed by a confirmation page. The table title is around y=6–11%; the issue-number / issue-date / receipt-number row is around y=13%; the applicant name and birth row is around y=16–18%; the query-period value spans two adjacent words around y=19–20%, above its label baseline. The body header spans two short baselines around y=25–27%. Monthly rows use a month/ordinal baseline, while the comma-separated day cell can wrap both above and below that baseline. The second page has notice text and a dated issuing confirmation, with an organization/role footer; it is not an empty attachment.

Only label words and geometric relationships are used. Values in tests remain overtly fictitious. This source shape does not prove the exact checkbox glyph, blank-table terminator or all possible pagination variants; unsupported variants must remain reviewable.

## Existing integration points

- `engine_v2/schemas/models.py:30`: add DAILY_WORK_RECORD enum, value `daily_work_record`.
- `engine_v2/engine.py:40`: register dedicated extract function.
- `demo/backend/ocr/pdftext.py:35`: current keyword `일용근로내역` misses the combined `일용근로·노무제공내역서` title. Add body-title aliases; coordinate `recognizes(pages)` can handle justified title splits.
- `demo/backend/ocr/localocr.py`: text-PDF and image routes should select dedicated daily extractor and common converter; expected slot must remain unused.
- `engine_v2/extractors/nhis_common.py:307`: shared `make_field` preserves source bounds and OCR/text-layer provenance.
- `engine_v2/extractors/nhis_forms.py:184`: label matching recognizes split labels without concatenating values.
- `engine_v2/extractors/nhis_forms.py:205`: column boundaries should derive from persistent observed whitespace; short day/count and currency tokens must remain part of their full cells.
- `engine_v2/tests/fail_case_samples.py:24`: authored fixture already models wrapped day lists and two-page insurance copies; it should gain explicit unselected insurance label and the same physical title/identity/period bands.

## Proposed extraction contract

`extract(pages, today=None) -> DailyWorkResult`: detected_type / type_confidence / fields / validations / warnings / form_kind=`comwel_daily_work` / structure_complete. Proposed top-level field strings are `발급번호`, `발급일`, `성명`, `생년월일`, `보험구분`, `조회기간`, `일용근로내역자료`. JSON values are serialized by the reader, preserving the existing demo string-valued field contract.

`일용근로내역자료` JSON: `{period: [YYYY-MM, YYYY-MM], rows: [{month, workplace, work_dates: [int], days: int, wage: int, remuneration: int, worker_category}], insurance_types: [산재, 고용], copies_consistent: bool}`. Duplicate copies produce one canonical row list only after full normalized equality, including workplace/day-list/day-count/amount/category and applicant/period/issue metadata. Receipt number is not a requested output and must not be confused with issue number. Each insurance copy may have a different document issue number; its observed number remains validated and listed rather than used as a duplicate-row equality key.

## Conservative parsing

1. Normalize page coordinates, not filenames or expected slots. Require upper title plus independently observed table headers for structural certainty.
2. Partition copy starts using repeated body title/table-header pages. A title/table page owns following confirmation pages until the next repeated title. Unassigned or extra table-like pages invalidate completeness.
3. Scope issue number/date to the labeled metadata row; do not borrow the receipt-number cell. Scope name/birth to their labeled header cells. Accept only one fully parsed date/value per cell; conflicting/malformed fragments fail structure.
4. Query-period label can be vertically offset from its value. Bound search above/beside the label and before body headers, then require one complete range and valid chronological month endpoints. Unknown/split malformed periods remain review.
5. Require an explicit checked insurance mark associated geometrically with exactly one insurance label in the upper title band. Mere occurrence of insurance words is insufficient to determine which copy it is.
6. Observe complete ordered headers for ordinal, work month, workplace, work dates, work-day count, wage, remuneration and worker category. Header split words are label views only. Use observed vertical whitespace to allocate cells and reject crossed/ambiguous boundaries.
7. Anchor row bands with an ordinal and canonical YYYY/MM cell. Midpoints between adjacent anchors include the two-line date cell without swallowing the next record. Every row-band word must allocate to one column. Unassigned apparent row tokens, skipped ordinals and incomplete last rows invalidate structure.
8. Full-match day-list grammar, bounds to days in that calendar month, no duplicates, count equals unique listed dates, positive integral work-day count. Full-match monetary grammar, optional currency suffix, no guessed OCR substitutions. Preserve `worker_category` without inferring weekly hours.
9. A table closes through an explicit observed terminator or a valid dated confirmation sequence, not merely end of OCR words. Each copy's confirmation date must corroborate the labeled issue date. Missing/sparse confirmation remains review.
10. Keep partial fields/rows for officer inspection but cap all fields at .4 when any required validation fails. Only complete, internally consistent evidence may establish negative work continuity downstream.

## Tests to implement after authorization gate

Font/model-independent text/OCR coordinate paths, scaling and jitter; split headers and wrapped day lists; duplicate insurance copies deduplicate; single-copy path; missing/wrong checkbox; missing/unreadable metadata; period omission/conflict; malformed/duplicate/out-of-month dates; count mismatch; missing or crossing column; skipped ordinal/orphan body tokens; missing/corrupt confirmation; duplicate copy row/name/birth/period conflict; arbitrary filenames and expected slots through real text-layer upload. A fake period with monthly gaps should parse completely, then be rejected only by the separate provisional continuity assessor.

## Implemented reader and verification

The agreed contract is implemented in `engine_v2/extractors/daily_work_record.py`. The parser additionally preserves a two-digit printed birth in `생년월일표기` and lists valid century candidates in `생년월일후보`; it never chooses a century. Only an explicit four-digit source produces canonical `생년월일`. The eligibility consumer must match the verified applicant birth to a candidate before any negative decision.

The source shape has no textual insurance checkbox glyph. Unknown graphic marks are recorded as `보험구분=[미확인]` and a warning, while table/period/identity validations remain independently usable. This is necessary because the supplied structure cannot prove which graphical box was checked. Explicit checkbox text, when present, determines the copy's observed insurance label; repeated known labels invalidate duplicate-copy structure. The parent accepted this boundary.

Column discovery reserves only observed amount-plus-currency/day-count-plus-unit geometric intervals; original tokens still determine values, confidence and evidence. This prevents a printed number/unit gap from becoming a false table boundary. Full-word column allocation still rejects crossing cells.

Verification: 30 new focused tests pass, including synthetic text/OCR coordinates at three scales, actual four-page fictitious text PDF through `_load_pages` without OCR, two-digit birth, missing graphic checkbox, copy conflicts and nineteen structural defects. Combined engine/portal/sample subset: 79 passed. No prior test expectation was changed, no source file copied, no private document accessed.
