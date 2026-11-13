# Implementation plan

## Gate

- Task creation/planning approved; branch `feat/verify-cases`, base `main`.
- PRD, design and plan were presented; the user approved implementation with the refinements in `approval.md`.
- Implementation approval received; apply the binding refinements in `approval.md`.
- `task.py start 11-13-verify-cases` completed; current status is `in_progress`.

## Ordered execution after approval

1. Follow Trellis's default implement-agent dispatch with prompt prefix `Active task: .trellis/tasks/11-13-verify-cases`. Agent reads implement manifest, PRD, design and this plan; implements directly without nesting implement/check agents or committing. Load backend specs. Capture exact existing CLI synthetic outputs for document, work, income, validation and errors before refactoring.
2. Separate structured document/income orchestration in `verify_upload.py` from existing text rendering. Preserve every call, pair refresh, identity callback, mode-specific blocker filter and legacy output. Share safe validation-name extraction. Run existing CLI tests and exact before/after comparisons before continuing.
3. Add `verify_cases.py` manifest parsing, ID/schema checks, manifest-relative paths and safe parser. Implement actual Git location enforcement, cwd independence, tracked-file rejection, lexical/resolved checks, snapshot/temp validation and collisions. No bypass flags, ignore-policy changes or assessment subprocess.
4. Add allowlisted snapshot generation, strict baseline validation, signed set comparison, case membership handling and exact O/X/count/exit behavior. Use the shared quiet/read-only assessment boundary; keep Git and atomic snapshot writes outside it. Preserve old baseline on failures.
5. Add synthetic acceptance tests in `test_verify_cases.py`, with only additive legacy compatibility coverage if required. Reuse authored document helpers and real temporary Git repositories. Cover the matrix below without opening private files.
6. Dispatch an independent Trellis check agent with the same `Active task:` prefix, `check.jsonl`, artifacts and complete diff; no nested implement/check dispatch. Review the entire affected backend scope and Quality Check guidelines, fix findings, rerun affected checks, then complete full regression validation. No rule/extractor/frontend edits or weakened expectations.
7. Apply `trellis-update-spec` and record the new private-manifest/snapshot/shared-assessment contract where appropriate. Report fake-path manifest example, changed files, actual counts and material limitations. Recheck Python lint/typecheck configuration; if absent report it as unavailable, using AST parsing/diff checks without calling them type checking.
8. Follow workflow Phase 3.4: inspect dirty paths/history, propose a concrete batched commit plan excluding unrelated files, obtain confirmation before git add/commit. No push/amend; finish-work/archive/journal at the later appropriate gate.

## Acceptance test matrix

| Area | Required evidence |
| --- | --- |
| Happy path | Document/work/three-file income record then all O, exit 0; complete safe per-slot fields; appended expected filename |
| Differences | Reason add/remove, severity/applicant-only changes, failed validation, type/status, identity/blocker, work/income changes; unaffected cases O; correct signs and exit 1 |
| Stability | Reordered cases/codes, duplicate findings and confidence jitter with unchanged verdicts stay O; no confidence serialized |
| Membership | Added/removed IDs, fixed signed codes, union denominator, ID-based matching |
| Manifest validation | Wrong/extra/duplicate JSON keys, IDs, path/control-like IDs, bool/type errors, empty cases, ambiguous/incomplete modes, invalid category/program/slot/file; fixed safe errors |
| Location | Outside/ignored/unignored/tracked/force-added paths; Git failure; expected/temp policy independent; cwd independence; symlink input/output/parent bypass; no echoed paths |
| Baselines | Missing/invalid JSON/schema/version/enums/codes/IDs/slots, extra messages/paths/raw data; reject without disclosure or implicit recording |
| Recording failures | Failed case/write/replace preserves old expected bytes; temporary cleanup; no source/manifest/DB/upload writes |
| Privacy | Distinct fake name in filename and OCR field, dates/amounts/raw text, arbitrary code/validation payloads, Python/native stdout/stderr/logging/exception text; absent from output and expected JSON |
| Shared reuse | Shared orchestration/pair refresh/applicant projection and blocker scope; byte-for-byte original CLI output; no assessment subprocess/copied logic |
| Standalone | `-B -m` entry point on synthetic documents, exact exits, safe help/errors and read-only default comparison |

## Validation

Use the virtual environment (bare `python` is unavailable), synthetic temporary inputs only:

```sh
PYTHONPATH=. .venv/bin/python -B -m pytest demo/backend/tests/test_verify_upload.py demo/backend/tests/test_verify_upload_validations.py demo/backend/tests/test_verify_cases.py -q
PYTHONPATH=. .venv/bin/python -B -m pytest engine_v2/tests -q
PYTHONPATH=. .venv/bin/python -B -m pytest demo/backend/tests -q
```

Inspect scenario entry points for synthetic/local behavior, then run every `demo.backend.tests.run_p*_scenarios` module sequentially with the same interpreter. Do not parallelize scenarios sharing DB/storage. Capture each exit code and final `통과 ... / 실패 ...` counts; P14 has no numerical summary and needs a separate zero exit check. Keep synthetic logs in `/tmp/verify-cases-*`. Preserve existing external-OCR opt-in defaults; do not enable real-document/remote assessment.

Also run `git diff --check`, AST parsing of modified Python without bytecode writes, configured lint/typecheck if present, and `python3 -B .trellis/scripts/task.py validate 11-13-verify-cases`.

| Suite | Baseline | Required comparison |
| --- | --- | --- |
| engine_v2 pytest | 1,264 passed / 3 skipped | No failures, same skips |
| backend pytest | 1,159 passed | Baseline plus actual additions; no removed/weakened expectations |
| 17 counting scenarios | 1,885 passed / 0 failed | Unchanged |
| All 18 scenario modules | all exit 0, including P14 | Unchanged |

Investigate and report baseline deviations rather than modifying assertions/counts to hide them. Repeat broad checks only after changes/findings justify it.

## File scope and rollback

- New `demo/backend/tools/verify_cases.py` and `demo/backend/tests/test_verify_cases.py`.
- Internal `demo/backend/tools/verify_upload.py` separation and, only if needed, additive `test_verify_upload*.py` compatibility tests.
- Relevant `.trellis/spec/backend/` contract/index and this task's planning/research/verification artifacts.
- No rules, extractors, frontend, ignore rules or real/private files.

If exact legacy compatibility cannot be preserved, stop and revise the design before widening scope. Material schema/output/scope changes require renewed plan review. Rollback is removal of new tool/tests and reversion of the internal separation, with private files untouched.

## Current results

Implementation and independent review complete. Final results: engine 1264 passed/3 skipped; backend 1227 passed (+68); scenarios 1885 passed/0 failed with all18 exits zero; focused and independent149 each. Existing CLI tests/output unchanged. See `report.md`. Commit remains gated on showing `git diff --stat main` and receiving user approval.
