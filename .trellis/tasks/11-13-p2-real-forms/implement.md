# Execution

- [x] Commit task planning artifacts.
- [x] Implement privacy ingestion and output coverage, upload tests and storage inventory. Commit stage 1.
- [x] Finish per-check cause classification and shared OCR helper plan. Commit stage 2.
- [x] Implement shared OCR helpers and regressions. Commit stage 3.
- [ ] Implement acquisition-history gaps and variants. Commit stage 4.
- [ ] Implement qualification variants and date scoping. Commit stage 5.
- [ ] Implement payment OCR variant with arithmetic checks. Commit stage 6.
- [ ] Implement business-proof extractor, adapter and identity checks. Commit stage 7.
- [ ] Investigate and correct resident numbering review behavior. Commit stage 8.
- [ ] Run `.venv/bin/python -m pytest engine_v2/tests`, backend pytest and eighteen scenario modules. Add requested synthetic integration coverage, run full-scope delegated review and record counts. Commit stage 9.
- [ ] Update applicable form/privacy specifications, final design outcomes and task review status. Commit stage 10.

All tests must use isolated temporary storage. Never run private benchmark data or enumerate the private-data tree. Existing benchmark tests must skip safely if they would access that tree. Review test collection code before the full suite. Keep stage changes independently reviewable, use fresh commits, and keep push/PR actions outside this task.
