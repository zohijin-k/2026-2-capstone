# Value-free upload verification

Run from the repository root with the project virtualenv active. `-B` disables interpreter startup bytecode writes before the tool can set its own read-only boundary. The tool does not create an application, open a DB session, create upload directories, copy inputs, or write a report. Output is intended for pasting into conversation.

```sh
# List business/category-specific upload slots (default business: double_savings).
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --slots-list --work-category '지역가입자·피부양자'
# Case 1: unopenable/encrypted payment document.
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --slot nhis_payment --self-identity '<파일>'
# Case 3a: daily-work document.
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --slot work_proof --work-category '지역가입자·피부양자' --self-identity '<파일>'
# Case 3b: insurance portal document with additional attachments.
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --slot work_proof --work-category '직장가입자' --self-identity '<파일>'
# Case 4: issue date earlier than the business cutoff.
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --slot resident_abstract --self-identity '<파일>'
# Case 5: abstract with reliable address-date omissions.
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --slot resident_abstract --self-identity '<파일>'
# Case 6: tiny unreadable image.
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --slot resident_abstract --self-identity '<파일>'
# Case 7: reliably excluded billing months.
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --slot nhis_payment --self-identity '<파일>'
# Income: payment, qualification, acquisition/loss, in this order.
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --self-identity --income '<납부파일>' '<자격파일>' '<자격득실파일>'
# Common job-package slots; no subsidy selections are supplied by this CLI.
PYTHONPATH=. python -B -m demo.backend.tools.verify_upload --program job_package --slots-list
```

`--self-identity` uses the selected document's readable name and full birth date in memory. If either is absent it prints `본인정보 없음` and proceeds with no identity; it never selects a century from birth candidates. Income uses payment identity as the single reference across all three documents. This option checks document behavior, and does not establish that a document belongs to the operator.

`document_status` is the upload grade, independent of `work_status`. Work can block a document whose upload grade is PASS. `blockers` includes only the selected document's FAIL or its work blocker (including work-capable acquisition/loss evidence in the NHIS slot); income includes the three supplied documents' FAIL and the income blocker. Missing unrelated documents/forms/consents and age do not contribute: this is not a complete application submission check. Income output contains only membership, income status, reason codes and its blocker flag. Exit zero means assessment completed, including a FAIL; exit two means a fixed-code tool/input error.

The checklist uses production default criteria through the same criteria-application helper as the API. No saved/custom criteria, declared issue date, multiple workplaces, paper-form selections, subsidy selections or receipt input amounts are supplied. Thus equality with an application that has those settings is outside this tool's scope. Existing work policy remains provisional. Real-document OCR accuracy is unverified (추정); source-shaped tests replace only OCR word recognition with authored words.

The configured upload OCR chain is preserved, including its existing remote opt-in. Filesystem mutations, DB connections and child processes are rejected during assessment. Dependencies' Python/native stdio and logging are suppressed. If an adapter attempts a temporary file, model/cache download or log write, the tool reports `WRITE_ATTEMPT_BLOCKED`, even if an existing OCR fallback catches that exception. In particular, explicitly selecting applevision or paddle may hit their existing tempfile transport; that adapter behavior is unchanged. Use an already installed memory-based engine or text-layer PDF for a side-effect-free run. Native library behavior beyond the inspected adapters remains unverified (추정).

Only fixed code/status vocabularies, static slot labels, bounded numeric metrics and O/X enter output; dynamic fields, filenames, paths, messages, evidence and exception text never enter it. Every numeric run of four or more digits is redacted, including the static year in a payment slot label. New production reason codes absent from the output vocabulary appear as UNKNOWN_CODE until explicitly added.

## Synthetic acceptance evidence

The targeted suite passed all 44 tests. The CLI acceptance suite uses authored files only: a real encrypted PDF; image PDFs with fake OCR words injected at the recognition boundary; text-layer insurance portal plus two image attachments; and three independently read NHIS text PDFs. It asserts upload grades/reason severities, work status/detail codes, document/work/income blocker flags, missing identity without century guessing, every work category's actual slot label, value-free errors, native/Python output suppression, numeric redaction and rejected write/copy/DB/log/tempfile/process attempts. The CLI never writes input copies or report files.

Confirmed existing limitation (not changed): the exact image-only `fail_case_samples.mixed_portal()` title bands interleave the confirmation-use label between the title fragments; keyword classification returns unknown, before the single-form extractor can isolate attachments. The CLI consequently reports UNKNOWN_DOCUMENT_TYPE / NEEDS_REVIEW and no certain work rejection. The equivalent authored text-layer portal plus attachments follows the expected case 3b PASS upload / NOT_MET work / blocker O path. Evidence: `demo/backend/ocr/pdftext.py:118`, `demo/backend/ocr/localocr.py:767`, `engine_v2/tests/fail_case_samples.py:56`, and the explicit limitation regression in `demo/backend/tests/test_verify_upload.py`. Original-document behavior remains unverified (추정). No classifier or judgment rule was changed.
