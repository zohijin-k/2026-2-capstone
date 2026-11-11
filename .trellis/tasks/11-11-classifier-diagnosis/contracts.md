# Preserved contracts and lessons

The Trellis spec-update review was performed. New knowledge belongs in the task notes and public engine documentation because the user explicitly prohibited changes to shared specs in this task.

## Scope / trigger

Standalone synthetic training/evaluation and privacy-safe classification/diagnostic CLIs. No application wiring, extraction fixes or scoring changes.

## Signatures

- `model.fit(samples, seed=20261111) -> DocumentClassifier`
- `model.predict(words, pixel_size, threshold=None, margin=None) -> Prediction`
- `Prediction.applicant_view()` and `.reviewer_view()` are distinct projections.
- `python -m engine_v2.classifier.data --split train|test`
- `python -m engine_v2.classifier.train --corpus PATH --output DIR`
- `python -m engine_v2.classifier.evaluate --corpus TEST --training-corpus TRAIN --output JSON`
- `python -m engine_v2.classifier.predict FILE --expected KEY`
- `python -m engine_v2.tools.extract_diag --synthetic-suite --unmasked-synthetic`
- `python -m engine_v2.tools.extract_diag FILE --doc KEY --engine own|applevision`

## Contracts

Feature input is OCR text/bounding boxes and raster dimensions only; input paths, expected categories, authored text, synthetic transforms and field truth are never classification features. Training corpus must explicitly be synthetic/train, contain train-only font/layout, and cover every catalog class. Test validates the analogous held-out properties and rejects font/template/image-hash overlaps; model training hash must match supplied training corpus.

Private prediction emits only category/probability/correctness. Default diagnostic output masks all recognized/expected/extracted values, including header trace. Arbitrary file input can never use the unmask flag. Unknown truth keys and native/exception logs are excluded. Other is a trained class; abstention is separate and remains an error in headline metrics.

## Validation and errors

| Input / failure | Outcome |
|---|---|
| Missing model | Explicit training command with correct generated corpus path |
| Empty or wholly unseen text | Human review even if thresholds are zero |
| Low top probability or small top-two margin | Human review |
| Test font/layout passed to training | ValueError before fitting |
| Training artifact does not match training corpus | Evaluation rejected |
| Invalid private CLI argument, path or dependency failure | Fixed generic message, no sensitive exception text |
| Real-file diagnostic unmask requested | Rejected before input read |
| Positive rule result outside catalog | Preserved extra confusion column, never dropped |

## Good/base/bad cases

Good: identical OCR under renamed files gives identical prediction; replacing bytes at the same filename changes prediction with content. Base: health-insurance bill can be other while missing rule match is abstention. Bad: counting missing rules as correct other or dropping abstentions from accuracy inflates results.

## Tests

New suites check seed identity/safe persistence, threshold+margin, empty/unseen text, same-path swaps/renames, forced PDF rasterization, private output/errors, font/layout/split gates, all-category synthetic inventory, confusion conservation, masked diagnostic traces and synthetic-only unmask.

## Wrong versus correct

Wrong: report a requested strong-phone correction as applied. Correct: retain `rectification_applied=False` and count the unchanged replay separately. Wrong: assume a common OcrWord API means common token size between own and Vision. Correct: compare boxes empirically on Mac; report current code assumptions and Linux limitation. Wrong: promise broad real-document accuracy from synthetic correlated pages. Correct: report measured synthetic results and narrow other coverage explicitly.
