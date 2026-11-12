# Demo stage-two seeding

## 1. Scope / trigger
Apply to `demo.backend.tools.seed_application` and its synthetic tests. This is a development helper for a person who already completed identity verification. Never fabricate or modify `identity_json` or call the identity endpoint. Do not change frontend, schema, eligibility rules or existing test expectations to make the helper succeed.

## 2. Signatures
`PYTHONPATH=. python -B -m demo.backend.tools.seed_application [--application-id ID] [--address ADDRESS] [--frontend-url URL] [--clean]`

There is no `--work-category`: `DocumentUpload` selects `doc_context_json.work_category` in stage three. `form1.workType` is a separate written-form question.

## 3. Contracts
- Only the actual checkout's existing `demo/demo.db` may be used. Check the SQLAlchemy engine target before opening a session; do not initialize/migrate another database.
- Select the newest verified draft with incomplete stage two unless an explicit ID is provided. Existing form completeness and self-check/consent predicates own validation; arbitrary JSON keys do not prove completion.
- Reuse `applications.patch`, `self_check`, `save_consents` and `subsidy.save_subsidy_items` with their request models. Compose their commits under a context-local outer transaction. Normal `get_session()` callers keep their existing behavior.
- Contact, bank and other test values are obviously synthetic. Name/birth duplicates copy the existing identity. Default address uses a configured target municipality; `--address` may intentionally change the subsequent region result. Synthetic dates/household inputs can affect scores and are never documentary proof.
- Ownership lives in `form1_json['_seed_application']` with a fixed versioned value. Test that it is absent from `forms_exports`, officer response projections and stage-two validation results. Existing raw applicant GET/PATCH responses echo stored JSON and include the marker; do not silently change that API contract.
- Known limitation: a stage-two PATCH whose form1 omits the marker replaces the JSON and removes ownership. Cleanup then skips that application (explicit ID returns NOT_SEEDED). Do not resave stage two after seeding; this is documented behavior, not a marker-preservation feature.
- Cleanup deletes only marked applications and their dependent Consent/Document/SubsidyItem/Review rows and exclusively owned files. Include later uploads, merged sources, consent/identity pledge signatures, scans and written-form exports. Validate storage containment and preserve unrelated/shared files. Seeding leaves the identity pledge unchanged; explicit cleanup authorizes removing the entire marked application.
- Successful output contains only IDs, work-category state, counts and the same-tab upload instruction. Dependency stdout/stderr/logging and exception strings never escape.
- Frontend route restoration uses `/apply/upload` plus `sessionStorage['applicant.activeApplicationId']`. Navigation must happen in that application's original verification tab. The tool cannot select another tab or change the already-rendered React state.

## 4. Validation and error matrix

| Condition | Required behavior |
| --- | --- |
| No eligible application, unverified/complete/nondraft explicit target | Fixed error code, no DB or file mutation |
| Wrong/missing/symlinked DB target | Refuse before connection or initialization |
| Stage-two handler failure | Roll back composed DB writes and restore affected signature files; fixed error only |
| Marker appears in an excluded projection | Stop implementation and report alternatives |
| Eligible fresh savings application | Remaining blockers are only required-upload omissions and unselected work category |
| Existing age/document eligibility failure | Preserve the rule and report the limitation |
| Unmarked application during cleanup | Leave its rows and files unchanged |

## 5. Good / base / bad cases
Good: verify a synthetic identity in the UI, seed once, then enter the printed upload URL in that same tab. Base: ordinary API calls retain normal session and validation behavior. Bad: set a work category or alter identity behind the UI, use metadata as completion proof, or delete unrelated files by a loose filename prefix.

## 6. Tests required
Use temporary synthetic SQLite/storage only. Cover marker projection gate before seeding implementation; exact blocker categories; actual submission-engine region check; duplicate name/birth and unchanged identity pledge; stdout/stderr privacy on success and exceptions; newest selection; zero mutation for rejected targets; wrong-DB refusal; late-failure DB/file rollback; completed unmarked targets; cleanup of later uploads/exports/reviews and preservation of unrelated/shared files. Confirm routing from code without editing frontend. Run full engine/backend pytest and all scenario modules against the recorded baseline.

## 7. Wrong versus correct
Wrong: copy validation into the CLI or call independently committed handlers with no rollback boundary. Correct: reuse the handlers/models and join their sessions to the CLI's outer transaction, verifying failure rollback.

Wrong: claim an address is unused because per-file upload identity comparison ignores it. Correct: trace submission `_run_review` through `extract_region` and the engine's `run_stage2` municipality check.
