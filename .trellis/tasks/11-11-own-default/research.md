# Investigation: demo own default

## Start and scope

- Initial git status --short was empty. Fetch and branch creation succeeded with sandbox escalation because .git is protected. feat/own-default tracks origin/main at c981c1a.
- Read .trellis/workflow.md and backend spec index, directory, error, logging, and quality guides. No specification or workflow writes.
- Trellis helpers under .agents/skills and .codex/agents are absent. Created this planning task using task.py create --no-start; no runtime pointer or workspace journal writes.
- No implementation, dependency installation, model loading, private-document access, or test execution occurred.

## localocr.py data flow

- Header describes ENGINE_V2_OCR choices applevision, easyocr, paddle, off and platform-specific defaults; own is currently absent from that explanation.
- _engine_name() returns a nonempty ENGINE_V2_OCR verbatim, otherwise applevision on darwin and easyocr elsewhere. Empty strings currently act as unspecified.
- LocalOcr.read chooses the engine, calls _read(file_path, engine), and fills result.engine only when the returned demo result has no engine name.
- _read passes the selected name into engine_v2.engine._load_pages for supported text PDFs. That function reads text-layer words directly; any raster page uses run_ocr. The demo text-layer result explicitly records engine=pdftext.
- Raster input passes the selected name to run_ocr for each preprocessed page. An engine_v2 result with error causes LocalOcr to return None. Successful words are classified, extracted, and converted into a demo OcrResult. Unsupported, missing, encrypted, or unreadable inputs continue to the next tier under existing behavior.
- off bypasses raster OCR; supported text-PDF extraction remains available. Preserve that distinction in any later implementation.

## Two distinct OcrResult contracts

The demo dataclass in demo/backend/ocr/base.py has these complete fields:

detected_doc_type, confidence, image_quality, issue_date, has_signature,
fields, bboxes, is_encrypted, is_screen_capture, page_count, tier, engine,
fallback_reason, quality_note, classification_evidence,
classification_confidence, elapsed_ms.

It has no error field. engine and fallback_reason are officer-only metadata;
quality_note is an existing officer-only quality memo. A new field has not
been shown necessary, and no fields were added.

The engine_v2 OCR dataclass instead has engine, words, elapsed_sec, error,
and a text property. Missing models and inference errors are recorded there;
the demo LocalOcr currently returns None on these errors rather than retaining
an error field in its own result.

## Mandatory stop: fallback_reason conflicts with JBAI

- demo/backend/ocr/__init__.py:40-43 catches OcrFallback from JBAI, appends its reason to fallback_reasons, and optionally retains fallback_result.
- At lines 66-67 it copies accumulated reasons into result.fallback_reason only if the result field is empty.
- Therefore setting LocalOcr's fallback_reason to an own-to-easyocr reason suppresses the preceding JBAI reason. The field is not merged and the accumulated reason is lost from the returned result.
- p15 asserts exact JBAI fallback_reason values for transport, reader, classification, and quality failures, including the local-unavailable path. Its fake engine does not exercise the simultaneous missing-own case.
- This matches the user's explicit investigation stop condition. Do not implement, change the chain, or repurpose another field as a workaround without revised direction. No implementation or commit was made.
- A possible later design is recording the local engine selection note in existing quality_note while reserving fallback_reason for chain failures, but its semantics need to be accepted before lifting this explicit stop gate.

## engine_v2 registry and defaults

- ENGINES contains own, applevision, easyocr, paddle. off is a demo control value, not a registered OCR engine.
- run_ocr rejects an unknown engine with ValueError before its try block. ImportError becomes error="미설치: {e.name}"; other exceptions become error="{exception type}: {message}" with elapsed time. It does not choose another engine.
- default_engine() honors nonempty ENGINE_V2_OCR, otherwise applevision on darwin and own elsewhere. The demo does not call this helper; its default is separately defined.

## own model paths and failures

- own.py imports MODEL_DIR and verify_models from engine_v2.tools.fetch_own_models. The default directory is engine_v2/models/own relative to the repository.
- sessions(), cached with lru_cache, calls verify_models(MODEL_DIR), creates CPU ONNX sessions for det.onnx and rec.onnx, and reads korean_dict.txt. No automatic download.
- verify_models checks every asset with is_file() and pinned SHA256. Missing files raise FileNotFoundError with "own 모델 없음: .venv/bin/python engine_v2/tools/fetch_own_models.py". Corrupt assets raise ValueError with an own SHA256 mismatch message. These are distinct from optional dependency ImportError.
- Future synthetic missing-model tests can patch own.MODEL_DIR to a temporary nonexistent directory without moving installed assets. Account for the sessions cache when testing actual inference failures.
- No engine_v2 helper was added. Model paths and fetch usage remain unchanged.

## Existing scenarios and unset environment

- p8 installs a fake registered engine and sets ENGINE_ENV=fake for OCR tests; it also sets off to verify raster bypass and text-PDF behavior, then restores the original environment.
- p15 uses p8's fake engine installer for local fallback comparisons, isolates JBAI environment variables, and restores them. It checks exact fallback metadata and applicant/officer boundaries.
- p16 installs fake and restores ENGINE_ENV in finally.
- Other scenarios do not uniformly set ENGINE_ENV: p2's text-PDF and synthetic screenshot path, for example, calls read_document without selecting an engine. Defaults can therefore affect existing scenario timing and behavior. They must be verified after any eventual change.

## Documentation and planned verification (not executed)

- own-ocr.md introduction and compatibility section still describe demo connection/default updates as excluded. own-ocr-history.md:64 says demo keeps its separate non-mac easyocr default. Both are accurate for the unchanged implementation and were left untouched.
- If the stop gate is lifted, record a design and execution plan before task activation, implement within the user's allowlist, add synthetic p17 tests including combined JBAI/local metadata, then install both requirements files, run pytest, all 15 scenarios in a non-stopping loop, and frontend npm ci/tsc/oxlint/vite.
- Preserve all 14 baseline counts and 256 pytest passes. p17 actual inference must skip only when own model assets are absent. Retain the baseline single StatusBadge.tsx warning.
- Stage and inspect only allowed files after all checks pass, then create the exact requested commit without amend, push, merge, or co-author trailers.
- No new specification writes: expressly prohibited by the user; findings are kept only in this task folder.
