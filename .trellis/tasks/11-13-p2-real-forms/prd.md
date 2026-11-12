# Own OCR form variants and resident-number redaction

## Requirements

Implement the user's ten ordered stages on `feat/p2-real-forms`, based on current main. Commit each coherent stage. Finish in review status awaiting the user.

Redact resident-number final six digits at text ingestion, retaining birth and sex digit. Cover own OCR, other coordinate OCR, text-layer words, PdfText and external OCR. Preserve unrelated identifiers. Verify upload responses, stored OCR data and logs with synthetic documents.

Support the four form shapes described in the read-only `/tmp/layout_shape2.txt` through body/coordinate evidence. Preserve previous text-layer behavior and strict review on incomplete/ambiguous input. Permit only conservative numeric corrections with recorded checks and arithmetic verification. Support acquisition-history gaps, qualification one-member/empty optional cells, payment eight-column tables and a dedicated business-registration proof extractor. Investigate resident history numbering from `/tmp/layout_shape.txt`.

Use fictitious values throughout artifacts and tests. Keep original private documents inaccessible. Keep the audit walkthrough untouched. Locate existing storage using metadata only. Preserve models, training and business employment rules.

## Acceptance

- Required field or structural failure yields NEEDS_REVIEW, preserving identity checks and preventing uncertain FAIL.
- Four synthetic own-OCR form variants parse with complete validations and no identity warnings when identity matches.
- Coordinate perturbation, scale, two-to-four-character names, optional empty columns, one-to-ten rows, trailing empty rows, overlap, numeric correction/arithmetic failure, invalid business checksum and corporate identity are covered.
- Existing engine/backend tests and all eighteen scenario modules remain passing. Compare against 499 passed/3 skipped, 139 passed, and 1,796 scenario checks.
- Final design contains cause classification, source-line evidence, privacy sink inventory, stage outcomes and unresolved assumptions. Final response has at most 25 lines.
