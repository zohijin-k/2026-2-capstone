# Remove application IDs from applicant page URLs

## Goal

Remove the numeric application identifier from applicant page URLs so changing the address cannot select a previously submitted application. Limit the change to applicant navigation and its documentation.

## Background

- `demo/frontend/src/pages/applicant/ApplyFlow.tsx:65` restores an application from `/apply/<id>/<stage>` or the legacy `application` query parameter.
- `demo/frontend/src/pages/applicant/ApplyFlow.tsx:204` writes the application ID into each applicant stage URL.
- Existing refresh and browser history behavior must keep working for the active application in the same tab.

## Requirements

- R1: Applicant page addresses contain only the stage, for example `/apply/identity`, with no application ID in the path or query.
- R2: Restore only the current application saved in this tab session. Never select an application from numeric URL segments or an `application` query parameter.
- R3: Without valid tab session state, show program selection. Old numeric URLs must not fetch the application named by the URL.
- R4: Preserve refresh, stage navigation, my-page return, and browser back/forward for the active application. Handle unavailable session storage safely.
- R5: Leave screen design, form behavior, officer routes, and backend API contracts unchanged.

## Acceptance Criteria

- AC1 (R1): New applications and every applicant stage use `/apply/<stage>` without the application identifier.
- AC2 (R2, R3): Editing or entering `/apply/46/identity` or `?application=46&stage=identity` cannot load application 46 from those URL values.
- AC3 (R2, R4): Refreshing a stage in the same tab restores that tab's active application and saved data; browser history and my-page return still work.
- AC4 (R3, R4): Missing, malformed, inaccessible, or stale saved session state falls back safely to program selection.
- AC5 (R5): Frontend lint and TypeScript checks pass, and unrelated application behavior is unchanged.

## Out of Scope

- Backend authorization redesign, database changes, officer navigation, or UI redesign.
- Restoring an application solely by copying its URL to another browser session.

## Decisions and Limits

- Keep the active application identifier in tab-scoped `sessionStorage`, outside the address.
- Retain only stage and optional my-page return stage in the URL.
- Update the existing frontend navigation convention to match the new behavior.
- URL hiding is navigation hardening; it does not replace server-side application access checks.
- This is a lightweight task, with this PRD as its planning artifact. Implementation requires approval of the final planning summary.
