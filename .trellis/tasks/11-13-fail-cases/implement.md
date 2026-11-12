# Execution

Follow the ten commits in design.md sequentially. Load backend OCR/form/income contracts and frontend conventions. Keep certainty evidence separate from aggregate field confidence. Reuse existing result adapters, evidence fields and blocker routing. Review whole changed scope with trellis-check and capture new contracts with trellis-update-spec. Leave status awaiting user verification; do not archive.

## Follow-up upload verification

- [x] Commit the design follow-up before implementation.
- [x] Extract and reuse explicit-slot upload, paired NHIS recheck, criteria checklist and document blocker projection; preserve decision logic and API order.
- [x] Implement the value-free CLI, category slots, self identity and three-file income mode with no persistence.
- [x] Commit 44 synthetic acceptance tests, privacy/no-write checks and known classification limitation; preserve every existing test.
- [x] Independently review shared paths and CLI output/write boundaries; correct CLI-only work blocker omission.
- [x] Run engine and backend full suites; compare counting scenarios and P14; persist results in design.md and verify-upload.md.
- [x] Review backend contract and diff; commit final verification. Leave awaiting user verification; no archive/push/PR/merge.
