# Scenario expectation changes for confirmed submission failures

Scope: only P3, P4, P6, P9 scenario scripts and new test-only `scenario_support.py`. No production rules, published fixture JSON, original fixture values, private files or existing check coverage were removed. Raw execution logs remain under /tmp.

## Normal synthetic work evidence

The legacy S2 authored work fixture had no verified identity and no complete insurance row evidence. The new continuity assessor correctly returns UNDETERMINED for it. `complete_synthetic_work()` explicitly strengthens these normal scenario fixtures with the application's existing synthetic name/birth, verified synthetic identity, complete four-insurance active rows, an overtly fictitious workplace/identifier and high-confidence acquisition dates before the criterion start. Original scoring employment inputs and unrelated uncertain document fixtures stay unchanged. This preserves normal PASS, existing scores, officer status filters and queues without weakening production certainty rules.

## Confirmed income rejection and historical officer fixtures

- P3 S7: expected `can_submit=True` and submit 200 changed to `False` and 400. Added exact eligibility kind, numeric household/limit/premium guidance and no persisted Review checks. All original engine FAIL, stage statuses, income percentage/over-limit, total-score and applicant privacy assertions remain, now inspecting an explicitly seeded historical Review after observing the current API rejection.
- P4 B: the confirmed-excess fixture's current final-check/submit must block (False/400), with limit/premium guidance. Only afterward a labeled historical submitted Review is seeded, preserving all four officer cases and every original filter, ranking, role, detail, decision, inline-file and scoring assertion. Normal and uncertain submitted cases use the real submit API.
- P6 S7: the published legacy expectation JSON is untouched. `load_expected()` adjusts only the stale `can_submit` expectation to False and adds submit 400 / OVER_LIMIT / historical-review marker assertions. Every original engine/scoring/result assertion is retained. A historical fixture follows checks for current submit rejection, numeric guidance and no automatic Review; this also preserves S9 officer coverage and original row-count/reset/idempotence assertions.
- P9 dependent reconciliation: the authored two-member household's premium is independently over its limit, so the old submit-200 expectation changes to 400 with an eligibility blocker and numeric evidence. Historical seeding then preserves the original officer cross-reference/name/privacy assertions. Relationship reconciliation itself and other identity assertions are unchanged.

`seed_blocked_historical_review()` requires a 400 response, DRAFT state and no existing Review, then calls the ordinary `_run_review()` and explicitly marks `synthetic_historical_fixture=True` in the stored payload. It is a test-only historical-data setup, never a successful applicant API submission.

## Numeric privacy assertion correction

P4's raw substring test for `99` also matches the applicant's newly populated synthetic birth date. The original substring assertion is retained over the whole response after removing only the explicitly asserted, expected applicant birth from document extracted-birth cells. A new assertion verifies that exact birth list. Embedded score text, other strings, numeric values, forbidden score keys and officer memo checks remain covered.

## Verification

Sequential affected modules: P3 186 passed / 0 failed (baseline 183); P4 189 / 0 (182); P6 261 / 0 (249); P9 98 / 0 (96). Total +24 checks, no deleted check calls. Logs: /tmp/fail-cases-p3-updated.log, -p4-updated.log, -p6-updated.log, -p9-updated.log. A final sequential rerun after adding the explicit historical payload marker confirmed the same counts and zero failures.
