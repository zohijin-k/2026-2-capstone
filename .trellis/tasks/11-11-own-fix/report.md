# Synthetic verification

Baseline pytest: 147 O / 0 X. Existing tests after extraction changes: 147 O / 0 X.
Baseline scenarios: 13 O / 0 X. Per-file check counts: 38,29,26,1,129,53,150,182,152,249,253,89,96. Frontend O / 0 X.

| Synthetic condition | Before O | After O |
|---|---:|---:|
| Dash variants | 0/10 | 10/10 |
| Same-row stamp | 0/1 | 1/1 |
| Empty right cell, absence required | 0/1 | 1/1 |
| Corrupt right cell, absence required | 0/1 | 1/1 |
| Missing label, absence required | 1/1 | 1/1 |
| Own stamp image | 0/1 | 1/1 |
| Own empty-cell image, absence required | 1/1 | 1/1 |
| Myeongjo clean | 2/4 | 4/4 |
| Myeongjo scan300 | 2/4 | 4/4 |
| Myeongjo rotate | 2/4 | 4/4 |
| Myeongjo blur | 3/4 | 4/4 |

Canonical synthetic compatibility against main: 5 O / 0 X, including fields, evidence, confidence, validations and warnings. Own Myeongjo field recovery: 4/4 conditions O. The timestamp parser also handles a complete hour/minute pattern without the printed space; it never replaces an unreadable date with another candidate.

The strict diagnostic projection uses only fixed keys, separator classes, counts and booleans. Native/Python dependency output is discarded. Synthetic CLI stderr: 0 bytes. No input values or identifying source metadata are recorded here. Workflow and specs remain unchanged by user constraint; extracted lessons are recorded in this task and the authorized OCR document.

Local documentation audit: chosen model names and documented license claims match the pinned fetch declarations and existing documentation; no remote license re-verification was performed. Defaults remain unchanged; engine choices are clarified. Timing tables remain historical one-run measurements, not guarantees on this CPU. The obsolete future-only demo connection description was corrected to the current explicit-environment adapter capability.

## Final checks

| Check | Before | After | X |
|---|---:|---:|---:|
| Pytest | 147 | 222 | 0 |
| Scenario scripts | 13 | 13 | 0 |
| Scenario checks | 1447 | 1447 | 0 |
| Frontend install/typecheck/lint/build | O | O | 0 |
| Existing tests edited | 0 | 0 | 0 |

New tests: 75 O / 0 X / 0 skip. Existing frontend warning and chunk-size notice remain. All 13 scenario per-file counts equal baseline. No decision/scoring changes. README files, workflow and specs unchanged. Only this task folder is written under Trellis. The requested documentation example is an inert sample string, not staged document data.
