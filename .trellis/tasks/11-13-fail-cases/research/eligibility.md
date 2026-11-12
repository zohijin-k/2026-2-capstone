# Eligibility integration research

All document inputs examined by the baseline tests are authored fixtures or temporary synthetic files. No private document directory was opened, listed, or supplied as an argument. This research does not change application code.

## Existing flow and integration points

- `demo/backend/rules/programs.py:124` defines `ProgramConfig`; `has_work_requirement` is at line 144. Double savings enables it at line 372, while job package disables it at line 421. The public call-center value is already configured at line 392.
- `demo/backend/rules/age_eligibility.py:42` has the authoritative inclusive age assessment. Missing or malformed birth and identity mismatch remain review; `AGE_OUT_OF_RANGE` is certain FAIL. Its basis contains the applicant birth and allowed birth interval (`:54`).
- `demo/backend/rules/facts.py:244` builds authoritative income facts, including qualification-only household size (`:250`) and trusted monthly premium (`:284`). Work scoring currently uses the form employment date (`:319`), so scoring completeness is not work-continuity evidence. Preserve that scoring contract.
- `demo/backend/rules/facts.py:304` prefers document move-in date but falls back to the form (`:316`). A confirmed missing-date finding should add an explicit caveat to this source, without changing scoring.
- `demo/backend/rules/scoring.py:307` returns income `MET / OVER_LIMIT / UNDETERMINED`; `ScoreSheet` serializes these fields at `:209`. Its scoring basis includes a linear score estimate, so applicant blockers must compose a separate message with household, actual premium, applicable published 140% limit and target months; do not expose the score basis wholesale.
- `demo/backend/api/common.py:232` produces `document_fact`, carrying raw fields, confidence, image quality, issue date and stage1 status (`:259`). It does not carry classification confidence, so work must require complete structure, readable values and applicant identity agreement before a negative determination.
- `demo/backend/api/review.py:113` owns blockers. `GET final-check` consumes them (`:427`) and `POST submit` calls the same function again (`:727`). `_run_review` assembles independent statuses at `:557`; `_merge_statuses` preserves `FAIL > NEEDS_REVIEW > PASS` at `:605`.
- `demo/backend/api/officer.py:719` currently marks work eligibility from the score item's `incomplete` flag. Replace that eligibility-only source with the shared continuity result; score points remain independent. `Entry` already has the review payload.
- `demo/backend/api/applications.py:217` serializes early application state and `:314` returns identity verification. Both can include the age assessment/reason after identity is locked at `:309`.
- `demo/frontend/src/api.ts:325` declares blocker kind without eligibility. Existing `goto` values support routing new reasons to upload or form1. `FinalCheck.tsx:120` renders grouped blockers, but currently only labels are visible and the reason is a tooltip (`:125`); eligibility reasons need visible message text. `IdentityCheck.tsx:112` renders verified identity and can show the early age reason with a minimal additional field/prop.

## Work evidence contracts

- `engine_v2/extractors/insurance_4.py:593` serializes `가입내역` rows with `보험`, `성명`, `가입자종별`, `사업장관리번호`, `사업장명칭`, `자격취득일`, `신고접수일`, `상태`, `bbox`, `신뢰도`. Work-related selection is already defined at `:611`: pension workplace member, health workplace member, employment or industrial insurance. Use full rows; earliest/latest acquisition summaries alone do not prove continuity. Receipt dates are not loss dates (`:1`).
- Portal `structure_complete` requires every existing validation at `insurance_4.py:634`; do not relax these validations for mixed attachments. Only split confidently identified independent form pages before invoking them.
- `engine_v2/extractors/nhis_acquisition_loss.py:516` serializes `자격이력자료` with `period`, `rows[{category,acquired,lost}]` and coverage evidence. Complete chronology can prove intervals/gaps; the recent-five-year helper's separate contract must not become the continuity rule. The current serialized rows omit employer names, which is a limit if employer-specific comparison is required.
- `engine_v2/extractors/business_registration.py:27` lists thirteen required fields including `개업일`; it currently has no explicit closure/suspension field. Any new status extraction needs bounded printed evidence, not a broad search over instructions/notices.
- `WorkCategory` uses `직장가입자`, `지역가입자·피부양자`, `사업소득 사업자`, `농업·임업`, `어업` (`demo/backend/rules/required_docs.py:33`). The form `workType` is a different concept.

## Baseline and expected fixture implications

- Pre-implementation engine pytest: **1,172 passed, 3 skipped**, 7 warnings; log `/tmp/fail-cases-baseline-engine.log`.
- Pre-implementation backend pytest: **735 passed**, 7 warnings; log `/tmp/fail-cases-baseline-backend.log`.
- Pre-implementation scenarios: **1,857 passed, 0 failed** across 17 modules with numerical summaries; P14 exits normally without a count. All 18 files exit 0. Log `/tmp/fail-cases-baseline-scenarios.log`. This matches the supplied baseline exactly.
- `demo/backend/tests/test_income_review.py:33` creates generic PASS work documents without authoritative intervals. Adding unknown work review changes existing overall PASS expectations. Prefer strengthening these shared synthetic fixtures with complete work rows instead of weakening income/age assertions. Keep separate tests that intentionally omit work evidence and assert review.
- `/tmp/layout_shape5.txt` temporarily read empty in the parent session, but a subsequent metadata/byte-count check reported nonzero content and a changed size. Concurrent rewrite is an **inference (추정)**; the parent confirmed a later read succeeded. No further source-content inspection was needed by this researcher.
