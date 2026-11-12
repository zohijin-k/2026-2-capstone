# Design

## Authorization and boundary

The user explicitly authorized task creation, planning followed by implementation, and ordered commits. Main was fetched and equals `5d0833d`. Existing untracked `docs/audit/` predates this work and is excluded from all commits.

The smallest behavior gaps are unredacted coordinate/text ingestion, OCR tokenization assumptions in existing readers, rejected valid NHIS variations, and an absent business-proof reader. Extend the existing ingestion/reader/adapter boundaries and preserve result field contracts. Trellis workflow explicitly requests implement/check delegation. Subagents receive this task's specifications and bounded file ownership.

## Ordered implementation

1. Central resident-number sanitizer reused at every textual ingress and serialization safety boundary. Date-valid six digits and sex digit 1–8 identify a candidate. Preserve coordinates and word segmentation while redacting same-line split words.
2. Classify each observed failed validation using shape and coordinates. Shape placeholders cannot establish the original misrecognized character, date values or checksums, so those conclusions remain inference.
3. Extend shared coordinate helpers only where OCR forms require it, retaining strict ambiguity checks.
4. Acquisition history accepts gaps and rejects overlaps. Preserve the existing five-year meaning.
5. Qualification scopes the issue date between confirmation and issuer and reads one member with empty management cells.
6. Payment preserves `billed_by_month` and other existing contracts, reads eight observed columns and retains empty cells. Correct only documented numeric lookalikes, then verify sums.
7. Dedicated business-proof reader returns existing fields used by identity/slot logic plus requested internal fields, checksum and completeness checks.
8. Resident history investigation determines whether numbering failure indicates missing input or a false alarm and connects actual uncertainty to review.
9. Full engine/backend/scenario regression and cross-layer review.
10. Record final outcomes and set status to review.

## Failure classification

The following tables record every supplied failure. Category (가) means character recognition, (나) token/line segmentation, (다) a rule rejecting a normal variation, and (라) a propagated or other failure. Exact original glyphs and date values remain inference (추정) because the sources replace them with shape characters.

### Qualification

| Failed validation | Category | Shape evidence | Code mechanism and action |
| --- | --- | --- | --- |
| `nhis_issue_location_unique` | (가), inferred issuer-label omission or stamp interference | `/tmp/layout_shape2.txt:172` confirmation at (292,2635,1159,2689), `:173` date at (1114,2726,1375,2789), `:175` issuer at (764,2855,1643,2950) has eight Hangul plus two Hangul. Adjacent stamp words `:174` and `:176` have confidence .33/.35. Exact issuer characters remain unknown. | `engine_v2/extractors/nhis_forms.py:23` requires both `국민건강보험공단` and `이사장` on one grouped row. Replacing the two-character role with fictitious `이사` in the same boxes reproduces failure. Restoring `이사장` passes. This is a reproduction of a plausible mechanism, with actual missing character still inference. Select a unique issuing-organization block below confirmation and above validity, using position and observed organization text, while retaining ambiguous-date rejection. |
| `발급일_consistent` | (라), propagated missing issue value | Same bounded date at source `:173`. | `engine_v2/extractors/nhis_qualification.py:152` passes the helper result to the required field check at `:157`. Fix the source selection. |
| `발급일_required` | (라), propagated missing issue value | Same bounded date at source `:173`. | Added by the adapter required-field guard at `demo/backend/ocr/localocr.py`, after extractor conversion. Keep this guard. |
| `nhis_blank_marker` | (다) | Marker at source `:168`, (977,1596,1159,1655), has no recognized dash words. Trailing fragments `:169`–`:171` occur at y1976–2186, confidence .10–.39. | `engine_v2/extractors/nhis_qualification.py:96` returns before marker analysis when body-only column discovery fails. Additionally `:111` rejects every trailing Hangul/digit, including artifacts in distant empty rows. Bound the geometry to the marker. Recognize marker-only rows and preserve checks against plausible table data hidden beside or immediately after the marker. |
| `household_rows_read` | (다), with (나) artifact grouping | The one genuine member occupies source `:165`–`:167`, y1481–1547. Its loss and suspension cells are empty. Source `:164` adds a tiny confidence .18 digit at (797,1480,827,1507), outside the real identity/date cells. Header loss/suspension cells exist at `:161` and `:163`. | `engine_v2/extractors/nhis_forms.py:165` discovers gaps only between occupied body intervals. With two entirely empty rightmost columns, a required corridor does not exist, causing `table_columns` to return `None`. The row loop at `nhis_qualification.py:113` also treats every grouped artifact row as a member. Use observed ordered headers plus persistent whitespace and row anchors. Only discount noise with measured geometry/confidence evidence. |
| `subscriber_matches_first_member` | (라), propagated no member rows | Subscriber source `:152`–`:153` and member `:165`–`:167` have matching placeholder shape, with actual equality established by user description only. | `engine_v2/extractors/nhis_qualification.py:181` requires an extracted first member. A failed column grid returns an empty list at `:98`. Preserve the equality check after row extraction is repaired. |

### Acquisition-loss

| Failed validation | Category | Shape evidence | Code mechanism and action |
| --- | --- | --- | --- |
| `nhis_history_cells_read` | (다), with (나) watermark grouping | Three genuine rows span source `:206`–`:217`, y1111–1427. Employer cells are empty under source `:202`, (966,978,1226,1044). A tall confidence .64 `.AA` token at source `:209`, (845,1201,1105,1420), overlaps row bands. Distant artifacts `:219`–`:222` also enter body geometry. | `engine_v2/extractors/nhis_acquisition_loss.py:264` includes all words before confirmation in corridor discovery. `nhis_forms.table_columns` requires one occupied-body corridor per adjacent header and cannot recognize an entirely empty employer column reliably. Marker and watermark intervals also bridge candidate whitespace. Derive the geometry from bounded genuine row bands and ordered headers, retaining employer continuation safety checks. |
| `nhis_row_numbers_continuous` | (라), propagated missing rows | Source `:207`, `:211`, `:214` each contains a high-confidence single-digit row-number shape. Actual original numbers remain unavailable. | If column discovery returns `None`, the branch at `nhis_acquisition_loss.py:275` skips all rows, so the nonempty continuity check at `:336` fails. Preserve sequence validation after extracting the observed three rows. A separate numeric-recognition error would remain reviewable. |
| `nhis_current_loss_blank` | (라), propagated missing rows | First row has only acquired date source `:208` and no loss-date token. | The check at `nhis_acquisition_loss.py:338` requires nonempty rows, so failed geometry also produces this failure. Keep current-row blank-loss validation. |
| `nhis_neighbor_dates_continuous` | (다), plus propagated empty rows | Lower loss dates at source `:213` and `:217`, x2048–2263. Their relation to upper acquired dates cannot be proved from numeric placeholders. The user explicitly identifies coverage gaps. | `nhis_acquisition_loss.py:339` requires exact equality. Change the inequality to lower loss <= upper acquired and require both relevant dates. Lower loss > upper acquired remains structural uncertainty. |
| `nhis_blank_marker` | (다) | Source `:218`, (646,1489,831,1554), contains a marker-only OCR token. Below it, source `:219`–`:222` contains distant watermark fragments at y2033–2339. | `nhis_acquisition_loss.py:289` requires more than one token on the marker line, so a marker without recognized dashes fails. `:297` turns every subsequent nonempty line into a structural failure. Support absent/arbitrary separator punctuation and distinguish bounded row evidence from distant watermark artifacts. |
| `history_dates_read` | (라), propagated empty rows | All five expected date tokens in the genuine rows have confidence 1.0 at source `:208`, `:212`, `:213`, `:216`, `:217`. | Nonempty/all-acquired check at `nhis_acquisition_loss.py:440` fails after grid failure skips rows. Date correctness cannot be proved from the placeholder values, so synthetic valid and invalid dates must cover the final parser. |
| `recent_five_years_covered` | (라), propagated empty rows | Three row dates exist, but original date values are redacted. | `nhis_acquisition_loss.py:465` calls the existing helper with empty rows after geometry failure. Whether the real date values satisfy the five-year rule remains inference. Preserve the helper's existing semantics and test coverage with gaps. |

### Payment

| Validation | Category | Shape evidence | Source cause |
| --- | --- | --- | --- |
| `monthly_amounts_numeric` | (가), plus (다) unsafe cell-selection assumption | `/tmp/layout_shape2.txt:45`–`:89` has twelve one-digit or two-digit month labels with alphabetic `A` in mandatory money cells. Examples are x391–421 y962–1011 at .49, x1195–1231 y961–1013 at .50, x592–621 y1375–1421 at .38. Nonzero-looking late rows have valid digit/comma shapes at lines 90–104. | `nhis_payment.py:58` accepts only decimal money. Lines 257–260 record missing numeric rows. Lines 273–293 choose the nearest numeric amount among the whole row, so a neighboring valid cell can become a missing column's value. Boundaries and whole-cell validation are needed before correction. |
| `monthly_total_matches` | (가) cascading to arithmetic verification, with (다) grouped-header selection | Sum row has health/care amounts at x332–478 and x546–669, y1726–1780, source lines 105–109. Group header `고지금액` is centered x640–778, source line 22. Empty optional body columns span header centers around x809 and x1010, source lines 24–42. | `nhis_payment.py:221` uses distance to the whole group header when choosing the sum cell. That can select the care total, while body rows use the health subheader at line 273. Lines 461–466 then compare mismatched/incomplete sums. Original numeric mismatch remains inference. |
| `paid_total_matches` | (가) cascading to arithmetic verification, with (다) missing eight-column contract | Paid health/care group spans x1141–1284 and x1352–1476, source lines 107/109. `납부총액` has a separate bottom amount x738–879 y1799–1848, source lines 110–113. | `nhis_payment.py:225` selects the total nearest the whole paid-group header. Lines 274–280 use the same whole-group center for paid body values. Lines 468–474 compare this chosen component against chosen totals. The separate `납부총액` amount is unreachable because line 228 stops on `합계`. |

### Business registration proof

| Failure | Category | Shape and source evidence | Action |
| --- | --- | --- | --- |
| No dedicated extraction validations, confidence .8 | (라) | `/tmp/layout_shape2.txt:243` title, `:251`–`:277` labeled rows, `:280` final date. Engine registry lacks a business-proof entry and `LocalOcr._generic` caps unvalidated OCR at .8. | Add the dedicated reader and validate complete identity, checksum and required rows before confidence can exceed the review threshold. |

Qualification issue-date selection already excludes request and expiry positions. Duplicate values outside the issuing block are harmless. The shortened issuer-role hypothesis remains inference. Details and executable synthetic reproductions are in `research/nhis.md` and `research/payment-resident.md`.

## Privacy inventory and stage 1 result

## Applied boundaries

There are 29 explicitly sanitized function boundaries. Several routes share constructors, so this count measures function sites rather than independent implementations.

| # | Boundary | Evidence |
| --- | --- | --- |
| 1 | Every complete coordinate word, including text-layer words | `engine_v2/pipeline/ocr/__init__.py:30` |
| 2 | Coordinate OCR result, split words and error text | `engine_v2/pipeline/ocr/__init__.py:41` |
| 3–5 | Apple Vision, EasyOCR and Paddle direct adapter returns | `engine_v2/pipeline/ocr/__init__.py:82`, `:99`, `:141` |
| 6 | Own OCR direct recognition return | `engine_v2/pipeline/ocr/own.py:136` |
| 7 | PDF text before retention in PageImage.text | `engine_v2/pipeline/preprocess.py:89` |
| 8–10 | PdfText pure parser, PDF raw read and merged-page reader | `demo/backend/ocr/pdftext.py:235`, `:344`, `:438` |
| 11–12 | LocalOcr text-layer existence and notification-routing reads | `demo/backend/ocr/localocr.py:470`, `:511` |
| 13–15 | External OCR response plus HTML-cell and OTSL-value parsing | `engine_v2/pipeline/jbai_ocr.py:549`, `:178`, `:232` |
| 16–17 | Demo result construction and fallback exceptions | `demo/backend/ocr/base.py:80`, `:97` |
| 18 | Common OCR-chain return after field/filter mutations | `demo/backend/ocr/__init__.py:84` |
| 19–21 | OCR JSON serialization, initial findings persistence and NHIS recheck findings persistence | `demo/backend/api/documents.py:197`, `:241`, `:306` |
| 22–24 | Applicant JSON, engine fact projection and officer OCR projection, including legacy rows | `demo/backend/api/common.py:184`, `:234`, `demo/backend/api/officer.py:657` |
| 25–26 | Review score/tiebreak/payload persistence and recomputed household review payload | `demo/backend/api/review.py:578`, `:627` |
| 27–29 | Officer eligibility, exclusions and detail projections of historical score/payload JSON | `demo/backend/api/officer.py:694`, `:787`, `:854` |

`engine_v2/engine.py:184` creates OcrWord objects for text-layer values and then OcrResult at line 189, thereby applying boundaries 1–2 before extraction. Existing job and insurance scrubbing accepts the earlier masked prefix, preserving birth fallback and complete source-token disposal at `engine_v2/extractors/job_common.py:35` and `engine_v2/extractors/insurance_4.py:25`. NHIS masked-prefix parsing also accepts compact/spaced forms at `engine_v2/extractors/nhis_common.py:21`.

## Sink inventory

| Sink | Stored or emitted material | Redaction coverage |
| --- | --- | --- |
| OCR words/result repr and dataclass serialization | Word text, error, confidence and geometry | Boundaries 1–6, asserted by new tests |
| PDF PageImage.text | Raw textual page body retained in memory | Boundary 7, asserted before `_load_pages` |
| ExtractedField.value/raw_text, validation detail, warning and rule evidence | Derived from OCR/PdfText/JBAI inputs | Inherits sanitized ingestion. Acquisition extraction repr is asserted |
| External JBAI page objects/cache | text_lines, HTML/OTSL cells, raw_content, table_content | Boundaries 13–15 precede JBAIPageResult and cache retention. Inline tags/entities have regressions |
| Demo Document.ocr_json | Fields, classification evidence, fallback reasons and quality notes | Boundaries 16, 18 and 19 |
| Demo Document.findings_json | Initial and recomputed findings | Boundaries 20–21 |
| Review.review_payload_json, score_json and tiebreak_json | OCR-derived rule evidence and review/score notes | Boundaries 25–26, sourced from sanitized `common.document_fact`; historical payload/score response protection at boundaries 27–29. `demo/backend/models.py:158` defines the persisted payload |
| Applicant and officer responses | Visible fields, findings, internal OCR metadata | Boundaries 22–24 also protect historical rows when read |
| LocalOcr warning log | Engine availability reason | Fixed operational reason at `demo/backend/ocr/localocr.py:482`, no OCR body |
| JBAI logs | Engine, status, page count and elapsed milliseconds | Fixed allowlist at `demo/backend/ocr/jbai.py:248`, `:260`, `:270`, `:273`, `:280` |
| run_engine JSON/output | Applicant view, warnings, full model result JSON | Sanitized ingestion and retained source fields at `engine_v2/tools/run_engine.py:54`, `:62`, `:67` |
| inspect_pdf output and word JSON | Full-value masking, metadata counts and geometry | Existing `mask_text` masks every value in `engine_v2/tools/inspect_pdf.py:125`, `:137`, `:139`, with no raw OCR dump |
| extract_diag JSON | Default masked fields/words, safe issue metadata | Existing allowlisted projections at `engine_v2/tools/extract_diag.py:95`, `:126`, `:250`; internally generated synthetic unmask mode still receives redacted resident suffixes |
| private_bench/ocr_bench JSON and logs | Metrics, fixed keys and status/count values | Existing `quiet_dependencies` and allowlists at `engine_v2/tools/private_bench.py:193`, `:228`, `:231`, checked only with fictitious test inputs |
| synth_bench/job_docs_bench JSON | Synthetic comparison results and fields | `_load_pages`/run_ocr sanitized ingestion precedes extraction, at `engine_v2/tools/job_docs_bench.py:61`, `:145`, `engine_v2/tools/synth_bench.py:270` |
| Upstage adapter | Stub with no text acquisition | `demo/backend/ocr/upstage.py:53` delegates to its unimplemented API stub |

Existing uploads and database locations are documented by metadata-only research in `business-storage.md`. Printed resident numbers remain in retained original PDF/image bytes and split-page PDFs. This stage redacts acquired text and stored OCR results. Existing files and database contents were preserved for user-controlled deletion.

## Verification

- 103 new tests cover all eight sex digits, separator variants, date validity, other identifier formats, split words/unequal heights/distant columns, G-prefixed split IDs, markup/entities, engine errors, full text-layer loading, birth fallbacks, nested data and legacy OCR/review/score response projections.
- Four actual TestClient uploads cover image/text-layer and full/split forms using isolated temporary SQLite/storage. Birth remains correct and response, saved OCR data, all row projections, explicit JSON output, logs and OCR object repr exclude the fictitious suffix.
- Latest targeted privacy plus format-parser and portal-upload suite passed 188 tests. Earlier comprehensive targeted privacy/NHIS/insurance/JBAI suite passed 162 tests.
- P9 identity scenarios passed 96 checks. P18 applicant precheck scenarios passed 156 checks.
- Two existing test preparations assumed raw RRN text remained available after OcrWord construction. `engine_v2/tests/test_format_parsing.py:22` and `demo/backend/tests/run_p18_applicant_precheck_scenarios.py:56` now locate either the raw or already-masked fictitious identifier. All existing assertions are preserved.
- Python compileall passed for changed ingestion/API modules. Full integration regression remains the parent task's final gate.


Existing storage metadata confirmed `demo/storage/documents/` and SQLite `demo/demo.db`, table `document`, with 31 persisted document/OCR rows. Upload layout is `<application_no>/<slot_key>/`, with merged originals in `_merged/`. Original uploaded PDF/image bytes can contain printed full identifiers. Existing data is retained for user-controlled cleanup. See `research/business-storage.md` for source evidence.

Stage 1 adds 103 synthetic tests, including four full/split and image/text upload combinations. The complete pytest run before the final cached-review projection test passed 740 tests with 3 skips. Targeted latest privacy tests passed 103. Existing fixture setup now accepts already-masked synthetic identifiers, preserving all prior assertions.

## Verification and unresolved assumptions

Only masked shape sources are used for real-document structure. Synthetic integration proves pipeline behavior. Actual original glyph correction and resulting real-file accuracy cannot be established from placeholders alone.

## Stage 2 outcome

All supplied failures are classified individually above. The supported changes follow observed geometry and typed-cell constraints. Unknown Latin numeric glyphs remain reviewable. Issue-date duplication outside the closing block already works, so the additional position test guards that behavior. The shortened issuer role remains inference. The five-year helper already permits insurance gaps and keeps its meaning.

## Stage 3 outcome

Shared NHIS geometry now accepts explicitly optional header-backed empty columns while retaining strict default corridor ambiguity checks (`engine_v2/extractors/nhis_forms.py:151`). Bounded label comparison supports justified glyph labels using observed cell bounds (`:120`). Closing organization scope retains unique date-only evidence even with an obscured officer role (`:24`). Geometry-plus-confidence noise recognition is opt-in for bounded OCR callers (`:205`). Source value words remain intact.

The amount-cell helper `engine_v2/extractors/format_text.py:24` returns normalized integer text or unreadable plus correction categories. It permits only O/o→0, I/l→1 and valid three-digit group punctuation. Unknown A stays unreadable. Numeric correction consumers must enforce arithmetic before completeness. Shared coordinate helpers add 21 tests and numeric helpers add 26 tests. Focused NHIS/portal/backend coverage passed 332 tests in the implementer's run, and the numeric plus format-parser set passed 98 tests.
