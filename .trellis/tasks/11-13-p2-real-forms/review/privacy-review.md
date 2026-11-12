# Stage 1 privacy review

Reviewed the in-progress ingestion and output diff without production edits. Existing targeted tests passed with 59 passing tests across JBAI OCR/transport, NHIS extraction and resident extraction.

## Findings sent to the implementing agent

1. **Split-word leak with differing token heights.** `mask_words` compares a word's center difference to only the incoming token's height times .6. Synthetic front token bbox `(0, 0, 70, 14)` and following suffix bbox `(73, 8, 143, 14)` have strong vertical overlap, but the suffix is grouped separately and stays raw. This must be fixed before the stage is complete.
2. **External HTML leak.** `mask_rrn` on raw JBAI HTML cannot match a number split by markup. Parsing `<p><span>900101-</span><span>1234567</span></p>` creates a plaintext number containing the final six digits. A table cell with the same spans has the same leak. Mask the parsed text/cell values and retain a safe raw-content representation, or perform markup-aware masking that maps concatenated text spans back to HTML offsets. Inspect OTSL separators as well.
3. **Birth parsing after compact or whitespace masking.** The sanitizer accepts compact and whitespace-separated synthetic identifiers, but `nhis_common.birth_from_rrn` returns `None` for these masked forms because both common RRN patterns demand a dash. Preserve birth extraction for the supported new ingestion formats.
4. **False masking across distant columns.** `mask_words` inserts a newline for a horizontal gap over twice token height, but the regex accepts that newline between birth and sex digits. Separate distant fields are still joined. A synthetic six-digit token bbox `(0, 0, 60, 10)` and unrelated seven-digit token bbox `(900, 0, 970, 10)` incorrectly modify the latter. Flush the candidate run or use a separator excluded from the pattern.
5. **Remaining raw acquisition calls.** `demo/backend/ocr/localocr.py` text-layer presence check and notification routing call `get_text()` directly around lines 469 and 510. They currently derive only a boolean/form decision, but the earliest-ingestion requirement calls for applying the shared sanitizer immediately there too.

All examples above use fictitious values. The implementing agent received concrete reproductions. Findings must be rerun after corrections.

## Covered surfaces inspected

- `OcrWord.__post_init__`, `OcrResult.__post_init__`, each coordinate OCR adapter return and own OCR return redact words before extraction.
- `_load_pages` constructs both shared OCR types for text-layer words. Constructor coverage therefore reaches this normal entry point without a second custom loop.
- `_process_pdf_page` masks `PageImage.text` at extraction from PyMuPDF.
- PdfText direct read, `read_page_text` and split-PDF read mask incoming text.
- Demo result construction/fallback and final chain output sanitize fields, quality notes, fallback reasons and classification evidence.
- Upload serialization applies nested masking to OCR fields and persisted findings.
- Applicant document representation and officer extracted fields/findings sanitize legacy rows at read time.
- `inspect_pdf` diagnostics already apply shape/value masking to printed text and saved word text. Its retained numeric values do not expose suffixes.
- Current local/JBAI logs report fixed reason codes or sanitized OCR errors. No document text logging was found at the reviewed runtime sites.
- Existing full-result CLI and diagnostic serialization inherit sanitized source words. They require suffix checks in the implementing agent's regression coverage.

## Identifier-preservation checks

Ephemeral probes confirmed unchanged 3-2-5 business numbers, 11-digit payer numbers, 4-3-4-3 issue numbers, 4-4-4-5 government document numbers and `G` plus eighteen digits. Date-invalid candidate fronts also remain unchanged. Shape-only source data cannot establish original real values.

## Resolution

All five reproduced findings were corrected in stage 1. Root verification passed 103 new privacy tests, including split heights, markup/entity spans, compact birth, distant-column preservation and cached historical review projections. Existing fixture setup was adapted to immediate masking while retaining its assertions.
