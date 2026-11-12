# Confirmed failure filtering design

## Change boundary and baseline

Base: cdcf68d. Changes belong to engine_v2 extractors and demo OCR conversion, document checks and eligibility/API adapters. No engine/ changes. The user has authorized all stage commits. Initial dirty path: untracked docs/audit/ (excluded throughout).

| Case | Current flow at base | Planned change / certain evidence |
|---|---|---|
| 1 | demo/backend/ocr/base.py:121 unreadable; demo/backend/rules/doc_check.py:490 engine result mapped by severity | Preserve UNREADABLE_FILE FAIL independently of zero confidence |
| 3a | demo/backend/ocr/localocr.py:702 generic classification; engine_v2/engine.py:40 no daily extractor | Dedicated coordinate daily-work reader; explicit period/table completeness; compare duplicate copies; provisional monthly continuity |
| 3b | engine_v2/extractors/insurance_4.py:499 requires one physical page; demo/backend/ocr/localocr.py:666 passes all pages | Isolate confidently identified one-page form from dissimilar attachments; leave duplicate/same-family pages under strict validation; evaluate full insurance rows |
| 4 | demo/backend/rules/doc_check.py:505 confirmed issue date -> DOCUMENT_ISSUED_TOO_EARLY | Regression only |
| 5 | engine_v2/extractors/resident_abstract.py:306 rows depend on date; demo/backend/rules/facts.py:324 application fallback | Independently record reliable address header/date omission evidence; fail only with reliable form and table evidence; retain explicit fallback warning in facts basis |
| 6 | demo/backend/ocr/localocr.py:706 unknown -> None -> pdftext; demo/backend/rules/doc_check.py:391 early UNKNOWN review | Retain source pixel dimensions at common OCR boundary; fail only objectively tiny page AND unknown type/mostly missing required values; preserve independently reliable page markers |
| 7 | demo/backend/rules/doc_check.py:579 skips absent monthly map | Independent period evidence before monetary completeness; title/range/rows must not conflict; complete arithmetic needed for zero/blank amounts |
| C | demo/backend/api/review.py:131 _blockers; :498 final-check; :710 submit reuses _blockers | Shared eligibility assessments for blockers, review and early identity/status; existing kind/message/goto UI |

## Codes and certainty

FAIL: UNREADABLE_FILE (existing), IMAGE_RESOLUTION_TOO_LOW, MISSING_ADDRESS_DATES, MISSING_BILLING_MONTHS (existing), DOCUMENT_ISSUED_TOO_EARLY (existing), WORK_CONTINUITY_NOT_MET with detail codes; eligibility OVER_LIMIT / AGE_OUT_OF_RANGE. Unknown periods, damaged headers, conflicting rows/copies/identity and unreadable values remain NEEDS_REVIEW.

Low-resolution hard cutoff: **short edge < 600 AND long edge < 800 pixels**, independent of orientation, plus unknown classification or fewer than half of applicable essential fields readable. This is a deliberately narrow product threshold inferred from the supplied two boundary examples, not a validated OCR limit (추정). It catches 586x709, excludes 970x1282 and normal 1654x2338/2065x2923/2480x3505. At/near the cutoff preserve review; dimensions alone never reject readable documents. Source dimensions must be measured before rendering/upscaling.

Address omission: high-confidence abstract title plus observed number/address header with absent occurred/reported labels, or observed address rows without any date. Never infer from absent parsed rows alone. Guidance uses the user-approved descriptive wording; exact Government24 option name is unverified (추정), not a quoted UI label.

Payment omission: parse unique query range, reconcile every observed payment title period and month row. A reliable exclusion survives unrelated monetary confidence cap; conflicting or missing range stays review. Explicit zero/blank needs complete observed columns and arithmetic. Legacy complete monthly maps retain compatibility.

Mixed pages: isolate only when exactly one supported single-page form is identifiable with its own 1/1 marker and all other pages are dissimilar/unknown; same-family extra pages remain incomplete. Store additional page indices in extracted metadata, visible to officer.

Work continuity is **provisional (잠정)**: one program setting `work_continuity_months=5`, start announcement minus calendar months, end announcement (2025-10-03 through 2026-03-03 for savings). Monthly daily coverage ends previous calendar month. Business opening deadline 2025-09-03 in program settings. No work requirement means no work rule. Identity + complete structure + reliable rows required for negative eligibility. Conflicting independent documents -> UNDETERMINED. Work contract parsing and 15-hour inference excluded.

## Test and commit sequence

1. Plan artifacts (this commit).
2. Fictitious source-shaped coordinate fixtures and encrypted PDF; record baseline reproduction.
3. Password / payment period checks and issue regression.
4. Tiny-image and missing-address-date checks.
5. Mixed-page isolation.
6. Daily work record reader and adapters.
7. Provisional continuity and review/checklist integration.
8. Submission blockers, fresh server recheck, minimal frontend.
9. Acceptance/uncertainty/normal regressions.
10. Full suite comparison, expectation log, code-spec and final evidence.

Run `.venv/bin/python -m pytest engine_v2/tests -q`, backend equivalent and all run_p*_scenarios modules. Inspect test sources first to avoid private-document execution. Frontend lint/build when touched. No tests removed or weakened; intentional changed expectations documented separately.

## Evidence availability

Initial read occurred during generation and returned empty; the user regenerated the 899-line masked structure file and it is now readable. Synthetic data follows its row bands, split header/day-list words, two-page insurance copies, mixed attachments, date-empty address rows and tiny damaged title. No source file is copied to the repository. Exact OCR accuracy remains unverified (추정).

## Pre-change synthetic reproduction

- 3a: body classifier returns unknown; no dedicated reader.
- 3b: portal plus two sparse image pages -> confidence .4, REQUIRED_FIELD_UNREADABLE / NEEDS_REVIEW.
- 5: date headers present and numbered address rows lack dates -> confidence .4, LOW_OCR_CONFIDENCE / NEEDS_REVIEW, history cannot establish residence.
- 6: synthetic fragmented unreadable upper title plus number/transfer/head-of-household labels -> unknown. Source case has no reliable 주민등록표/초본 title text, so lower table cues cannot choose abstract versus register; localocr returns None and PdfText image fallback returns type None / confidence 0. This is classification evidence failure, not proof that OCR produced no words (source reports 124).
- 7: damaged component/month header -> incomplete payment form, no reliable monetary facts, NEEDS_REVIEW. The first variant still produced a partial monthly map (and a review-only MISSING_BILLING_MONTHS); damage to the month header models the no-map variant.
- 1: actual synthetic encrypted PDF already returns UNREADABLE_FILE FAIL at base, confidence 0. The request's expected pre-change NEEDS_REVIEW was **not reproduced**. Preserve the confirmed path with a regression and an explicit early invariant; do not claim an existing failure.
- Baseline independently verified before code edits: engine 1172 pass / 3 skip, backend 735 pass; 17 counting scenario modules 1857 pass / 0 fail, P14 exit 0 (18 files total).

## Final implementation and evidence

| Case | Final result and certain condition | Current implementation / synthetic assertion |
|---|---|---|
| 1 | Upload FAIL / UNREADABLE_FILE for a password/unopenable file, independently of OCR=0. This path already failed at the baseline; preserve regression and guidance. | demo/backend/rules/doc_check.py:454; test_payment_failure_certainty.py password regression |
| 2 | Eligibility OVER_LIMIT blocks final-check and fresh submit; existing review INCOME_OVER_THRESHOLD remains FAIL. Requires trusted household/category/monthly billed amounts and the public integer 140% bound. | demo/backend/rules/eligibility_blockers.py:36; test_eligibility_blockers.py |
| 3a | Work NOT_MET / WORK_CONTINUITY_NOT_MET, detail WORK_DAILY_MONTHS_MISSING (or WORK_DAILY_QUERY_PERIOD_TOO_SHORT). Requires complete table/period/copies and reliable matching applicant/issue evidence. | demo/backend/rules/work_continuity.py:213; test_failure_cases_work_acceptance.py |
| 3b | Main portal form validates independently; extra pages recorded, then all work acquisitions after start => NOT_MET / WORK_CONTINUITY_NOT_MET, detail WORK_ALL_ACQUISITIONS_AFTER_START. | engine_v2/extractors/attached_pages.py:56; demo/backend/rules/work_continuity.py:127; test_mixed_attachments.py and work acceptance |
| 4 | Existing DOCUMENT_ISSUED_TOO_EARLY upload FAIL for reliable date before inclusive public cutoff. | demo/backend/rules/doc_check.py:620; test_payment_failure_certainty.py cutoff regression |
| 5 | Upload FAIL / MISSING_ADDRESS_DATES when reliable abstract title and address header prove absent date columns, or reliable address rows have no dates. Source case belongs to rows-without-dates branch. | engine_v2/extractors/address_dates.py:10; demo/backend/rules/doc_check.py:516; test_address_resolution_failures.py |
| 6 | Upload FAIL / IMAGE_RESOLUTION_TOO_LOW for original short<600 AND long<800 plus unknown type/mostly unreadable applicable essentials. Reliable independent 1/2 adds PAGES_INCOMPLETE. | demo/backend/ocr/file_evidence.py:8; demo/backend/rules/doc_check.py:457; tiny-baseline-replay.md and 124-word synthetic upload |
| 7 | Upload FAIL / MISSING_BILLING_MONTHS for reliable excluded quarter or certain bounded zero/blank target amounts. Conflicting/unreadable periods, target amounts or arithmetic => NEEDS_REVIEW. | demo/backend/rules/doc_check.py:374; engine_v2/extractors/payment_period.py; test_payment_failure_certainty.py |

### Original resolution and case 6 diagnosis

Final hard pixel threshold is 600/800, narrowed from the preliminary 650/900 proposal to leave a review band near that proposal. It is a conservative product choice inferred from the supplied examples (추정), not a validated general OCR limit. 586×709 rejects only with unreadability; 970×1282, 1654×2338, 2065×2923, 2480×3505 and tested boundaries are not resolution FAILs. A text-layer PDF is not limited by its background bitmap. Receipt/exam/interview essential fields are their own values, rather than unrelated birth/name requirements.

The full 124-word tiny-page geometry now has a synthetic-only fixture. A read-only baseline module replay on that authored white PNG confirms: LocalOcr returns None after type failure; PdfText supplies type None / confidence 0; old doc_check returns UNKNOWN_DOCUMENT_TYPE / NEEDS_REVIEW. The new path retains independently readable folios and original dimensions. Exact original title glyph errors remain **추정**, because no original document or raw OCR replay was permitted or executed.

### Work and extractor contract for verification scripts

Daily fields: `발급번호`, `발급번호목록`, `발급일`, `성명`, `생년월일` (explicit four-digit year), `생년월일표기` / `생년월일후보` (two-digit year), `보험구분`, `조회기간`, `일용근로내역자료`, `양식판독상태`, `판독검증`, `판독검증실패`, optional `판독경고`. Every final OcrResult field is a string; parse JSON-valued fields before inspecting nested data.

Daily JSON has `period`, `rows` (`month`, `workplace`, `work_dates`, `days`, `wage`, `remuneration`, `worker_category`), `insurance_types`, `copies_consistent`. Unknown graphical insurance marks are explicit, with no invented label. Confirmation-only pages cannot silently contain another labeled applicant/issue grid.

`review_payload_json.work_continuity` contains `status` MET / NOT_MET / UNDETERMINED, `reason_code`, `detail_codes`, `basis`, `period_start`, `period_end`, `evidence`, `missing_months`, `provisional`. `WorkContinuityResult.review_status` is PASS / FAIL / NEEDS_REVIEW. Full insurance rows retain `자격취득일신뢰도`; full NHIS history rows retain `acquired_confidence` and `lost_confidence`. Fresh work-capable conversions carry `근로근거신뢰도` from bounded original identity and issue tokens. Unknown source evidence cannot establish a new work rejection. Noncoordinate JBAI document compatibility is preserved while work certainty remains unconfirmed.

Settings are `ProgramConfig.work_continuity_months` and `business_opening_deadline`, explicitly provisional. User's intermediate response repeated/confirmed 2025-10-03~2026-03-03, required daily months October–February, opening no later than 2025-09-03. No work rule is applied to job package. Weekly 15 hours and employment contract reading are not inferred.

### Submission and frontend

`GET final-check.blockers[]` reuses `{kind:"eligibility",target,label,code,message,goto,evidence}`; work adds detail_codes. `POST submit` recomputes the current blockers and returns HTTP400 with a `detail` string including eligibility reasons. Unknown eligibility remains submittable. Identity POST, application GET and status GET expose identical age blockers early.

Applicant numeric guidance is separate from score-item basis and includes no points or ranking. Public contact fallback uses the configured website when a program has no configured call-center number. Frontend changes are exactly `demo/frontend/src/api.ts`, `src/pages/applicant/FinalCheck.tsx`, `src/pages/applicant/IdentityCheck.tsx`. No stage-2 form/workspace files or CSS changed.

### Review fixes and retained scope

Final review fixed source-title confidence, applicable essentials for readable tiny job documents, low source identity/issue confidence, unreadable historical categories, low-confidence zero/sum arithmetic, incorrect address-note date attribution and unexpected daily confirmation headers. Existing ASCII snapshot digest remains unchanged after separately asserting only additive history confidence keys. All expectation/fixture changes are itemized in changed-test-expectations.md and research/scenario-expectations.md; no tests/check calls removed.

Residence score fallback is intentionally unchanged. Its FactSource.origin now explicitly states that missing date evidence forced an unproven applicant-input reference calculation (demo/backend/rules/facts.py:320). Residence eligibility, contract parsing, weekly hours, mixed/multiple workplace rules and resident-number nonstorage redesign remain outside scope. Government24 guidance is descriptive; the exact current option label remains **추정**. Original-document OCR accuracy is unverified; all executions used authored synthetic fixtures.

## Stage commits

1 00106d8; 2 205094f; 3 6309602; 4 9891840; 5 317c191; 6 02879f3; 7 bfd7bc9 + 727e013; 8 c8173c4; 9 d19b44e; 10 source/verification refinements 4536155, followed by final documentation commit.

## Final verification at 4536155

| Suite | Baseline cdcf68d | Final | Delta |
|---|---|---|---|
| engine_v2 pytest | 1172 passed, 3 skipped | 1236 passed, 3 skipped | +64 passed; skipped count unchanged |
| demo/backend pytest | 735 passed | 885 passed | +150 passed |
| 17 counting scenario modules | 1857 passed, 0 failed | 1885 passed, 0 failed | +28 checks |
| P14 (18th scenario file) | exit 0 | exit 0 | unchanged |
| Frontend | existing lint warning | lint/build exit 0 | only preexisting StatusBadge refresh and bundle-size warnings |

Commands: `.venv/bin/python -m pytest engine_v2/tests -q`; corresponding demo/backend command; every `run_p*_scenarios.py` via module invocation, sequentially. All 18 scenario file exit codes are zero. Final raw logs: `/tmp/fail-cases-release-engine.log`, `-backend.log`, `-scenarios.log`. Frontend `npm run lint` / `npm run build` passed after the last frontend edit. `git diff --check` passed. No tests/check calls removed or weakened; all necessary expectation/fixture revisions are documented separately.

The final code/spec review covered backend and frontend contracts and all task requirements. Source files under `engine/` and `docs/audit/engine-walkthrough.md` were not changed or committed. No private directory inspection, real-document execution, push, PR or main merge occurred. The preexisting untracked `docs/audit/` remains excluded. Browser layout and real-document OCR accuracy were not executed/verified; synthetic source geometry and API behavior were verified.

Task remains `review` / awaiting user verification; do not archive or publish automatically.

## 후속: 실서류 확인 도구

The follow-up is authorized on the current feature branch. Commit this plan before implementation, then commit implementation, synthetic acceptance tests, and complete verification separately. Keep the existing audit document and untracked audit directory excluded. Never inspect private documents or run a command against them. No push, PR, merge, or archive.

### Shared path and boundary

Extract the existing explicit-slot upload orchestration from `api/documents.py:382` onward into a callable assessment function: read_document, optional consent observations, check_document, and existing consent/receipt adjustments in the same order. Supply identity, checklist, uploaded rows and receipt input explicitly; keep DB lookup, destination creation, copying, replacement and persistence in the API. Do not change checks, thresholds, reasons, or status precedence. Extract checklist construction/criteria application from `api/common.py:111` into an input-only helper shared by the API and CLI. The CLI uses default_criteria with build_checklist and the same criteria application, never DB criteria lookup. Stored custom criteria, electronic forms and subsidy selections are outside this CLI's input scope; report that limit.

For work and income, reuse document_fact, assess_work, build_facts, score_income and eligibility_blockers after upload assessment, matching final-check ordering. Reuse the document FAIL blocker projection from review._blockers if extraction is needed; ignore missing unrelated application fields/documents. A blocker flag describes only the selected document/work or income assessment, not overall application readiness.

### CLI and privacy contract

Create `demo/backend/tools/verify_upload.py`: --program (default double_savings), --slot, --work-category, --self-identity, --slots-list, and one input path. --income accepts exactly three ordered inputs: payment, qualification, acquisition/loss. Build genuine business/category slots and reject unsupported combinations with fixed error codes. Self identity uses only an explicitly readable name and full birth date, without guessing the century; missing either is reported as 본인정보 없음 and assessment continues. For income derive the reference identity from payment only, preserving cross-document mismatch checks.

Use a positive output schema containing only enum/code names, statuses, bounded confidence formatted to two decimals, counts, static slot names and O/X. Never serialize OCR fields, findings messages, basis, evidence, filenames, paths or exception strings. Redact every numeric run of four or more digits, including static year-bearing slot labels. Silence Python/native stdout and stderr and logging during assessment; emit only the prepared safe summary afterward. Prevent write attempts during CLI assessment (including bytecode, DB, cache, model downloads and logs); do not copy inputs. Surface blocked write/error as a fixed safe code instead of traceback. Preserve the configured OCR chain; remote permission/settings remain the existing chain's responsibility.

### Acceptance and verification

Use authored encrypted PDF, image and source-shaped coordinate fixtures only. Cover cases 1, 3a, 3b, 4, 5, 6, 7, their expected codes/statuses and actual blocker projection. Exercise common upload and final-check functions, not fabricated status summaries. Test slots/category/default criteria, missing identity, income MET/OVER_LIMIT/UNDETERMINED, cross-document identity, safe errors/help, malicious dynamic metadata, native output suppression, numeric redaction and no filesystem/DB/storage/log writes. Record the synthetic OCR seam where exact OCR accuracy remains unverified (추정). Keep existing tests intact.

Run full engine/backend suites and all eighteen scenario modules after source review for synthetic-only execution. Compare against engine 1236 passed / 3 skipped, backend 885 passed, counting scenarios 1885 passed / 0 failed, P14 exit zero. Review diff and update the backend contract with the CLI boundary, then commit verification evidence and leave task awaiting user verification.

### Follow-up implementation and verification evidence

Plan dffdd7e; implementation 0ad6d76; synthetic acceptance 2d1f220. API `demo/backend/api/documents.py:327` and CLI `demo/backend/tools/verify_upload.py:211` call the same `upload_assessment.assess_upload` (`:42`, read_document `:58`, check_document `:70`). Paired NHIS recheck shares `assess_nhis_identity` (`upload_assessment.py:133`, API `documents.py:256`, CLI `verify_upload.py:175`). `checklist_from_inputs` (`api/common.py:97`) applies real default criteria without a DB; `document_blockers` (`api/review.py:116`) and existing eligibility_blockers provide the actual selected-document/work/income flags.

All 44 new synthetic acceptance tests passed. Existing tests were neither removed nor weakened. Separate review confirmed unchanged decision blocks and caught a CLI-only omission: work-capable acquisition/loss evidence outside work_proof must also reflect the actual work blocker. That orchestration condition and its regression were included in the acceptance commit; no rule/threshold/extractor changed. A final helper rename avoids the existing applicant-download source scanner's reserved tokens without changing or bypassing its checks.

The image-only interleaved insurance title is an existing confirmed classifier limitation (`ocr/pdftext.py:118`, `ocr/localocr.py:764`, fixture `engine_v2/tests/fail_case_samples.py:56`, regression `tests/test_verify_upload.py:395`). It was reported and retained as NEEDS_REVIEW, not repaired. Case 3b's expected certain work rejection is verified with an authored text-layer portal plus two image attachments. Actual documents and native filesystem isolation remain unverified (추정); saved criteria overrides and unsupplied application settings are outside the CLI input scope. See verify-upload.md for complete commands, privacy boundary and acceptance details.

### Follow-up full verification

| Suite | Requested baseline | Follow-up | Difference |
|---|---|---|---|
| engine_v2 pytest | 1236 passed, 3 skipped | 1236 passed, 3 skipped | Unchanged |
| backend pytest | 885 passed | 929 passed | 44 additional synthetic CLI tests |
| Counting scenarios | 1885 passed, 0 failed | 1885 passed, 0 failed | Unchanged |
| P14 | exit zero | exit zero | Unchanged |

Commands: `.venv/bin/python -B -m pytest engine_v2/tests -q`, `.venv/bin/python -B -m pytest demo/backend/tests -q`, every `demo.backend.tests.run_p*_scenarios` module sequentially. All eighteen scenario exit codes are zero. Final targeted rerun: 44 passed after the helper rename; independent review subset: 11 passed. Only nonsemantic cleanup followed the full backend run (helper rename to satisfy the existing scanner, unused imports). P4's unchanged scanner passed. `git diff --check` passed. Logs are synthetic-only at `/tmp/verify-upload-engine.log`, `/tmp/verify-upload-backend.log`, `/tmp/verify-upload-scenarios.log`, and `/tmp/verify-upload-scenarios-summary.log`.

No engine rules, thresholds, extractors or existing tests changed. No private document inspection/execution, input copying by the tool, DB/storage/log creation by the tool, audit-document change, merge, push or PR. API file/DB persistence remains only in the normal API; synthetic API tests still use their isolated stores. Preexisting untracked docs/audit/ is excluded. Task remains review / awaiting user verification.


## 후속 2: 사례 3a·5

Authorized continuation on feat/fail-cases; commit all six requested stages in order. Use only authored fictitious fixtures and read-only masked layout evidence. No private document inspection/execution, audit document, engine/, frontend, threshold, income or age policy changes; no merge/push/PR. Existing untracked docs/audit/ stays excluded.

### Current paths and masked evidence (before implementation)

- Daily birth already accepts two-digit Korean dates and emits century candidates without selecting one (`engine_v2/extractors/daily_work_record.py:117-132`, `:377-381`). Applicant/issue/table/confirmation checks determine structure (`:303-348`); incomplete structure caps converted confidence (`demo/backend/ocr/localocr.py:382-387`) and returns REQUIRED_FIELD_UNREADABLE before identity comparison (`demo/backend/rules/doc_check.py:523`). Work requires matching identity and complete trustworthy evidence (`demo/backend/rules/work_continuity.py:90-120`). CLI self identity accepts full ISO birth only (`demo/backend/tools/verify_upload.py:111-118`). Proposed missing-birth root cause is **추정**: reproduce source-shaped metadata and inspect failed check names/field presence without outputting identity values. Masked layout shows two-digit birth tokens at `/tmp/layout_shape5.txt:15` and `:169` (birth labels; candidate value shapes at :16/:170), receipt labels at `:10` and `:164`, and confirmation pages at `:142-155` and `:296-309`. Supplied layout records an older unknown-type result at `:310-313`; the user's current result is the authoritative current observation.
- Date omission currently requires type >= .85, reliable title, number/address header and strict address/ordinal evidence (`engine_v2/extractors/address_dates.py:10-74`). Converter attaches independent evidence (`demo/backend/ocr/localocr.py:125-128`); doc_check preserves certain MISSING evidence before global quality checks (`demo/backend/rules/doc_check.py:511-521`). Insufficient structural recognition, rather than the global quality gate itself, is **추정** until synthetic reproduction.
- Case 5 satisfies the requested positional condition: reliable title/subtype block (`/tmp/layout_shape5.txt:497-506`); occurrence/report headers (`:525-526`, spaced label and prefixed OCR noise); body ends before blank marker (`:567`). Date-header union spans x=530..745. Address words (`:537-566`) lie left of it and form >2 rows. No body word overlapping those date-header x ranges contains a digit shape; address/ordinal/note digits lie outside. Use labels/geometry only; never copy source data into the repository.

### Ordered execution and validation

1. Commit this plan before code.
2. Author synthetic variants reproducing current failures; record failed validations and missing required fields with no values in diagnostics; commit reproduction/evidence.
3. Fix demonstrated daily parsing/identity boundaries, preserve copy agreement/four-digit behavior. CLI may resolve a century only if program birth_range leaves exactly one candidate; otherwise retain uncertainty. Required checks accept usable short-year candidates. Commit daily changes.
4. Add independent title-confirmed positional date-blank proof: observed spaced/OCR-variant date headers, bounded table body, no digit-bearing token in either date column, >=2 Hangul address rows. Any digit or missing/ambiguous header remains review. Every history-bearing page must agree; preserve dated multi-page forms. Commit.
5. Acceptance tests: NOT_MET/blockers, birth/name/copy mismatch, four-digit regression, blank dates and each negative control; commit.
6. Full engine/backend suites and all scenario modules versus 79406ed: 1236 passed/3 skipped; 929 passed; 1885 scenario checks/zero failures; P14 exit zero. Review/spec-sync, document changed expectations (or none), update this design, commit. Real-document success remains **추정** until user verification.


### Stage 2 — synthetic reproduction, before fixes

Plan commit: 12fbbcb. Four new reproduction tests passed using only authored fixtures. `engine_v2/tests/followup_daily_samples.py` preserves the four-page word bands, receipt metadata, note and nine fictitious monthly rows. Current daily extraction is complete with every validation passing and confidence >=.9; full `생년월일` is absent by design, while `성명`, `발급일`, `생년월일표기`, `생년월일후보` are present. Matching authenticated identity already yields document PASS. Thus the observed .40/REQUIRED_FIELD_UNREADABLE cannot be reproduced or attributed to any unreadable required field from the available masked evidence; the user's proposed structural cause remains **추정**. Confirmed defect: CLI `_identity_from_ocr` ignores candidates, giving no self identity, work UNDETERMINED/WORK_IDENTITY_UNCONFIRMED and no work blocker (`demo/backend/tests/test_followup_daily_reproduction.py`). No full-century value will be invented in extracted document fields.

`engine_v2/tests/followup_address_samples.py` uses justified address header glyphs, the noisy report-header prefix, region-independent fictitious Hangul addresses, and a note outside the date columns. Its deliberate low-quality metadata reproduces confidence .40, LOW_IMAGE_QUALITY, NEEDS_REVIEW and no MISSING_ADDRESS_DATES (`demo/backend/tests/test_followup_address_reproduction.py`). Source quality itself is not recoverable from layout coordinates; the low-quality seam is explicit. Legacy `address_dates.assess` requires a joined address label and administrative-region/ordinal evidence; the new proof will derive observed date columns independently. Reproduction command: `.venv/bin/python -B -m pytest demo/backend/tests/test_followup_daily_reproduction.py demo/backend/tests/test_followup_address_reproduction.py -q` — 4 passed. New reproduction expectations will transition to acceptance outcomes in stages 3–5 and be recorded separately; no baseline test was changed.


### Stage 3 — daily short-year CLI identity

`demo/backend/tools/verify_upload.py:111-147` now accepts the existing daily extractor's normalized short-year printed date and its complete valid century-candidate set, only for DAILY_WORK_RECORD. A temporary self-reference is formed only when program.birth_range selects exactly one candidate; zero/multiple candidates, malformed JSON, incomplete/duplicate candidates, mismatching printed date and other types remain unresolved. Both orchestration callbacks pass the existing program (`:237`, `:298`). The entire OCR fields mapping is unchanged and full `생년월일` stays absent (`demo/backend/tests/test_followup_daily_reproduction.py:68-84`). The existing extractor already accepts spaced Korean short-year dates; authenticated identity matching, copy agreement, mandatory-field checks and work thresholds are unchanged.

The demonstrated synthetic result is document PASS followed by WORK_CONTINUITY_NOT_MET / NOT_MET and an actual work eligibility blocker. The supplied real-document .40 / REQUIRED_FIELD_UNREADABLE remains unreplicated; no unreadable mandatory field can be identified from masked evidence, so resolving that separate structural symptom remains **추정**. Do not report the CLI fix as proof that this real-document symptom is repaired.

Targeted verification: daily extractor, new daily reproduction/acceptance, daily uploads, verify_upload, work continuity, work-source identity confidence and NHIS identity suites — **181 passed**, seven preexisting dependency warnings. Log: `/tmp/followup2-daily-targeted.log`; `git diff --check` passed. One necessary baseline test output change is recorded in changed-test-expectations.md; no assertions deleted or weakened. No shared short-birth helper exists outside the daily reader, so unrelated extractors were left unchanged.


### Stage 4 — positional date-column omission

Daily stage commit: f22635d. Independent source-shape counting (read-only, no file copy or actual values) confirmed **zero digit-bearing body words** overlapping the observed date-header union and **seven numbered Hangul-address rows** in case 5. Date headers are `/tmp/layout_shape5.txt:525-526`; numbered addresses occupy `:536-565`, with the table-end marker at `:567`. Thus the required condition holds; the label text hidden by the masking is not treated as readable value evidence.

`engine_v2/extractors/address_dates.py:_positional_page` uses the observed number/date-header boxes, ordered occurrence/report headers and the table end (the final review narrows the terminator to a reliable standalone blank marker). Comparison-only Hangul normalization recognizes spaced labels and the observed non-Hangul OCR prefix. Row ordinals delimit separate rows so multiline address continuations cannot manufacture two rows. It requires >=2 rows containing Hangul in the address area left of the date columns. Every body word horizontally overlapping either date column is checked for digits, even low-confidence/malformed/boundary-crossing words. A digit vetoes new omission evidence; no field value or overall confidence/quality is used to infer a blank. All physical pages must independently meet the new proof before it can establish MISSING, preserving uncertainty on mixed/dated/unknown pages. Existing reliable title/type gates, old omission evidence reasons and doc_check precedence are retained.

Targeted address suites: **18 passed**. All baseline expectations remain unchanged. Stage-2 sparse-header reproduction now expects FAIL/MISSING_ADDRESS_DATES while retaining the .40 and LOW_IMAGE_QUALITY assertions; this transition is recorded in changed-test-expectations.md. Synthetic geometry proves the contract, not native OCR accuracy or final real-document behavior (**추정**).


### Stage 5 — acceptance and conservative boundaries

Positional implementation commit: 79588bb. New `engine_v2/tests/test_followup_address_columns.py` covers scaling, image/text source, faint/malformed/boundary-overlapping digit words, missing/ambiguous headers, uncertain title/number header, one address with multiple continuation lines, all-page agreement and normal low-quality dated multi-page forms. `demo/backend/tests/test_followup_failure_acceptance.py` traverses authored four-page text PDFs through value-free CLI for short/full-year identity, actual document/work blocker projection, authenticated YYMMDD/name mismatch with existing severity, duplicated short-year copy disagreement, each sparse-address negative control and an actual synthetic image CLI blocker/no-write/privacy check.

Full-scope code review reproduced a false omission when the new path had no table end and counted numbered footer notes as addresses. The new path now requires an observed blank/next-section/footer boundary; a new regression proves unrelated footer notes cannot establish rows. A duplicate-header test also exposed first-hit-only label matching; repeated date labels in one header comparison row now invalidate uniqueness. These conservative refinements preserve all baseline tests rather than broadening rejection. The supplied case has the observed table-end marker and is unaffected.

Targeted acceptance run: **61 passed**, seven dependency warnings. Separate reviewer subset before the conservative refinements: **125 passed**. No new baseline expectation changes beyond the documented short-year CLI [True] result; no tests/check calls removed or weakened. Real native OCR accuracy and the user's unreplicated daily .40 symptom remain outside the demonstrated evidence.


### Stage 5 review refinements

Acceptance commit: b12adc2. Further adversarial review found premature table-end detection from an address containing the blank-marker phrase or an in-table margin note, and a digit with its center above the table top but its box crossing into it. The new positional path now requires a **standalone, reliable `이하 여백` marker**, rather than substring matches or generic note/fee/section cues. Date-digit veto uses both horizontal and vertical box intersections. Added regressions retain the later numeric evidence in all these variants; no prior tests changed. This is a deliberately conservative recognition boundary: without an observed standalone marker, new positional certainty is unavailable and the prior assessment remains. The supplied masked delimiter has the correct geometry; its hidden exact label/native OCR behavior is still **추정**. Final independent review subset: **67 passed**, seven dependency warnings; no open review findings. Full suites are repeated after this final source refinement.


### Stage 6 — final verification and limits

Final source at 0142b7d. Stage commits: plan 12fbbcb; reproduction 5961fe0; daily f22635d; address 79588bb; acceptance b12adc2 plus conservative review fixes 0142b7d. Final spec sync records candidate identity and bounded positional-proof contracts in `.trellis/spec/backend/failure-filtering.md`.

| Suite | Baseline 79406ed | Final at 0142b7d | Delta |
|---|---|---|---|
| engine_v2 pytest | 1236 passed / 3 skipped | 1264 passed / 3 skipped | +28 passed |
| demo/backend pytest | 929 passed | 956 passed | +27 passed |
| 17 counting scenario modules | 1885 passed / 0 failed | 1885 passed / 0 failed | unchanged |
| P14 (18th module) | exit 0 | exit 0 | unchanged |

Commands: `.venv/bin/python -B -m pytest engine_v2/tests -q`; `.venv/bin/python -B -m pytest demo/backend/tests -q`; all `demo/backend/tests/run_p*_scenarios.py` invoked as modules with the same interpreter. All eighteen scenario exits are zero. Seven preexisting dependency warnings per pytest suite; no failures. Final synthetic-only logs: `/tmp/followup2-engine-final.log`, `/tmp/followup2-backend-final.log`, `/tmp/followup2-scenarios-final-summary.log`, `/tmp/followup2-final-run_p*_scenarios.log`. Final targeted adversarial acceptance: 54 passed; final independent review subset: 67 passed. `git diff --check` passed. Review compared the entire source diff and backend guidelines; no out-of-scope policy, engine/, frontend or audit-document changes.

- **3a confirmed:** the full-century `생년월일` field is intentionally absent for a short-year date; the existing extractor already emits usable candidates (`engine_v2/extractors/daily_work_record.py:117`, `:377`). Its required structure/identity checks already accept them. The repaired CLI forms a temporary reference only from one program-bounded candidate (`demo/backend/tools/verify_upload.py:111`). Authenticated birth/name mismatch and insurance-copy consistency remain unchanged. Authored source-shaped four-page PDFs now yield document PASS / work NOT_MET / actual blocker O (`demo/backend/tests/test_followup_failure_acceptance.py:28`). **Unresolved:** the actual .40/REQUIRED_FIELD_UNREADABLE symptom did not reproduce; no unreadable required field can be identified from masked evidence. Its cause and real-document success remain **추정**, not a completed structural repair.
- **5 confirmed:** source-shape counting found seven address rows and zero date-column digit words (`/tmp/layout_shape5.txt:525`, `:526`, `:536-567`). The independent proof uses observed header boxes (`engine_v2/extractors/address_dates.py:25`), standalone reliable blank marker (`:46`), digit box intersection veto (`:60`), >=2 separate address rows (`:65`) and reliable abstract title (`:83`). Overall confidence/quality does not prevent MISSING/FAIL. Synthetic actual-image CLI and document blocker tests pass (`demo/backend/tests/test_followup_failure_acceptance.py:99`). **Limit:** the masked end marker's exact hidden label/native OCR is unverified (**추정**); without a readable standalone marker the added proof conservatively remains unavailable. Existing legacy omission evidence is retained.
- **Expectations:** only the baseline short-year CLI `[True]` outcome changes as requested; the `[False]` case, existing identity mismatch rules, four-digit documents and old address expectations remain. The new stage-2 address reproduction transitions to its intended acceptance outcome. Full reasons are in changed-test-expectations.md; no existing tests/check calls removed or weakened.
- **Scope/status:** no private directory inspection, real-document execution, source-file copying, value-bearing output/logs, main merge, push or PR. Task remains review/awaiting user verification; `docs/audit/` is the preexisting untracked directory and is excluded from every commit. The actual 3a structural symptom is an unresolved in-scope evidence limit; no additional out-of-scope repair was attempted.


## 후속 3

Authorized continuation from f656893 on feat/fail-cases. Preserve private-document prohibition, value-free output, body/coordinate-only form selection, existing tests, audit exclusion, and no engine/, frontend, income/age/work-threshold changes. No merge/push/PR. Commit the seven user stages in order; stop after quality validation if objective quality cannot be separated safely. Existing task/implementation artifacts remain applicable; this section records the new execution plan.

### Current daily failure path and source evidence

- `_query_period` uses substring label matching through `_unique` (`engine_v2/extractors/daily_work_record.py:135-155`, `:49-65`). The source has a standalone left query label and a following selection note containing that label (`/tmp/layout_shape6.txt:17-20`, `:171-174`). The note can create two label candidates; hypothesis must be tested. The range grammar already permits year/month and attached tilde, so do not loosen arbitrary period matching.
- `_confirmation` looks only for 확인합니다 and uses an issuer substring search (`daily_work_record.py:267-285`). Source has the different fixed phrase 위와같이자격내역을알려드립니다., an intervening date, and the standalone issuer, but upper notice prose also mentions the agency (`/tmp/layout_shape6.txt:149-155`, repeated on fourth page). `_unique` can confuse the issuer with prose; exact failure reproduction is pending.
- Continuation validation repeats the same issuer search (`daily_work_record.py:335-345`) and excludes independently labeled applicant/issue grids. Preserve that exclusion and require a confirmation/date/issuer block tied to the same copy; never pass a random attachment as a continuation.
- Missing query period and failed confirmation/continuation set structure incomplete and cap confidence at .4 (`daily_work_record.py:361-363`; converter `demo/backend/ocr/localocr.py:382-387`). `demo/backend/rules/doc_check.py:523-527` returns REQUIRED_FIELD_UNREADABLE for incomplete daily structure. Work `_trust_issue` returns WORK_STRUCTURE_UNCONFIRMED (`demo/backend/rules/work_continuity.py:90-122`). Short-year birth candidates and self identity from follow-up 2 remain intact. Actual unreadable required field is suspected query period; reproduce before declaring it established.
- Insurance checkbox absence is already only a warning when unknown (`daily_work_record.py:349-360`); retain that reference-only behavior, preserve full row agreement across copies, and do not invent an insurance type. New certain selection evidence M<N must become DAILY_RECORDS_PARTIALLY_SELECTED upload FAIL with the requested recovery wording; it cannot establish missing-month work rejection. Unreadable counts must not establish FAIL. Validate bounded whole note grammar, independent token confidence and cross-copy consistency.

### Quality path, gate and intended projection

- Engine threshold is IMAGE_QUALITY_THRESHOLD=.6 (`engine/config.py:14`; read only), independent of OCR threshold (`engine/stage1_document_check.py:34-36`). Backend currently classifies LOW_IMAGE_QUALITY as review (`demo/backend/rules/doc_check.py:136-150`). Do not change engine files.
- Image heuristic is original short-side pixels: >=1400 ->.9, >=1000 ->.75, >=700 ->.55, otherwise .35 (`demo/backend/ocr/pdftext.py:380-391`). Local/JBAI combine it with page DPI: >=200 ->.9, >=150 ->.7, lower ->.5; absent DPI ->.75 (`demo/backend/ocr/localocr.py:89-96`, `:624-631`; JBAI :322). These are resolution proxies, not measured blur/brightness or proof that a person cannot read the image. Text-layer PDF read_page_text uses quality1 (`pdftext.py:327`); mixed/local source behavior needs verification.
- A nonmeasurement default .5 remains when all OCR adapters fail (`demo/backend/ocr/__init__.py:54-59`); this must not become an image-quality FAIL merely because recognition failed. Stage 4 will audit/separate uncertain fallback quality, verify original-size normal images (including requested sizes and phone orientation), and prove source text PDFs remain outside quality rejection. If normal inputs fail frequently or objective separation is unavailable, commit the evidence and stop before stage 5 as requested.
- IMAGE_RESOLUTION_TOO_LOW is a narrower independent rule: original short<600 AND long<800 plus unknown type/mostly unreadable applicable fields (`demo/backend/ocr/file_evidence.py:7-8`, `:69-99`); it already precedes and returns before ordinary quality checks (`doc_check.py:454-476`). Keep that more specific failure first and retain independently established missing-page/date defects when applicable.
- After passing the gate, remove only LOW_IMAGE_QUALITY from REVIEW_ONLY_CODES, preserve LOW_OCR_CONFIDENCE/other review-only codes and avoid confidence-based downgrade. Use the exact requested PDF/retake guidance. Ensure quality failure survives early unknown-type/structure paths without suppressing other certain reasons. `api/review.py:116-151` currently projects findings_json[0]; aggregate all FAIL reason messages in stable order without showing review-only reasons as rejection.

### Ordered execution and validation

1. Commit this plan. 2. Author a fake four-page text-layer PDF with the observed word splits, bounded selection note, notice/confirmation wording and unknown graphical marks; reproduce exact six failed validations, missing query period, .4, REQUIRED_FIELD_UNREADABLE and work UNDETERMINED; commit.
3. Implement narrowly scoped query/selection/issuer/continuation support and certain partial-selection FAIL, preserve candidate identity/copy consistency and unknown marks as warning; commit with targeted verification.
4. Audit objective quality provenance, separate recognition-only defaults, test requested normal sizes/text PDF; commit gate evidence (stop here if unsafe).
5. Only after gate passes, implement backend quality FAIL/guidance and multi-reason blocker projection; commit.
6. Add full acceptance for daily complete/partial/unreadable counts/copy disagreement/unknown marks; quality FAIL plus other reasons, normal images/text PDF, OCR-only review and case5 regression. Record changed baseline expectations; commit.
7. Run complete suites against f656893: engine1264 passed/3 skipped, backend956 passed, 17 counting scenarios1885 passed/zero failures, P14 exit0. Review source/specs, update design/changed-expectations/task state and commit verification. Real-document behavior remains **추정** until user verification; source-shaped synthetic evidence must not be reported as native OCR accuracy.


### Follow-up 3 stage 2 — exact synthetic reproduction

Plan commit 19b6c8a. `engine_v2/tests/followup3_daily_samples.py` authors fictitious four-page coordinates with a split Korean year/month query range, selection note containing 조회기간, unmarked insurance labels, notice prose mentioning the issuer, and the supplied fixed confirmation phrase. No original file was copied. The actual authored text-layer PDF and direct coordinate extraction both reproduce exactly **daily_0/1_query_period, daily_0/1_confirmation, daily_0/1_continuation** failures; no other failed validation. Backend confidence=.4, structure incomplete, required-field review and WORK_STRUCTURE_UNCONFIRMED/UNDETERMINED all reproduce (`demo/backend/tests/test_followup3_daily_reproduction.py:20`).

The unreadable required extracted field is **조회기간**. The full-century birth field is intentionally absent; its short-year candidates are readable and CLI identity is present. Issued metadata/name/candidates/insurance/rows remain present. Query label collision is now confirmed: `_unique` sees the standalone label and the whole selection-note token. Issuer collision is confirmed: upper notice prose and standalone issuer all match `_unique`; additionally the fixed 알려드립니다 confirmation phrase was unsupported. The continuation repeats that issuer collision. The old range grammar itself parses the observed split range when isolated. Targeted reproduction: **1 passed**, seven dependency warnings. The test's pre-fix expected failure set will transition to post-fix acceptance in stage 3 and be recorded; no baseline expectations changed yet.


### Follow-up 3 stage 3 — daily query, continuation and selection

Reproduction commit 5b20963. The exact four-page authored text PDF now passes every validation, emits the query period, preserves short-year birth candidates without adding a century, and yields document PASS / work NOT_MET / WORK_CONTINUITY_NOT_MET / actual work blocker O (`demo/backend/tests/test_followup3_daily_reproduction.py`). The unreadable required field was 조회기간; identity/issued metadata were already readable.

`daily_work_record._query_words` (`engine_v2/extractors/daily_work_record.py:138`) selects an exact query label in the observed left metadata cell, excluding the similarly named selection note. `_query_period` retains full-range matching and independent conflicting-range rejection while handling split Korean year/month and tilde tokens. A token-only exact issuer filter was insufficient after PDF extraction split notice prose into words; `_issuer` (`:334`) therefore requires a whole standalone issuer line. `_confirmation` (`:340`) recognizes the existing fixed confirmation and the supplied 알려드립니다 phrase, requires reliable confirmation/issuer/date words, and ties continuation confirmation to the same issue date. Independent applicant/issue grids and extra tables on continuation pages remain review.

Selection evidence `일용근로선택자료` records version, status and per-copy count confidence; `selection_status` (`:211`) rechecks saved provenance instead of trusting categorical status. Only full note grammar, high confidence >=.85, valid count order, agreement between copies and agreement of selected count with a complete observed table can establish certain partial selection. M<N returns **DAILY_RECORDS_PARTIALLY_SELECTED FAIL**, with recovery **전체 이력을 선택해 다시 발급받아 올려 주세요** (`demo/backend/rules/doc_check.py:528`), and work remains UNDETERMINED/WORK_DAILY_SELECTION_INCOMPLETE (`work_continuity.py:103`). Damaged punctuation/labels, unreadable/low-confidence counts, count/row conflict or one missing copy note cannot establish FAIL or negative work; they produce WORK_DAILY_SELECTION_UNCONFIRMED. Absent notes retain established legacy compatibility. The CLI fixed-code vocabulary includes all new codes without emitting values.

Unobserved graphical marks and repeated readable insurance marks are reference warnings only; they never lower confidence, fail structure validation or block work certainty by themselves. Full row/identity/issue/query/copy agreement remains mandatory. The existing same-checkbox test is retained and now asserts complete high-confidence consistent rows plus the reference warning, reflecting the user's explicit decision.

Targeted verification: daily extractor, daily text/image uploads, new reproduction/selection controls, previous short-year reproduction, verify_upload and shared work acceptance — **120 passed**, seven dependency warnings. Log `/tmp/followup3-daily-targeted.log`; `git diff --check` passed. No quality behavior changed in this stage; actual native document behavior remains **추정** until user verification.


Final stage-3 review additionally requires saved copy-agreement provenance before any partial-selection FAIL; even partial-count notes cannot override contradictory duplicated work rows. The existing copy-disagreement acceptance now runs both complete and partial-selection variants. Final source subset: **119 passed**, seven warnings (`/tmp/followup3-daily-final.log`); the earlier broader agent run was 120 passed. No quality edits preceded this stage commit.


### Follow-up 3 stage 4 — objective resolution gate

Daily implementation commit fc93c0b precedes every quality edit. The quality gate now passes with **63 new synthetic tests** (`demo/backend/tests/test_objective_image_quality.py`), six dependency warnings. The final broader subset is **175 passed**, seven dependency warnings, covering original-resolution evidence, both address reproductions, isolated attachments, daily uploads/reproduction, verify_upload, guidance, NHIS identity and resident uploads. Logs: `/tmp/followup3-quality-gate.log`, `/tmp/followup3-quality-regression.log`. `git diff --check` passed. No quality severity has changed in this stage.

`demo/backend/ocr/file_evidence.py:49` computes an **original-resolution proxy**, independent of recognized text, OCR confidence and fallback success. Raw PNG/JPEG preserve existing short-edge bands: >=1400px .9; >=1000px .75; >=700px .55; otherwise .35. Embedded PDF pages preserve original pixel-width-axis DPI bands: >=200dpi .9; >=150dpi .7; otherwise .5. The physical pixel-width axis comes from the original image transform (`:82-90`), so 90/270-degree placement retains the correct DPI. An initial normal rotated-scan false warning was detected and fixed by replacing enclosing-box width with transform-vector length; all rotated normal-size/phone controls now pass. The existing quality rejection threshold remains .6; no new image threshold, blur or brightness heuristic was introduced.

Scalable text pages score 1.0 without using decorative bitmaps. Pages without a measurable dominant original bitmap, unsupported sources and failed measurements use **neutral 1.0**, meaning no proven low-resolution evidence; it is not a measured assertion of perfect quality. Rendered/upscaled dimensions never establish original quality. Unencrypted production reader results are normalized centrally after adapter selection (`demo/backend/ocr/__init__.py:85-87`); adapter-miss quality is neutral rather than an invented .5 (`:53-60`). Explicit fixture and unreadable-file evidence is preserved. Normal PNG/JPEG sizes 1654×2338, 2065×2923 and 2480×3505, phone portrait/landscape sizes, original A4 scan PDFs and rotated scan controls produce no LOW_IMAGE_QUALITY. Low OCR confidence and complete adapter miss do not change the original-source score. Real-document/native OCR accuracy and human readability remain **추정**; the proxy does not measure blur, exposure, framing or legibility.

Existing form scope is preserved (`file_evidence.py:96-115`): validated one-based 추가첨부쪽 metadata from the established body/coordinate partition can exclude certified dissimilar attachments from this quality measurement. It does not infer quality from confidence. Malformed/duplicate/all-page/out-of-range/noninteger exclusions are rejected. An actual complete text main form plus a tiny scanned attachment retains main quality 1.0; a genuine mixed text/scan PDF without certified attachment metadata retains the low scan score. Original-size evidence fields retain their existing schema; no new extracted field keys were added.

NHIS stored-document rehydration (`demo/backend/upload_assessment.py:163-167`) now treats only missing/None quality as neutral; explicit 0/.5 values remain intact. This path directly calls check_document, so its old missing-value default would create false quality FAILs after stage 5. The separate engine_adapter missing-quality default feeds the engine pipeline rather than demo check_document and remains an existing out-of-scope issue; no engine/ files changed. No baseline test assertion or expectation changed in stage 4. Gate decision: proceed to the separately committed quality-FAIL transition while keeping LOW_OCR_CONFIDENCE review-only.


### Follow-up 3 stage 5 — quality FAIL and complete blocker reasons

Quality gate commit 6ecdac6 passed before the severity transition. `LOW_IMAGE_QUALITY` alone is removed from REVIEW_ONLY_CODES; LOW_OCR_CONFIDENCE and all other review-only codes remain. `check_document` now applies a final independent quality projection after the existing rule paths, so unknown type, incomplete daily/NHIS structure, low OCR confidence and identity-related downgrades cannot erase a measured quality FAIL. The canonical finding uses the requested PDF/bright/straight/clear reupload guidance. Actual text-layer source pages score neutral1 before this rule; scanned PDFs retain their measured source score.

`IMAGE_RESOLUTION_TOO_LOW` remains the more specific first failure for its existing narrow original-pixel-plus-unreadability predicate. It suppresses duplicate generic LOW_IMAGE_QUALITY, retaining accompanying independent page findings. On other documents, existing certain findings such as MISSING_ADDRESS_DATES/PAGES_INCOMPLETE coexist with the generic quality FAIL; the quality finding is appended after specific findings. `api.review.document_blockers` joins distinct FAIL messages in stable order instead of exposing only findings_json[0]; review-only messages do not become rejection reasons. Historical message-only FAIL entries retain compatibility.

Review also found the receipt tier-none fallback replaced every finding after doc_check. It now preserves quality-related FAIL plus accompanying certain file findings while keeping RECEIPT_OCR_UNAVAILABLE as review. Recognition-only receipt uncertainty still does not reject. This is necessary to preserve the requested quality policy and specific-resolution precedence, without changing receipt amount rules.

Verification before commit: shared document/blocker smoke checks and **87 targeted tests passed**, seven dependency warnings (`/tmp/followup3-quality-transition.log`), including all objective-quality gate tests, guidance, exact daily reproduction and selection controls. Expected existing low-quality review assertions are intentionally updated in stage 6 with reasons, not deleted.
