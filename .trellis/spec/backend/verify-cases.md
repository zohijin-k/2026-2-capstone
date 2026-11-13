# Private verification cases

## 1. Scope / trigger

Apply to `demo.backend.tools.verify_cases`, its synthetic tests and the structured assessment boundary shared with `verify_upload`. Never change verdict/blocker rules, extractors or frontend to make regression tooling pass. Preserve all existing `verify_upload` output and test expectations, including `--validations` and `applicant_reason`.

## 2. Signatures

`PYTHONPATH=. python -B -m demo.backend.tools.verify_cases --cases <cases.json> [--record]`

`verify_upload.assess_document(args, program, category, criteria, checklist)` and `assess_income(...)` return transient `Assessment` context. Existing `_document` / `_income` render that same context. These objects can contain private OCR/document facts in memory; never serialize them wholesale or parse legacy rendered output to build a snapshot. `_failed_validation_names(fields)` owns the same reviewed vocabulary used by the legacy validation renderer.

## 3. Contracts

- Manifest: `{"schema_version": 1, "cases": [...]}`. Each unique ID matches `[A-Za-z][A-Za-z0-9_-]{0,63}` and must be nonidentifying. Unknown/duplicate keys and invalid types are errors.
- Document case: `id`, `slot`, `file`; optional `program` (default `double_savings`), `work_category`, `self_identity` (default false).
- Income case replaces `slot`/`file` with `income: {payment, qualification, acquisition_loss}`, three path strings in that assessment order. Relative source paths resolve from the resolved manifest directory.
- Snapshot appends `.expected.json` to the requested manifest path, then resolves its target independently. Both manifest and expected resolve symlinks. Inside this checkout they must pass `git check-ignore` and be untracked. Outside actual paths are allowed without invoking check-ignore. No bypass flag or added ignore rule. Snapshot must not alias manifest or any original document.
- Git checks run with the actual checkout root as cwd, no shell and suppressed output. They stay outside the assessment audit guard. Recording temporary siblings follow the same location policy; no new parent directories.
- Snapshot: versioned `cases` map keyed by ID. Each case has `identity` O/X, `blockers` O/X and `documents` map keyed by validated slot. Each document stores only `detected_type`, `document_status`, `reason` / `applicant_reason` code+severity pairs and `failed_validation` names. Use final refreshed row findings/status, especially after NHIS pair reassessment. Optional `income_status` / `income_reason` and `work_status` / `work_reason` contain only applicable statuses/codes. Do not add work analysis to income mode.
- Call `applicant_findings` before projecting applicant codes. Keep existing mode-scoped blockers; unrelated missing upload slots must not turn a single-file case into a blocker.
- Use positive code/enum/name vocabularies. Unreviewed current metadata maps to fixed unknown markers; loaded baseline schemas/values are validated strictly before use. No fields, messages, raw text, source names/paths, confidence numbers, scoring values, basis or full evidence objects may enter recorded data/output.
- Compare canonical sets by ID and slot. Ordering/duplicates and numeric confidence jitter alone do not differ; real verdict changes caused by confidence still differ. Emit ID O/X, only changed field-qualified signed tokens, then matching/union-total count. Removed tokens use `-`, current tokens `+`. Added/removed cases use `+CASE_ADDED` / `-CASE_REMOVED`.
- Sequential assessment uses the shared Python/native/log suppression and read-only audit guard. No DB connection/persistence, source-file mutation, OCR subprocess or dependency stdout/stderr. Set bytecode suppression before backend imports and retain `python -B` usage.
- `--record` writes only after every case succeeds, through a checked temporary sibling and atomic replacement; preserve old expected bytes on failure. Case exceptions emit only ID, X marker and validated exception class name, never exception message/path/stack.

Example with an intentionally fake source:

```json
{"schema_version":1,"cases":[{"id":"case7","slot":"nhis_payment","self_identity":true,"file":"fake-documents/payment.pdf"}]}
```

## 4. Validation and error matrix

| Condition | Result |
| --- | --- |
| Recorded unchanged verdicts | Every case O, matching/total, exit 0 |
| Verdict/code/severity/name differs | Case X, signed changed tokens only, exit 1 |
| Added/removed ID | Case X with signed membership marker; union denominator, exit 1 |
| Case execution exception | ID X exception class only, continue other cases, exit 1 |
| Case execution exception during record | Same safe error, exit 1, previous baseline preserved |
| Invalid CLI/manifest, unsafe location, missing/invalid baseline | Fixed safe diagnostic, exit 2; no argument/path echo |
| Recording I/O failure | Fixed safe diagnostic, exit 2, previous baseline preserved |
| Dependency/native/log output | Suppressed on success and failure |

## 5. Good / base / bad cases

Good: an authored synthetic manifest outside the checkout records then compares all O. Base: existing `verify_upload` invocations produce byte-for-byte unchanged output. Bad: a tracked case list, an expected symlink resolving to a source PDF, arbitrary OCR text presented as a code, or a whole work result dumped into expected JSON.

## 6. Required tests

Use temporary synthetic manifests/documents and temporary Git repositories only, never real documents or actual private-data paths. Cover record/compare, reason +/- and severity/status/identity/blocker/applicant-only/validation changes, order and confidence stability, income per-slot refresh, missing/invalid baselines, case membership, exact exception-class privacy, native/log/error noise, ignored/unignored/tracked paths, no check-ignore outside, resolved symlinks and source collisions, atomic-failure preservation and zero DB/source writes. Existing CLI tests and expectation lines must remain unchanged. Run full engine/backend suites and all scenario modules sequentially; compare explicit baselines and report actual counts before commit approval.

## 7. Wrong versus correct

Wrong: run `verify_upload` in a subprocess, parse its presentation text, serialize `Assessment`/work evidence, or use a path's lexical spelling as privacy proof. Correct: both CLIs call shared assessment directly, explicitly project reviewed statuses/codes/names and apply Git policy to resolved targets.

Wrong: print `str(exc)` or a traceback for a case failure, or overwrite expected after some cases fail. Correct: emit only the case ID/X/exception class and preserve the prior record until every assessment and the atomic write succeed.
