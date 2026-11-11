# Synthetic document classifier and extraction diagnostics

This is the first locally trained document classifier: a standalone CPU tool. It does not change the running application's classification, extraction, eligibility rules or scores. All training and evaluation inputs are fictitious rendered pages. The experiment measures transfer across synthetic font/layout families, not real-document accuracy.

## Existing keys and baseline

`demo/backend/rules/required_docs.py` defines upload slots. `demo/backend/rules/doc_types.py` defines Korean document labels; `engine_v2/schemas/models.py` defines an overlapping but different engine enum. The new `classifier/catalog.py` keeps existing keys where available and explicitly maps the others. Do not use document predictions as automatic slot routing: `work_proof` accepts several types, and several interview/receipt slots accept the same type.

`demo/backend/ocr/pdftext.py:26` defines ordered title/phrase keywords. `classify_with_evidence` removes whitespace and takes the first matching keyword. It is reused unchanged on the exact same own OCR words in evaluation, with no filename, expected slot or reference text. A missing rule match is abstention, not a correct prediction of `other`. Specialized body detectors also exist in the resident/NHIS extractors; those are not an all-document baseline. Fixture filename dispatch in `demo/backend/ocr/fixture.py` is deliberately excluded.

| Key | Category / repository source |
|---|---|
| resident_abstract | Resident abstract; sample + exact slot |
| resident_register | Resident register; sample + existing engine key (demo label RESIDENT_CERTIFICATE) |
| nhis_payment | NHIS payment certificate; sample + exact slot |
| nhis_qualification | NHIS qualification certificate; sample + exact slot |
| nhis_acquisition_loss | NHIS acquisition/loss certificate; sample + exact slot |
| insurance_4 | Four-insurance subscription; sample, subtype of polymorphic work_proof slot |
| interview_confirm | Interview confirmation; sample + job_interview_confirmation PDF, existing engine key |
| exam_admission | Exam attendance confirmation; sample, existing engine key |
| exam_score | Exam transcript; sample, existing engine key |
| receipt | Payment receipt; samples for suit/photo/exam purposes, existing engine key |
| id_photo_copy | Text-bearing photo-copy dummy sample, demo enum name |
| admin_info_consent | Form5 administration information consent; exact slot |
| application_form | Form1 savings application; exact slot |
| self_check | Form2 eligibility self-check; form-only identifier |
| consent_form | Form3 information collection/use consent; existing engine key |
| third_party_consent | Form4 third-party consent; form-only identifier |
| job_application | Job package application PDF identifier |
| job_consent | Job package combined information consent PDF identifier |
| other | Health-insurance/electric bills in training; held-out health-insurance bill confounder |

The 19 classes cover all 11 unique sample categories and eight PDF templates (interview overlaps), plus other. Parent-name variations share the same document category. The old extraction evaluation's composite four-insurance/acquisition certificate is separated into two unambiguous classification samples. Bill is `other`, receipt is `receipt`, payment certificate is `nhis_payment`.

All requested confusable pairs are synthetically represented: abstract/register, qualification/acquisition-loss, payment certificate/bill/receipt, four-insurance/acquisition-loss. No requested textual pair is omitted. Pure portrait photographs without OCR text cannot be recognized as photo copies by this method; only the existing text-bearing dummy is represented. There is no coverage claim for official form artwork, unknown organizations or arbitrary other documents. Current held-out other examples are health-insurance bills, so open-set accuracy is unmeasured. Engine enum entries with no repository sample/template, such as bankbook, are outside this inventory.

## Model and output contract

`classifier/data.py` reuses `make_synth_eval.SPLITS`, rendering and all eight degradations: clean, scan300, blur, noise, rotate, jpeg, phone_weak, phone_strong. Train uses Nanum Gothic Coding and `stacked_header_v1`; test uses Nanum Gothic/Myeongjo and `inline_header_v1`. The header labels/values move between vertical and horizontal arrangements and the body changes placement. Two train content variants versus one per held-out font give 304 train and 304 test pages. Train/test fonts, layout IDs and image hashes must be disjoint. Vocabulary, IDF and coefficients use training OCR only. Reference text, layout transforms, class IDs and filenames never enter features. Header/body wording is related across splits; these pages are correlated variations, not independent real forms.

Own OCR is the existing frozen public PP-OCR pipeline; its weights are not retrained. We train the document classifier on its actual recognized strings and bounding boxes. OCR caches are content-addressed by image SHA256 and remain local; no authored reference text is substituted for OCR errors.

The model uses NFC/lowercase/whitespace-normalized character 2–4 grams, separate top-30%-page grams, and coarse normalized position/box-size statistics. Sublinear TF-IDF with L2 normalization feeds multinomial logistic regression (`C=8`, `lbfgs`, tolerance `1e-7`, 1000 iterations, seed `20261111`). These choices are small, CPU-friendly and give inspectable feature contributions. Scikit-learn's [logistic regression reference](https://scikit-learn.org/1.7/modules/generated/sklearn.linear_model.LogisticRegression.html) describes the regularized linear model.

Threshold `.65` and top-two probability margin `.15` were fixed before test evaluation. Empty/unseen text abstains even if the intercept favors a class. `other` is a learned category; abstention is `document_type=None` with `판별 불가 → 담당자 확인`. The score is a softmax probability, not a guarantee of correctness or a calibrated real-document probability.

`Prediction.applicant_view()` allowlists category and message. `reviewer_view()` adds candidate, probabilities, margin and up to five positive feature contributions to the winning-versus-runner-up logit. These contributions may contain recognized substrings and are for authorized reviewer use only; the private CLI never prints them.

Artifacts are JSON metadata and numeric NPZ arrays loaded with `allow_pickle=False`, under ignored `engine_v2/models/classifier/`. Metadata records seed, threshold, hyperparameters, corpus SHA256, package versions and training count. A missing artifact returns a training command. Fixed-seed reruns are reproducible on the same environment; bitwise identity across different BLAS/CPU/package versions is not promised.

## Reproduce on CPU

From repository root, with the existing own OCR and font assets installed:

```bash
.venv/bin/python -m pip install -r engine_v2/requirements.txt
.venv/bin/python -m engine_v2.tools.fetch_own_models
.venv/bin/python -m engine_v2.tools.fetch_synth_fonts
.venv/bin/python -m engine_v2.classifier.data --split train
.venv/bin/python -m engine_v2.classifier.data --split test
.venv/bin/python -m engine_v2.classifier.train \
  --corpus engine_v2/data/synth_eval/classifier/train/corpus.json
.venv/bin/python -m engine_v2.classifier.evaluate \
  --corpus engine_v2/data/synth_eval/classifier/test/corpus.json \
  --training-corpus engine_v2/data/synth_eval/classifier/train/corpus.json \
  --check-filenames \
  --output engine_v2/data/synth_eval/classifier/evaluation.json
```

Generation invokes own OCR for each rendered page, so this is much slower than fitting or inference on cached OCR. Run the same generation command to reuse matching cached outputs; change the output directory for a fresh end-to-end run. Model files, fonts, synthetic images, OCR caches and generated metric JSON remain ignored and are never committed.

## Mac input benchmark (no text output)

Generate/train locally as above, or explicitly transfer the ignored model artifact using an approved local method. The command below does not search directories or create an input directory. Run it only against the specific file you intend to process:

```bash
.venv/bin/python -m engine_v2.classifier.predict \
  "$HOME/Documents/ocr-input.pdf" \
  --model engine_v2/models/classifier \
  --expected resident_abstract
```

Images and every PDF page are rasterized and passed to own OCR, including PDFs with searchable text. Filename is only an IO handle. Output has three fields per page: `document_type`, `probability`, `correct`. Without `--expected`, `correct` is null. Abstention uses the human-review message and is incorrect against any expected known class. Dependencies' native/Python logs and exception text are suppressed. The CLI never prints paths, OCR text, truth values or evidence substrings. Multi-page input uses the same expected category for all pages; run pages separately if their reference types differ. No Mac or real-document run was performed in this CPU/Linux experiment.

## Dependencies and licensing

Additional direct dependency: **scikit-learn 1.7.2**, pinned for API/reproduction stability, [BSD-3-Clause license](https://github.com/scikit-learn/scikit-learn/blob/1.7.2/COPYING). This environment additionally installed SciPy 1.18.1, joblib 1.6.0, threadpoolctl 3.8.0 and cloudpickle 3.1.2 (BSD-3-Clause metadata; SciPy wheels include additional bundled-library notices). Existing NumPy is 2.5.4. No pickle/joblib model deserialization is used. Check redistributed wheels' bundled notices if packaging binaries.

Existing OCR model licenses and hashes are documented in [own-ocr.md](own-ocr.md); existing Nanum fonts are OFL-1.1. This change downloads no new OCR model or font family. Existing PyMuPDF rendering dependency/license remains unchanged. Trained weights and third-party binaries/fonts are not distributed in the commit.

## Results and read-only extraction diagnosis

Measured fixed-threshold accuracy is **21.05%**, macroF1 **0.2105**, with **78.95% abstention** (64/304 accepted, all correct). The unchanged rule baseline is **56.58%** / **0.5371**. Candidate top1 is100%, but this must not be presented as deployed accuracy. The current model is a training/diagnostic artifact, not a validated replacement for the rule path. Keep the predeclared threshold; future calibration must use training-only validation and a fresh held-out set. Loaded-model inference max13.83ms/page meets100ms; fresh interpreter imports+load take1.493s separately.

The measured classification tables, full confusion matrices, confidence bins, timing, filename experiment and regression results are in [the task report](../../.trellis/tasks/11-11-classifier-diagnosis/report.md). The [extraction diagnosis](../../.trellis/tasks/11-11-classifier-diagnosis/extraction-diagnosis.md) records all 31 replay cases and 93 failing fields, exact expected/actual values, source lines, box assumptions, effects and proposed-fix risks. The low historical extraction scores were reproduced without changing extraction or scoring.

```bash
mkdir -p engine_v2/data/synth_eval/diagnosis
.venv/bin/python -m engine_v2.tools.extract_diag \
  --synthetic-suite --include-legacy --unmasked-synthetic \
  --output engine_v2/data/synth_eval/diagnosis/report.json
# Actual input is always masked; there is no real-file unmask option:
.venv/bin/python -m engine_v2.tools.extract_diag \
  "$HOME/Documents/ocr-input.pdf" --doc resident_abstract --engine own
```
