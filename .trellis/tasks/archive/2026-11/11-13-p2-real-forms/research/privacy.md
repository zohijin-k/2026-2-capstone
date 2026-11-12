# Resident-number redaction

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
