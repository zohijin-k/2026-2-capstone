# Confirmed failure filtering design

## Change boundary and baseline

Base: cdcf68d. Changes belong to engine_v2 extractors and demo OCR conversion, document checks and eligibility/API adapters. No engine/ changes. The user has authorized all stage commits. Initial dirty path: untracked docs/audit/ (excluded throughout).

| Case | Current flow at base | Planned change / certain evidence |
|---|---|---|
| 1 | demo/backend/ocr/base.py:121 unreadable; demo/backend/rules/doc_check.py:490 engine result mapped by severity | Preserve UNREADABLE_FILE FAIL independently of zero confidence |
| 3a | demo/backend/ocr/localocr.py:702 generic classification; engine_v2/engine.py:40 no daily extractor | Dedicated coordinate daily-work reader; explicit period/table completeness; compare duplicate copies; provisional monthly continuity |
| 3b | engine_v2/extractors/insurance_4.py:499 requires one physical page; demo/backend/ocr/localocr.py:666 passes all pages | Isolate confidently identified one-page form from dissimilar attachments; leave duplicate/same-family pages under strict validation; evaluate full insurance rows |
| 4 | demo/backend/rules/doc_check.py:505 confirmed issue date -> DOCUMENT_ISSUED_TOO_EARLY | Regression only |
| 5 | engine_v2/extractors/resident_abstract.py:306 rows depend on date; demo/backend/rules/facts.py:324 application fallback | Independently record reliable address header/date omission evidence; fail only with reliable form and table evidence; retain explicit fallback warning in facts basis |
| 6 | demo/backend/ocr/localocr.py:706 unknown -> None -> pdftext; demo/backend/rules/doc_check.py:391 early UNKNOWN review | Retain source pixel dimensions at common OCR boundary; fail only objectively tiny page AND unknown type/mostly missing required values; preserve independently reliable page markers |
| 7 | demo/backend/rules/doc_check.py:579 skips absent monthly map | Independent period evidence before monetary completeness; title/range/rows must not conflict; complete arithmetic needed for zero/blank amounts |
| C | demo/backend/api/review.py:131 _blockers; :498 final-check; :710 submit reuses _blockers | Shared eligibility assessments for blockers, review and early identity/status; existing kind/message/goto UI |

## Codes and certainty

FAIL: UNREADABLE_FILE (existing), IMAGE_RESOLUTION_TOO_LOW, MISSING_ADDRESS_DATES, MISSING_BILLING_MONTHS (existing), DOCUMENT_ISSUED_TOO_EARLY (existing), WORK_CONTINUITY_NOT_MET with detail codes; eligibility OVER_LIMIT / AGE_OUT_OF_RANGE. Unknown periods, damaged headers, conflicting rows/copies/identity and unreadable values remain NEEDS_REVIEW.

Low-resolution hard cutoff: **short edge < 650 AND long edge < 900 pixels**, independent of orientation, plus unknown classification or fewer than half of applicable essential fields readable. This is a deliberately narrow product threshold inferred from the supplied two boundary examples, not a validated OCR limit (추정). It catches 586x709, excludes 970x1282 and normal 1654x2338/2065x2923/2480x3505. At/near the cutoff preserve review; dimensions alone never reject readable documents. Source dimensions must be measured before rendering/upscaling.

Address omission: high-confidence abstract title plus observed number/address header with absent occurred/reported labels, or observed address rows without any date. Never infer from absent parsed rows alone. Guidance uses the user-approved descriptive wording; exact Government24 option name is unverified (추정), not a quoted UI label.

Payment omission: parse unique query range, reconcile every observed payment title period and month row. A reliable exclusion survives unrelated monetary confidence cap; conflicting or missing range stays review. Explicit zero/blank needs complete observed columns and arithmetic. Legacy complete monthly maps retain compatibility.

Mixed pages: isolate only when exactly one supported single-page form is identifiable with its own 1/1 marker and all other pages are dissimilar/unknown; same-family extra pages remain incomplete. Store additional page indices in extracted metadata, visible to officer.

Work continuity is **provisional (잠정)**: one program setting `work_continuity_months=5`, start announcement minus calendar months, end announcement (2025-10-03 through 2026-03-03 for savings). Monthly daily coverage ends previous calendar month. Business opening deadline 2025-09-03 in program settings. No work requirement means no work rule. Identity + complete structure + reliable rows required for negative eligibility. Conflicting independent documents -> UNDETERMINED. Work contract parsing and 15-hour inference excluded.

## Test and commit sequence

1. Plan artifacts (this commit).
2. Fictitious source-shaped coordinate fixtures and encrypted PDF; record baseline reproduction.
3. Password / payment period checks and issue regression.
4. Tiny-image and missing-address-date checks.
5. Mixed-page isolation.
6. Daily work record reader and adapters.
7. Provisional continuity and review/checklist integration.
8. Submission blockers, fresh server recheck, minimal frontend.
9. Acceptance/uncertainty/normal regressions.
10. Full suite comparison, expectation log, code-spec and final evidence.

Run `.venv/bin/python -m pytest engine_v2/tests -q`, backend equivalent and all run_p*_scenarios modules. Inspect test sources first to avoid private-document execution. Frontend lint/build when touched. No tests removed or weakened; intentional changed expectations documented separately.

## Evidence availability

The supplied /tmp/layout_shape5.txt has nonzero stat size but reads as an empty string in this runtime; initial `wc -l` is zero. Exact coordinate reproduction is pending user-provided readable contents. Do not claim a real-document replay. Synthetic fixtures will use request-described layout and established synthetic form helpers; unverified source equivalence is explicitly 추정.
