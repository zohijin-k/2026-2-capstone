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

The demo uses React component state for the active applicant and officer screens. Keep only navigation coordinates (mode, application ID, stage, and officer view) in tab-scoped `sessionStorage` so refresh can restore the screen. Fetch application data and consent values from the API when restoring an applicant draft; do not duplicate forms or identity data in browser storage.

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
