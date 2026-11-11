# Full-scope review

Reviewer reads code only; no real input or private directories accessed. Scope reviewed against task PRD/design/implementation and backend OCR quality contract.

## Inventory and mappings

- `demo.fixtures.make_samples.BODY_HINTS` / fixture records represent 11 unique document types. Eight tracked PDF templates add seven non-overlapping types (interview confirmation overlaps). The 19-class catalog therefore covers those 18 types plus other.
- Exact existing upload keys are retained for resident abstract, three NHIS types, admin consent, application form. Existing engine category keys are retained for resident register/interview/exam/receipt. `insurance_4` names the document subtype accepted by polymorphic `work_proof`; repeated interview/receipt slots cannot be inferred from content and are not routed by this classifier. Form-only identifiers do not change existing APIs or schema enums.
- Pure portrait photos without text are outside OCR classification capability. The photo-copy class represents the existing text-bearing dummy sample, not visual face detection.
- Default held-out `other` examples contain only the health-insurance bill confounder. This is not evidence of general open-set recognition; unrelated/unseen text is subject to the abstention rule.

## Findings and resolution

1. Missing-model training guidance initially referenced `train/ocr.json`, but the generator writes `train/corpus.json`. Sent to implementation agent; corrected in both model constant and train documentation.
2. Diagnostic CLI argument parsing initially occurred outside privacy suppression, allowing malformed argument strings to appear in argparse errors. Sent to diagnostic agent for localized correction and regression test.

## Model/API review

- Features consume only OCR words and raster dimensions. No sample ID, filename, expected class, authored strings, or truth enters features. Prediction IO reads paths only for bytes/rasterization. PDF text layers are deliberately rasterized and passed to own OCR.
- Vocabulary and IDF are fit exclusively on supplied training data; CLI validation requires explicit synthetic train markers, allocated training font and layout, and all catalog classes. Production split definitions are reused without modifying the old generator.
- Fixed threshold/margin and classifier parameters were set before evaluation. Max-softmax probability is a model score, not a calibrated real-document guarantee; evaluation must report empirical reliability bins.
- Applicant output is allowlisted to category/message. Reviewer output exposes probability and positive logit-difference feature contributions. CLI output is limited to known category/probability/correctness and catches dependency/file/parse errors without verbatim paths or values.
- Persistence uses JSON + numeric NPZ with `allow_pickle=False`, shape/finite validation, no executable serialization. Weights and generated corpora live under ignored trees.
- New tests cover deterministic fit/round trip, uncertainty threshold/margin, empty/unseen inputs, other versus abstention, geometry scale invariance, same-path content swaps and renames, PDF rasterization, safe private output, held-out split rejection.

## Pending integration gates

Actual trained artifact, held-out metrics/timing, diagnostic evidence tables, final unchanged 108-test subset, 13 scenario runners, frontend checks, protected-path diff and staged-secret/generated-asset audit remain the parent integration gates. Final reviewer pass will update this record when those artifacts are available.

## Diagnostic final pass

The safe diagnostic parser now sanitizes invalid option values; five new diagnostic tests pass per implementation evidence. Corrected stale own OCR line references to 134/135. Independently compared all 93 failed-field rows in the committed report against the generated synthetic JSON: each case/field appears exactly once and every expected/actual pair matches. Recounted 31 cases, 67 correct and 93 failed field comparisons. Examined the referenced name/RRN fallback, normalized row grouping, NHIS name/date association and acquisition header-window branches; report explanations match these paths. Explicit Apple runtime and real-document-rate limitations are appropriate. No blocking diagnostic finding remains.

## Evaluation review follow-up

Requested preservation of unsupported positive rule labels in confusion-matrix columns (a matrix restricted to catalog classes would silently omit such cases). Requested model-class/provenance checks against the evaluated training corpus. Awaiting integration update and actual held-out report.

## Classification documentation/evaluator second pass

The evaluator now retains unsupported positive baseline labels in confusion columns, with a matrix conservation regression assertion. It validates catalog classes and training artifact corpus hash. Reviewed `engine_v2/docs/classifier.md`: inventory arithmetic, existing-key aliases, pure-photo limitation, narrow other coverage, correlated synthetic split, probability calibration caveat, private CLI semantics, Mac not-run caveat, and relative report links are accurate. One optional robustness finding remains for intentionally incomplete all-other evaluation subsets: common-rule coverage has an empty denominator; full planned evaluation is unaffected. Parent was notified.

Parent reports full pytest 126 passed (108 unchanged + 18 new), all 13 scenario runners zero failures after an environment-related sandbox retry, frontend checks passed with existing warnings. Actual classification generation/training/evaluation and final staged audit remain pending; these are not yet claimed verified by this reviewer.

The incomplete-subset finding is resolved by requiring full test-catalog coverage. Reviewed the added actual filename experiment: two clean synthetic contents are passed through `predict_file` and own OCR four times, first using an identical misleading path and then another name; accepted types and full Prediction equality are checked. Paths only identify raster IO, temporary files are cleaned up, and experiment work is excluded from classifier timing. No finding in this helper.

## Actual evaluation artifact audit

Reviewed generated `evaluation.json` after all 304 train and 304 test pages completed. Independently recounted model and baseline accuracy from individual rows and checked confusion-matrix and class-support totals: all 304 test pages are represented. Deployed model accuracy/macro F1 are **0.210526/0.210526**, with **0.789474 abstention**; baseline accuracy/macro F1 are **0.565789/0.537068**, with **0.328947 abstention**. Candidate top-1 accuracy is 1.0 but must not be represented as deployed performance. The fixed pre-test threshold rejects 240 correctly ranked examples; no threshold should be changed based on these test observations. The standalone prototype does not alter existing application behavior. Future confidence calibration needs a training-only validation design and a new untouched evaluation, not test-threshold tuning.

Timing includes feature generation, logits and explanations but excludes OCR/load/IO: measured mean 2.004 ms, maximum 13.829 ms, every page below 100 ms. Four additional actual own-OCR filename runs all selected the expected content class, and misleading renames produced exactly equal predictions/probabilities. Diagnostic and model evidence are internally consistent. Final human-facing report and staged-path/content audit remain to inspect.

## Final report review

The final report prominently leads with the thresholded classifier's worse operational accuracy and high abstention, distinguishes candidate ranking, and advises against replacing the current rule path. No inference bug was found in the runtime sublinear TF-IDF/L2 transform or softmax relative to the fitted representation. No test-driven threshold change occurred.

Independently compared both published full confusion matrices to generated evaluation JSON: exact match. Both recorded corpus SHA256 values match the corresponding files. Per-run scenario counts total 1420 checks plus eight forms. Class/support, degradation, confidence-bin, timing, four-call filename and extraction diagnostic tables are consistent. Relative links resolve to the intended repository documents. Suggested two editorial changes: use “headline comparison” rather than “headline improvement,” and call 100 ms/page a measured bound for tested pages with a loaded model rather than a general guarantee.

No blocking code/report finding remains. The baseline production paths and original tests remain unchanged; the new classifier is standalone and intentionally unsuitable for replacing the rule path at current coverage. Parent owns the final staged secret/asset/protected-path audit and the authorized commit gate.
