# Design

- engine_decision() -> tuple[str, str] returns (engine, reason), with an empty reason when no replacement occurs. It performs no inference, checksum verification, download or logging.
- Preserve the existing nonempty environment override and empty-string default semantics.
- Read own.MODEL_DIR and the ASSETS keys from the existing model preparation module. Check is_file for every required asset, matching the real loader without duplicating paths or filenames. No own.py helper is needed.
- LocalOcr.read calls the decision once and emits one module logger warning when the reason is nonempty. The existing _load_pages already returns (PageImage, OCR result) pairs; pass those unchanged to job extraction. Derive engine attribution from these pairs: all text_layer means pdftext, otherwise the first actual OCR engine. One engine is selected per document.
- Model corruption, missing dependencies and inference errors remain on the existing error path with no engine retry.
- Tests patch the model directory rather than moving installed assets. Synthetic outputs live in temporary directories. Disable both JBAI environment variables inside p17.
- No OCR result fields, schema, score rules or applicant/officer UI changes.

## Approved source-aware job-document correction (2026-11-12)

- _from_job_doc keeps current confidence for present required fields. For missing fields, all text layers use 0.9 (confirmed absence); any OCR page uses 0.5 (uncertain reading).
- Existing check_document handles pdftext absence as MISSING_REQUIRED_FIELD/FAIL and OCR absence as LOW_OCR_CONFIDENCE plus REQUIRED_FIELD_UNREADABLE/NEEDS_REVIEW. Do not change that rule or its messages.
- Import TEXT_LAYER_MIN_CHARS in tests; construct exactly threshold-1/threshold/threshold+1 extracted characters. Test PNGs and mixed PDF page orders as well as successful extraction and upload/list privacy. Use deterministic OCR words for routing tests; p17 retains real CPU inference.
- The approved 46-to-59-character p16 input extension remains. Engine-v2 preprocessing, OCR registry, JBAI code/environment handling and tier order remain unchanged.
