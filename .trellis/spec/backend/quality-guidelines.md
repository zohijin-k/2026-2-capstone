# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

<!--
Document your project's quality standards here.

Questions to answer:
- What patterns are forbidden?
- What linting rules do you enforce?
- What are your testing requirements?
- What code review standards apply?
-->

(To be filled by the team)

---

## Forbidden Patterns

<!-- Patterns that should never be used and why -->

(To be filled by the team)

---

## Required Patterns

<!-- Patterns that must always be used -->

(To be filled by the team)

---

## Testing Requirements

<!-- What level of testing is expected -->

(To be filled by the team)

---

## Code Review Checklist

<!-- What reviewers should check -->

(To be filled by the team)

## OCR engine compatibility

- Preserve `engine_v2.pipeline.ocr` imports and top-left pixel OcrWord bounds when adding adapters.
- Own OCR uses CPU ONNX Runtime, pinned weights/dictionary hashes and no inference-time downloads.
- Synthetic CER and extracted field accuracy are separate: perspective can preserve text while breaking coordinate-based extraction.
- Keep real-document masking enabled by default; only explicitly synthetic evaluation may opt out.
- Model assets and generated evaluation images/results are ignored, never staged.
