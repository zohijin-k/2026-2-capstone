# Verification-case design

## Architecture and boundaries

Data flow: manifest validation -> location checks -> shared in-process assessment -> allowlisted snapshot -> explicit record OR signed comparison.

Separate `verify_upload.py` document/income orchestration from formatting with the smallest internal refactor. Shared structured results retain transient OCR/document/rule objects for existing rendering; they are never generically serialized. Keep `_document` / `_income` as formatters and preserve their ordering/wording/metrics. Both entry points call the same orchestration. Factor safe validation-name extraction so both tools reuse it while legacy `_failed_validations` output stays unchanged.

Unchanged verdict owners: `assess_upload`, `assess_nhis_identity`, `applicant_findings`, `document_fact`, `document_blockers`, `eligibility_blockers`, `build_facts`, `score_income`, `assess_work`. Preserve their invocation order, identity callback, paired refresh, income order and blocker target filtering. Do not parse existing formatted text: income text lacks per-document statuses/severities/applicant findings. Do not copy orchestration or call an upload API/DB.

## Manifest contract

Require `schema_version: 1` and a nonempty `cases` array; reject unknown keys and duplicate JSON keys. IDs match `[A-Za-z][A-Za-z0-9_-]{0,63}`, are unique and must be nonidentifying. Validate booleans without coercion.

Common case keys: `id`, optional `program` (default `double_savings`), optional `work_category`, optional `self_identity` (default false). Document cases require `slot` and `file`; income cases instead require `income` with exactly `payment`, `qualification`, `acquisition_loss`. The modes are mutually exclusive. Delegate existing program/category/slot/file validation to shared CLI helpers. Failed-validation names are always collected; no extra flag.

Fake-path example (place outside the checkout or in `engine_v2/data/private/`):

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "case7",
      "slot": "nhis_payment",
      "self_identity": true,
      "file": "/fake/example/payment.pdf"
    },
    {
      "id": "work_history",
      "slot": "work_proof",
      "work_category": "직장가입자",
      "self_identity": true,
      "file": "fake-documents/history.pdf"
    },
    {
      "id": "ok_income",
      "program": "double_savings",
      "work_category": "직장가입자",
      "self_identity": true,
      "income": {
        "payment": "/fake/example/payment.pdf",
        "qualification": "/fake/example/qualification.pdf",
        "acquisition_loss": "/fake/example/history.pdf"
      }
    },
    {
      "id": "job_residence",
      "program": "job_package",
      "slot": "resident_abstract",
      "file": "/fake/example/residence.pdf"
    }
  ]
}
```

Relative document paths resolve from the manifest directory, independent of cwd. Expected filename appends `.expected.json`: `cases.json.expected.json`.

## Location, execution and writes

Find this checkout from module ancestry, independent of caller cwd. Resolve symlink targets/parents and apply policy to the actual resulting paths. For every inside-checkout location run `git check-ignore -q -- <relative-path>` with this checkout as cwd, no shell and captured stdout/stderr. Reject tracked files, including force-added ignored files; normal check-ignore semantics do not treat tracked files as ignored. Unexpected Git status fails closed. Outside locations require no ignore match.

Validate manifest and expected locations independently on both modes, including nonexistent output parents. Allow symlinks whose resolved targets satisfy policy, check resolved parent aliases and reject input/output collisions. Outside actual paths do not call check-ignore. Do not add ignore rules or create parent directories. In record mode assess all cases before writing; create a checked temporary sibling, write only safe JSON, atomically replace expected and clean up on failure. If the temporary sibling is not ignored inside the repository, refuse. Preserve prior expected bytes on all failures; use restrictive permissions where supported.

Git is the sole new implementation subprocess, only for location policy. It must run outside `read_only_assessment`, which blocks subprocesses. Actual backend imports/assessment run inside existing `quiet_assessment`; recording writes also occur outside its read-only guard. Set `sys.dont_write_bytecode` before backend imports and keep `python -B` usage. Sequential execution is required by process-global suppression/audit state. No DB session, source-file mutation or upload/cache output.

## Snapshot contract

Versioned JSON keyed by case ID, with explicit projections only:

| Field | Allowed content |
| --- | --- |
| `identity` | Case-level O/X for temporary reference availability |
| `documents` | Map keyed by validated slot; all three NHIS slots in income mode |
| Per-document `detected_type`, `document_status` | DocType vocabulary and PASS/FAIL/NEEDS_REVIEW, fixed missing marker |
| Per-document `reason`, `applicant_reason` | Sorted unique `{code, severity}` pairs from final refreshed findings; call shared applicant projection |
| Per-document `failed_validation` | Sorted unique safe validation names |
| `blockers` | Case-level O/X with unchanged mode-specific scope |
| `income_status`, `income_reason` | Income mode only; status and sorted unique scorer reason codes |
| `work_status`, `work_reason` | Applicable document/work mode only; status and primary/detail codes |

Reuse `SAFE_CODES`, `SAFE_VALIDATIONS`, DocType and status/severity vocabularies. Map unreviewed current metadata to fixed `UNKNOWN_CODE`, `UNKNOWN_VALIDATION` or `X`; never pass through arbitrary strings. Do not invent severities for income/work reason codes. Do not add new work analysis to income mode.

No membership values, confidence, tier/page counts, scores, basis/messages, evidence, dates, paths, person identity or manifest metadata. In-memory `_ocr_json()` rows remain permitted for existing rules, but are never a snapshot payload. Never serialize complete OCR/work result objects via `as_dict`/`model_dump`.

Validate loaded baselines strictly with schema/version/types/IDs/slots/enums and reject extra keys or value-bearing strings without echo. Invalid baseline is an error, not a silently normalized match. Schema migration requires explicit re-recording.

## Comparison and console contract

Flatten safe fields into field-qualified canonical tokens, distinguishing slot/reason/applicant reason/severity. Compare sets so repeated or reordered findings alone do not differ. Scalar changes remove old tokens and add current tokens. Print deterministic removed tokens first, then added tokens. Example:

```text
case7 X
-nhis_payment.document_status:PASS
+nhis_payment.document_status:FAIL
+nhis_payment.reason:MISSING_BILLING_MONTHS:FAIL
+nhis_payment.applicant_reason:MISSING_BILLING_MONTHS:FAIL
ok_income O
1/2
```

Print only changed tokens below X, no unchanged details. Manifest IDs retain input order; removed baseline IDs follow sorted. Added/removed cases emit `+CASE_ADDED` / `-CASE_REMOVED`, not full snapshots; final denominator is the union of IDs. Successful record prints each `<id> O` and `<total>/<total>`, never the expected path.

Top-level errors emit only fixed codes (e.g. `MANIFEST_LOCATION_REJECTED`, `EXPECTED_MISSING`, `EXPECTED_INVALID`, `RECORD_ERROR`), exit 2. In comparison, individual assessment exceptions emit only `<id> X <ExceptionClass>`, continue and exit 1. Record-mode case exceptions also exit 1 and preserve expected bytes. No exception message/path/stack. Keyboard interrupt produces only a fixed code. Argparse and dependency exception strings are never printed.

## Compatibility, risks and rollback

- Separating assessment/formatting is the principal regression risk. Capture exact synthetic output before refactoring and compare it afterward for all legacy modes; preserve existing tests/expectations.
- A numeric confidence change is ignored only if the rule verdict is unchanged. Safe vocabularies need reviewed updates when legitimate new codes/names are introduced; never broaden to arbitrary strings.
- Existing native/log suppression and audit guard are process global; no threads. Test native/Python/log noise and swallowed write attempts.
- ASCII ID validation prevents paths/control injection but cannot detect a real name deliberately used as an ID. Document nonidentifying IDs. Paths never enter output or snapshots.
- Ordinary symlink aliases and tracked paths are checked. Concurrent hostile filesystem swaps are outside this local developer tool's threat model.
- Synthetic tests establish wiring/privacy, not native OCR accuracy for actual private documents. Do not open real documents during development.
- Rollback removes the new CLI/tests and reverts only the internal separation; no migration or private-data rewrite. Keep owner-managed manifests/snapshots untouched.

## Current state

Implementation and independent review completed under `approval.md`; all three suites passed. See `report.md` for actual counts. Awaiting commit approval.
