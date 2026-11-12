# Confirmed document defects and work eligibility

## 1. Scope / trigger

Apply when changing upload certainty, mixed-document PDF handling, daily-work records, provisional work continuity, applicant blockers or officer work checklist. Classify from body text/coordinates; never from filenames or expected slots. Synthetic evidence only during development. Work contracts, residence eligibility, weekly hours, mixed-household rules and score policy remain separate.

## 2. Signatures

- `check_document(req, ocr, ...) -> CheckResult` retains its signature. File defects precede unknown-type returns.
- `original_image_sizes(path)` measures original upload/dominant full-page embedded bitmap dimensions. Never substitute rendered/upscaled dimensions or treat a scalable text-layer page as limited by its background bitmap. `resolution_defect(ocr)` requires narrow pixel and applicable-field unreadability evidence together.
- `address_dates.assess(pages, *, type_confidence)` returns independent `status` MISSING/PRESENT/UNDETERMINED, confidence and page evidence. Its new rejection also requires reliable source title/subtype words, not merely categorical type confidence.
- `payment_period.collect(pages, extraction)` emits versioned `고지월검증자료`; payment aggregate field confidence does not replace independent period/amount certainty.
- `attached_pages.extract_form(extractor, pages, today=None)` returns `(extraction, scoped_pages)`. `_load_pages(..., allow_page_errors=False)` preserves existing default errors; only mixed-form adapters opt into retaining failed attachment pages.
- `daily_work_record.extract(pages, today=None) -> DailyWorkResult`; registered as engine_v2 `DAILY_WORK_RECORD`, value `daily_work_record`.
- `assess_work(program, announcement_date, work_category, documents, identity) -> WorkContinuityResult`; `review_status` maps MET/NOT_MET/UNDETERMINED to PASS/FAIL/NEEDS_REVIEW.
- `age_blockers(program, form1, identity)` and `eligibility_blockers(program, form1, identity, documents, work_category, criteria)` return applicant-safe blocker dictionaries.

## 3. Contracts

- `원본이미지크기`: JSON list of `{page,width,height}` (zero-based page). Hard pixel criterion is **short <600 AND long <800**, plus unknown type or a strict majority of applicable essential fields unreadable. Receipts use amount/payment date; exams/interviews use their own fields. Unsupported known types do not acquire identity-field requirements accidentally. Readable tiny documents retain normal quality review behavior.
- `독립쪽표기자료`: top-right folios with independent confidence. Low-resolution unknown-title uploads can retain reliable 1/2 evidence without inventing a resident type.
- `주소날짜검증자료`: reliable abstract title plus number/address header without date labels, or observed numbered address rows without date values. A separate positional proof accepts observed occurrence/report header x ranges (spacing/non-Hangul OCR prefix normalized only for comparison), a reliable standalone blank marker, and >=2 ordinal-delimited Hangul address rows left of those columns on every page. Any digit-bearing word whose box intersects either bounded date column vetoes that proof, irrespective of token confidence; header uniqueness/order and reliable source title remain mandatory. An address containing the marker phrase or an in-table margin note is not a terminator. This proof is independent of overall confidence/image quality and never consumes date-dependent parsed history. Missing header, low-confidence title, ambiguous date residue or contradictory layout stays review. Parse dates only in date columns; address-note dates do not establish them. Residence fallback scoring remains unchanged, with an explicit unproven-input warning in FactSource.origin.
- `고지월검증자료`: version 1, status READABLE/CONFLICT/UNDETERMINED, period, observed periods/month rows, amounts_certain, absent_amount_months and uncertain_absent_amount_months. Title/query/positive or explicit year-month contradictions prevent rejection. Annual zero placeholders are not conflicts. Unknown outside-period monetary tokens prevent certainty; only proven bounded numeric correction plus all arithmetic can rescue O/o zeros.
- `PaymentResult.billing_absence_states`: per-month ZERO_CONFIRMED/ZERO_UNCERTAIN/BLANK_CONFIRMED/BLANK_UNCERTAIN, independent from ordinary form completeness. Confident zero or bounded blank requires observed headers/columns, every column sum and paid grand total; uncertain target zero or arithmetic tokens stay review. Low-confidence annual placeholders outside target months do not invalidate a normal form.
- `추가첨부쪽`: JSON one-based physical page indices. Exactly one confidently identifiable 1/1 form can be scoped; duplicate/same-family continuation evidence retains strict whole-form validation. Attachment existence never adds FAIL or reduces the valid form's confidence. Officers retain original file access and metadata.
- Daily fields: 발급번호, 발급번호목록, 발급일, 성명, explicit four-digit 생년월일, 보험구분, 조회기간, 일용근로내역자료. Two-digit birth emits `생년월일표기` and `생년월일후보` only; verified identity must match a candidate before negative eligibility.
- Daily JSON: `{period:[YYYY-MM,YYYY-MM],rows:[{month,workplace,work_dates,days,wage,remuneration,worker_category}],insurance_types,copies_consistent}`. Wrap day lists across baselines; preserve original source words. Compare duplicated copies fully before deduplicating. Unknown graphical checkmarks are explicit metadata uncertainty and cannot invent an insurance label. Unexpected labeled identity/issue grids in confirmation-only continuations require review.
- Work settings are explicitly **provisional (잠정)**: `ProgramConfig.work_continuity_months=5`, `business_opening_deadline=2025-09-03` for savings. Announcement minus calendar months gives 2025-10-03 through 2026-03-03. Daily monthly coverage ends February; query must extend through notice month. No work requirement => no work eligibility contribution.
- Work JSON: status, reason_code, detail_codes, basis, period_start/end, evidence, missing_months, provisional. Complete full rows, verified applicant identity, valid high confidence/quality and issue date on/after announcement are required. Preserve fresh insurance `자격취득일신뢰도`, NHIS `acquired_confidence`/`lost_confidence`, and bounded identity/date source confidence. Fresh converters store `근로근거신뢰도` from bounded identity/issue source words. Noncoordinate JBAI retains prior document compatibility but records unconfirmed work evidence. Legacy absent provenance never bypasses full-row/structure/global trust checks. Summaries alone are unknown. Conflicting determinate documents => UNDETERMINED.
- Final-check `blockers[]`: `{kind:"eligibility",target,label,code,message,goto,evidence,...}`. Only OVER_LIMIT, AGE_OUT_OF_RANGE and work NOT_MET block. Submit recomputes blockers from current stored facts and returns HTTP400 `detail` string with eligibility reasons. Unknown eligibility stays submittable. Identity POST, application GET and status GET include the same age `eligibility_blockers`.
- Applicant evidence includes public household/category/140% limits/average months and amount, birth/date range or work period/missing months. Never reuse score-item basis or expose points/ranks. Use configured call center; when absent, direct users to the configured public contact page without inventing a number.

## 4. Validation and error matrix

| Evidence | Result |
|---|---|
| Password/unopenable PDF, even confidence zero | UNREADABLE_FILE FAIL |
| Tiny original plus applicable unreadability | IMAGE_RESOLUTION_TOO_LOW FAIL |
| Reliable abstract header/date omission | MISSING_ADDRESS_DATES FAIL |
| Missing/low-confidence title/header/date evidence | NEEDS_REVIEW |
| Reliable excluded query months or certain zero/blank target bill | MISSING_BILLING_MONTHS FAIL |
| Unknown/conflicting range, uncertain amount/arithmetic | NEEDS_REVIEW |
| Complete single form plus dissimilar attachments | Preserve form checks/confidence, record attachment indices |
| Verified complete daily table lacks required month or query coverage | WORK_CONTINUITY_NOT_MET / NOT_MET |
| All relevant active acquisitions after start; provable history gap; late opening/explicit closure | NOT_MET |
| Contract-only, summaries-only, partial table or identity uncertainty | UNDETERMINED |
| Work/income not required | No corresponding blocker or work checklist |

## 5. Good / base / bad cases

Good: body-recognized four-page daily duplicate, matching verified identity, complete monthly rows, independent period; all consumers share work assessment. Base: normal source dimensions and complete forms retain their previous result; explicit issue-date cutoff remains inclusive. Bad: infer missing months from an absent map, infer centuries, trust low-confidence date/title glyphs, or let extra pages pollute single-form checks.

## 6. Required tests

Run full engine/backend pytest separately and every scenario module. Preserve baseline coverage and record intentional expectation changes. Include actual synthetic encrypted PDFs, text/image uploads with arbitrary names/expectations, normal image sizes and hard-cutoff boundaries, date-empty versus broken-header variants, contradictory/unknown periods, confident/uncertain zero/blank and arithmetic, duplicate/continuation corruption, full work gaps/boundaries/conflicts/identity/date uncertainty, officer agreement, fresh submit rechecks, unknown-submittable behavior and no-work programs. Source-shaped fixtures prove contracts, not real-document OCR accuracy.

## 7. Wrong versus correct

Wrong: overall confidence .4 means every independent defect must become review. Correct: preserve file facts and separately proven printed period defects while deferring uncertain values.

Wrong: type score .95 proves title glyphs were read confidently; a known receipt must have birth/name fields. Correct: verify source title certainty for new rejection and choose essential fields by actual document kind.

Wrong: synthesize a successful current submit for a now-ineligible officer fixture. Correct: assert current blocker/400, then explicitly seed an isolated synthetic historical review only for downstream officer regression coverage.

## 8. Read-only upload verification

`demo.backend.tools.verify_upload` is a value-free CLI for an explicitly chosen upload slot, or an ordered payment/qualification/acquisition-loss income bundle. Use `python -B -m` so interpreter startup cannot write bytecode. Keep default criteria construction and application in `api.common.checklist_from_inputs`; `checklist_for` supplies saved API context, while the CLI supplies only program/category and default criteria. Stored overrides and other unsupplied application inputs are outside CLI parity.

`upload_assessment.assess_upload` is the shared explicit-slot orchestration: read_document, consent observation, check_document, then consent/receipt adjustments. API-only persistence, copied destinations and DB loaders stay in the API. Its optional input callbacks preserve the existing order of row and receipt lookups. `assess_nhis_identity` shares the API's exact paired-NHIS rehydration and checking. CLI rows are unsaved Documents, projected by the same document_fact helper before assess_work/build_facts/score_income/eligibility_blockers. `review.document_blockers` is the shared FAIL/missing-document projection; CLI filters away unrelated missing slots and age/form/consent blockers. Include a selected document's actual work blocker regardless of whether its slot is work_proof or nhis_acquisition_loss.

Self identity requires an explicitly readable name and a full ISO birth date, or the daily reader's validated short-year printed date plus its complete valid century-candidate set. For daily candidates only, the supplied program.birth_range must select exactly one candidate before forming a temporary CLI reference; otherwise leave the reference unresolved. Never insert that century into OCR fields or select it arbitrarily. Existing authenticated daily identity matching compares the candidate birth and name; incomplete structure/copy disagreement still prevents work rejection. Income uses payment as one reference identity across the entire bundle. This is verification context, not actual identity authentication.

Output is a positive schema with fixed code/type/tier/status vocabularies, static checklist labels, bounded metrics, counts and O/X. Drop fields, names, dates, monetary amounts, identifiers, messages, basis, evidence, filenames, paths and exception strings. Redact all numeric runs of four or more digits at final emission, including static label years. Suppress Python/native stdout/stderr and logging around all dependency work, including failure paths. Unknown production codes become UNKNOWN_CODE until reviewed for addition to the vocabulary.

Reject Python filesystem writes, DB connections and child processes with a CLI-only audit guard; remember rejected attempts even when OCR fallback catches the exception. Do not silently continue with a different verdict after a blocked write. Existing tempfile-based OCR transports are not changed to satisfy the CLI; report WRITE_ATTEMPT_BLOCKED. Native library filesystem isolation is not established by a Python audit hook (추정). Keep the configured OCR chain and its existing external-service opt-in semantics.

Required acceptance tests use authored encrypted/text/image files and, where needed, synthetic recognition words. Cover all failure cases, income states/pair mismatch, category slots, missing identity, actual document/work/income blockers, no value/long-number output, safe argument/dependency errors, native buffered output, unchanged inputs/logs and blocked copies/tempfiles/DB/storage writes. A positive extractor-only result does not prove image title classification: retain explicit tests for that preceding boundary. The source-shaped interleaved image insurance title is a confirmed existing classification limitation; do not claim original-document accuracy from synthetic tests.


## 9. Short-year and positional-proof regressions

Keep the source-shaped fixtures fully fictitious. Cover short/full-year PDFs through value-free CLI, authenticated birth/name mismatch, cross-copy disagreement, unchanged extracted fields, zero/multiple program-range matches and malformed candidate sets. Positional tests must include digit words crossing each horizontal/vertical table boundary, absent/duplicate headers, one address with multiple continuation lines, missing table end, footer-only numbered notes, addresses containing marker text, in-table margin notes, mixed pages and normal dated image/text multi-page forms. Do not claim an actual document's unrelated low-confidence structural failure is fixed when masked geometry reproduces complete extraction; record that limit explicitly.
