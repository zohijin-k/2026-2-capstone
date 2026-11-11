# Design

Standalone engine_v2/classifier package: canonical slot-key catalog, deterministic synthetic extension reusing make_synth_eval render/degradation/split definitions, own OCR cache, char n-gram and normalized position features with CPU multinomial logistic regression. No runtime wiring into engine/application or changes to scoring. Train-only fitted vocabulary, fixed seed/threshold, no test tuning. Safe JSON+numeric weights artifact under ignored engine_v2/models/classifier (avoid untrusted pickle). Baseline directly calls unchanged pdftext.classify and maps enum labels. Unknown class is distinct from abstention.

Input API accepts words and page size only. CLI always rasters PDFs through own OCR; file paths are IO only. Applicant response allowlists category/review message; reviewer adds probability and model feature contributions. Private CLI emits only category/probability/correctness with captured logs and generic failures.

Diagnostic tool is a new file, reuses unchanged generators/extractors and adds explicit rotation/blur probes, masking default with synthetic-only opt-out. Evidence and tables in task report. Split implementation: classifier model/API/tests, diagnostic tool/evidence, main integration owns catalog/data/evaluation/report. No modifications to protected paths. Generated outputs remain ignored. Rollback is removal of standalone additions.
