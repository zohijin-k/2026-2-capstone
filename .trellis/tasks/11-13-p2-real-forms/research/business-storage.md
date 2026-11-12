# Business proof contract and storage inventory

## Business-proof integration

`demo/backend/rules/required_docs.py:196` selects `DocType.BIZ_REG_PROOF` for the business-income work-proof slot. The slot uses the ordinary issue-date contract and currently supplies no proof-specific required fields. `demo/backend/rules/identity.py:51` compares `성명` and `생년월일`. The general identity branch in `doc_check.py` permits missing identity fields and can issue FAIL on mismatch, so the dedicated proof path must require both fields and return review for missing/mismatching evidence.

`engine_v2/extractors/job_common.py:103` already implements the business registration checksum and `brn_is_valid`, so reuse it. The engine enum currently has no business-proof type, and the registry lacks a dedicated reader. Add `BIZ_REG_PROOF = biz_reg_proof`, register it, and add a LocalOcr dedicated conversion path that serializes existing Korean identity/date keys plus requested internal fields. Body title evidence selects the proof reader independently of filenames and expected slots. Do not change employment eligibility rules.

The value column starts to the right of labels. Derive its boundary from observed label ends and right-hand token starts. Derive row bands from neighboring label vertical centers and the joint-business section. Long industry/category rows can span multiple lines. The business number must full-match 3-2-5 digits and satisfy the existing checksum. Corporate identifiers must never become birth dates. Scope final issuance below `증명합니다` and the current-status notice, above the tax-office issuer. Require unique evidence and date ordering checks.

For the corporate identity safeguard, reuse the document's validated business registration number's middle two-digit entity code. NTS describes individual taxable codes 01–79, individual exempt codes 90–99, and corporate codes 81–88. A corporate-code proof must omit birth even if its legal-entity identifier happens to look like YYMMDD followed by a sex digit. This classifies the identifier for extraction and leaves employment eligibility untouched. The NTS primary-source FAQ was checked on 2026-11-13. [NTS business registration number allocation](https://www.nts.go.kr/nts/na/ntt/selectNttInfo.do?mi=2448&nttSn=1386)

## Existing storage

Source-defined uploads are under `demo/storage/documents/<application_no>/<slot_key>/` (`demo/backend/api/documents.py:373`). Merged uploads use `<application_no>/_merged/` (`documents.py:487`). Files are persisted before reading (`documents.py:376`, `documents.py:490`). `Document.file_path`, `source_file_path`, `ocr_json`, and `findings_json` are in SQLite `demo/demo.db`, table `document` (`demo/backend/models.py:15`, `models.py:102`). Officer views consume these saved fields (`demo/backend/api/officer.py:657`) and applicant views whitelist fields (`demo/backend/api/common.py:190`). Review payloads are persisted in `review.review_payload_json` (`models.py:158`).

A read-only metadata check confirmed the database and document directory exist, with 31 document rows and 31 nonempty OCR JSON rows. No document content, row values or original PDF was inspected. No stored row or upload was deleted. Previously uploaded PDFs retain whatever identifiers are printed in their page images or text layer. Text-result redaction does not rewrite the original uploaded artifact. Cleanup belongs to the user.

## Baseline

Before production edits, engine tests completed with 499 passed, 3 skipped in 11.18 seconds. Backend pytest completed with 139 passed in 2.41 seconds. Both exit codes were zero. Benchmark tests use synthetic temporary inputs and contain no original-document enumeration. The eighteen scenario modules will be executed with their temporary-storage entry points.
