# Verification evidence

Commands follow the user request. Scenario loop was first attempted inside the sandbox; TestClient stalled exactly as documented in the prior bench. It was interrupted (exit130, no completed scenario result) and the identical loop was rerun with approved sandbox escalation; no source change was made. All thirteen files completed, no FAILED markers.

| Scenario runner | Passed | Failed |
|---|---:|---:|
| run_p11_criteria_scenarios.py | 38 | 0 |
| run_p12_subsidy_criteria_scenarios.py | 29 | 0 |
| run_p13_household_scenarios.py | 26 | 0 |
| run_p14_pdf_forms_scenarios.py | 8 forms | 0 |
| run_p15_jbai_scenarios.py | 129 | 0 |
| run_p2_scenarios.py | 53 | 0 |
| run_p3_scenarios.py | 150 | 0 |
| run_p4_scenarios.py | 182 | 0 |
| run_p5_scenarios.py | 152 | 0 |
| run_p6_scenarios.py | 249 | 0 |
| run_p7_scenarios.py | 238 | 0 |
| run_p8_localocr_scenarios.py | 89 | 0 |
| run_p9_identity_scenarios.py | 85 | 0 |

Initial full engine test run: **126 passed in15.84s**, including all108 unchanged baseline tests and18 new tests. Final targeted evaluator checks repeated after review changes. Frontend `npx tsc -b && npx oxlint && npx vite build`: exit0; existing StatusBadge Fast Refresh warning and Vite large-chunk notice remain. No frontend changes.

Final full engine test run after review/evaluation helper changes: **126 passed in11.13s**. Original108 tests have no tracked diff.

Protected baseline comparison: all95 original tracked files under existing tests, extractors, backend and shared specs match004e45a byte-for-byte. Only new test files are added.

Actual full classifier training performed twice (7.501s / 8.187s); seed20261111 reproduces weights/intercepts/IDF/vocabulary exactly. Held-out304 pages: all loaded-model classifications below100ms; actual same-path swaps and renames4/4 correct and identical under renaming. The experimental thresholded classifier has lower accuracy than rules due high abstention, prominently reported; existing service behavior is unchanged and no integration is performed.

Numerical inference audit: independent scikit-learn probability computation agrees on all304 test pages to maximum absolute difference2.665e-15. Training candidate accuracy100%, confidence min/median/max0.700/0.888/0.960; low held-out confidence is not a serialization/softmax bug. Default privacy-safe CLI was exercised on a synthetic PNG and emitted only type/probability/correctness.
