# Shared assessment evidence

Inspected 2026-11-13 on `feat/verify-cases`, from clean main `b61fa69`. Local source inspection only; no real documents opened or assessments run.

## Existing orchestration

- `demo/backend/tools/verify_upload.py:150`: `_context` validates program/category and builds criteria/checklist without DB. `:172` validates upload slot; `:180` validates file extension/availability.
- `:111`: existing self-identity helper includes supported short-birth candidate selection; reuse rather than invent identity rules.
- `:231`: document mode calls shared upload, builds transient row (`:190`), refreshes paired identity (`:201`), projects applicant findings, computes scoped blockers and applicable work result, then renders text.
- `:294`: income mode reads payment/qualification/acquisition-loss in order, optionally seeds identity from payment, refreshes pairs, builds facts, scores and computes mode-scoped blockers. Text output lacks per-document status/severity/applicant findings, so parsing it cannot meet requirements.
- `:219`: validation names already pass a reviewed positive vocabulary and deduplication; factor names from formatting without changing legacy lines/order.
- `:59`, `:76`: existing audit and quiet contexts reject writes/DB/subprocesses and suppress Python/native/log output. New Git policy checks and authorized snapshot writes must run outside the assessment audit guard.
- `:357`: existing CLI prints safe output/fixed errors. Numeric confidence/page output remains for that CLI but must not enter new regression data.

## Verdict and privacy owners

- `demo/backend/upload_assessment.py`: shared direct upload and NHIS reassessment; no need for endpoint, DB or subprocess.
- `demo/backend/api/common.py:193`: shared applicant projection hides NEEDS_REVIEW only with FAIL, retaining FAIL/INFO and order. Compare both all findings and this projection.
- `demo/backend/api/review.py:116`: document blockers include unrelated missing slots; preserve current tool's target filtering rather than marking every single-document case blocked.
- `demo/backend/rules/eligibility_blockers.py:28`: dictionaries contain sensitive messages/evidence; retain only existing scoped blocker boolean.
- `demo/backend/rules/work_continuity.py:20`: full result contains basis/periods/evidence; read only status/reason/detail codes, never serialize `as_dict()`.
- `demo/backend/rules/scoring.py:219`: income result includes numerical estimates/notes; project only status/reason codes.
- `demo/backend/rules/required_docs.py:27` and `rules/doc_types.py`: canonical work-category and document-type vocabularies.

## Locations and validation evidence

- Root `.gitignore` already covers `engine_v2/data/` and `**/data/private/`. Actual manifest, expected and temporary paths still need independent `git check-ignore`; no new ignore rule is necessary.
- `demo/backend/tests/test_verify_upload.py`: authored synthetic document/work/income integration, safe errors, native/log noise, swallowed write/DB/process attempts, adversarial metadata, standalone CLI. Reuse authored helpers only.
- `demo/backend/tests/test_verify_upload_validations.py`: bounded names/unknown markers, unchanged default rendering, explicit validation rendering and three-slot income association.
- `.trellis/tasks/archive/2026-11/11-13-fail-hides-review/report.md:39`: engine1264/3 skips, backend1159, counting scenarios1885/0; all18 module exits zero including non-counting P14. Its implementation plan requires sequential scenario execution to avoid shared DB collisions.
- `.trellis/tasks/archive/2026-11/11-13-seed-application/report.md:111`: prior task found no configured Python lint/typecheck; reported AST parsing/diff checks separately. Recheck configuration at implementation time.
- `.venv/bin/python` exists; bare `python` is unavailable. Use `python3 -B` for Trellis scripts and virtual environment Python for tests.

## Conclusion

Share structured assessment and preserve current renderers. Build a separate strict, positive-vocabulary snapshot; validate loaded baseline data equally strictly. No rule/extractor/frontend changes or real-document access are necessary. Repository-answerable questions are resolved; the remaining gate is user approval of the complete plan.
