# Address and resolution evidence

Source: regenerated masked layout_shape5, read-only. No source file copied.

Case 5: date labels are observed, including split 발생일/신고일 words. Numbered address rows and transfer reasons are present, but there are no full date values in their date columns. Evaluate the second A3 condition, not absent labels. Evidence must be independent of date-dependent history parsing, which currently cannot construct those rows. Unknown/numberless headers or date-shaped unreadable residue must remain review.

Case 6: supplied final result is PdfText unknown/confidence zero despite own OCR words. Code localocr.py returns None when classify_pages_with_evidence cannot choose a type; the chain then preserves only PdfText image heuristics. resident_title.py needs a large upper 주민등록표 plus adjacent subtype; table terms alone cannot distinguish register/abstract. Masked title tokens do not establish their original OCR text: exact glyph-level cause is 추정. The synthetic damaged-title replica verifies this routing failure. Preserve confidently parsed top-right 1/2 independently of type, without inventing a type from the upload slot.

Low-resolution evidence is measured on original uploaded image dimensions (or dominant embedded full-page bitmap), never the rendered 300dpi substitute. Short <600 AND long <800 plus unknown type/mostly missing essential fields is narrow; dimensions equal to either boundary and all normal source sizes remain reviewable, never hard rejection based on pixels alone.

Scoring scope: preserve existing fallback value computation, but annotate residence FactSource.origin when date omissions force fallback. This does not certify residence eligibility or change points.
