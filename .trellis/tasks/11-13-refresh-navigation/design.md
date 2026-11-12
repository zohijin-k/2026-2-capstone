# Design

- Keep only the current mode, application ID, stage, and officer navigation in per-tab session storage.
- Rehydrate applicant form data from the existing application, consent, program, status, and subsidy APIs after refresh.
- Treat the Jeonbuk mark as an explicit home action: clear applicant navigation and remount the applicant flow.
- If a stored application is unavailable, clear its navigation and show program selection.
