# State Management

> How state is managed in this project.

---

## Overview

<!--
Document your project's state management conventions here.

Questions to answer:
- What state management solution do you use?
- How is local vs global state decided?
- How do you handle server state?
- What are the patterns for derived state?
-->

(To be filled by the team)

---

## State Categories

The demo uses React component state for the active applicant and officer screens. Applicant paths contain only the stage, such as `/apply/identity`; keep the current application ID in tab-scoped `sessionStorage` under `applicant.activeApplicationId`. Restore applicant drafts only from this tab state, never from numeric path segments or an `application` query parameter. Missing, invalid, inaccessible, or unavailable saved state returns to program selection. Refresh and stage history restore the active application in the same tab; copying a URL alone does not identify an application. Officer paths such as `/officer/province/review/9` remain unchanged. Use query parameters only for optional filters and preserve unrelated options such as `mock` and `debug`. Fetch application data and consent values from the API when restoring an applicant draft; do not put forms or identity data in the URL. Hiding IDs does not replace server-side access checks.

---

## When to Use Global State

<!-- Criteria for promoting state to global -->

(To be filled by the team)

---

## Server State

<!-- How server data is cached and synchronized -->

(To be filled by the team)

---

## Common Mistakes

<!-- State management mistakes your team has made -->

(To be filled by the team)
