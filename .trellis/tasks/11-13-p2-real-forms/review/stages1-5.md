# Cross-layer review of stages 1–5

Reviewed commits through `6c5946d` against the task artifacts and backend form contracts. This pass made no production edits. All probes used fictitious values and in-memory word data. Private documents and the audit walkthrough were not accessed.

## Findings

### High priority — merged ASCII labels bypass resident-number masking

`engine_v2/pipeline/privacy.py:11` excludes every ASCII letter immediately before a candidate. Consequently a fictitious resident number after a merged `RRN` label remains unchanged in both dashed and compact forms. `OcrWord.__post_init__`, raw PdfText masking, nested output masking and API persistence all reuse this function, so the leak propagates through every otherwise-correct boundary.

The user requires valid-date resident shapes to be redacted and specifically preserves other identifier formats. A broad ASCII-letter exemption is unsupported. The minimal central solution is a digit-only left boundary plus explicit protection for an observed `G` followed by eighteen digits, including its supported whitespace-split representation. Existing date validity and sex-digit checks should remain.

Immediate per-word masking introduces a context issue for a `G` plus thirteen-digit word followed by a separate five-digit word. A complete batch proves this is the preserved eighteen-digit issue number, while the first word alone cannot. Keep provisional G-prefixed fragments until same-line assembly resolves that context, then ensure all returned words and results are sanitized. Avoid globally exempting standalone G-prefixed resident-shaped candidates in final text/output.

Required regression coverage should include merged ASCII labels, compact forms, a label ending in G, complete G+18 identifiers and same-line G+13/five-digit splits. Each case needs raw text plus coordinate-word entry points. Reuse upload privacy tests for persisted/result behavior.

### High priority — malformed loss dates can become employer continuation text

`engine_v2/extractors/nhis_acquisition_loss.py:347` reserves only already-valid numeric date words. The employer continuation path at `:364` accepts an unknown token in a date column when its x coordinate is close to an oversized employer token.

A reproduction starts from `acquisition_cells()`, replaces the first employer with the fictitious text `가상상사` repeated seventeen times, and adds a loss-column token shaped `YYYY.OI.OI`. The current result has `structure_complete=True` and no failed validations. Its loss date becomes `None` and the corrupted date is included in the employer value. This permits uncertain input to assert the current loss cell is blank.

The mechanism predates stage 4, but the user's strict uncertainty requirement covers it. Date-shaped numeric or lookalike tokens located in observed date cells must remain invalid date evidence when parsing fails. They must not be reclassified as employer continuation. Preserve the existing test for legitimate long employer continuations and require a new malformed-loss regression to reach NEEDS_REVIEW at extraction and demo verdict boundaries.

### Lower priority — newline inside the resident suffix stays unmasked

`privacy.py:12` permits space/tab separators inside the last six digits, while the birth/sex separator also permits newlines. A fictitious valid resident number with a newline inside its suffix is unchanged. Its six digits remain reconstructable even though they are no longer one contiguous substring.

The stated whitespace tolerance supports recognizing this in raw PdfText/OCR text. Consider allowing line whitespace within the suffix too. Coordinate runs already use a NUL separator to prevent joining distant columns, so that guard can remain. Tests should compare the retained digits after removing whitespace as well as searching a contiguous suffix.

### Scoped observation — direct OTSL merge helper can reconstruct an unmasked value

`engine_v2/pipeline/jbai_ocr.py:232` masks each OTSL token value before `lcel` continuation merges it. Directly parsing a fictitious front token followed by a suffix in a continuation token yields a reconstructed raw resident number. The normal JBAI ingress currently prevents this through `mask_markup_rrn` before parsing, which was confirmed with an ephemeral probe. This is not a reproduced upload leak. Sanitizing the final merged cell would align the helper with the documented direct parsing boundary and simplify future caller safety.

## Verified behavior

- The observed regional acquisition shape reads all one-to-ten synthetic rows, retains empty employers and accepts gaps while rejecting overlaps. Required identity remains unchanged after early masking.
- Qualification reads one-to-ten complete synthetic members with empty management/loss/suspension cells. Missing member cells suppress both household list and count.
- Marker-only rows and alternate punctuation are accepted in their observed columns. Ordinary distant names, employer fragments and malformed dates remain reviewable. Only isolated source-shaped watermark glyphs or confidence-plus-geometry anomalies are ignored.
- Issue-date selection uses the unique closing organization below confirmation. Identical request and validity dates elsewhere are harmless. Duplicate or malformed dates inside the block, including dates grouped into the tall issuer row, are rejected.
- Text-layer and previous NHIS/portal tests retain their assertions. The invalid-neighbor fixture correction uses an overlapping fake date and keeps its original review assertion.
- Adapter completeness checks cap confidence and precede demo eligibility checks. Current incomplete acquisition and qualification shapes reach NEEDS_REVIEW instead of uncertain business FAIL.
- Existing upload persistence and applicant/officer/review projections sanitize strings and nested containers. Early masking reaches own, other coordinate OCR, text-layer and JBAI paths. The ASCII-prefix finding is a central recognizer gap affecting all these sites.

## Validation evidence

The final stage-5 focused run passed 523 tests spanning existing and new NHIS, portal, coordinate and actual upload paths. The stage-4 run included 92 new tests with six actual image-PDF uploads. Stage 5 added 90 tests with seven actual image-PDF uploads. No production changes were made during this audit pass.

## Stage 9 resolution

All findings above are repaired. Central masking recognizes merged ASCII labels, suffix line breaks and explicit protected G-number spans. Complete word/cell batches provide the context needed to preserve split issue identifiers before returned data is exposed. HTML raw attribute values are sanitized too. OTSL continuation cells receive final masking after all fragments are assembled. Resident compact/spaced masked values retain birthday extraction and legacy dashed century handling.

Acquisition date-column values shaped like malformed numeric or all-lookalike dates stay invalid evidence even when a workplace token crosses that column. Ordinary supported long workplace continuations retain their existing coverage. Engine and actual upload regressions assert review on the reproduced malformed-loss cases.

The final integration report and test counts are in `review/final.md`. The current masking inventory has 28 complete function boundaries in `research/privacy.md`.
