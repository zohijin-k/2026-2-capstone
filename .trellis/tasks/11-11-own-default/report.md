# Own default and source-aware job-document validation

## Final result — 2026-11-12

Implementation and all required checks pass on feat/own-default. The user explicitly authorized implementation and the final commit. Existing working changes and the applicant-check research directory are included. No branch switch, stash, reset, amend, push or merge was used. Repository README files, general documentation, specifications, workflow, engine-v2 source, decision/score rules and the OCR chain were not edited. No real documents were opened or generated.

## Implementation contract

- engine_decision() -> tuple[str, str] returns (engine, replacement reason). A nonempty ENGINE_V2_OCR wins verbatim. Otherwise own.MODEL_DIR is checked against all ASSETS keys with is_file(); missing files alone choose easyocr. No inference, checksum, download or logging occurs during selection. LocalOcr.read logs one warning for a replacement. No result fields or reason metadata are added.
- Existing _load_pages returns pairs of actual PageImage source and engine-v2 OCR result. These pairs already reach _from_job_doc; no engine-v2 change is needed. _pages_engine uses pdftext only if all pages are text_layer, otherwise the actual OCR result engine. The text-PDF branch no longer overwrites an OCR engine with pdftext.
- Required fields present: existing confidence calculation stays unchanged. Required fields missing: all text-layer pages use confidence 0.9, any OCR page uses 0.5, still capped by existing type confidence.
- Existing check_document consequently returns FAIL with only MISSING_REQUIRED_FIELD for a text-layer exam without an exam date, and NEEDS_REVIEW with LOW_OCR_CONFIDENCE plus REQUIRED_FIELD_UNREADABLE for OCR omissions. Existing recapture guidance is retained; no rules or messages were changed.
- The demo default changes on macOS too. The separate engine-v2 CLI still defaults to applevision on macOS and own elsewhere. Environment names/choices, model path and fetch command remain unchanged.

## p16 assertions and coverage

The approved neutral sentence extends the original synthetic missing-date input from 46 to 59 extracted characters. Existing assertion calls and all existing functions were compared by AST with HEAD; the only exceptions are that approved input extension and three calls to new test groups. No existing assertion or expected result changed.

TEXT_LAYER_MIN_CHARS is imported from preprocessing, currently 50. Boundary inputs are exactly 49, 50 and 51 characters measured using get_text().strip(). The 49-character page renders and calls the own registry once, returns own/0.5 and NEEDS_REVIEW. The 50/51-character pages never call OCR, return pdftext/0.9 and FAIL with only MISSING_REQUIRED_FIELD. Mixed 51+49 and 49+51 page orders both return own/0.5 and NEEDS_REVIEW.

A PNG without the date returns NEEDS_REVIEW, no FAIL severity and existing recapture guidance. Complete PNG and text PDF inputs retain confidence 0.95 and PASS. Five synthetic upload cases check HTTP status and application verdict; upload, list and checklist responses contain no engine strings or metadata. New routing tests use deterministic synthetic OCR words; p17 retains actual own CPU inference.

p16 now has 29 original plus 67 added checks = 96 passes. One initial new call-count check patched an imported dispatcher instead of its bound reference; instrumentation was corrected to count the registry callable. All product verdict checks and existing assertions passed throughout this correction.

## Full validation

The fifteen modules ran in the requested non-stopping shell loop. TestClient stalled inside the sandbox, so the p16 API check and full loop ran outside after approval. No product/test expectation was changed for the sandbox issue.

| Scenario | Baseline passes | Final passes | Failures |
|---|---:|---:|---:|
| p2 | 53 | 53 | 0 |
| p3 | 150 | 150 | 0 |
| p4 | 182 | 182 | 0 |
| p5 | 152 | 152 | 0 |
| p6 | 249 | 249 | 0 |
| p7 | 253 | 253 | 0 |
| p8 | 89 | 89 | 0 |
| p9 | 96 | 96 | 0 |
| p11 | 38 | 38 | 0 |
| p12 | 29 | 29 | 0 |
| p13 | 26 | 26 | 0 |
| p14 | 8 forms | 8 forms | 0 |
| p15 | 129 | 129 | 0 |
| p16 | 29 + new | 96 | 0 |
| p17 | 75 | 75 | 0 |

- pytest engine_v2/tests: 256 passed in 43.73 seconds.
- TypeScript build, oxlint and Vite: passed. The one preexisting StatusBadge.tsx warning and Vite large-chunk advisory remain.
- Both Python requirements were successfully installed/confirmed already satisfied in the preceding continuation; npm ci also succeeded there. Dependency manifests did not change.
- p17 SKIP: 0. Platform defaults, partial/missing assets, explicit overrides, inference/checksum errors, off behavior, actual CPU inference and applicant/officer metadata boundaries all pass.
- Scenario log: /tmp/own-default-source-scenarios.log
- Pytest log: /tmp/own-default-source-pytest.log
- Focused p16 log: /tmp/own-default-source-p16-outside.log

## Review and research audit

All changed paths are confined to localocr.py, p16, p17, the two own documentation files and the two explicitly allowed Trellis directories. Model assets, fonts and generated evaluations are excluded. Full-source review of research.md, probe.py, diagnose.py and verify.py found synthetic values and source/test paths only, no real-document values or filenames. The snapshot hashes in verify.py describe the earlier research baseline; it is a historical preservation verifier, not a post-change regression test. Those four research files remain unchanged.

The source-confidence contract and the earlier 46-to-59-character failure are recorded here because specification/workflow writes are prohibited. All previous research remains available in the two research.md files. A future broad source-routing or missing-field policy change is outside this work.

## Commit

Required message: feat(demo): 로컬 OCR 기본 엔진을 own으로 통일하고 글자층·OCR 출처별로 필수 항목 부재 판정을 분리

No co-author or session trailers. No amend or push.

## README impact

Demo local OCR now defaults to own on every platform; explicit nonempty ENGINE_V2_OCR wins and only missing files for implicit own select easyocr. Confirmed text-layer missing fields use the existing missing-field FAIL path, whereas OCR omissions use the existing NEEDS_REVIEW and recapture guidance. README files are intentionally untouched.
