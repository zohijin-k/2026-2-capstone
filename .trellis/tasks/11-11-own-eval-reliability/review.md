# Independent full-scope code review

Reviewed metric alignment/ordering/calibration, generator/split/font downloader, standalone rectification, private CLI/output module and all three new test files against task artifacts and backend quality contract.

- Existing test files, demo/backend and .trellis/spec have no tracked modifications.
- NFC/Unicode-whitespace normalization remains strict; punctuation/case/lookalikes remain errors. Geometric order does not inspect truth text. Synthetic camera homography is oracle geometry for evaluation ordering only and must be explicitly distinguished from end-to-end reading order; raw_stream_cer is retained. Axis-aligned detected bounds yield approximate inverse-mapped bounds.
- Found and reported cross-word Hangul composition causing calibration IndexError; parent fixed normalized character score provenance and added regression coverage. Parent also included correction overhead in JBAI synthetic timing.
- Private benchmark uses allowlisted generic keys and fixed status codes; exception/input strings and native/Python logs are suppressed. No implicit output directories/files. Real-input code was reviewed without accessing any private-data path. Structured value CER no longer gives credit for schema labels/JSON punctuation. Partial address/date annotation semantics are documented.
- Font downloads are immutable and hash-checked, preserve OFL notices locally, and generated/downloaded assets are ignored. Train/test fonts and actual layout families are disjoint. New phone formation includes independent signed corner displacements, background, shading and blur.
- Perspective implementation detects pixels only, has explicit failure/no-op status, and is not wired into engine defaults.
- New targeted suites pass; final whole-project regression, benchmark tables and staged content audit remain parent integration gates.

No outstanding blocking code finding at this review snapshot. No files edited by reviewer except this task note.

## Follow-up: strong-perspective bbox ordering

Reviewed revised `ordered_words(..., line_baselines=...)` after strong-perspective inverse axis-aligned bounds became tall enough to merge separate rows. Revised manifests associate inverse-mapped bbox centers with the nearest authored baseline only within 0.45 times the minimum neighboring baseline gap. Distant detections keep their geometric position; all recognized words and false background detections remain in the stream. Row sorting uses no truth text and does not alter characters or extraction. Legacy manifests keep height-relative row grouping. This is additional oracle row geometry for synthetic recognition evaluation, not a deployable document-order algorithm.

Targeted metric suite: 6 passed in 0.39s, including tall inverse boxes and retained background false-positive coverage. Requested parent update current CER documentation to distinguish authored-baseline rule from legacy fallback. No blocking code finding in this delta.
