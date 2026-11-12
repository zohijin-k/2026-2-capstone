# Demo stage-two seed application

## Goal
Remove repeated manual stage-two entry during upload testing. A person completes identity verification in the UI first.

## Requirements
- Branch feat/seed-application based on main adb002f. Entry point demo/backend/tools/seed_application.py; run PYTHONPATH=. python -B -m demo.backend.tools.seed_application.
- Default newest identity-verified draft with incomplete stage two; --application-id explicitly selects one. Reject absent, unverified, completed and nondraft targets without any mutation; fixed error code only.
- Reuse patch, self_check, save_consents and save_subsidy_items handlers/models and existing validation. No direct SQL, schema changes, frontend changes, identity updates, judgment rule changes or existing test expectation changes.
- Fill applicable forms, consents/signatures and subsidy choices using obviously synthetic values. All duplicated verified identity fields copy existing name/birth exactly, without printing or logging them.
- --address defaults to an obviously synthetic address in a municipality from program configuration. --frontend-url defaults to http://localhost:5173. No --work-category option: category is a stage-three choice.
- Ownership marker in existing form1_json is permitted only if absent from forms_exports, officer responses and stage-two validation outputs. If exposed, stop implementation and report alternatives.
- --clean deletes only tool-marked applications, dependent rows and exclusively owned files (including later uploads, signatures, scans and exports). Preserve unrelated applications and shared files.
- Refuse DBs other than this checkout's demo/demo.db. Tests use isolated synthetic data, never local applicant records.
- Output only application ID, work-category state, same-tab upload instruction and processing/deletion counts. Errors print fixed codes; suppress dependency stdout/stderr.
- Statically verify same-tab /apply/upload restores sessionStorage ID without a stage-two redirect. If supported print: 1단계를 한 같은 탭 주소창에 <frontend-url>/apply/upload 입력. Otherwise report blocking code and minimum future fix.

## Acceptance Criteria
- Identity-only savings seed has exactly missing-required-upload and unselected-work-category blocker categories. Four-category tests are excluded. Job package naturally has no work-category blocker.
- Default address passes actual submission-engine municipality judgment; override works.
- Identity duplicates match; identity_json and pledge bytes stay unchanged. Identity values never appear in either output stream, including exceptions.
- Marker nonexposure tests precede feature implementation. Invalid-target and completed-target tests prove zero DB/file changes.
- Cleanup removes marked applications plus all owned rows/files, preserves unrelated rows/files and is repeatable.
- Full regression comparison: engine 1264 passed/3 skipped; backend 1057 passed plus additions; scenarios 1885 passed/0 failed, 18 modules including P14 exit zero.

## Out of scope
Frontend, identity creation/updates, schema migrations, eligibility rule changes, existing expectation changes, automatic submission and real-document OCR evaluation.

## Approval
User approved the plan and four additional constraints on 2026-11-13; implementation is authorized.

## Approved pre-commit follow-up
- User approved the proposed commit, excluding docs/audit, and froze models.py.
- Establish marker-free frontend-shaped PATCH behavior without modifying preservation/cleanup code; if ownership is lost, add the exact README warning.
- Audit four write handlers and their callees for get_session bypasses.
- Prove newly created placeholder files do not survive rollback; change only the tool if a residual file is actually found.
