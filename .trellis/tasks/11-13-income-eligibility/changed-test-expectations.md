# Existing expectations and scenario data changed

No existing test was deleted. Existing monetary values, public table entries, fixture categories, scenario flow and household-source/privacy assertions remain. Changes below implement the user's decided policy rather than accepting an unexplained regression.

## P3: official households, unsupported households and mixed compatibility

`demo/backend/tests/run_p3_scenarios.py:66` (`test_income_table`):

- The first direct 11-person `income_percent` call previously expected a clamped 10-person estimate and demo note. It now asserts `ValueError`: no supported row exists and no smaller household may substitute.
- For each 8/9/10-person table row, the old health-ministry/outside-seven-person/manual-confirmation note assertion becomes an exact empty-note assertion. All nine public table amount lookups are retained unchanged because the user confirmed all 1–10 rows are official.
- Workplace/regional exact-limit and limit-plus-one checks remain, with new explicit `MET` / `OVER_LIMIT` state assertions.
- The three mixed-table exact-limit cases previously expected eligibility success. Each now expects `OVER_LIMIT` because that amount exceeds **both** actual workplace/regional limits; this does not select the mixed row. The existing plus-one rejection remains. Added checks prohibit labeling the applicant as mixed and require `UNDETERMINED` for a membership-sensitive middle amount supplied with only mixed membership.
- The second 11-person clamping/note assertion becomes four stronger checks: `UNDETERMINED`, no percent, no certain excess and `HOUSEHOLD_SIZE_UNSUPPORTED`.
- Retained one-person mixed fallback assertions explicitly test only the historical informational conversion helper; automatic eligibility never selects that helper fallback.
- P3 gains 27 assertions; all unrelated scoring, age points, residence and API assertions remain.

## P13: complete synthetic evidence for existing household tests

`demo/backend/tests/run_p13_household_scenarios.py:46` (`test_household_source_and_income_review`): both pre-existing synthetic payment dictionaries now include all three requested billed months, each repeating their existing obviously synthetic aggregate amount. This keeps the original missing-household and certificate-only household-source assertions isolated from the newly prohibited aggregate-only fallback. No expected household result or score estimate was changed.

`demo/backend/tests/run_p13_household_scenarios.py:151` (`_add_app`): stored synthetic qualification OCR JSON now supplies confidence 0.95. Previously the DB adapter projected absent confidence as an explicitly supplied `None`; the new trust guard correctly refuses that value. The scenario intends trusted household lists, so supplying synthetic trust metadata preserves its existing generic applicant warning and name-nondisclosure assertions. New facts tests independently assert that missing/invalid supplied confidence cannot establish authoritative income.

## P2 payment facts: one missing membership source

`demo/backend/tests/test_p2_payment_facts.py:63` (`test_complete_matching_payment_preserves_income_scoring`), same two parametrized cases retained:

- Low case: the observed B workplace cell is blank (regional), A is absent and the amount lies between regional/workplace limits. The previous non-None percent / not-over assertion depended on the removed workplace default. It now asserts `UNDETERMINED`, no percent, incomplete income item, no certain excess and `INSURANCE_EVIDENCE_INSUFFICIENT`.
- High case: still asserts a non-None percent above 140 and certain excess, adding exact `OVER_LIMIT` status and boolean assertions. It exceeds both limits, so missing A does not prevent a definite outcome.

## Additional regression coverage

New `demo/backend/tests/test_income_extracted_review.py` has four integration cases. Authored fictitious qualification and payment text-layer PDFs use opaque arbitrary filenames, are renamed and read with contrary expected types, checked against matching fictitious identity, stored and passed through the real review pipeline. Both blank cells reproduce regional excess; both present meet workplace eligibility; disagreement and unreadable A require review. No private document or source layout file is executed or copied.

The full-scope checker found a necessary age-edge fix: an otherwise valid ancient synthetic birth reached `score_age` before eligibility evaluation and exhausted the former <=200-year final band. `score_age` now keeps the existing final 35+ band for larger ages, without changing any eligible applicant's points. Two new real-pipeline regressions in `test_age_eligibility.py` assert `AGE_OUT_OF_RANGE` for both programs. No existing age expectation changed.

## Verification

- Full backend pytest: **604 passed**, no failures (baseline 345; +259 new cases including the two checker age-edge regressions).
- P3: **177 passed / 0 failed** (27 stronger/new assertions beyond the existing 150).
- P13: **26 passed / 0 failed** (same assertion count and expected household/privacy behavior).
- Renamed PDF integration matrix after opaque filename strengthening: **4 passed**.
- `git diff --check`: clean.
- Whole-engine and every-scenario final verification belongs to stage 9.

## Follow-up: FAIL precedence and possible mixed households

The following entries supersede only the earlier policy expectations named here. No existing parametrized case or scenario assertion is deleted, skipped, or made optional. Public limits and existing synthetic inputs are unchanged.

- `demo/backend/tests/test_age_eligibility.py`, renamed `test_definite_failure_precedes_uncertainty_without_discarding_reason_details`: three combinations (unknown income + age outside; excess income + missing age; excess income + identity mismatch) now expect final/stage2/payload FAIL instead of NEEDS_REVIEW. The user confirmed any definite FAIL wins; every original income/age reason assertion remains. The two existing FAIL combinations are unchanged.
- `demo/backend/tests/test_income_scoring.py`, renamed `test_each_official_threshold_is_inclusive_with_exact_plus_one_outcome`: nine workplace-plus-one cases (sizes 2–10) now require UNDETERMINED, no certain excess, no percent, incomplete income item and INCOME_MIXED_POSSIBLE instead of OVER_LIMIT, rounded 140.0 and complete item. Those amounts exceed ordinary bounds but stay below the mixed bound. The other 31 exact-boundary cases retain their original outcomes.
- Same file, `test_unconfirmed_category_has_disclosed_demo_score_reference_without_becoming_membership_fact`: the existing two-person workplace-plus-one input now requires mixed-possible review, no estimate/excess and incomplete item, replacing the prior certain-excess/reference estimate. Both existing low cases still require the disclosed demo reference; the unknown category remains unchanged in every case.
- Same file, `test_table_helpers_preserve_informational_mixed_values_without_automatic_selection`: nine existing mixed-equality cases (sizes 2–10) now require UNDETERMINED / INCOME_MIXED_POSSIBLE, incomplete item and no percent/excess/mixed membership claim, replacing OVER_LIMIT. All informational helper/table checks remain.
- `demo/backend/tests/run_p3_scenarios.py:test_income_table`: sizes 8/9/10 at mixed equality now expect no certain excess and UNDETERMINED (formerly OVER_LIMIT); workplace-plus-one now expects the same (formerly OVER_LIMIT). The existing no-mixed-selection assertion now requires the mixed-household uncertainty basis instead of a demo-reference basis. Three mixed-plus-one and three regional-plus-one rejection pairs remain unchanged. Added six exact reason-code assertions; P3 assertions 177 → 183.

New coverage in `test_review_status_priority.py` exercises the actual pipeline for six combinations, separate stage1/stage2, all reason retention and payload/action consistency; six persisted overlap permutations keep old stage1/stage2 FAIL, preserve current FAIL, reset officer decisions and deduplicate links/reasons, with list/detail HTTP agreement; two new-review endpoint cases verify PASS/review. `test_income_mixed_possible.py` adds all nine mixed rows × four A/B combinations × three boundaries, two/ten-person final-payload/checklist boundaries, and three one-person regional-excess cases. These use public limits plus synthetic offsets and fictitious identities/documents only.

Focused follow-up pytest: 304 passed (131 added cases across the two new modules); no existing tests deleted or weakened. Whole-suite verification is recorded after stage 5.
