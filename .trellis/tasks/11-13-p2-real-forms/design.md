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

## Initial cause classification

| Form and failed checks | Category | Shape evidence and investigation target |
| --- | --- | --- |
| Payment `monthly_amounts_numeric`, `monthly_total_matches`, `paid_total_matches` | (가), cascading arithmetic failures | Numeric cells at x390–421 and x1195–1231, y959–1487 contain `A` at confidence .33–.67. Original glyph identity is inference. Eight header columns include entirely empty optional columns. |
| Qualification `nhis_issue_location_unique`, `발급일_consistent`, `발급일_required` | (나)/(다), pending code trace | Request date x1841–2079 y677–729, issue date x1114–1375 y2726–2789, validity date in sentence x278–889 y3011–3059. Confirmation y2635–2689 and issuer y2855–2950 bound the intended date. |
| Qualification `nhis_blank_marker`, `household_rows_read`, `subscriber_matches_first_member` | (나)/(다), pending code trace | Single member y1481–1547, marker x977–1159 y1596–1655, empty management cell and trailing low-confidence artifacts y1976–2186. |
| Acquisition `nhis_history_cells_read`, `nhis_row_numbers_continuous`, `nhis_current_loss_blank`, `history_dates_read` | (나)/(다), pending code trace | Three numbered rows y1111–1427, empty employer column under header x966–1226, low-confidence tall overprint x845–1105 y1201–1420. |
| Acquisition `nhis_neighbor_dates_continuous` | (다) | User reports genuine gaps. Shape dates at x1652–1867 and x2048–2263 cannot establish ordering. Code and synthetic dates must verify the rule. |
| Acquisition `nhis_blank_marker`, `recent_five_years_covered` | (나)/(다), pending trace | Marker x646–831 y1489–1554 and trailing blank rows/overprints y2033–2339. Five-year coverage depends on valid row extraction. |
| Business proof lacking validations | (라) | Dedicated extractor absent from engine registry. Labels and right-side values span y568–1834, final unlabeled date x1311–1567 y2112–2156. |

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
