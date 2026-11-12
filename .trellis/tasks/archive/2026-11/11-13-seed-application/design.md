# Design

## Change boundary
Add a developer CLI and synthetic acceptance tests using existing endpoint handlers. Other expected edits: demo usage docs, backend CLI spec, task artifacts. No frontend or judgment-rule edits.

Approved narrow shared change: models.get_session keeps its signature and normal engine behavior; a ContextVar-bound connection and session_transaction context let the CLI compose existing independently committing handlers atomically. Bound Sessions use rollback_only transaction joining, avoiding SQLite savepoint release commits. Test ordinary session behavior and late-handler rollback explicitly. This changes no schema or validation rules.

## Data and validation
Guard the actual SQLAlchemy engine URL before connecting or initializing. Never create/migrate a missing DB. Select ORM Application rows by created_at/id descending. Reuse identity parsing, form completeness predicates, self-check evaluation and consent checks for preflight. Do not infer completion from presence of arbitrary JSON keys.

Ownership: form1_json['_seed_application'] with a fixed versioned value, only after projection tests prove it absent from rendered exports, officer responses and validation outputs. Applicant raw GET compatibility remains unchanged; this exclusion was not requested for raw applicant GET. The marker survives doc-context replacement because it is in form1.

Fill form1/form5 using verified identity duplicates, a configured municipality fake address, documented synthetic household/date inputs, placeholder PNG signature and one deterministic subsidy selection for job_package. Call patch, self_check, save_consents and save_subsidy_items with their request models and a synthetic Request. Existing patch identity locking remains authoritative. Suppress all dependency output using quiet_dependencies and logging suppression. Errors never format dependency exception strings. Service failures must not leave unmarked partial changes; implement suitable transaction/recovery without copying validation.

Cleanup uses ORM deletion for Consent, Document, SubsidyItem, Review and Application. Validate application-specific storage paths and recorded paths before deleting documents, signatures (including original identity pledge under explicit --clean authorization), scans and forms_exports/archive. Preserve shared files, unrelated paths, prefix collisions and symlinks. Seed itself never changes the pledge or identity JSON.

## Compatibility
Work category belongs to stage three, distinct from form1.workType. Omit the option and preserve context. Savings seed retains missing uploads and work_category blockers; job package has no work requirement. Existing age/document/eligibility blockers must never be suppressed to satisfy tests.

ApplyFlow.savedPage accepts /apply/upload and reads applicant.activeApplicationId from sessionStorage; restore uses initialPage.stage directly. Output requires original tab and full navigation, not URL application-ID selection. No frontend changes.

## Verification and rollback
All tests use temporary synthetic SQLite/storage with the expected path explicitly patched inside tests (no production bypass option). Probe marker exposure first. Exercise endpoint handlers and the submission region check. Full pytest/scenario suites preserve expectations. Report exact counts and source anchors. Rollback is removal of new tool/tests/docs; do not broaden scope if constraints fail. Commit only after the project's concrete commit-plan approval gate.

## Independent review
The check agent corrected preexisting stage-two signature scans taking precedence over the fake electronic signature by reusing the scan-delete handler with byte-for-byte restoration on failure. It removed duplicated consent/subsidy completion checks in favor of existing _blockers. Final focused suite: 45 passed. Same-tab routing is confirmed by source inspection only; no browser execution claim. No unresolved review findings.

## Pre-commit evidence
Marker-free form1 PATCH replaces stored JSON and loses the marker; cleanup then skips the application. This limitation is intentionally documented, with no API/tool preservation change. The four handlers and reachable helpers use get_session; only the intended outer transaction opens engine.begin. New tests prove fresh PNG removal after handler, partial-write and outer-commit failure. No tool/model modification was needed. User froze models.py and approved the work commit excluding docs/audit.
