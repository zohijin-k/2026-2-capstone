# Income and age eligibility contracts

## 1. Scope and trigger
Use for qualification/payment evidence, monetary facts, income scoring, demo engine adaptation, final review and officer eligibility rows. Residence policy, mixed-insurance aggregation and multiple workplace-insured member rules are outside this contract. Public mixed limits only bound possible mixed households; they never establish membership. Never use filenames or expected slots to infer form kind or membership.

## 2. Signatures
- `nhis_qualification.extract` emits `사업장관리번호` when usable and always `사업장관리번호_상태`.
- Government payment `nhis_payment.extract` emits `사업장명칭_상태`, preserving its existing `사업장명칭` output.
- `build_facts(form1, documents, payment_months=None) -> ScoringFacts` uses the default October–December 2025 months or all three explicitly configured distinct months.
- `score_income(facts) -> IncomeScoreResult`: `item`, `percent`, `over_limit`, `notes`, `status`, `reason_codes`. Historical iteration/index/slice/len exposes only `(item, percent, over_limit, notes)`.
- `to_engine_applicant(..., income_percent, income_over_limit=None, ...)` optionally accepts authoritative integer eligibility: True maps to decile 10 even with percent None; False caps a known decile at 9; False plus no percent stays None. Absent override preserves legacy mapping.
- `assess_age(program, form_birth, identity=None) -> AgeEligibilityResult` supplies `status`, `reason_code`, `basis`, `birth_date`, and `as_dict()`.

## 3. Data and trust contracts
A/B states are `값 있음`, `확실한 공란`, `못 읽음`. Blank requires observed bounded labels/value cells, no ordinary value words, and complete form structure; missing metadata is not a blank. Entire management cell must be ASCII digits, without dropping punctuation from a populated cell. Workplace text uses a conservative complete-name grammar. Optional unreadable membership evidence must not invalidate otherwise complete document checks, since income can be decided independently below/above both limits.

`ScoringFacts.insurance_type` is `직장`, `지역` or `모름` (default). `insurance_evidence` records A/B declared and usable states, value, category and serialized source; recorded legacy category evidence is separate. `sources` includes `insurance_a`, `insurance_b`, `insurance_explicit_qualification`, `insurance_explicit_payment`. Two agreeing A/B sources establish membership; trusted recorded category is a legacy compatibility fallback. `insurance_conflict` and `insurance_explicit_conflict` distinguish A/B disagreement from any usable recorded-category contradiction.

`premium_determinable`, `premium_issue`, `premium_reason_code` expose monetary trust. Every selected month must have a valid nonnegative whole integer billed-health amount. Never fall back to aggregate `건강보험료` when monthly data is absent. Preserve `(sum(values) * 2 + len(values)) // (2 * len(values))`. Exclude care and extra-income columns. Known failed payment validations, nonnormal status, bad supplied confidence or incomplete structure block amounts. Known untrusted qualification metadata blocks household count. Missing metadata remains supported only for established minimal legacy fact inputs; A/B evidence itself requires complete metadata and trusted confidence.

Direct pure `ScoringFacts` with already established premium/type remains supported (`premium_determinable=None`); the builder always sets its trust flag explicitly. Production uncertainty must never be converted into a default workplace category.

`IncomeScoreResult.status` and serialized `ScoreSheet.income_status` are `MET`, `OVER_LIMIT`, `UNDETERMINED`; sheet also serializes `income_reason_codes`. Exact integer bounds decide eligibility; rounded `income_percent` is only the unchanged linear demo estimate used for scoring. For an unknown membership category and a certain low/high outcome, disclose any reference row used for score estimation without asserting applicant membership.

## 4. Validation and final-status matrix
| Input | Eligibility/final behavior |
|---|---|
| Complete amount <= min(workplace, regional) | MET regardless of A/B agreement |
| Complete amount > max(workplace, regional, mixed when present) | OVER_LIMIT regardless of A/B agreement; existing engine INCOME_OVER_THRESHOLD path |
| Mixed row exists, max(workplace, regional) < amount <= mixed | UNDETERMINED, INCOME_MIXED_POSSIBLE; no percent or certain excess, even with agreeing ordinary-category evidence |
| Middle amount, established workplace/regional | Compare its integer limit, equality accepted |
| Middle amount, insufficient/disagreeing/unreadable A/B without recorded fallback | UNDETERMINED |
| Any usable recorded category contradicts another recorded or A/B source | UNDETERMINED even outside the middle band |
| Missing/untrusted amount or household | UNDETERMINED |
| Households 8–10 | Official rows, no out-of-table warning |
| Household 11+ | UNDETERMINED, never clamp to 10; direct limit helper raises ValueError |
| Birth equals either configured endpoint | PASS age eligibility |
| Birth outside inclusive program birth_range | FAIL, AGE_OUT_OF_RANGE |
| Missing/malformed form birth | NEEDS_REVIEW, AGE_UNDETERMINED; do not substitute identity birth |
| Supplied identity birth differs/is malformed | NEEDS_REVIEW, AGE_IDENTITY_MISMATCH |

`review._run_review` uses the existing demo payload/status override boundary. Required-income UNDETERMINED adds `INCOME_UNDETERMINED` with `detail_codes` and the income item's basis. It contributes NEEDS_REVIEW without lowering a definite FAIL. Age snapshot is `payload.age_eligibility`; its non-PASS reason enters the same stage2 reason list. Merge all contributions using `review._merge_statuses`: FAIL > NEEDS_REVIEW > PASS, with absent stages contributing nothing. Final status merges engine final with household/income/age/overlap results; stage2 separately merges engine stage2 with those same additional results, never with engine final or stage1. Preserve every reason. When overlap reopens an existing review, merge with its own stored final/stage2 and retain FAIL while clearing the existing officer decision as before. Do not overwrite either status after overlap linking. Keep persisted final/stage2 status, payload final_status, recommended_action, supplement deadline and officer checklists consistent. Programs without an income requirement get no income result/checklist/override. Engine files need no changes.

The officer income row uses `income_status == MET` and exactly the income item's basis. The age row uses `assess_age` and its basis. Age scoring points remain separate from eligibility.

## 5. Good, base and bad cases
- Good: one-person household, two observed blanks, a trusted three-month average between regional and workplace bounds: membership regional, definite income FAIL.
- Base: fixture/legacy explicit recorded category with no contradictory evidence stays supported. Synthetic fixtures supply all monthly values deliberately; production does not infer them from an average.
- Bad: missing labels treated as blanks, one cell sufficient in the middle band, mixed limits selected automatically, rounded 140.0 used to suppress integer excess, or age sentinel values used for eligibility.

## 6. Required tests
Preserve A/B coordinate, scale/jitter/skew, text-layer adapter and missing/partial/malformed value tests; legacy printed category compatibility; all evidence permutations; exact integer equality/+1 for each supported size/type; low/high independence; explicit-conflict precedence; missing month/trust failures; zero;8/10/11; real stored-document review/payload/checklist agreement; both programs' age endpoints/day outside/missing/identity mismatch; malformed date and huge dict-year review; valid very old births reach AGE_OUT_OF_RANGE instead of crashing age scoring; API identity immutability; no-income job package; FAIL precedence over uncertainty, separate stage1/stage2 results, reopened overlap FAIL retention, officer list/detail/payload/action consistency and supplement deadlines. Cover every mixed-table row at ordinary-max-plus-one, mixed equality and mixed-plus-one without inferring membership; verify two/ten-person final reasons and checklist ④, and one-person two-blank regional excess. Run engine pytest, backend pytest and every scenario module, recording intentional obsolete expectation changes without deleting/weakening coverage.

## 7. Wrong versus correct and assumptions
- Wrong: use `percent > 140` after display rounding. Correct: use integer premium > selected limit and pass the authoritative bool through the adapter.
- Wrong: allow unknown income to skip engine stage2 and remain final PASS, or overwrite a certain FAIL with review. Correct: merge required-income NEEDS_REVIEW with every independent result and persist all visible reasons.
- Wrong: reject above both ordinary bounds but at/below the available mixed bound. Correct: require INCOME_MIXED_POSSIBLE review; reject certainly only above all available bounds. One-person regional middle-band excess remains FAIL.
- Wrong: compute age from a fallback birth or silently truncate malformed raw birth. Correct: assess the original submitted date and compare any stored identity date; missing/unreadable stays review.
- Confirmed limitation: legacy generic payment code can infer its recorded category from body/workplace text. This task preserves that unrelated extractor behavior; its provenance is weaker than the new bounded A/B states.
- 추정 (unverified): synthetic coordinate/text-layer tests establish contracts, not real-document OCR accuracy or coverage of every company-name glyph. Unsupported names must remain unreadable.
- Demo identity is user-entered once and then locked by the server; it is not an external identity-provider assertion.
