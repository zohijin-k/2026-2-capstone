# Design

- Keep the current mode, application ID, stage, and officer view in readable URL paths. Use query parameters only for optional filters.
- Rehydrate applicant form data from the existing application, consent, program, status, and subsidy APIs after refresh.
- Treat the Jeonbuk mark as an explicit home action: clear applicant navigation and remount the applicant flow.
- If a stored application is unavailable, clear its navigation and show program selection.
- Preserve unrelated query parameters and use browser history for navigation changes.
