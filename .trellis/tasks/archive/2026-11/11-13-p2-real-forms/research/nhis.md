# NHIS own-OCR variants research

## Evidence boundary

This investigation reads the redacted shape sources and source code. Values remain fictitious in experiments. The shape file preserves token boxes, confidence, character classes and selected labels. It cannot establish the original contents of a placeholder-only issuer token, original dates, or the original character represented by `A`. Conclusions that require those contents are marked inference.

## Qualification validation classification

| Failed validation | Category | Shape evidence | Code mechanism and action |
| --- | --- | --- | --- |
| `nhis_issue_location_unique` | (가), inferred issuer-label omission or stamp interference | `/tmp/layout_shape2.txt:172` confirmation at (292,2635,1159,2689), `:173` date at (1114,2726,1375,2789), `:175` issuer at (764,2855,1643,2950) has eight Hangul plus two Hangul. Adjacent stamp words `:174` and `:176` have confidence .33/.35. Exact issuer characters remain unknown. | `engine_v2/extractors/nhis_forms.py:23` requires both `국민건강보험공단` and `이사장` on one grouped row. Replacing the two-character role with fictitious `이사` in the same boxes reproduces failure. Restoring `이사장` passes. This is a reproduction of a plausible mechanism, with actual missing character still inference. Select a unique issuing-organization block below confirmation and above validity, using position and observed organization text, while retaining ambiguous-date rejection. |
| `발급일_consistent` | (라), propagated missing issue value | Same bounded date at source `:173`. | `engine_v2/extractors/nhis_qualification.py:152` passes the helper result to the required field check at `:157`. Fix the source selection. |
| `발급일_required` | (라), propagated missing issue value | Same bounded date at source `:173`. | Added by the adapter required-field guard at `demo/backend/ocr/localocr.py`, after extractor conversion. Keep this guard. |
| `nhis_blank_marker` | (다) | Marker at source `:168`, (977,1596,1159,1655), has no recognized dash words. Trailing fragments `:169`–`:171` occur at y1976–2186, confidence .10–.39. | `engine_v2/extractors/nhis_qualification.py:96` returns before marker analysis when body-only column discovery fails. Additionally `:111` rejects every trailing Hangul/digit, including artifacts in distant empty rows. Bound the geometry to the marker. Recognize marker-only rows and preserve checks against plausible table data hidden beside or immediately after the marker. |
| `household_rows_read` | (다), with (나) artifact grouping | The one genuine member occupies source `:165`–`:167`, y1481–1547. Its loss and suspension cells are empty. Source `:164` adds a tiny confidence .18 digit at (797,1480,827,1507), outside the real identity/date cells. Header loss/suspension cells exist at `:161` and `:163`. | `engine_v2/extractors/nhis_forms.py:165` discovers gaps only between occupied body intervals. With two entirely empty rightmost columns, a required corridor does not exist, causing `table_columns` to return `None`. The row loop at `nhis_qualification.py:113` also treats every grouped artifact row as a member. Use observed ordered headers plus persistent whitespace and row anchors. Only discount noise with measured geometry/confidence evidence. |
| `subscriber_matches_first_member` | (라), propagated no member rows | Subscriber source `:152`–`:153` and member `:165`–`:167` have matching placeholder shape, with actual equality established by user description only. | `engine_v2/extractors/nhis_qualification.py:181` requires an extracted first member. A failed column grid returns an empty list at `:98`. Preserve the equality check after row extraction is repaired. |

Empty `사업장관리번호` is already ignored by qualification extraction and contributes no existing validation. It should remain optional metadata. The current issue helper searches only between confirmation and issuer. Identical request/expiry dates elsewhere cannot explain its uniqueness failure. Source `:144` request date and `:177` validity date are outside that interval. Add a regression that repeats the issue date in both places.

## Acquisition-loss validation classification

| Failed validation | Category | Shape evidence | Code mechanism and action |
| --- | --- | --- | --- |
| `nhis_history_cells_read` | (다), with (나) watermark grouping | Three genuine rows span source `:206`–`:217`, y1111–1427. Employer cells are empty under source `:202`, (966,978,1226,1044). A tall confidence .64 `.AA` token at source `:209`, (845,1201,1105,1420), overlaps row bands. Distant artifacts `:219`–`:222` also enter body geometry. | `engine_v2/extractors/nhis_acquisition_loss.py:264` includes all words before confirmation in corridor discovery. `nhis_forms.table_columns` requires one occupied-body corridor per adjacent header and cannot recognize an entirely empty employer column reliably. Marker and watermark intervals also bridge candidate whitespace. Derive the geometry from bounded genuine row bands and ordered headers, retaining employer continuation safety checks. |
| `nhis_row_numbers_continuous` | (라), propagated missing rows | Source `:207`, `:211`, `:214` each contains a high-confidence single-digit row-number shape. Actual original numbers remain unavailable. | If column discovery returns `None`, the branch at `nhis_acquisition_loss.py:275` skips all rows, so the nonempty continuity check at `:336` fails. Preserve sequence validation after extracting the observed three rows. A separate numeric-recognition error would remain reviewable. |
| `nhis_current_loss_blank` | (라), propagated missing rows | First row has only acquired date source `:208` and no loss-date token. | The check at `nhis_acquisition_loss.py:338` requires nonempty rows, so failed geometry also produces this failure. Keep current-row blank-loss validation. |
| `nhis_neighbor_dates_continuous` | (다), plus propagated empty rows | Lower loss dates at source `:213` and `:217`, x2048–2263. Their relation to upper acquired dates cannot be proved from numeric placeholders. The user explicitly identifies coverage gaps. | `nhis_acquisition_loss.py:339` requires exact equality. Change the inequality to lower loss <= upper acquired and require both relevant dates. Lower loss > upper acquired remains structural uncertainty. |
| `nhis_blank_marker` | (다) | Source `:218`, (646,1489,831,1554), contains a marker-only OCR token. Below it, source `:219`–`:222` contains distant watermark fragments at y2033–2339. | `nhis_acquisition_loss.py:289` requires more than one token on the marker line, so a marker without recognized dashes fails. `:297` turns every subsequent nonempty line into a structural failure. Support absent/arbitrary separator punctuation and distinguish bounded row evidence from distant watermark artifacts. |
| `history_dates_read` | (라), propagated empty rows | All five expected date tokens in the genuine rows have confidence 1.0 at source `:208`, `:212`, `:213`, `:216`, `:217`. | Nonempty/all-acquired check at `nhis_acquisition_loss.py:440` fails after grid failure skips rows. Date correctness cannot be proved from the placeholder values, so synthetic valid and invalid dates must cover the final parser. |
| `recent_five_years_covered` | (라), propagated empty rows | Three row dates exist, but original date values are redacted. | `nhis_acquisition_loss.py:465` calls the existing helper with empty rows after geometry failure. Whether the real date values satisfy the five-year rule remains inference. Preserve the helper's existing semantics and test coverage with gaps. |

The full RRN shape at source `:199`, (1579,725,1929,778), is already parseable by `nhis_common.RRN_RE`. After the privacy stage it must match `MASKED_RRN_RE` and yield the same birth. No identity extraction heuristic should retain the final six digits.

## Five-year meaning and government24 impact

`engine_v2/extractors/nhis_acquisition_loss.py:353` defines `history_covers_recent_years` as follows.

- With a printed query period, require its start <= issue minus five years and end >= issue.
- Without a printed period, accept one row spanning the cutoff through the issue date.
- Otherwise accept any loss date strictly earlier than the cutoff, which establishes a history listing extending beyond the requested lookback.

It does not require continuous insurance coverage and does not sum insured days. Valid gaps therefore do not require changing this function. Its current old-loss semantics are tested in `engine_v2/tests/test_nhis_history_consistency.py:8`. The adapter serializes its boolean result in `demo/backend/ocr/localocr.py:250`. The demo checker reuses the same helper for legacy data at `demo/backend/rules/doc_check.py:526`.

Government24 `_parse_history` at `nhis_acquisition_loss.py:129` checks dates within a row through `acquisition_before_loss` at `:441`. It currently has no adjacent-row continuity validation. The NHIS adjacent-row correction therefore has no matching government24 validation to alter.

## Shared helper design

1. Keep comparison-only spaced-label reconstruction. Existing normalized grouping already recognizes most labels. Extend row/anchor scope around tall low-confidence glyphs without altering original values or the text-layer path.
2. Locate exactly one marker using comparison text before measuring the body. Use header height and median genuine row pitch to bound the table. Marker-adjacent plausible rows remain disqualifying. Distant fragments in empty rows can be excluded only with observed geometry/noise evidence.
3. Build column boundaries from both ordered header extents and bounded body whitespace. If an optional column is entirely empty, its observed header establishes its existence and interior position. Keep required-header checks and reject a token that crosses a supported boundary. Never insert a missing header or guess a value.
4. Accept a sole `이하여백` marker in its correct column. Additional separator characters may be punctuation variants. Any neighboring name, RRN, category, row number or date still signals incompleteness.
5. Find the issue date only below the confirmation and above the observed closing organization. Require exactly one valid date-only candidate in that region. Keep malformed and duplicate physical date candidates as failures. An identical value in request/validity positions is irrelevant to issue-date uniqueness.

## Regression conflict requiring fixture repair

`engine_v2/tests/test_nhis_nhis_form.py:59` labels a fake lower-row loss in the year before the upper acquisition as an invalid `neighbor`. The requested gap rule makes that fixture valid. Preserve its invalid-neighbor intent by moving that fake lower loss after the upper acquisition, then add a new explicit gap-acceptance test. This is a necessary fixture correction for the requested behavior and must be disclosed. Existing ambiguity, marker-hiding and missing-header tests retain their assertions.

## Experiments

A read-only shape parser built OcrWord lists in memory with fictitious names, dates and identifiers. Both observed layouts return `None` from current `table_columns`, even when the body is cut before the marker. The qualification reproduction emits the exact five extractor failures listed in the source. The sixth `발급일_required` is the adapter guard. A shortened two-character issuer role reproduces issue-date failure, and a full issuer role passes in the same coordinates. The actual issuer omission remains inference because the source masks its contents.
