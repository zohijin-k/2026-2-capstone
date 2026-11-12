# Implementation plan

- [x] Read backend specs and research; prove marker projections safe with synthetic tests. Stop/report if unsafe.
- [x] Implement guarded CLI, reuse handlers/models, completion preflight, fake values, private output, marker and scoped cleanup.
- [x] Add acceptance tests including rollback, no-mutation, same-tab source contract and submission region judgment. No original expectation changes.
- [x] Run focused tests and independent full-scope review; fix within boundary.
- [x] Run .venv/bin/python -B -m pytest engine_v2/tests -q and backend equivalent; run every demo.backend.tests.run_p*_scenarios sequentially.
- [x] Write report.md: field dependencies, required fields/consents, work stage/field, address behavior, routing, marker, changed files and exact counts.
- [x] Update backend CLI spec and demo usage docs; git diff --check.
- [x] Present the concrete commit plan and receive user approval; exclude preexisting docs/audit. No push, amend or premature archive.

## Approved pre-commit checks
- [x] Confirm marker-free PATCH loss and --clean skip for both programs; add exact README warning without behavior changes.
- [x] Audit all four handlers and reachable session construction; no bypass found.
- [x] Test actual new placeholder PNG cleanup on late-handler, partial-write and outer-commit failures; no tool fix needed.
- [x] Complete final backend run (1107 passed); execute the user-approved work commit with models.py unchanged from its approved content and docs/audit excluded.
