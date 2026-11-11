# Demo own OCR default

## Goal

Use own as the demo local OCR default on every platform, including macOS, and distinguish confirmed missing job-document fields from uncertain OCR omissions.

## Requirements

- Honor explicit nonempty ENGINE_V2_OCR selections, including off.
- Only missing files for an implicit own selection may select easyocr.
- Return the selection reason from engine_decision and warn once per read when replacing own.
- Never write selection reasons to fallback_reason or quality_note; preserve OcrResult and applicant API contracts.
- Preserve OCR tier order, field extraction, schemas and decision rules. For missing required job-document fields only, use confidence 0.9 when all pages are text layers and 0.5 when any page requires OCR. Attribute the engine to actual page processing.
- Reuse prior research; use synthetic documents only and leave installed models in place.
- Restrict source and documentation changes to the user allowlist; all Trellis writes stay in this task.

## Acceptance criteria

- p17 covers defaults on macOS/Linux, missing files, explicit selections, errors, and actual CPU inference.
- Missing models skip only the actual inference scenario.
- Pytest retains 256 passes; all fourteen existing scenario counts match the supplied baseline.
- Frontend checks pass with only the existing StatusBadge warning.
- Keep all existing assertions; add imported-threshold boundary, PNG, mixed-page, successful-field and applicant-response privacy checks to p16.
- Commit only after zero failures, using the exact user-specified message.

## Decision

The earlier metadata conflict is resolved by the user's instruction: use only engine_decision and warning logs for the local selection reason. The previous investigation remains in research.md.
