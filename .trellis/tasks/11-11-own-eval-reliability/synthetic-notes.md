# B implementation evidence

Three Korean fonts are downloaded from Google Fonts commit `1c96438dec81b2b5078557d91315e31fb29b9462`; all are SIL Open Font License 1.1. Their notices are downloaded and checked alongside the fonts. Binary/font/notice files live under ignored `engine_v2/data/synth_fonts`, never committed. Official licenses were read online on 2026-11-11. Immutable source base: https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl

| Family | Font path after base | SHA256 | OFL source |
|---|---|---|---|
| Nanum Gothic | nanumgothic/NanumGothic-Regular.ttf | `76f45ef4a6bcff344c837c95a7dcc26e017e38b5846d5ae0cdcb5b86be2e2d31` | [OFL](https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl/nanumgothic/OFL.txt) |
| Nanum Myeongjo | nanummyeongjo/NanumMyeongjo-Regular.ttf | `7ed9e8653a8ed04285d51dc343ffea6eb3d9c73afc27383ea8929ee4ffd03205` | [OFL](https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl/nanummyeongjo/OFL.txt) |
| Nanum Gothic Coding | nanumgothiccoding/NanumGothicCoding-Regular.ttf | `787effd7efed2abca88ade231faa8191f4e9fcf85b1805a13ee1dc3724b72089` | [OFL](https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl/nanumgothiccoding/OFL.txt) |

## Generation contract

`python -m engine_v2.tools.fetch_synth_fonts` verifies existing files or downloads each font and OFL notice via a temporary file, verifies SHA256, then atomically replaces. Damaged existing files fail closed; inference/render never downloads.

`python -m engine_v2.tools.make_synth_eval --split test` creates 48 pages under `engine_v2/data/synth_eval/revised`: three document classes × eight conditions × two test fonts. `--output` selects destination and `--fonts` restricts to fonts belonging to the split. No training evaluation is performed in this task. `--split train` uses Nanum Gothic Coding only and stacked header templates. Test uses Nanum Gothic and Myeongjo only and inline header templates. Template families differ structurally (header values below labels, rearranged columns/body), not just seed or degradation. Class semantics/values remain common; this is font/template isolation, not a claim of independent real-document distributions. Rejects cross-split fonts before writing output.

Legacy `documents()`, `render(cells)` and `degrade(...,"phone",...)` remain for existing tests/diagnostics. New generation uses only `phone_weak`/`phone_strong`. Original images are untouched.

Each of four corners has independently sampled displacement magnitudes on both axes, with alternating inward/outward directions to produce genuine trapezoid/skew: weak 3–5%, strong 6–8%. Canvas exposes 7%/10% background margins. Illumination gradient x/y is 13%/8% weak, 24%/16% strong; broad oblique shadow opacity 20%/38%, Gaussian blur sigma 0.65/1.15 px. Dark textured desk surrounds every corner. These are controlled phone-like distortions, not a calibrated real-phone model. Metadata stores original raster size, raster homography, exact independent cells and parameter values for diagnostics. OCR/rectifier never receives generation truth.

Standalone `pipeline.perspective.rectify_document(PIL.Image)` detects exterior convex quadrilaterals from Canny/threshold masks at ≤1200px, rejects frame-touching or small boundaries, selects largest candidate, and returns `.image`, `.applied`, `.matrix` (input→output), `.corners`. No engine default calls this function. Detection failure returns unchanged image and applied=False. Result shape uses measured side lengths, no assumed ground-truth geometry. This method can fail on weak boundary contrast/clutter and is experimental.

## Validation

`pytest engine_v2/tests/test_synth_realism.py -q`: 6 passed. Checks split isolation, deterministic four-corner bounds, background and shading, independent polygon detection, no-op blank image, phone correction without GT metadata. Damaged font hash rejection is also covered. Existing tests are unmodified; `test_synth_eval.py` passes all 6 tests.

Final generated test manifest: `engine_v2/data/synth_eval/revised/manifest.json`, 48 images. Twelve phone images use final signed corner geometry, with source→destination corner projection checked in tests. Pixel-only rectifier probe detects 6/6 weak cases and 0/6 strong cases. Strong failures return original pixels unchanged and must be reported as not applied; no OCR result was used to tune generation or rectifier. Strong shading can weaken the page/background boundary, a known limitation of contour-based detection. This is not evidence supporting default engine activation.
