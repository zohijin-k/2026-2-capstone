# Keep the current page on refresh

## Goal

Refreshing the browser keeps the applicant or officer on the current screen. Clicking the Jeonbuk mark returns to the applicant program selection screen.

## Acceptance criteria

- Refreshing an applicant draft keeps the selected program, application number, stage, and saved inputs.
- Refreshing officer mode keeps the officer screen.
- Clicking the Jeonbuk mark returns to program selection without creating a new application.
- Invalid or unavailable saved application state falls back safely to program selection.
- Copying the URL to a new tab restores the same screen, and browser back/forward follows previous screen locations.
