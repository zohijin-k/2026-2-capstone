# Execution

1. Inventory slots, templates, body rules and existing synthetic assets; read backend/guides specs.
2. Implement standalone classifier, data extension and diagnostic tooling in disjoint files following Trellis sub-agent workflow.
3. Generate actual train/test images with disjoint make_synth_eval font/layout families; run own OCR, train fixed-seed model and evaluate same OCR against rules. Record uncertainty and all metrics.
4. Reproduce diagnostic cases, explain each failed field and code assumptions without modifying extractors.
5. Review full diff and new tests. Run unchanged engine_v2/tests, exact scenario loop, tsc/oxlint/vite. Stop/report existing failures without fixing them.
6. Audit staged bytes and paths, exclude secrets/private paths/assets/protected files. Commit exact requested message only on all gates passing. Report log -3/status. Preserve discoveries in task notes (user prohibits spec edits).
