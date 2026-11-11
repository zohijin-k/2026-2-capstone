# A/C measured report — synthetic only

Baseline: `004e45a`, branch `feat/own-ocr`, CPU-only WSL Ubuntu24.04, Intel Core i7-1355U. Existing extractors/backend/specs/tests and scoring remain unchanged. No real input was opened. All numbers below are actual executions, not estimates.

**Operational limitation:** the fixed-threshold classifier scores only 21.05% accuracy /0.2105 macroF1 with 78.95% abstention, below the unchanged rules' 56.58% /0.5371. Candidate ranking is 100% correct but is not an operational accuracy claim. Only 64/304 pages are accepted (all correct); 240 require review. Do not replace the existing rule path with this model. A future experiment needs training-only confidence calibration/validation and a fresh held-out evaluation. No threshold/parameter was changed after observing these test results.

## 1. Existing keys and body rules

Upload slots live in `demo/backend/rules/required_docs.py`; Korean labels in `rules/doc_types.py` differ from `engine_v2/schemas/models.py` engine enums. Exact slot keys retained include `resident_abstract`, `nhis_payment`, `nhis_qualification`, `nhis_acquisition_loss`, `admin_info_consent`, `application_form`. `resident_register`, `interview_confirm`, `exam_admission`, `exam_score`, `receipt` preserve existing engine names. `insurance_4` is the subtype accepted by polymorphic `work_proof`, not a replacement slot; numbered interview/receipt slot routing is not inferable from content.

Unchanged all-type rule baseline: `demo/backend/ocr/pdftext.py:26` ordered keyword list, `:97` classify, `:102` classify_with_evidence (whitespace removed, first match). Specialized detectors: `resident_abstract.py:330`, `nhis_payment.py:341`, `nhis_acquisition_loss.py:153`. Filename fixture dispatch is excluded. Both evaluated methods receive exactly the same own OCR words.

## 2. Classes and representation limits

| Key | Label | Train | Test |
|---|---|---:|---:|
| resident_abstract | 주민등록초본 | 16 | 16 |
| resident_register | 주민등록등본 | 16 | 16 |
| nhis_payment | 건강보험료 납부확인서 | 16 | 16 |
| nhis_qualification | 건강보험 자격확인서 | 16 | 16 |
| nhis_acquisition_loss | 건강보험 자격득실확인서 | 16 | 16 |
| insurance_4 | 4대보험 가입내역 확인서 | 16 | 16 |
| interview_confirm | 면접확인서 | 16 | 16 |
| exam_admission | 응시확인서 | 16 | 16 |
| exam_score | 성적표 | 16 | 16 |
| receipt | 결제영수증 | 16 | 16 |
| id_photo_copy | 면접용 사진 사본 | 16 | 16 |
| admin_info_consent | 행정정보 공동이용 사전동의서 | 16 | 16 |
| application_form | 두배적금 참여 신청서 | 16 | 16 |
| self_check | 신청자격 자가진단 및 필수사항 확인 동의서 | 16 | 16 |
| consent_form | 개인정보 수집 및 이용 동의서 | 16 | 16 |
| third_party_consent | 개인 신용정보 제3자 제공 동의서 | 16 | 16 |
| job_application | 청년 취업지원패키지 신청서 | 16 | 16 |
| job_consent | 개인정보 수집 이용 제공 동의서 | 16 | 16 |
| other | 기타 | 16 | 16 |

All requested textual confusion pairs are represented: abstract/register; qualification/acquisition-loss; payment certificate/bill/receipt; four-insurance/acquisition-loss. Existing composite extraction sample was separated only in the new classification generator. All11 sample types and 8 PDF templates (one overlap) are covered plus other. A pure portrait without text cannot be recognized by OCR-based classification; photo-copy here is the existing text-bearing dummy. Held-out other covers health-insurance bills only; unseen-open-set performance is not measured. Official artwork and real-document distributions are not modeled.

## 3. Model, split, reproducibility and dependencies

Training 304 pages =19 classes ×2 content variants ×8 degradations, Nanum Gothic Coding / stacked_header_v1. Test 304 =19 ×2 held-out fonts ×8, Nanum Gothic and Nanum Myeongjo / inline_header_v1. Uses make_synth_eval renderer, split allocations and degradation functions. Fonts, layout IDs and image hashes do not overlap. OCR sees pixels, classifier sees recognized text/boxes only. Same wording across layouts is intentional; these are correlated synthetic variants, not 608 independent real forms.

Character2–4 grams + top30%-page grams + normalized box/position statistics → sublinear TF-IDF → multinomial logistic regression. C8, lbfgs, tol1e-7, max_iter1000, seed20261111. Threshold0.65 and margin0.15 fixed before test evaluation; no test-driven tuning. Sparse linear features are CPU-light and expose winning-vs-runner feature contributions. Applicant projection excludes scores/text; reviewer projection supplies top5 contributions. Private CLI outputs category/probability/correctness only. Other is distinct from abstention.

Actual repeated full training: coefficients identical=True, IDF identical=True, vocabulary identical=True; first fit+save 7.501s, repeat 8.187s. Artifact features=10868. Reproducibility is same-environment, not a promise of cross-platform bitwise identity.
Training corpus SHA256: `d0ab18ce75a97d6f8d2a323c7220ef5ec0786192a8ca9ee4428254491472971a`. Test corpus SHA256: `784b8816438555a4df7b575b4a5adb34c049804f3ad890573978e2f90931acb5`.

Direct addition: scikit-learn1.7.2, [BSD-3-Clause](https://github.com/scikit-learn/scikit-learn/blob/1.7.2/COPYING). Installed transitives: SciPy1.18.1, joblib1.6.0, threadpoolctl3.8.0, cloudpickle3.1.2; BSD-3-Clause project metadata with bundled-wheel notices retained. Existing NumPy2.5.4 and OCR/fonts reused. Nanum fonts OFL1.1. No weights/fonts/generated images included in commit. [Reproduction and Mac commands](../../../engine_v2/docs/classifier.md).

## 4. Classification results

Headline metrics count abstentions as incorrect; macroF1 averages all 19 catalog classes. Accepted-only accuracy and raw top1 are separate. No-rule-match is abstention, not correct other.

| Method | Accuracy | Macro F1 | Abstention | Accepted-only accuracy |
|---|---:|---:|---:|---:|
| Trained classifier (thresholded) | 21.05% | 0.2105 | 78.95% | 100.00% |
| Unchanged body rules | 56.58% | 0.5371 | 32.89% | 84.31% |
| Classifier candidate top1 (no rejection) | 100.00% | 1.0000 | 0.00% | 100.00% |

Common rule-supported 12 classes (192 pages): classifier 33.33%, rules 89.58%. Six form-only classes plus other are outside the rule baseline's label coverage; headline comparison must be read with this scope difference.

| Class | Model precision | Model recall | Model F1 | Rule precision | Rule recall | Rule F1 | n |
|---|---:|---:|---:|---:|---:|---:|---:|
| resident_abstract | 1.000 | 1.000 | 1.000 | 0.500 | 1.000 | 0.667 | 16 |
| resident_register | 0.000 | 0.000 | 0.000 | 1.000 | 0.938 | 0.968 | 16 |
| nhis_payment | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 16 |
| nhis_qualification | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 | 16 |
| nhis_acquisition_loss | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 16 |
| insurance_4 | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 | 16 |
| interview_confirm | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 | 16 |
| exam_admission | 0.000 | 0.000 | 0.000 | 1.000 | 0.938 | 0.968 | 16 |
| exam_score | 0.000 | 0.000 | 0.000 | 1.000 | 0.938 | 0.968 | 16 |
| receipt | 1.000 | 1.000 | 1.000 | 1.000 | 0.938 | 0.968 | 16 |
| id_photo_copy | 0.000 | 0.000 | 0.000 | 0.500 | 1.000 | 0.667 | 16 |
| admin_info_consent | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 16 |
| application_form | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 16 |
| self_check | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 16 |
| consent_form | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 16 |
| third_party_consent | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 16 |
| job_application | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 16 |
| job_consent | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 16 |
| other | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 16 |

Full confusion matrices: rows are truth, columns predictions. Labels C01…C19 follow the class table above; U=abstention. The all-zero U truth row is omitted; all sample counts are retained.

### Thresholded classifier

| Truth \ prediction | C01 | C02 | C03 | C04 | C05 | C06 | C07 | C08 | C09 | C10 | C11 | C12 | C13 | C14 | C15 | C16 | C17 | C18 | C19 | U |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C01 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C03 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C05 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C09 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C17 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |

### Body rules

| Truth \ prediction | C01 | C02 | C03 | C04 | C05 | C06 | C07 | C08 | C09 | C10 | C11 | C12 | C13 | C14 | C15 | C16 | C17 | C18 | C19 | U |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C01 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C02 | 0 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| C03 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C04 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C05 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C06 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C07 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| C09 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| C10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| C11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C12 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C17 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |
| C19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |

| Degradation | n | Classifier accuracy | Candidate top1 | Rules accuracy | Abstention |
|---|---:|---:|---:|---:|---:|
| blur | 38 | 21.05% | 100.00% | 57.89% | 78.95% |
| clean | 38 | 21.05% | 100.00% | 57.89% | 78.95% |
| jpeg | 38 | 21.05% | 100.00% | 57.89% | 78.95% |
| noise | 38 | 21.05% | 100.00% | 57.89% | 78.95% |
| phone_strong | 38 | 21.05% | 100.00% | 47.37% | 78.95% |
| phone_weak | 38 | 21.05% | 100.00% | 57.89% | 78.95% |
| rotate | 38 | 21.05% | 100.00% | 57.89% | 78.95% |
| scan300 | 38 | 21.05% | 100.00% | 57.89% | 78.95% |

| Model probability interval | n | Mean probability | Candidate correctness | Abstentions |
|---|---:|---:|---:|---:|
| 0.00–0.50 | 192 | 37.34% | 100.00% | 192 |
| 0.50–0.65 | 48 | 53.64% | 100.00% | 48 |
| 0.65–0.80 | 32 | 73.29% | 100.00% | 0 |
| 0.80–0.90 | 22 | 86.70% | 100.00% | 0 |
| 0.90–1.00 | 10 | 90.76% | 100.00% | 0 |

Timing includes per-page feature construction, logits, threshold and evidence; excludes OCR/IO/model loading. First inference included; no batching. n304, mean2.004ms, median1.837ms, p953.028ms, max13.829ms. All pages under100ms: True. Fresh-process Python imports+model load measured1.493s separately; the measured100ms/page bound is for the already-loaded model, not a new CLI process per page. Artifact size821338 bytes,10868 features.

## 5. Filename independence

Actual image→own OCR→model calls: 4. Same filename with replaced contents correctly changes category: True; misleading renames produce identical full predictions: True. The corresponding small unit test stubs only OCR for speed and also passes.

| Run | Expected | Predicted | Probability |
|---|---|---|---:|
| 1 | resident_abstract | resident_abstract | 0.881940 |
| 2 | nhis_payment | nhis_payment | 0.908381 |
| 3 | resident_abstract | resident_abstract | 0.881940 |
| 4 | nhis_payment | nhis_payment | 0.908381 |

## 6–8. Extraction failures, box assumptions and proposed changes

[Complete diagnosis table](extraction-diagnosis.md) records each of93 failed fields (all31 executed cases), expected→actual, failure stage, precise file/line, trace evidence and proposed-fix effect/risk. Revised28 cases exactly reproduce prior field match maps (57/144); legacy3 add10/16. Weak correction applies6/6, strong0/6 and returns original pixels. Unicode dash regex failures, fixed header bands, horizontal row grouping and label/date association cause the failures; wrong premium186667 instead of110000 is a dangerous row-shift example. No extractor fix was applied. Apple adapter/own box contracts were inspected; Apple runtime comparison remains unmeasured on Linux. Real-document risk is inferred from code, not an observed real-document failure rate.

## 9. Verification and scope

[Per-file validation table and exact execution notes](verification.md): all108 original tests retained; full suite126 passed including18 new tests. All13 scenario files pass (1420 counted checks plus8 forms), failures0. Frontend tsc/oxlint/vite exit0; prior warnings remain. Final staged audit checks protected paths, binary/model/font/generated artifacts and secret patterns. Details recorded after final gate.

## 10. Commit

The requested commit hash is returned in the final task response; this report belongs to that commit. No amend, push or coauthor trailer.

Numerical inference audit: independent scikit-learn probability computation agrees on all304 test pages to maximum absolute difference2.665e-15. Training candidate accuracy100%, confidence min/median/max0.700/0.888/0.960; low held-out confidence is not a serialization/softmax bug. Default privacy-safe CLI was exercised on a synthetic PNG and emitted only type/probability/correctness.
