# Verification-case implementation report

## Result

Implemented the private multi-case regression CLI on `feat/verify-cases` from `main` at `b61fa69`. Shared assessment calls preserve existing upload verdicts, applicant findings, blocker scope and legacy output. Independent review found no changes needed. Awaiting user commit approval; no commit or push performed.

## Usage and fake manifest

```sh
PYTHONPATH=. python -B -m demo.backend.tools.verify_cases --cases /fake/cases.json --record
PYTHONPATH=. python -B -m demo.backend.tools.verify_cases --cases /fake/cases.json
```

Example only; these paths are fictitious and were not used for testing:

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "case7",
      "slot": "nhis_payment",
      "self_identity": true,
      "file": "/fake/payment.pdf"
    },
    {
      "id": "work_case",
      "slot": "work_proof",
      "work_category": "직장가입자",
      "self_identity": true,
      "file": "/fake/work.pdf"
    },
    {
      "id": "ok_income",
      "self_identity": true,
      "income": {
        "payment": "/fake/payment.pdf",
        "qualification": "/fake/qualification.pdf",
        "acquisition_loss": "/fake/history.pdf"
      }
    }
  ]
}
```

The adjacent expected name is `cases.json.expected.json`. Actual resolved manifest/expected targets outside the checkout are allowed without check-ignore; inside targets must be ignored and untracked. Relative document paths resolve from the resolved manifest directory. Case IDs must be nonidentifying. Successful comparison prints IDs with O/X, changed signed tokens only, and matching/total; any mismatch or case error exits 1. Case exceptions show only ID/X/class name. Top-level invalid input/location/baseline or recording I/O errors use safe fixed diagnostics and exit 2.

## Changed files

- `demo/backend/tools/verify_cases.py`: strict manifest/baseline schemas, resolved Git policy, allowlisted snapshots, comparison, class-only case errors, atomic recording and original-document collision protection.
- `demo/backend/tools/verify_upload.py`: shared transient `Assessment`, `assess_document`, `assess_income` and validation-name helper; legacy text renderers preserved.
- `demo/backend/tests/test_verify_cases.py`: 68 new synthetic tests. Existing verify_upload test files remain byte-for-byte unchanged.
- `.trellis/spec/backend/verify-cases.md` and backend index: executable CLI/privacy/location/reuse contract.
- This task directory: PRD/design/implementation plan, binding approval conditions, research, context manifests, metadata and this report.

No verdict/blocker rules, extractors, engine source, API, frontend or ignore policies changed. No DB persistence. New tests use temporary authored documents/manifests/Git repositories only, with no real-document or actual private-data-path references.

## Verification

| Suite | Baseline | Final | Difference |
| --- | --- | --- | --- |
| engine_v2 pytest | 1,264 passed / 3 skipped | 1,264 passed / 3 skipped | Unchanged |
| backend pytest | 1,159 passed | 1,227 passed | +68 new tests |
| 17 counting scenarios | 1,885 passed / 0 failed | 1,885 passed / 0 failed | Unchanged |
| All 18 scenario modules | All exit 0 | All exit 0, including P14 | Unchanged |
| Focused CLI tests | 81 existing | 149 passed | 81 unchanged + 68 new |
| Independent review rerun | — | 149 passed | No findings or changes |

Commands: `PYTHONPATH=. .venv/bin/python -B -m pytest engine_v2/tests -q`, backend equivalent, focused three CLI test files, and all `demo.backend.tests.run_p*_scenarios` modules sequentially. Engine reported 7 existing dependency warnings, backend 9 existing dependency/deprecation warnings. No test failures, weakened assertions, new skips or removed checks.

Original CLI test file hashes match the pre-implementation hashes. Exact pre/post synthetic output comparison is identical for document, validations/self-identity, work, income and error modes. Final AST parsing of all three changed Python files, P4 static source scan, `git diff --check` and Trellis context validation (9 entries per manifest) pass. No configured Python lint/typecheck command was found; AST parsing is not claimed as type checking.

Coverage includes record-then-compare, reason add/remove signs and affected-case isolation, applicant-only/severity/status/identity/blocker/validation/work/income deltas, code-order/duplicate/confidence stability, added/removed cases, schema injection, outside/ignored/tracked/symlink locations, no outside Git invocation, source collisions, atomic failure preservation, swallowed write attempts, exception-class-only errors, source-resolution exceptions, native/Python/log suppression and zero value/path/confidence persistence.

## Evidence and limits

Synthetic-only logs: `/tmp/verify-cases-engine.log`, `/tmp/verify-cases-backend.log`, `/tmp/verify-cases-scenarios.log`, `/tmp/verify-cases-scenarios-summary.json`, per-module `/tmp/verify-cases-run_p*_scenarios.log`, `/tmp/verify-cases-focused.log`, `/tmp/verify-cases-independent-check.log`. Legacy comparisons: `/tmp/verify-cases-legacy-before.json`, `/tmp/verify-cases-legacy-after.json`; original test hashes: `/tmp/verify-cases-original-test-hashes.txt`.

These results establish synthetic integration, verdict reuse and privacy boundaries. No real-document OCR accuracy was measured. Positive vocabularies require reviewed updates for future legitimate codes/validation names. Commit approval must include `git diff --stat main` and the three complete suite results above, per the user's condition 6 and workflow Phase 3.4.
