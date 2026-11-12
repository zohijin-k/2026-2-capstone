# Seed application implementation report

## Branch and scope
Based on main adb002f; branch feat/seed-application. Frontend, identity verification flow/values, schema, eligibility/blocker rules and existing test expectations are outside this change. Preexisting untracked docs/audit/ is unrelated.

## 1. Inputs read during stage-three upload judgment

| Source field | Consumer | Purpose |
| --- | --- | --- |
| identity_json.name, birth | rules/identity.py identity_of; api/documents.py upload_document/_upload_merged; upload_assessment.py assess_upload/assess_nhis_identity | Verified identity comparison, including NHIS relationships. Phone/method/verified_at/pledge are not upload identity comparison fields. |
| doc_context_json.work_category | api/common.py doc_context/checklist_for; rules/required_docs.py build_checklist | Required work-proof slot/type. This is a stage-three input, not a stage-two form field. |
| doc_context_json.admin_fixed_term, workplace_count | same checklist path | Additional labor-contract slot and multiple workplace slots. |
| doc_context_json.handwritten_admin_consent, paper_forms.서식5 | same checklist path; api/documents.py upload_document; upload_assessment.py assess_upload | Administrative-consent upload mode and scan inspection. |
| SubsidyItem.item_type, count_index, linked_interview_index | api/common.py subsidy_selections/checklist_for | Stage-two subsidy choices determine job-package evidence slots and linked interview evidence. |
| SubsidyItem.receipt_amount | api/documents.py upload_document.receipt_amount_loader; upload_assessment.py assess_upload | Compare recognized receipt amount with declared amount. |

Program code, pinned criteria version and application created/submitted date also determine checklist and issue-date bounds through api/common.py checklist_for/checklist_from_inputs. Previously uploaded Document rows provide paired-document and duplicate-slot context. Raw form1 contact/address values, form5 text and self-check answers are not the identity reference used by explicit-slot upload assessment.

Later final-check/submission reads form1.birth (age), householdSize (comparison with document household size only), transferIn (residence-duration fallback), employedAt (work-duration scoring), address (municipality eligibility) and name (engine applicant), in rules/facts.py build_facts, api/review.py _blockers/_run_review and engine_adapter.py to_engine_applicant. These are separate from per-file upload assessment. Synthetic household/date values can therefore affect demo scoring and are test inputs, not documentary proof.

## 2. Stage-two requirements in final-check and submit
Both api/review.py:442 final_check and api/review.py:749 submit call the same _blockers function (api/review.py:157). submit additionally requires draft status and rejects any current blocker.

- Savings required form1 keys, from rules/programs.py DOUBLE_SAVINGS_REQUIRED_FIELDS: name, birth, address, mobile, transferIn, householdSize, employedAt, bankName, accountNo.
- Job-package required keys, from JOB_PACKAGE_REQUIRED_FIELDS: name, birth, address, mobile, bankName, accountNo, accountHolder, bankbookFileName. The existing demo stores only the bankbook filename in stage two, not bankbook bytes.
- Nonempty email must be valid, including when email is not in required_form_fields.
- Job package must have at least one SubsidyItem; actual-cost selections must have receipt_amount.
- Savings agreed consents: privacy, unique_id, third_party, admin_info (paper-form mode substitutes an uploaded consent). Job package: privacy, third_party.
- Required upload omissions, explicit document FAILs, unselected savings work category and confirmed existing age/income/work eligibility failures also block submission.

The existing _blockers does not independently require every export-form field, self-check completion or signature bytes. The tool must still fill full written forms and signatures and use api/forms.py _form_is_complete plus existing self-check/consent paths for stage-two completion, without strengthening or weakening final-check/submit rules.

## 3. Work category
DocumentUpload.tsx:503-521 asks for the category in stage three; api/documents.py:149 set_doc_context saves doc_context_json.work_category via DocContextRequest. form1.workType asks a different question (employment contract type). No --work-category option is implemented and no category is synthesized. For job_package the CLI prints work category as 해당 없음, because no category control exists. For an otherwise eligible identity-only savings application, exact remaining blocker classes must be missing required uploads and work_category. A job-package application naturally has no work-category requirement. Existing age or preexisting document failures are preserved.

## 4. Address
Address is already used in actual submission eligibility: api/review.py:470 _run_review -> rules/facts.py:394 extract_region(form1.address, program.target_regions) -> engine_adapter.py to_engine_applicant -> engine/stage2_eligibility_check.py:22 run_stage2, which checks residence_region against configured target municipalities. It also determines officer jurisdiction through api/officer.py Entry and extract_town. It is not merely a planned future residence field.

The default must be built from the selected program's target_regions, followed by clearly fictitious street/unit text. --address remains caller-controlled and can deliberately produce a different eligibility result. No rule is changed to force that override to pass.

## 5. Frontend restoration (code inspection)
frontend/src/pages/applicant/ApplyFlow.tsx:63 savedPage accepts pathname /apply/upload, reads sessionStorage['applicant.activeApplicationId'], and rejects only absent/invalid IDs or invalid routes. The restore effect (lines 148-192) loads application/program/consents/status and sets initialPage.stage directly. It does not redirect incomplete stage two to forms. Therefore a full navigation in the same original identity-verification tab restores the upload screen with current server data. Tool completion alone cannot change an already-rendered React stage.

The URL does not carry an application ID, and a new tab without that sessionStorage state cannot select the seeded application. Explicit --application-id can refer to an application different from the tab's stored ID; the operator must use its original tab. No frontend change is required for the requested same-tab route. Vite uses its default port; demo/README.md documents http://localhost:5173.

## 6. Marker, files and tests
The ownership value is `form1_json["_seed_application"] = "seed-application-v1"`. Synthetic preflight tests for both programs passed before the feature was implemented, then filled-form export tests reconfirmed nonexposure. Marker nonexposure applies to exported forms, officer response projections and validation outputs; existing applicant raw GET/PATCH save responses echo form1_json, including metadata, by their existing contract. No attempt is made to change those APIs.


The CLI checks the actual engine URL, requires the existing canonical demo/demo.db, rejects symlinks/URI overrides/other drivers or targets, and never initializes a database. Invalid arguments/targets emit only `error: FIXED_CODE` and exit 2; success exits 0. Development tests patch the expected path explicitly into temporary synthetic fixtures; there is no production database-bypass option.

Selection uses created_at descending, then ID descending. It composes existing validators within a transaction explicitly rolled back after preflight so lazy legacy criteria creation cannot mutate a rejected application. Filling composes existing handler commits using models.session_transaction and ContextVar-bound sessions with rollback_only joining. Normal API get_session still returns an ordinary Session(engine). Failure/interrupt tests verify the actual database bytes and affected signature files are restored.

The tool writes seed@example.com, 010-0000-0000, a clearly fake bank/account, synthetic household/date choices and a PNG visibly labeled SEED / FAKE SIGNATURE. It copies verified name/birth to form1/form5 and the applicant's account-holder name. Any preexisting stage-two signature scan is removed through the existing scan-delete handler so restoration selects the fake electronic signature; its exact bytes are restored on failure. Existing incomplete paper-consent signing choice is switched to electronic using the existing doc-context handler while preserving work category/other context. Already complete paper-consent applications are rejected without changes. No work category is created or changed.

Cleanup deletes marked Application rows and dependent Consent/Document/SubsidyItem/Review rows via ORM. It validates recorded file paths against each application's storage namespace and includes later uploads, merged originals, orphan files within the owned directory, electronic signatures, identity pledge, signature scans and written-form PDF/archive/temp files. Unrelated application's references protect shared files. Unsafe paths/symlinks cause a pre-mutation refusal. Files are temporarily moved within storage and restored if database deletion fails; successful cleanup removes empty owned directories. If storage was already removed, rows can still be cleaned. The all-clean and ID-scoped forms are repeatable; an unmarked explicit ID is never expanded into an all-clean operation.

## Changed files

| File | Purpose |
| --- | --- |
| demo/backend/tools/seed_application.py | New guarded stage-two CLI and scoped cleanup |
| demo/backend/models.py | Context-local outer transaction composition; no schema change |
| demo/backend/tests/test_seed_application.py | New synthetic acceptance coverage; existing tests unchanged |
| demo/README.md | Invocation, original-tab navigation, synthetic values and cleanup instructions |
| .trellis/spec/backend/seed-application.md | Executable CLI/transaction/privacy/cleanup contract |
| .trellis/spec/backend/index.md | Index the new contract |
| .trellis/tasks/11-13-seed-application/ | task.json, prd.md, design.md, implement.md, implement.jsonl, check.jsonl, research/contracts.md and this report |

No frontend, engine, existing test or judgment-rule source was modified. No real local application was seeded or deleted while developing; only isolated authored fixtures were mutated. This report is included in the user-approved implementation commit. No archive, push or merge is performed.

## Pre-commit checks requested by the user

### 1. Resaving form1 without the ownership marker

Confirmed for both programs using an actual HTTP PATCH on the existing applications router, with the frontend-shaped body `{form1, self_check, form5}` and `_seed_application` omitted from form1. `api/applications.py:234` replaces form1_json with the normalized/identity-locked request object; it does not merge the old marker. The marker disappears in both the save response and the reloaded application.

After that PATCH, `--clean` reports zero deleted applications/rows/files and leaves the application and its dependent rows/files intact. `--clean --application-id ID` returns `error: NOT_SEEDED` and also leaves everything intact. **Cleanup therefore misses a seeded application if stage two is resaved without the marker.** No preservation or cleanup-identification code was changed. README now includes the exact usage line: `시드한 신청은 2단계를 다시 저장하지 말 것.` This check does not claim that every possible frontend save omits the marker; it establishes the requested marker-free payload behavior.

### 2. Session construction in the four handlers and their callees

| Handler / reachable helper | Session entry |
| --- | --- |
| applications.patch | api/applications.py:227 get_session; conditional consent cleanup uses that same session |
| applications.self_check | _load at :179 and its own session at :330 both use get_session |
| applications.save_consents | _load at :179 and its own session at :360 both use get_session |
| subsidy.save_subsidy_items | api/subsidy.py:140 get_session |
| common.load_application, subsidy_rows, subsidy_selections | api/common.py:30 and :39 use get_session; selections delegates to subsidy_rows |
| criteria.for_application, history, latest (including lazy default creation) | rules/criteria.py:159, :134 and :149 all use get_session |
| subsidy._used_in_scope and _response | api/subsidy.py:180 uses get_session; response delegates to the common/criteria paths above |

No direct Session(engine) exists in those four handlers or their reachable helpers. The only production Session constructors found in the backend are inside models.get_session (Session(connection, rollback_only) and ordinary Session(engine)). models.session_transaction intentionally opens its outer connection with engine.begin. models._add_missing_columns has engine.connect at line 202, but the tool never calls init_db or _add_missing_columns. Conditional paper-consent/document checklist lookups also use get_session. This was independently audited without edits.

### 3. Files left after rollback

No residual placeholder files were found. The PNG is initially generated in memory; save_consents writes storage/signatures/{application_no}_admin_info.png. The tool already snapshots this path and scan paths, unlinks files absent before the run and restores preexisting file bytes on BaseException. No tool cleanup change was necessary.

Three new savings tests inject failure (a) after save_consents has actually written the PNG, (b) immediately after a partial PNG disk write, and (c) at the outer database commit after all handlers ran. Each proves a PNG existed inside the failing operation, is absent afterward, all file hashes match the pre-run snapshot, the application and identity pledge are unchanged and no Consent rows remain. Existing tests additionally cover interrupts, overwritten signatures and scan restoration. The two marker-free PATCH cases plus these three cases add five tests, for 50 focused cases total.

models.py was not changed during this follow-up; its SHA-256 remained `6d5c33d3ffc1f1dbcae529f80cf85fa5ae71d1e8928e726d624850858bd21c72`. docs/audit remains excluded from the approved commit.

## Validation results

| Suite | Requested baseline | Final result | Comparison |
| --- | --- | --- | --- |
| engine_v2/tests | 1264 passed, 3 skipped | 1264 passed, 3 skipped | Unchanged |
| demo/backend/tests | 1057 passed | 1107 passed | +50 new acceptance cases; no failures |
| All counting scenarios | 1885 passed, 0 failed | 1885 passed, 0 failed | Unchanged |
| All scenario module exits | 18 successful modules | 18 exit zero, including P14 | Unchanged |

Commands: `.venv/bin/python -B -m pytest engine_v2/tests -q`, `.venv/bin/python -B -m pytest demo/backend/tests -q`, and each `demo.backend.tests.run_p*_scenarios` module sequentially. Engine reported 7 warnings; final backend reported 9 warnings, all from the existing dependency/deprecation paths. No configured Python lint/typecheck command was present. New/changed Python files passed AST parsing, `git diff --check` passed, and Trellis context validation passed.

Final focused suite: 50 passed (45 original cases plus the five requested pre-commit checks). Acceptance covers both programs, exact savings blocker classes, actual engine municipality PASS, name/birth duplication and unchanged identity pledge, stdout/stderr privacy including native output and interruptions, no mutation on refused targets including lazy legacy criteria creation, rollback of committed handlers and replaced signatures/scans, complete paper-form refusal and incomplete paper-to-electronic signing, demo DB guard, full scoped cleanup and preservation of unrelated/shared files. Code inspection confirms original-tab upload restoration; no browser runtime claim is made.

Independent review fixed an existing stage-two scan overriding the fake electronic signature and removed duplicate completion validation. Final review has no unresolved concrete findings. Existing tests and scenario expectations were unchanged.

Synthetic-only logs: `/tmp/seed-application-engine.log`, `/tmp/seed-application-precommit-backend.log` (final 1107 passes), `/tmp/seed-application-precommit-focused.log` (50 passes), `/tmp/seed-application-backend.log` (prior 1102 passes), `/tmp/seed-application-scenarios.log`, `/tmp/seed-application-scenarios-summary.log`. These are local execution evidence, not committed fixtures.

The final pre-commit backend rerun passed 1107 cases with 9 dependency/deprecation warnings. Engine and scenario results above remain valid: no product code, including models.py or the tool, was changed during this pre-commit follow-up. AST, diff and context validation passed; independent follow-up review found no unresolved issues.
