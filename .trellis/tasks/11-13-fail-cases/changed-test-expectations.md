# Changed existing test expectations

No existing assertions have been removed or weakened.

- `demo/backend/tests/test_income_review.py::make_application`: normal synthetic work proofs now include all four validated insurance rows and explicit complete structure. The new independent continuity rule cannot treat a generic PASS document without intervals as positive evidence. This fixture upgrade preserves existing income/age/status assertions while strengthening their unrelated work precondition.
- `test_age_eligibility.py::test_both_programs_enforce_inclusive_range_and_checklist_matches_final_reason`: when intentionally varying the shared fictitious identity birth across published age bounds, update the normal work proof birth to that same value. Otherwise this age-only test would introduce an unrelated work-identity uncertainty. Explicit mismatch tests remain unchanged.
- `engine_v2/tests/test_nhis_recent_history.py::test_serialized_coverage_matches_evidence_and_structure`: preserve every existing row/value assertion and add exact `acquired_confidence` / `lost_confidence` expectations. These additive date-token provenance fields keep low-confidence valid-looking OCR dates from establishing a new work-continuity rejection; five-year coverage semantics are unchanged.
