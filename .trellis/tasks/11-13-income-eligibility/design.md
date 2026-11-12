# Income and age eligibility design

## Baseline and boundaries
Base: feat/p2-real-forms e10438a. Existing untracked docs/audit/ is excluded. The user explicitly authorizes task creation, implementation and all staged local commits; that instruction supersedes Trellis default repeated planning/commit approval gates. Use the available Trellis workflow and specs. No unresolved product decision remains.

## Current flow (base line anchors)
- A: engine_v2/extractors/nhis_qualification.py:158 reads notification body/coordinates; nhis_forms.py:100 reads identity, but management number is absent. Generic printed legacy qualification uses demo/backend/ocr/pdftext.py; preserve it.
- B: engine_v2/extractors/nhis_payment_gov.py:49 scopes metadata cells; :245 emits workplace including empty, without a separate unreadable state. nhis_payment.py preserves printed 직장/지역.
- demo/backend/ocr/localocr.py:319 converts arbitrary extracted fields into persisted strings and carries complete/incomplete form metadata.
- demo/backend/rules/facts.py:87 suppresses untrusted payment amounts; :165 averages configured months but falls back to the aggregate if monthly JSON is absent; :174 defaults missing category to workplace. :237 reads application birth.
- demo/backend/rules/scoring.py:28 table, :138 ScoringFacts, :231 premium_limit_140 clamps and warns for 8+, :285 score_income defaults category and compares a float, :429 score_application serializes the sheet.
- demo/backend/engine_adapter.py:144 converts percent to decile; :163 creates Applicant. engine/stage2_eligibility_check.py:34 skips unknown decile, contains no age rule. engine/pipeline.py:95 combines stage statuses and creates non-PASS payloads.
- demo/backend/api/review.py:478 builds facts/sheet, :510 runs the pipeline, :513 applies the established household review override, :581 persists final/stage2 statuses.
- demo/backend/api/officer.py:684 checklist computes age directly from birth_range; :747 computes income using percent/over flag, which must use new authoritative state.
- demo/backend/api/applications.py:155 locks birth/name to identity on updates (:231); :263 demo identity accepts user input once and :309 copies it to form1. Thus verified values cannot be edited through normal update API, but verification itself is a demo input, not a real identity-provider assertion. Defensively review stored mismatches.

## Evidence contracts and compatibility
A fields: 사업장관리번호, plus 사업장관리번호_상태; B: 사업장명칭 and 사업장명칭_상태. State values: 값 있음, 확실한 공란, 못 읽음. An incomplete form or missing/ambiguous label/value cell is unreadable. Management number full-matches a digits-only complete cell; unknown residue never becomes a number. Derive empty cells from paired printed headers and neighboring sections, not filenames/slot expectations. Preserve all existing extraction checks.
ScoringFacts.insurance_type becomes 직장/지역/모름; insurance_evidence holds A/B states, values/category and source references. sources includes insurance_a / insurance_b / insurance_explicit_*; income basis summarizes the decision.
Trusted explicitly printed 가입구분 (fixture/legacy) is a compatibility fallback when tri-state fields are absent or insufficient; never fabricate it from roles. All usable explicit declarations must agree with each other and all usable A/B declarations. A conflict always requires review, including explicit-vs-cell conflict. Without explicit legacy evidence, a middle-band decision requires both A and B to agree. One A/B alone does not suffice. Mixed remains undetermined. No new rule for number of workplace-insured members is inferred.
ScoringFacts.premium_determinable and premium_issue expose amount trust/completeness. Configured months must all exist and be valid nonnegative integer amounts; retain existing averaging formula. Fixture monthly records remain compatible.

## Income output and exact eligibility
score_income returns a named result with item, percent, over_limit, notes, status, reason_codes; retain four-value iteration/index compatibility for existing consumers. ScoreSheet serializes income_status / income_reason_codes in addition to existing fields. States MET / OVER_LIMIT / UNDETERMINED. Percent remains a rounded demo scoring estimate; never use its rounding to decide excess. 8–10 are official, without out-of-table warnings; 11+ is undetermined. Limits use only workplace/regional rows for eligibility. For category-independent low/high decisions, a conservative existing row supplies demo band estimation with its uncertainty described, not an inferred membership category.

## Final-status pattern
Keep engine/ unchanged: pass the authoritative over_limit bit optionally to to_engine_applicant so integer excess maps to decile 10 even if percent rounds to 140.0; met maps at most 9, undetermined maps None. This preserves the existing engine INCOME_OVER_THRESHOLD path.
Extend review.py existing override after payload creation: undetermined required income adds INCOME_UNDETERMINED plus detail codes, forces final and stage2 NEEDS_REVIEW. Age eligibility is a shared pure helper used by review and officer checklist: AGE_OUT_OF_RANGE -> FAIL; AGE_UNDETERMINED or AGE_IDENTITY_MISMATCH -> NEEDS_REVIEW. If any required fact is uncertain, final review takes priority over automatic rejection; otherwise definite age failure makes FAIL. Existing engine reasons remain available. Recompute payload final_status, recommended_action, Review.final_status, stage2_status and supplement deadline from the same resolved result. No DB migration.

## Verification and reporting
Add coordinate/text-layer evidence tests and facts/scoring/final-review/checklist tests using fictitious values; test exact limits/+1, all A/B permutations, missing/untrusted months, 8/10/11, age endpoints/day outside/missing and both programs, identity mismatch, fixture compatibility. Run engine_v2/tests, demo/backend/tests and every run_p*_scenarios module. Base counts: engine 1129 passed/3 skipped; backend 345 passed; 17 counted modules 1824 passed/0 failed, P14 normal. Record altered expectations and scope issues below.

## Results
Pending implementation and verification.
