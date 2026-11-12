# Income and age eligibility design

## Baseline and boundaries
Base: feat/p2-real-forms e10438a. Existing untracked docs/audit/ is excluded. The user explicitly authorizes task creation, implementation and all staged local commits; that instruction supersedes Trellis default repeated planning/commit approval gates. Use the available Trellis workflow and specs. No unresolved product decision remains.

## Current flow (base line anchors)
- A: engine_v2/extractors/nhis_qualification.py:158 reads notification body/coordinates; nhis_forms.py:100 reads identity, but management number is absent. Generic printed legacy qualification uses demo/backend/ocr/pdftext.py; preserve it.
- B: engine_v2/extractors/nhis_payment_gov.py:49 scopes metadata cells; :245 emits workplace including empty, without a separate unreadable state. nhis_payment.py preserves printed 직장/지역.
- demo/backend/ocr/localocr.py:319 converts arbitrary extracted fields into persisted strings and carries complete/incomplete form metadata.
- demo/backend/rules/facts.py:87 suppresses untrusted payment amounts; :166 averages configured months but falls back to the aggregate if monthly JSON is absent; :175 defaults missing category to workplace. :229 reads application birth.
- demo/backend/rules/scoring.py:28 table, :116 ScoringFacts, :229 premium_limit_140 clamps and warns for 8+, :288 score_income defaults category and compares a float (:313), :428 score_application serializes the sheet.
- demo/backend/engine_adapter.py:144 converts percent to decile; :163 creates Applicant. engine/stage2_eligibility_check.py:34 skips unknown decile, contains no age rule. engine/pipeline.py:95 combines stage statuses and creates non-PASS payloads.
- demo/backend/api/review.py:476 builds facts/sheet, :498 runs the pipeline, :501 applies the established household review override, :570 persists final/stage2 statuses.
- demo/backend/api/officer.py:687 checklist computes age directly from birth_range (:721); :741 computes income using percent/over flag, which must use new authoritative state.
- demo/backend/api/applications.py:155 locks birth/name to identity on updates (:231); :263 demo identity accepts user input once and :309 copies it to form1. Thus verified values cannot be edited through normal update API, but verification itself is a demo input, not a real identity-provider assertion. Defensively review stored mismatches.

## Evidence contracts and compatibility
A fields: 사업장관리번호, plus 사업장관리번호_상태; B: 사업장명칭 and 사업장명칭_상태. State values: 값 있음, 확실한 공란, 못 읽음. An incomplete form or missing/ambiguous label/value cell is unreadable. Management number full-matches a digits-only complete cell; unknown residue never becomes a number. Derive empty cells from paired printed headers and neighboring sections, not filenames/slot expectations. Preserve all existing extraction checks.
ScoringFacts.insurance_type becomes 직장/지역/모름; insurance_evidence holds A/B states, values/category and source references. sources includes insurance_a / insurance_b / insurance_explicit_*; income basis summarizes the decision.
Trusted explicitly printed 가입구분 (fixture/legacy) is a compatibility fallback when tri-state fields are absent or insufficient; never fabricate it from roles. All usable explicit declarations must agree with each other and all usable A/B declarations. Any conflict involving a usable explicit recorded value always requires review. A/B-only disagreement requires review in the middle band; below/above both limits it does not prevent a certain outcome. Without explicit legacy evidence, a middle-band decision requires both A and B to agree. One A/B alone does not suffice. Mixed membership is never selected automatically; membership-sensitive amounts remain undetermined. No new rule for number of workplace-insured members is inferred.
ScoringFacts.premium_determinable and premium_issue expose amount trust/completeness. Configured months must all exist and be valid nonnegative integer amounts; retain existing averaging formula. Fixture monthly records remain compatible.

## Income output and exact eligibility
score_income returns a named result with item, percent, over_limit, notes, status, reason_codes; retain four-value iteration/index compatibility for existing consumers. ScoreSheet serializes income_status / income_reason_codes in addition to existing fields. States MET / OVER_LIMIT / UNDETERMINED. Percent remains a rounded demo scoring estimate; never use its rounding to decide excess. 8–10 are official, without out-of-table warnings; 11+ is undetermined. Limits use only workplace/regional rows for eligibility. For category-independent low/high decisions, a conservative existing row supplies demo band estimation with its uncertainty described, not an inferred membership category.

## Final-status pattern
Keep engine/ unchanged: pass the authoritative over_limit bit optionally to to_engine_applicant so integer excess maps to decile 10 even if percent rounds to 140.0; met maps at most 9, undetermined maps None. This preserves the existing engine INCOME_OVER_THRESHOLD path.
Extend review.py existing override after payload creation: undetermined required income adds INCOME_UNDETERMINED plus detail codes, forces final and stage2 NEEDS_REVIEW. Age eligibility is a shared pure helper used by review and officer checklist: AGE_OUT_OF_RANGE -> FAIL; AGE_UNDETERMINED or AGE_IDENTITY_MISMATCH -> NEEDS_REVIEW. If any required fact is uncertain, final review takes priority over automatic rejection; otherwise definite age failure makes FAIL. Existing engine reasons remain available. Recompute payload final_status, recommended_action, Review.final_status, stage2_status and supplement deadline from the same resolved result. No DB migration.

## Verification and reporting
Add coordinate/text-layer evidence tests and facts/scoring/final-review/checklist tests using fictitious values; test exact limits/+1, all A/B permutations, missing/untrusted months, 8/10/11, age endpoints/day outside/missing and both programs, identity mismatch, fixture compatibility. Run engine_v2/tests, demo/backend/tests and every run_p*_scenarios module. Base counts: engine 1129 passed/3 skipped; backend 345 passed; 17 counted modules 1824 passed/0 failed, P14 normal. Record altered expectations and scope issues below.

## Implementation notes and confirmed baseline
- Stage commits so far: plan 58d8ad1; A 7a83f28 (102 focused passed); B 6e61166 (88 focused passed); facts 15ecb8d (82 new facts cases, 152 including existing related regressions).
- Re-ran the unchanged baseline with .venv/bin/python: engine 1129 passed / 3 skipped (19.79 s), backend 345 passed (37.39 s), all 18 scenario processes exit 0. Seventeen counted modules total 1824 passed / 0 failed; P14 confirms eight original forms. Logs in /tmp/income-{engine,backend,scenarios}-baseline.log; per-module logs currently /tmp/income-scenarios/. Final run will overwrite per-module logs but preserve baseline summary log.
- Masked geometry references read only: /tmp/layout_shape4.txt:146 management label paired with certificate row before identity headings; /tmp/layout_shape.txt:148 text-layer management label. /tmp/layout_shape4.txt:17–18 payment workplace/payer labels. Tests reuse existing fictitious coordinate builders and add clearly fictitious values; no masked file was copied.
- A requires a whole ASCII digit cell with no discarded numeric punctuation; no unverified fixed digit length is imposed. B accepts a conservative company-name grammar. Unsupported names/symbols remain unreadable. Synthetic coordinate/text-PDF verification is not a real-document OCR accuracy claim.
- Facts distinguish insurance_conflict from insurance_explicit_conflict: A/B disagreement can still establish income below/above both limits, while a conflicting printed/recorded category always requires review. Evidence retains declared_state separately from normalized usable state.
- Known untrusted cached qualification metadata now suppresses authoritative household size, preserving original stored fields. This is necessary to keep the category-independent min/max path from failing an applicant using an uncertain household count; household text parsing itself is unchanged.
- Fixtures S2 payment, P9 parent payment and S7 excess payment gain monthly JSON with the existing synthetic premium repeated in each required month. This is synthetic fixture construction, not an inference from a real aggregate or a production fallback.
- Existing legacy nhis_payment.py:385–390 can infer a category from body substrings/workplace text, so old 가입구분 provenance is not guaranteed to be an explicitly printed category. Its existing output remains a recorded compatibility input; modifying that unrelated extractor logic is out of scope. New government-reader A/B evidence does not use that inference. This limitation must be reported.
- Identity is a one-time demo user input, then server-locked on normal application updates; it is not a production identity-provider verification. Review independently detects stale/corrupt stored mismatches. Confirmed write paths: applications.py:231 and :309 only; forms.py:536 changes a print-only copy. Frontend locks are PdfFormsWorkspace.tsx:463 and ApplyFlow.tsx:93 / :375.

## Final source evidence and outcomes
- A: engine_v2/extractors/nhis_qualification.py:83 bounds the management cell; :271 emits 사업장관리번호_상태 (값 있음 / 확실한 공란 / 못 읽음). B: engine_v2/extractors/nhis_payment_gov.py:78 bounds workplace evidence; :367 emits 사업장명칭_상태 with those same states while preserving the original field.
- Facts contract: demo/backend/rules/scoring.py:115 ScoringFacts.insurance_type (직장/지역/모름), insurance_evidence, premium_determinable, premium_issue, premium_reason_code, insurance_reason_codes and insurance_explicit_conflict; demo/backend/rules/facts.py:154 assembles membership/sources and :220 validates all monthly amounts.
- Income result: demo/backend/rules/scoring.py:219 IncomeScoreResult(item, percent, over_limit, notes, status, reason_codes), :307 score_income. Four-value iteration/index/slice/len remains compatible; named status/reason_codes are authoritative. ScoreSheet exposes income_status and income_reason_codes.
- Final boundary: demo/backend/engine_adapter.py:183 passes authoritative excess to the established decile10 engine rejection; demo/backend/api/review.py:543 emits INCOME_UNDETERMINED with detail_codes, :548 assesses age, then resolves final/stage2/payload/action/deadline consistently. Officer income uses MET at demo/backend/api/officer.py:735; age uses the same helper at :697.
- Age: demo/backend/rules/age_eligibility.py:42 assess_age returns PASS / FAIL / NEEDS_REVIEW, AGE_OUT_OF_RANGE / AGE_UNDETERMINED / AGE_IDENTITY_MISMATCH. Missing form birth never borrows identity. Normal identity updates are immutable; dedicated API test confirms method demo and repeated identity409. Very old valid fictitious births previously exhausted score_age before eligibility; the minimal final35+band fallback at scoring.py:464 now allows AGE_OUT_OF_RANGE to be reached, with both-program actual-review regression. Eligible age scores remain identical. Huge malformed raw birth is handled locally in the age path without changing residence/work parsers.
- Engine files unchanged; no schema migration, main merge, push or PR. Existing audit work remains untouched. New backend spec records executable boundaries and error matrix.

## Results
| Check | Baseline e10438a | Final af5bc57 | Difference |
|---|---|---|---|
| engine_v2 pytest | 1129 passed,3 skipped | 1172 passed,3 skipped | +43, skips unchanged |
| demo/backend pytest | 345 passed | 604 passed | +259 |
| 17 counted scenario modules | 1824 passed,0 failed | 1851 passed,0 failed | +27 P3 assertions |
| P14 separate validation | Normal,8 forms | Normal,8 forms | Preserved |

All18 scenario processes exited0. Commands used .venv/bin/python -m pytest engine_v2/tests -q; .venv/bin/python -m pytest demo/backend/tests -q; and each demo/backend/tests/run_p*_scenarios.py as a module. Final runtimes: engine29.10s, backend41.59s. Logs: /tmp/income-engine-final.log, /tmp/income-backend-final.log, /tmp/income-scenarios-final.log and /tmp/income-scenarios/*.log. All changed source modules compile; git diff --check passes. No configured backend lint/type-check command was found; no new suppression was added.

PR#27 is local merge5d0833d and an ancestor of e10438a (verified by git merge-base --is-ancestor). Its document-guidance, NHIS identity/qualification, portal upload, observed-form, coordinate and resident-title regression files are retained and included in the full suites. Existing feat/p2-real-forms tests likewise run in full. Fixture scenarios retain their categories/results; complete synthetic monthly data was added in stage4.

No old test was deleted or weakened. Exact old expectation/data changes are recorded in changed-test-expectations.md: P3 official8–10 note,11+no-clamp and no mixed automatic selection; P2 low-premium single-source case now undetermined; P13 receives complete monthly/trust metadata with its household/privacy assertions unchanged. P3 assertions increase150→177; P13 remains26. New opaque renamed-PDF integration4cases demonstrate A/B extraction, conflicting expected type, document validation, storage and actual final review.

The final engine suite emits two additional dependency deprecation warnings because its new adapter tests import backend TestClient/fitz (already present in the backend baseline). No tests fail or gain skips; dependency migration is outside this task.

## Assumptions (추정), limitations and out-of-scope items
- 추정/미확인: synthetic coordinate/text-layer tests establish the form/evidence contracts, not real-document OCR accuracy or universal company-name glyph coverage. No actual private document was opened, enumerated, passed to a command or executed; masked layout files were read only and not copied.
- Legacy generic payment 가입구분 can still come from body/workplace inference (nhis_payment.py:385); retained recorded compatibility evidence is not a guarantee of literal printed category provenance. Changing that unrelated reader is outside the two requested evidence fields.
- Mixed aggregation and multiple workplace-insured member rules remain undefined; neither is newly inferred. Residence policy and resident-number storage remain outside scope.
- Existing officer score display rounds the demo income ratio; it can show140.0% alongside exact integer excess. The authoritative state and basis show the correct integer limit comparison. Further ratio-display redesign is outside scope.

## Stage commits and handoff
1 plan58d8ad1;2 A7a83f28;3 B6e61166;4 facts15ecb8d;5 scoringae09ec8;6 finale0f7a1c;7 age636562e;8 regressionsaf5bc57. Stage9 commits this verification/spec/handoff record; tested implementation HEAD is af5bc57. Task status review, awaiting user confirmation; no archive or remote operation.
