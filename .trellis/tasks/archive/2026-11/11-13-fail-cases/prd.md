# Confirmed failure cases

Implement the explicitly authorized ten-stage request on `feat/fail-cases`, based on `feat/income-eligibility` at `cdcf68d`; no merge, push or PR. Keep task awaiting user verification after implementation.

## Acceptance

- Password PDFs fail as UNREADABLE_FILE; certain undersized unreadable images fail; recognized resident histories with demonstrably absent date columns fail; reliable payment period/month omissions fail. Uncertain evidence stays NEEDS_REVIEW.
- Preserve issue-date rejection and existing normal documents. A supported single-page form plus unrelated attachments validates only its own page without weakening form checks; retain attachment page evidence for officers.
- Add body/coordinate-only daily work record classification and extraction, including duplicate insurance-copy consistency and identity.
- Add provisional five-month work continuity (employee coverage, monthly daily work, business opening/closure), conservative conflict handling and consistent officer review.
- Block certain income excess, age outside inclusive birth range and work NOT_MET in final-check and fresh submit checks. Keep unknown eligibility submittable. Include numeric evidence and recovery/contact guidance; age available immediately after identity.
- Run complete engine/backend/scenario suites, preserve existing coverage and document every intentional changed expectation.

## Boundaries

Never inspect private documents or execute against them. Only fictitious synthetic fixtures. Do not edit `engine/` or `docs/audit/engine-walkthrough.md`. Contract reading, residence eligibility, mixed/multiple workplace rules and redaction redesign are excluded. Frontend edits limited to existing blocker presentation. User has explicitly authorized task creation, implementation and stage commits.
