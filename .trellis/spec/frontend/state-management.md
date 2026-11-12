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

The demo uses React component state for the active applicant and officer screens. Keep the active screen in readable paths such as `/apply/45/identity` and `/officer/province/review/9` so refresh, copied links, and browser history can restore it. Use query parameters only for optional filters and preserve unrelated options such as `mock` and `debug`. Fetch application data and consent values from the API when restoring an applicant draft; do not put forms or identity data in the URL.

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
