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

Failure-mechanism code locations use base revision `5d0833d`. The following tables record every supplied failure. Category (가) means character recognition, (나) token/line segmentation, (다) a rule rejecting a normal variation, and (라) a propagated or other failure. Exact original glyphs and date values remain inference (추정) because the sources replace them with shape characters.

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

## Implemented contract

`engine_v2/pipeline/privacy.py:10` recognizes six date-valid birth digits followed by sex digit 1–8 and six trailing digits. The suffix alone is replaced, preserving birth, sex digit, whitespace and geometry. Merged ASCII labels do not exempt a resident shape. Explicit G-plus-eighteen-digit spans are protected at line 14, including whitespace and same-line word splits. Compact, spaced, Unicode-dash and suffix-line-break cases are covered.

`mask_words` at `engine_v2/pipeline/privacy.py:88` groups by relative word heights and horizontal proximity. A NUL barrier protects distant numeric columns. Unequal token heights and tilt retain coverage. `mask_markup_rrn` at line 54 maps inline HTML/entity characters back to source spans, preserves glyph-mapped G-number context and masks raw attribute values. Table/block boundaries prevent concatenation of unrelated identifiers.

Complete adapter word batches are the earliest context that distinguishes a split resident number from a G-prefixed issue number split after thirteen digits. `OcrWord` is now a transient internal representation. All real adapter returns and `OcrResult` construction sanitize the entire word batch before exposing it. No hidden raw suffix or restoration state is stored. HTML and OTSL cells are likewise sanitized after inline/continuation fragments have formed the complete cell. The original format-parser and P18 resident-number fixture selectors were restored to their main-branch wording.

## Applied boundaries

There are 28 explicitly sanitized function boundaries. Several routes share constructors, so this count measures function sites rather than independent implementations. Stage 9 removed the premature per-word constructor boundary and retained every complete ingestion/return boundary.

| # | Boundary | Evidence |
| --- | --- | --- |
| 1 | Complete coordinate OCR result, split words and error text | `engine_v2/pipeline/ocr/__init__.py:38` |
| 2–4 | Apple Vision, EasyOCR and Paddle direct adapter returns | `engine_v2/pipeline/ocr/__init__.py:78`, `:95`, `:137` |
| 5 | Own OCR direct recognition return | `engine_v2/pipeline/ocr/own.py:136` |
| 6 | PDF text before retention in PageImage.text | `engine_v2/pipeline/preprocess.py:89` |
| 7–9 | PdfText pure parser, PDF raw read and merged-page reader | `demo/backend/ocr/pdftext.py:235`, `:344`, `:438` |
| 10–11 | LocalOcr text-layer existence and notification-routing reads | `demo/backend/ocr/localocr.py:578`, `:619` |
| 12–14 | External OCR response, complete HTML cells and complete merged OTSL cells | `engine_v2/pipeline/jbai_ocr.py:549`, `:178`, `:272` |
| 15–16 | Demo result construction and fallback exceptions | `demo/backend/ocr/base.py:80`, `:97` |
| 17 | Common OCR-chain return after field/filter mutations | `demo/backend/ocr/__init__.py:85` |
| 18–20 | OCR JSON serialization, initial findings persistence and NHIS recheck findings persistence | `demo/backend/api/documents.py:197`, `:241`, `:306` |
| 21–23 | Applicant JSON, engine fact projection and officer OCR projection, including legacy rows | `demo/backend/api/common.py:205`, `:236`, `demo/backend/api/officer.py:658` |
| 24–25 | Review score/tiebreak/payload persistence and recomputed household review payload | `demo/backend/api/review.py:578`, `:627` |
| 26–28 | Officer eligibility, exclusions and detail projections of historical score/payload JSON | `demo/backend/api/officer.py:694`, `:787`, `:854` |

`engine_v2/engine.py:189` creates transient OcrWord objects for text-layer values and then constructs OcrResult at line 191, applying boundary 1 to the complete batch before extraction. Existing job and insurance scrubbing accepts the earlier masked prefix, preserving birth fallback and complete source-token disposal at `engine_v2/extractors/job_common.py:35` and `engine_v2/extractors/insurance_4.py:25`. NHIS masked-prefix parsing accepts compact/spaced forms at `engine_v2/extractors/nhis_common.py:21`. The resident header now accepts a complete compact/spaced masked shape while retaining legacy dashed sex-digit century handling at `engine_v2/extractors/resident_abstract.py:44`.

## Sink inventory

| Sink | Stored or emitted material | Redaction coverage |
| --- | --- | --- |
| OCR words/result repr and dataclass serialization | Word text, error, confidence and geometry | Boundaries 1–5, asserted at complete public ingestion/return boundaries |
| PDF PageImage.text | Raw textual page body retained in memory | Boundary 6, asserted before `_load_pages` |
| ExtractedField.value/raw_text, validation detail, warning and rule evidence | Derived from OCR/PdfText/JBAI inputs | Inherits sanitized ingestion. Acquisition extraction repr is asserted |
| External JBAI page objects/cache | text_lines, HTML/OTSL cells, raw_content, table_content | Boundaries 12–14 precede JBAIPageResult and cache retention. Inline tags/entities, continuation cells and protected G-number context have regressions |
| Demo Document.ocr_json | Fields, classification evidence, fallback reasons and quality notes | Boundaries 15, 17 and 18 |
| Demo Document.findings_json | Initial and recomputed findings | Boundaries 19–20 |
| Review.review_payload_json, score_json and tiebreak_json | OCR-derived rule evidence and review/score notes | Boundaries 24–25, sourced from sanitized `common.document_fact`; historical payload/score response protection at boundaries 26–28. `demo/backend/models.py:158` defines the persisted payload |
| Applicant and officer responses | Visible fields, findings, internal OCR metadata | Boundaries 21–23 also protect historical rows when read |
| LocalOcr warning log | Engine availability reason | Fixed operational reason at `demo/backend/ocr/localocr.py:590`, no OCR body |
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
- Stage 9 adds complete-batch, merged-ASCII-label, split G-number, HTML/OTSL continuation, suffix-line-break and resident birth regressions. The focused privacy collection now has 146 tests. Eight actual uploads cover the original full/split image/text combinations plus ASCII-prefixed notes, and preserve birth while keeping outputs/logs clean.
- `engine_v2/tests/test_format_parsing.py:22` and the P18 RRN selector at `demo/backend/tests/run_p18_applicant_precheck_scenarios.py:56` use their original main-branch raw synthetic selectors again. Complete-batch sanitization preserves that test preparation.
- Python compileall passed for changed ingestion/API modules. Full integration regression remains the parent task's final gate.

## Limits and inference

The OCR model naturally produces transient recognition text before the immediate ingestion sanitizer runs. Original PDF/image bytes retain printed identifiers. Source-derived fields, OCR caches and outputs retain the sanitized representation. Recognition-model accuracy on the unavailable original files is inference from shape and synthetic coverage.

Existing storage metadata was checked again after integration. `demo/storage/documents/` and `demo/demo.db` exist, with 31 document rows and 31 nonempty OCR JSON rows. Only aggregate counts and path existence were read. Stored rows and original artifacts remain available for user-controlled cleanup.

## Verification and unresolved assumptions

Only masked shape sources are used for real-document structure. Synthetic integration proves pipeline behavior. Actual original glyph correction and resulting real-file accuracy cannot be established from placeholders alone.

## Stage 2 outcome

All supplied failures are classified individually above. The supported changes follow observed geometry and typed-cell constraints. Unknown Latin numeric glyphs remain reviewable. Issue-date duplication outside the closing block already works, so the additional position test guards that behavior. The shortened issuer role remains inference. The five-year helper already permits insurance gaps and keeps its meaning.

## Stage 3 outcome

Shared NHIS geometry now accepts explicitly optional header-backed empty columns while retaining strict default corridor ambiguity checks (`engine_v2/extractors/nhis_forms.py:151`). Bounded label comparison supports justified glyph labels using observed cell bounds (`:120`). Closing organization scope retains unique date-only evidence even with an obscured officer role (`:24`). Geometry-plus-confidence noise recognition is opt-in for bounded OCR callers (`:205`). Source value words remain intact.

The amount-cell helper `engine_v2/extractors/format_text.py:24` returns normalized integer text or unreadable plus correction categories. It permits only O/o→0, I/l→1 and valid three-digit group punctuation. Unknown A stays unreadable. Numeric correction consumers must enforce arithmetic before completeness. Shared coordinate helpers add 21 tests and numeric helpers add 26 tests. Focused NHIS/portal/backend coverage passed 332 tests in the implementer's run, and the numeric plus format-parser set passed 98 tests.

## Stage 4 outcome

Acquisition history now derives the bounded table through its marker, reads empty employer/current-loss columns from observed headers, and discounts only scoped geometric OCR anomalies (`engine_v2/extractors/nhis_acquisition_loss.py:265`). Marker-only rows and alternate separator punctuation pass. Ordinary row text, numbers, malformed dates or employer fragments after the marker remain incomplete. OCR callers opt into a half-glyph minimum corridor through the shared helper, preserving its default.

The neighboring date rule is lower loss <= upper acquisition (`:379`). An overlap remains incomplete and reaches NEEDS_REVIEW before eligibility. `history_covers_recent_years` retains its existing printed-lookback/old-loss meaning and already permits gaps. Government24 has no matching neighbor-continuity validation, so no additional rule needed adjustment. The old invalid-neighbor test's fake lower loss changed from before the upper acquisition to after it, preserving the test's assertions and invalid-history intent.

Added 84 engine tests and 8 backend tests, including six actual image-PDF uploads. Every row count 1–10, names 2–4 characters, resolution/jitter/skew, empty employers, full/masked birth, gaps, overlaps and hidden fragments are covered. Engine-focused 300 and cross-layer-focused 244 tests passed.

## Stage 5 outcome

Qualification now reads a single member with empty management, loss and suspension cells, deriving the optional columns from observed headers and marker-bounded body whitespace (`engine_v2/extractors/nhis_qualification.py:83`). Tiny/tall glyphs require geometric and confidence evidence within observed gaps. Names, dates and ordinary fragments after the marker remain incomplete. Household counts/lists are published only after every row and subscriber-first-member check passes.

The issue date remains scoped below confirmation and above the closing organization. Identical values in request and validity positions pass. A second valid or malformed date inside that block, including one grouped into a tall issuer row, remains ambiguous (`engine_v2/extractors/nhis_forms.py:24`). The obscured issuer-role explanation for the real OCR failure remains inference.

The source-shaped fixture preserves the five-plus-one title split, tiny preheader/member glyphs, low-confidence trailing fragments and two seal words. Added 82 engine and 8 backend tests, including seven image-PDF uploads. Every household count 1–10 and names 2–4, resolution/jitter/skew, optional empty cells and date/marker corruption are covered. The old/new NHIS and portal focused suite passed 523 tests. The shared noise helper now compares physical width and height in matching units (`nhis_forms.py:210`).

## Stage 6 outcome

The recognized government eight-column payment family uses `engine_v2/extractors/nhis_payment_gov.py:22`, entered by `nhis_payment.extract`. Signature evidence includes the body title/information grid and surviving repeated outside-income headers, preserving a legacy three-month/fewer-column government fixture. Twelve calendar months keep their printed zero amounts even outside the query period. Empty optional cells remain JSON null. Existing monthly maps and fixed October–December average meanings remain compatible. All eight per-column sums and the paid grand total are mandatory.

Only bounded OCR amount cells receive allowed numeric corrections. Row/column/category records survive API and database serialization in `숫자형식교정`, and failed arithmetic prevents completeness. Text-layer numeric values follow their existing grammar. The type has no printed insurance category, so the dedicated extractor emits none. Downstream `facts.py` still defaults missing category to 직장. That policy fallback and the fixed legacy averaging months are reported as existing scope-external behavior.

Cross-layer verification found two related safety gaps. Payment amounts with explicit NEEDS_REVIEW/FAIL could establish income rejection, including markerless fallback after damaged headers. `demo/backend/rules/facts.py:85` now withholds those financial facts while preserving the saved OCR data for officers. A present incomplete marker also withholds amounts. `demo/backend/engine_adapter.py:206` now carries an explicit high-confidence review into the engine through its existing confidence threshold, retaining raw saved confidence and already-low confidence. These are evidence-trust and status-propagation fixes supporting the requested uncertainty contract. Eligibility thresholds and employment rules are preserved.

Added 49 engine and 34 backend tests, including fifteen image-PDF uploads and one text-layer PDF upload. Latest payment plus full backend coverage passed 245 tests. The preceding complete engine/backend run passed 1,046 tests with 3 skips before the final seven markerless regressions. All eighteen scenario modules passed the existing 1,796 checks plus the separate eight-form verification, and P3 passed again after the trust refinement. Real alphabetic glyph identity and first-applicant payment-shape compatibility remain inference because those values/layout were not supplied.

## Stage 7 outcome

The dedicated NTS proof reader publishes the thirteen requested fields with body-title/grid evidence, full-cell identifiers, checksum reuse, bounded justified labels, multiline lists, internal address and a uniquely scoped issue date (`engine_v2/extractors/business_registration.py:237`). Both OCR and text-layer paths enter the registered reader. Final conversion and post-filter required checks preserve the Korean identity/date contract (`demo/backend/ocr/localocr.py:216`, `:274`). Missing reference identity, missing/mismatching representative identity, checksum failure, incomplete cells or corporate birth ambiguity reach NEEDS_REVIEW before other checks (`demo/backend/rules/doc_check.py:362`).

Personal/corporate classification uses the validated business number's entity code and explicit corporate taxpayer text. Corporate/unknown codes and contradictory corporate text suppress birth. Corporate numbers resembling dates cannot establish a representative birthday. The existing checksum function is reused. Dates are read as document metadata. Opening after issuance remains readable, consistent with NTS pre-opening registration guidance linked in `research/business-plan.md`. Employment eligibility receives no new rule.

Joint-business presence requires an explicit absence phrase or complete, aligned name/identifier columns. Counts 1–10 tolerate relative jitter and skew. Partial rows, conflicting absence, unmatched equal-length column fragments and competing issuer-overlap dates remain incomplete. The purpose of the source-shaped oversized two-plus-one-character fragments remains inference. An observed absence phrase and their geometry govern their treatment.

Added 94 engine and 37 backend tests. The new suites passed 131 tests and combined previous-form coverage passed 277. Tests include actual image/text PDF uploads, all thirteen missing fields, checksum/code variants, corporate-text conflict including split glyphs, future opening metadata, name/scale/jitter variants, one-to-ten participants, hidden/partial evidence and post-filter completeness. Detailed source references and remaining inference are recorded in `research/business-results.md`.

## Stage 8 outcome

The resident-numbering alarm is reproducible from the supplied geometry. A final-page law-change note and its isolated ordinal have overlapping vertical boxes but different token heights. Ordinary line grouping separates them, and the former parser discarded the ordinal when the preceding address already had a number. `resident_abstract._join_note_numbers` now associates only uniquely adjacent note/number evidence using relative font height and observed row pitch. A source-coordinate synthetic reproduction retains all 29 ordinals, comprising 27 address rows and two notes. Original numeric sequence values remain inference because they are masked.

Observed orphan/duplicate tokens and missing ordinals on parsed address entries remain failures. Existing contiguous offsets and unnumbered annotations keep their prior interpretation. A remaining history validation failure caps all extracted fields and demo confidence at .4 and adds a review warning. Direct core evaluation also stays NEEDS_REVIEW when declared issue date or residence checks use those uncertain fields. Correctly associated notes preserve normal confidence and PASS.

Added 35 engine and 9 backend tests, including nine three-page image-PDF uploads. Focused resident/title/core/format coverage plus the entire backend suite passed 397 tests. P8 retained 89 passing scenario checks. Detailed geometry and source references are in `research/payment-resident.md`.

## Stage 9 review repairs

Full-scope delegated review covered privacy and stages 1–5, government payment and financial/status propagation, and business-proof extraction/identity. Reproductions and resolutions are retained in `review/stages1-5.md`, `review/payment.md` and `review/business.md`.

- Privacy now recognizes merged ASCII-label resident shapes with an explicit G+18-digit exclusion. Complete adapter/result batches resolve split preserved identifiers before redaction. Raw word construction remains transient. Final reconstructed OTSL cells are sanitized, and raw suffix whitespace includes line breaks. The original format-parser and P18 raw-word selectors are restored.
- Acquisition date-shaped loss errors cannot become employer continuation text beside an oversized employer box. Unknown dates remain incomplete.
- Payment metadata accounts for crossing words, every period-shaped candidate and complete document-number values. Header-only purpose/workplace evidence remains incomplete through final common filtering. All critical legacy payment identity/month/numeric/arithmetic failures cap confidence. The shared failure recognizer also withholds financial facts and carries review for historical high-confidence cached PASS rows while preserving the stored row.
- Business multiline values extend to the observed joint-section header. Partial participant names left of a centered header and crossing fragments remain accounted evidence, requiring review when incomplete.
- P18 synthetic multi-page histories originally restarted their dates on each page and repeated body ordinals in duplicate-marker cases. Their dates/ordinals now continue across pages, isolating the intended page-marker checks. Two independent common-rule specimens assumed business proof had no identity/required-field contract. They now use the existing farm-proof type for those common-rule checks. All expected states, error-code assertions and BIZ missing-issue-date assertions remain intact. New business-proof tests cover its requested mandatory identity/field contract.

The unchanged recent-five-year helper, eligibility thresholds, employment assessment and fixed legacy average field meaning retain their existing behavior. Test values and identifiers are fictitious. Real-document evidence remains limited to the supplied masked shape files.

### Final verification

| Gate | Main baseline | Final result | Added passing tests |
| --- | --- | --- | --- |
| Engine pytest | 499 passed, 3 skipped | 1,049 passed, 3 skipped | 550 |
| Backend pytest | 139 passed | 289 passed | 150 |
| Scenarios | 18 modules, 1,796 checks | 18 successful modules, 1,796 passed, zero failed | Existing checks retained |
| P14 original forms | Eight-form verification | Eight forms verified | Existing verification retained |

There are 700 new passing pytest cases overall. Stage 9 contributes 110, including twenty-seven actual upload cases. A separate parent verification passed 241 privacy/review/business tests. The three existing skips retain their missing synthetic-font reason. Compilation and `git diff --check` pass. The repository defines no Python lint/type-check command.

Full results, per-module counts, synthetic fixture corrections and resolved review findings are recorded in `review/final.md`. Final execution logs are `/tmp/p2-review-engine-tests-final.log`, `/tmp/p2-review-backend-tests-final.log`, `/tmp/p2-final-scenarios-summary.json` and `/tmp/p2-final-run_*.log`. Parent verification is `/tmp/p2-root-final-review.log`.

## Stage 10 outcome and handoff

The backend executable contract now covers the complete ingestion lifecycle, optional-column geometry, conservative corrections/arithmetic, payment financial trust/status propagation, thirteen-field business identity, and resident history uncertainty. The backend index points to the expanded contract. The task is in `review` with `awaiting_user_confirmation=true`.

### Current correction locations

| Area | Final source evidence |
| --- | --- |
| Central text and complete-batch privacy | `engine_v2/pipeline/privacy.py:31`, `:88`, `engine_v2/pipeline/ocr/__init__.py:38` |
| Acquisition empty columns, marker and neighbor order | `engine_v2/extractors/nhis_acquisition_loss.py:245`, `:383` |
| Qualification one-member table and scoped issue date | `engine_v2/extractors/nhis_qualification.py:83`, `engine_v2/extractors/nhis_forms.py:24` |
| Government payment table, metadata and arithmetic | `engine_v2/extractors/nhis_payment_gov.py:109`, `:192` |
| Fresh and historical payment uncertainty | `engine_v2/extractors/nhis_payment.py:36`, `demo/backend/rules/facts.py:87`, `demo/backend/engine_adapter.py:207` |
| Business proof and final identity/required checks | `engine_v2/extractors/business_registration.py:241`, `demo/backend/ocr/localocr.py:226`, `demo/backend/rules/doc_check.py:362` |
| Resident annotation association and review | `engine_v2/extractors/resident_abstract.py:269`, `demo/backend/ocr/localocr.py:115` |

### Remaining inference

- The original alphabetic amount glyphs, issuer-role omission and oversized business fragments remain 추정. Masked A placeholders cannot identify the source glyph. Unknown numeric characters require review.
- The resident note geometry reproduces the false alarm, while original ordinal values and their exact real-file sequence remain 추정. Synthetic source geometry accounts for all twenty-nine observed ordinal shapes.
- Original-file re-execution and the first applicant's payment-layout compatibility remain unverified because the supplied shape files omit that payment layout. Existing earlier-form/text-layer fixtures and P14 eight-form verification pass.

### Existing scope-external behavior

- Missing insurance category still defaults to 직장 at `demo/backend/rules/facts.py:176`. The dedicated reader preserves the absence of printed category evidence. Existing average aliases use the fixed 2025 October–December months at `engine_v2/extractors/nhis_payment.py:312`. These policy/field-meaning choices remain available for user review.
- The preexisting fixture tier selects predefined synthetic results by basename at `demo/backend/ocr/fixture.py:378`, before the body-based readers, with its documented synthetic identity exemption at `demo/backend/rules/doc_check.py:601`. Actual reader/upload regressions exercise body/coordinates with filenames outside this mapping.
- Original PDF/image and split-page artifacts retain printed identifiers. Existing uploads are under `demo/storage/documents/<application_no>/<slot_key>/` and `<application_no>/_merged/`. SQLite `demo/demo.db` retains document OCR/findings and review/score payload rows. Aggregate verification found thirty-one document rows and thirty-one populated OCR JSON rows. Historical responses receive read-time masking. Existing originals and rows await user-controlled cleanup.

### Ordered local commits

| Stage | Commit |
| --- | --- |
| Planning | `f183c38` |
| 1 privacy | `890770d` |
| 2 classification | `7f02099` |
| 3 common helpers | `5493e8f` |
| 4 acquisition | `879a075` |
| 5 qualification | `6c5946d` |
| 6 payment | `0f3b652` |
| 7 business proof | `9c7a16a` |
| 8 resident history | `dbe70bd` |
| 9 regression/review repairs | `951dec9` |
| 10 specification and review handoff | This documentation commit |

## 후속: 실서류 재현

### Purpose and boundaries

Reproduce the three remaining own-OCR form failures from the exact word geometry in `/tmp/layout_shape3.txt`, then repair demonstrated reader assumptions. Keep this task in user-review status. The user authorizes implementation and a fresh local commit for each ordered stage. Preserve the current branch and all existing expectations. The existing untracked audit directory is excluded.

Read the supplied shape files only. Do not copy their contents into the repository. Author obviously fictitious values with valid dates, matching identities and balanced payment arithmetic, retaining every source box, word boundary, order, confidence, literal bracket label and page size. Route injected own-OCR words through LocalOcr's image path, classification, extraction and validation. Source placeholders cannot establish original dates or original misrecognized letters. Mark those conclusions as 추정.

### Ordered stages

1. Commit this plan before implementation.
2. Author exact-shape synthetic samples and a LocalOcr image-path helper. Verify the original structural failures and record any arithmetic difference. Commit.
3. Classify each failed validation as (가) OCR glyph error, (나) segmentation/geometry assumption, (다) rejected normal variation or (라) propagated/other. Record source coordinate ranges and code references. Commit.
4. Repair the common NHIS confirmation/issuer issue-date selection, including split words/lines, retaining strict uniqueness and request/validity/output-date exclusion. Verify existing text-layer fixtures. Commit.
5. Investigate recent-five-year coverage against query-period and gap semantics. Fix a demonstrated reader/rule defect only. Otherwise record the unsupported conclusion and retain review. Commit.
6. Recognize fragmented government-payment group/component headers with observed eight-column order, strict cells and arithmetic. Preserve empty workplace and result contracts. Commit.
7. Restore both identical-page P18 cases with their original FAIL codes, retain distinct-body variants under separate names, and repair the paging cause if necessary. Commit.
8. Promote the exact-shape tests to complete/readable expectations except explicitly documented unresolved evidence. Add duplicate/missing issue-date, missing/split headers and one-digit arithmetic-error variants. Commit.
9. Run the full established engine/backend/scenario/P14 commands, compare counts, review all changes and record outcomes, remaining inference and out-of-scope findings. Commit and leave awaiting user confirmation.

### Verification plan

Baseline revision `f929da5` has engine 1,049 passed / 3 skipped, backend 289 passed, eighteen scenario modules with 1,796 checks / zero failures, and P14's separate eight-form verification. Inspect collection guards before full execution. Use synthetic images/PDFs and isolated temporary storage. Never execute original-document commands. No changes to income, age, residence, subscriber-category rules, resident-number handling or the audit walkthrough are authorized.

Structural reproduction must cover payment group/component/column failures and both NHIS issue-location failures. Balanced synthetic amounts may eliminate `paid_total_matches`; classify that difference from shape evidence without guessing original glyphs. Candidate count zero or multiple, incomplete headers and unreadable/arithmetic-inconsistent money must remain NEEDS_REVIEW. Keep existing numeric correction scope and all required/column/order/sum validations.

### Stage 2 reproduction evidence

`p2_shape3_samples.py` preserves all 126 / 47 / 49 words for payment / qualification / acquisition. An independent source comparison verified exact boxes, source ordering, confidence, bracket labels, word shapes and page sizes. Golden shape digests protect that comparison without reading the supplied files during tests. The actual LocalOcr image branch receives own-OCR words under an unrelated synthetic filename with no expected type.

**Important inference (추정)** — exact geometry with normal authored labels already passes all three readers before changes. Shape3 masks substrings inside longer notice words, so it cannot establish the original notice text. Adding a repeated group label to the existing four-character notice segment at payment (192,2298,1244,2335), and the organization label to existing eight-character notice segments at qualification (165,3070,2085,3119) and acquisition (141,3016,2283,3078), reproduces the complete reported failure sets. These are explicitly hypothetical fictitious notices with identical source word shapes. They establish a concrete rule defect, but do not prove the original glyphs or the real-document root cause. Additional label-only source context has been requested. The normal-label controls remain passing tests.

With that stated hypothesis, payment reproduces `payment_group_headers`, `payment_component_headers`, `payment_columns`, `paid_total_matches`. Qualification reproduces `nhis_issue_location_unique`, `발급일_consistent`, `발급일_required`. Acquisition reproduces `발급일_consistent`, `nhis_issue_location_unique`, `recent_five_years_covered`, `발급일_required`. The synthetic payment arithmetic balances after conservative O-to-zero correction. Here `paid_total_matches` is (나)/(라), propagated from an unavailable header grid and hence an empty totals list, rather than a demonstrated numeric OCR error. Original alphabetic money glyph identity remains 추정.

Validation before changes ran six image-path cases, all passing their observed/hypothetical expectations. No production code was changed for this stage.

### Stage 3 cause classification

Code references in this table use `613c639`. Every root-cause attribution involving notice substrings is 추정 until the original label-only text is available. The supplied geometry alone does not reproduce those failures. This limitation is part of the result.

| Form / failed validation | Category | Source geometry | Demonstrated mechanism and planned correction |
| --- | --- | --- | --- |
| Payment `payment_group_headers` | (다), original trigger 추정 | Group labels (640,762,778,815), (1447,762,1586,815). Existing four-character notice segment at (192,2298,1244,2335). | `nhis_payment_gov.py:112` uses `_unique_label` across the whole document. A repeated notice substring removes an otherwise valid table label. Scope group recognition above the observed first month. |
| Payment `payment_component_headers` | (라), plus (나) for further splits | Eight component columns x352–1885, y820–952. | `nhis_payment_gov.py:127` refuses components after a failed group. The exact existing component splits already pass when group labels are unique. Extend the comparison view for separately split glyphs/lines while retaining all eight exact component texts and order. |
| Payment `payment_columns` | (라) | Header x187–1885, y820–952. Monthly body x182–1476, y959–1665. | `nhis_payment_gov.py:135` cannot derive boundaries without component headers. Preserve full-cell and corridor checks. |
| Payment `paid_total_matches` | (라)/(나), original numeric cause unknown | Column totals x332–1476, y1726–1781. Grand total (738,1799,879,1848). | `nhis_payment_gov.py:139` returns an empty totals list after failed headers. `:285` requires eight totals, so balanced synthetic amounts still fail. After fixing structure, test unknown money glyphs and one-digit sum mismatch separately. Original A-shaped zero-like glyphs at x390–1429, y961–1482 may be (가), but exact originals are unavailable. |
| Qualification `nhis_issue_location_unique` | (다), original trigger 추정 | Confirmation (292,2635,1159,2689), date (1114,2726,1375,2789), issuer (764,2855,1643,2950), notice (165,3070,2085,3119). | `nhis_forms.py:32` counts every later organization substring, including notices. Restrict to observed standalone issuing blocks, and assemble bounded date fragments independently of global line grouping. |
| Qualification `발급일_consistent` | (라) | Same issue-date box. | `nhis_qualification.py:177` consumes the failed shared selector. Repair the selector and retain consistency checks. |
| Qualification `발급일_required` | (라) | Same issue-date box. | `localocr.py:197`–`:222` adds a missing required-date failure after conversion. Preserve this guard. |
| Acquisition `nhis_issue_location_unique` | (다), original trigger 추정 | Confirmation (325,2475,1444,2529), date (1103,2585,1361,2637), issuer (752,2764,1657,2855), notice (141,3016,2283,3078). | Same shared selector and hypothesized repeated organization substring as qualification. |
| Acquisition `발급일_consistent` | (라) | Same issue-date box. | `nhis_acquisition_loss.py:423` passes the missing selector result into consensus. |
| Acquisition `발급일_required` | (라) | Same issue-date box. | Same final required-field guard at `localocr.py:197`–`:222`. |
| Acquisition `recent_five_years_covered` | (라), real date sufficiency 추정 | Five history-date words at x1639–2263, y1115–1422. No printed query-period label in the supplied shape. | `nhis_acquisition_loss.py:511` requires an issue date before invoking the existing helper. The authored history has an old loss date before the five-year cutoff and passes once its issue date is available. Original numeric placeholders cannot prove real coverage. Preserve helper semantics at `:398`–`:413`. |

The repeated-label mechanism explains all supplied failures without a numeric correction expansion. It is a falsifiable hypothesis, not a confirmed reconstruction of masked source text. Normal-label controls and exact-shape digests prevent silently claiming otherwise.

### Stage 4 shared issuing-date correction

The shared selector now requires a standalone organization/role anchor below confirmation, distinguishing high-confidence notice prose from issuing text while allowing the observed low-confidence neighboring seals. It assembles full date fragments independently of global prose/stamp line grouping. Separate year/month/day/unit words, two/three lines, the confirmation baseline and a date suffix in the sentence's own token are supported. All fragments must form exactly one valid date. Missing, repeated, malformed or unrelated labeled dates retain review. Required-field checks remain intact.

The qualification and acquisition hypothetical-footer image cases now have no failed checks and contain the issue date. Acquisition's existing confidence is 0.9 and qualification's is 0.95. Existing text-layer/portal and own-OCR regressions passed together with the new fragment cases, 336 tests total after correcting the new assertion to the existing acquisition confidence. The source-glyph trigger remains 추정.

### Stage 5 recent-five-year conclusion

No coverage-rule change is justified. The exact-shape authored history has three rows, no query-period label, and two genuine insurance gaps. Relative to its fictitious issue date the oldest loss precedes the five-year cutoff, which satisfies the existing listing-coverage helper. Removing only the issue-date word reproduces `recent_five_years_covered` as a propagated failure. A dedicated regression asserts the extracted serialized rows, both gaps, absent query period, helper result and missing-issue failure.

This verifies the synthetic history's existing meaning only. Shape3 replaces all original date digits, so whether the real history includes five years remains **추정**. Gaps do not independently invalidate the established listing rule. The helper at `nhis_acquisition_loss.py:398` remains unchanged, including explicit query-period precedence. Existing gap/short-query-period regressions remain intact.

### Supplementary label evidence and baseline replay

The user supplied `/tmp/layout_shape4.txt` during stage 6. It exposes public label/notice text while retaining masked personal values and dates. The organization repeats are now confirmed at qualification (165,3070,2085,3119) and acquisition (141,3016,2283,3078). Payment repeats **납부금액**, twice, in the notice words (144,2340,1875,2377) and (144,2426,1906,2463). The earlier fictitious notice's repeated 고지금액 was an unconfirmed alternative and has been replaced with these confirmed public notice strings. Every original shape3 word, label and geometry digest still matches.

Replaying the updated samples with the `f929da5` shared selector loaded into an isolated module, before payment changes, reproduced all three original failure lists exactly. This resolves the earlier unknown-label blocker. It confirms (다) for both organization uniqueness and payment group-header scoping, with (라) cascades for the dependent failures. The original component splits themselves already worked. The payment arithmetic failure is confirmed as a structural cascade on balanced fake amounts. The original money glyphs and original date values remain unknown.

Shape4 also reports the user's post-stage-4 run. Qualification has no failed checks and confidence 0.95. Acquisition has complete structure, confidence 0.9, and only `recent_five_years_covered` remains. Thus its original remaining five-year failure is **not solely** the issue-date cascade. The current original OCR dates do not satisfy the unchanged listing-coverage helper. Whether the document itself lacks the range or a valid-looking original date was misread remains **추정**, because all date digits are masked. No five-year semantic change is authorized by that evidence.

### Stage 6 payment result

Group selection is confined to the observed pre-month header band after metadata and above component headers. Header comparison supports nearby horizontally separated glyphs and vertically split fragments. It reconstructs the same four component names in each group and requires all nine ordered headers (month plus eight amounts), body corridors, complete cells, every column sum and the paid grand total. Form recognition reconstructs the bounded component comparison view too, preserving the legacy three-month reader regression. Empty workplace, monthly aliases, null optional columns and numeric correction records retain their contracts.

The confirmed exact-shape payment now has no failed checks, complete structure, an issue date and confidence 0.95. Original A-shaped money glyph identity remains 추정. Unsupported letters and one-digit sum mismatches still produce incomplete structure at confidence 0.4. Added eight split-header and five malformed/header-order/arithmetic cases. Focused payment plus exact-shape coverage passed 88 tests, including the existing real text-layer synthetic upload. That upload also exposed text-layer seal words with confidence 1.0, so the issuing anchor now uses leading organization geometry and digit exclusion instead of requiring low seal confidence. Existing expectations were preserved.

### Stage 7 P18 restoration

Restored both identical-content inputs under the original case names and retained `index=1` variants as `duplicate-missing-distinct-body` and `duplicate-distinct-body`. Before the fix, the restored cases produced four failed scenario assertions. Duplicate body history causes `history_numbers_sequential` and `history_dates_ordered` failures, capping global confidence at 0.4. `_check_resident_pages` incorrectly reused that downstream history cap to discredit independently readable page counters.

Paging now uses marker plus classification confidence only when the document's exact 0.4 cap accompanies solely history/occurred failures and the derived `pages_complete` failure. Other low-confidence conditions retain the original gate. This changes paging evidence only. Address extraction, residence assessment and history uncertainty remain intact. Both restored cases now FAIL with the original PAGES_INCOMPLETE / PAGES_DUPLICATED codes. Four additional low-marker/low-type variants retain NEEDS_REVIEW and every existing low-document-confidence assertion passes. P18 increased from 156 to 176 passing checks, zero failures.
