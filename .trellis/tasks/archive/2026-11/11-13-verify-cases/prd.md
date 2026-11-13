# Private verification-case regression CLI

## Goal

Replace repeated manual `verify_upload` runs and visual comparison with one command that assesses multiple private document cases and reports only verdict changes from an explicitly recorded baseline.

## Background

- Branch `feat/verify-cases` was created from clean `main` at `b61fa69`; base branch is `main`.
- Task creation/planning was approved on 2026-11-13. Implementation requires separate approval of these artifacts; status stays `planning` until then.
- Existing document/income orchestration returns text (`demo/backend/tools/verify_upload.py:231`, `:294`). The CLI already provides read-only execution and native/Python output suppression (`:59`, `:76`).
- Applicant finding projection is shared in `demo/backend/api/common.py:193`. Local evidence and other verdict owners are recorded in `research/shared-assessment.md`.

## Requirements

### R1 — Execution and cases

Add `demo/backend/tools/verify_cases.py`:

`PYTHONPATH=. python -B -m demo.backend.tools.verify_cases --cases <cases.json> [--record]`

The uncommitted JSON manifest represents unique nonidentifying IDs, explicit slot, selected work category, file path, self-identity mode and the three-document income mode of `verify_upload`. Support its program selection too, with the same default. Relative document paths resolve from the manifest directory. Reject malformed cases and ambiguous document/income combinations with fixed codes. `--slots-list` is a diagnostic listing, not an assessment case.

### R2 — Private locations

Permit manifests and adjacent `<cases.json>.expected.json` only outside this checkout or at git-ignored paths inside it. Verify inside paths with `git check-ignore`; refuse tracked/non-ignored files and fail closed if checks fail. Resolve symlinks and apply the policy to the actual path. Outside-checkout actual paths are allowed without calling check-ignore; inside-checkout actual paths must be ignored and untracked. Apply the restriction independently to the expected file and any recording temporary file. Never echo rejected paths or add blanket ignore rules.

### R3 — Direct reuse

Both CLIs must call shared in-process orchestration over the same existing assessment functions. No `verify_upload` subprocess, text parsing, duplicated orchestration or copied verdict rules. Preserve self-identity behavior, NHIS pair refresh, income document order, selected work category and mode-specific blocker scope. Existing `verify_upload` visible output remains exactly unchanged; internal separation of assessment and formatting is in scope.

### R4 — Value-free verdicts

For each document retain detected type, final document status, reason/applicant-reason code and severity pairs, and failed-validation names. Retain identity availability and blockers as case-level O/X. Income cases retain all three per-slot results plus income status/reason codes; applicable document/work cases retain work status/reason/detail codes. Identity means availability of the existing temporary self-identity reference, never name/birth or external verification. Compare statuses, codes, severities and names only; ignore code ordering/duplicates and numeric confidence. Confidence changes that actually change a rule's verdict still produce a verdict difference.

### R5 — Recording and comparison

- `--record` explicitly writes all successfully assessed cases to the adjacent snapshot. Do not replace an old baseline if any case or write fails. Never record implicitly during comparison.
- Default execution prints every case ID with O/X, then only signed field-qualified tokens for X (`+` current, `-` recorded), followed by matching/total count. No unchanged details or full snapshot dumps.
- Match by ID/slot, not position. Added/removed IDs produce X and `+CASE_ADDED` / `-CASE_REMOVED`; include the union of IDs in the denominator so stale records cannot silently pass.
- All matches / successful record: exit 0. Any comparison X: exit 1. Missing/invalid/incompatible baseline, invalid manifest/location/arguments or recording I/O failure: fixed code and exit 2.
- Individual assessment exceptions print only the case ID, X marker and exception class name, never message/path/stack, and do not prevent other cases from running. Comparison or recording with any case error exits 1. They cannot become expected successful results. Recording aborts without replacing the prior baseline.

### R6 — Privacy

Output may contain only nonidentifying case IDs, reviewed codes/enums, severities, validation names, structural field/slot identifiers, O/X and counts. IDs are bounded ASCII identifiers without dots, slashes, whitespace or controls; authors must not use names. Paths, filenames, extracted values, raw text and numeric confidence never enter output or recorded data. Do not persist arbitrary model/OCR objects or messages/evidence. Apply strict allowlists to current results and loaded baselines; never echo malformed input. Suppress dependency stdout/stderr/native output/logging and exception text. Execute sequentially under the existing quiet/read-only boundary. No DB/upload/cache writes during assessment; recording writes only the checked snapshot and its temporary sibling.

## Acceptance criteria

| ID | Observable outcome | Requirements |
| --- | --- | --- |
| AC1 | Synthetic mixed document/work/income cases record then compare all O, exit 0; requested safe fields include all three income slots. | R1, R3–R5 |
| AC2 | Code additions/removals affect only that case with correct +/-; severity, applicant projection, type/status, identity, blockers, validation and work/income changes are detected. Order/confidence-only jitter with unchanged verdicts stays O. | R4–R5 |
| AC3 | Fake names/filenames/paths, dates/amounts/raw text and confidence do not appear in stdout/stderr or snapshots, including malformed baselines, native logs and error paths. | R6 |
| AC4 | Outside/ignored paths work; non-ignored/tracked manifests or snapshots, Git-check failure and symlink bypasses are refused without path disclosure. | R2, R6 |
| AC5 | Invalid inputs/baselines, ID additions/removals and assessment/record failures follow R5; old baseline and original files remain intact on failure. | R1, R5–R6 |
| AC6 | Existing document/work/income/validation/error CLI output remains byte-for-byte compatible; no existing assertions are weakened. | R3 |
| AC7 | Compare full regressions against engine 1,264 passed / 3 skipped, backend 1,159 passed plus additions, counting scenarios 1,885 passed / 0 failed; all 18 scenario modules exit 0 including P14. | R3 |
| AC8 | Report fake-path manifest example, changed files and actual test counts; distinguish synthetic evidence from real-document behavior. | R1–R6 |

## Out of scope

No verdict/blocker rule or threshold changes, extractors/OCR-engine changes, frontend changes, database migration, application seeding, real-document execution or references to actual private paths during development, real manifests/snapshots committed, CI case inventory or automatic baseline refresh.

## Planning status

Requirements are converged for review; no blocking questions remain. Proposed schema/output and risks are in `design.md`; execution and validation are in `implement.md`. Implementation was approved in the subsequent user message with six binding conditions recorded in `approval.md`. Those conditions override conflicting details in the initial plan.
