# Stage 6 payment review

Reviewed `0f3b652` using synthetic in-memory cells from `p2_payment_samples.payment`. This pass made no production edits. Findings below are reproduced through the reader and, where stated, adapter/demo verdict or scoring pipeline.

## Confirmed fixes required

### High priority — crossing metadata words are silently discarded

`engine_v2/extractors/nhis_payment_gov.py:57` selects first-cell words only when their entire box ends before the next label. Line 58 selects second-cell words only when they start after that label. A word overlapping the intervening label is therefore discarded even when it lies in the value row.

Add a fictitious high-confidence word `가상다름` with box `(1100,509,1250,560)` to the normal fixture. It overlaps the birth label boundary beside the name value. The current result remains `structure_complete=True`, confidence .95 and final PASS with matching identity. The same omission occurs for a money-shaped extra token in that box and for a number token crossing the payer label boundary.

Reject unaccounted non-label words that intersect a selected metadata cell/label boundary. Keep words wholly left of the first label outside the value region so authenticity-stamp artifacts remain irrelevant. Add actual upload coverage for crossing-name and crossing-number uncertainty.

### High priority — conflicting period is ignored when grouped with unit text

`nhis_payment_gov.py:227` counts only complete grouped rows matching PERIOD. Add a fictitious period shaped `YYYY년 MM월 ~ YYYY년 MM월 납부내역`, with a conflicting earlier year, at `(757,705,1310,746)`. It groups with the unit label at y700–750, so its row fails `PERIOD.fullmatch` and disappears from candidate counting. The original period remains authoritative and final verdict is PASS.

Count every period-shaped candidate in the bounded pre-table header, including candidates accompanied by unit text or malformed residual content. A second occurrence should retain ambiguity regardless of whether its value equals the first. Validate one candidate's full period grammar after this completeness check. Retain the known standalone unit annotation where it shares a row with the single genuine period.

### High priority — markerless legacy low-confidence amounts can cause income FAIL

`demo/backend/rules/facts.py:85` trusts payment amounts when explicit status and structure marker are absent. It ignores a supplied OCR confidence below the review threshold.

A concrete reproduction uses `payment_fact(high=True, damaged=True)` from `test_p2_payment_facts.py`, removes `status` and `양식판독상태`, and retains the resulting confidence .4 and extracted amounts. This models a legacy row without the new metadata. `build_facts` emits a monthly premium above the eligibility threshold. The engine pipeline returns stage 1 NEEDS_REVIEW, stage 2 `INCOME_OVER_THRESHOLD` FAIL and final FAIL. Keeping the incomplete marker suppresses the amount and yields review, demonstrating the missing trust condition.

When confidence is explicitly supplied, require it to meet the existing OCR threshold before financial fields can feed scoring. Missing-confidence legacy fact dictionaries should retain their existing supported contract. Explicit NEEDS_REVIEW handling already works and needs to stay intact.

### Medium priority — document-number residue is ignored

`nhis_payment_gov.py:221` accepts a regex substring inside the document-number row. Append fictitious Hangul residue to the merged `문서확인번호` plus valid-number token. The result remains complete and PASS because the valid substring is extracted while the unknown suffix is discarded.

Read the entire value suffix after the observed label, including separate value words, and require its full format. Scope rightward from the actual label so unrelated authenticity-stamp words to its left do not become value text. Preserve the supported four-four-four-four/five digit layouts.

## Other observed behavior

- Removing multiple outside-income header fragments routes the new shape to the legacy reader because `recognizes` requires three copies of each outside-income phrase. The tested variants still reach NEEDS_REVIEW through existing low field confidence. They can emit the legacy inferred `가입구분=직장` from an empty workplace label. This confirms the documented legacy limitation, with no reproduced final PASS from the supplied source variants. A stable coarse form signature could keep damaged twelve-month shapes on the dedicated review path while preserving the old three-month reader.
- The dedicated reader itself emits no insurance category. `facts.build_facts` retains its existing default to 직장 when qualification/payment omit it. The task design already documents this policy assumption.
- Duplicate/missing month labels, malformed amounts, an extra header word, missing sum and grand-total mismatch produce review. All eight columns retain arithmetic checks. Empty optional cells remain null values in the detailed table.
- Explicit NEEDS_REVIEW status, with or without a structure marker, suppresses payment money in facts and is carried into the generic engine by reduced conversion confidence. Complete matching payment fixtures retain scoring and pipeline PASS.

## Existing fixture-tier limitation for final reporting

`demo/backend/ocr/fixture.py:378` chooses predefined synthetic output solely by basename before reading file contents. `demo/backend/rules/doc_check.py:601` documents the fixture identity exemption. Newly added own-OCR readers use body/coordinates and their upload fixtures use names outside this mapping.

Binding fixed responses to actual file hashes would require a fixture manifest and changes to scenario preparations that intentionally exercise this tier. It is an existing demo architecture limitation and is recorded for final reporting, without introducing a global fixture migration into this reader task.

## Stage 9 resolution

The four confirmed findings are repaired. Metadata boundary-crossing words remain incomplete evidence. The pre-table period scan accounts for conflicting, duplicated and malformed period candidates even when unit text shares a grouped row. Document numbers require a complete typed value after their observed label. Explicit low confidence suppresses financial facts while absent-confidence legacy fact dictionaries retain their existing contract.

Further source review reproduced an existing legacy arithmetic gap. Failed monthly/paid sums could retain high confidence and PASS through the adapter. A shared critical-validation set now controls fresh conversion, financial trust and engine conversion. It also protects cached markerless rows whose old status/confidence still claim PASS. Read-time conversion preserves stored rows while carrying those known failures into review and withholding their financial values.

Header-only purpose or workplace text now fails the dedicated reader. A recognized payment's required-field guard runs again after common field safety, preserves an explicitly empty workplace, and updates stale completeness when a required value disappears. New direct, upload, cached-row and whole-pipeline tests cover these cases. Final counts and the P18 fixture corrections are recorded in `review/final.md`.
