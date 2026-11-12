# Savings step 2: inline original PDF forms

## Goal

Let a double-savings applicant move directly between forms 1–5 from a persistent form list and fill each original PDF inside the application page, without repeatedly opening and closing a viewer dialog.

## Confirmed background

- The current workspace presents a form list and opens the original PDF background plus coordinate-based controls in a modal. Evidence: `demo/frontend/src/forms/PdfFormsWorkspace.tsx:711`, `:775`, `:795`.
- Applicant-facing numbers differ from stored identifiers for forms 1 and 2. Evidence: `demo/form_numbers.py:10`; labels already use layout `public_form` in `PdfFormsWorkspace.tsx:700`.
- The user explicitly requires the original PDF appearance and every existing input/check action to remain functional. Rebuilding the document as a new HTML form does not satisfy the request.

## Requirements

| ID | Requirement |
| --- | --- |
| R1 | Show public forms 1–5 in a left-side navigation list on desktop, with the selected form and existing completion/remaining-field status visible. Allow direct navigation to any form regardless of completion. Initially display public form 1 after loading. |
| R2 | Display the selected original PDF in the main page. Both editing and written-preview modes stay in this panel. Preserve the original document's content, proportions, page order, and input alignment. |
| R3 | Preserve text inputs, checks/radio choices, identity-locked fields, automatic values, conditional fields, date helpers, phone/email formatting and validation, missing-field indicators, multi-page controls, reset confirmation, downloads, and read-only behavior. |
| R4 | Preserve draft state and the existing storage/payload contract. Form switching must save pending values, including consents previously flushed on modal close. A save failure must retain the current form and values and provide a visible retryable error. |
| R5 | Keep form 5's signature dialog, including drawing, signature image upload, preview, clearing, confirmation, mode-change confirmation, and existing file restrictions. The form itself remains inline. |
| R6 | Preserve form 5's online-versus-paper submission option and guidance. Paper mode must not expose online editing or alter the downstream upload requirement. |
| R7 | Use the existing application visual style with clear navigation hierarchy, a document toolbar, and sufficient PDF viewing space. On narrow screens, place form navigation above the document and keep controls usable without distorting document coordinates. |
| R8 | Preserve eligibility/consent checks, completion progress, and the conditions for continuing to document upload. Keep the employment-package application and unrelated dialogs unchanged. |
| R9 | Follow-up requested by the user: move the active application number and My Page action into the shared top bar. Keep the application steps immediately below it in a compact presentation. Reduce duplicated headings, explanatory text and vertical gaps so the selected PDF's top is visible promptly on entry to savings step 2. Use restrained existing typography and borders rather than large decorative cards, step circles or extra guidance blocks. |
| R10 | The user supplied a reference and requests a connected horizontal progress bar instead of separate stage boxes. Place four small circular markers on one line, with stage captions/names and readable statuses below. Completed stages use checks, the current stage uses a clear ring/dot and emphasized label, and upcoming stages use pale circles. Keep the compact header, restrained navy/neutral colors, existing four stage names/counts, and clear non-color status cues. Do not reproduce the reference image's annotation dots or unrelated labels. |
| R11 | The user rejects the overall visual quality and explicitly requests a more polished contemporary application UI. Treat the applicant top bar, compact overview/connected stage bar, sidebar and PDF panel chrome as one coherent composition: consistent alignment, readable type, deliberate spacing, quiet surfaces and a clear action hierarchy. Retain all original PDFs, controls, persistence, the top-bar number/My Page placement, compact height and connected-bar structure. Do not add decorative dashboards, marketing copy, extra information cards or new product behavior. |
| R12 | The user's sidebar screenshot shows public form 2 before form 1 and an oversized decorated selected row. Explicitly order savings forms by the same public numbers used for their labels, regardless of response/internal order, and initially select public form 1. Present a plain compact contents list with subtle separators/selection, normal-weight readable titles and concise statuses; remove the colored selected card and trailing chevron. Preserve all underlying form IDs/data and document functions. |
| R13 | Give '작성 중' stronger color/weight than '미작성' without badges/cards. Keep the savings progress area's width aligned to the right PDF toolbar containing Save, excluding the sidebar. The user's final request removes the line tails beyond the first/last circles: the connection should end at those markers while the approved area width and current marker positions stay intact. Keep all states, sizes and compact spacing. |
| R14 | Move the first/last circles near the progress area's ends with the middle two at equal center intervals, as annotated by the user. Preserve the approved overall width and inward endpoint captions. The final tail-removal refinement trims only line outside those circles, not their positions. Retain state, size, height and behavior; blue handwriting is positioning guidance, not artwork. |
| R15 | Restore the application heading's original typography. Remove compact-heading overrides so the existing `.flow__head h1` base style (22px, original tracking/color/line height) applies again, including narrow screens. Do not change the heading text or progress diagram styling. |
| R16 | Align stage 2's caption/name left and stage 3's caption/name right, anchored to their own circles, without moving the circles or changing the rail. Balance-wrap the savings application title in the sidebar-width area (naturally '전북청년 함께' / '두배적금 신청') to improve header spacing. Keep the restored title typography, all other visual styling, state, wording and document functions intact. |

## Acceptance criteria

1. After double-savings identity verification, step 2 immediately displays public form 1 and a list of all five forms. Selecting 1 → 4 → 2 → 5 works without completing intervening forms. (R1)
2. Selecting forms or entering/leaving PDF preview opens no form viewer modal; the selected document appears in the main panel. Original wording, tables, proportions, and overlaid controls match the existing PDFs across every page. (R2)
3. Enter representative values and toggle every control type across forms; switch away and return; saved text, checks, consents, and signatures remain correct. Reload after a successful save and confirm restored values. Original field keys and public numbering remain correct. (R3, R4)
4. Verify identity locks, automatic dates and period bands, conditional choices, phone/email validation, missing-field markers, multi-page navigation, reset, downloads, and read-only restrictions. (R3)
5. A simulated save failure leaves the current form and its inputs available, reports the failure, and supports retry without switching to a stale requested form. (R4)
6. Form 5's signature action opens the signature dialog alone. Drawing and JPG/PNG upload, validation, clearing, confirmation, and reopening work; closing or pressing Escape returns to the signature trigger and leaves the inline PDF present. (R5)
7. Form 5 paper mode presents its existing submission guidance, disables online editing, and produces the same upload requirement and completion behavior as before. (R6, R8)
8. Check desktop and narrow layouts: navigation, toolbar, and actions remain reachable; PDF background and input overlays stay aligned through resizing and page changes. Keyboard users can select every form and operate signature controls. (R7)
9. Completion progress and upload gating behave as before. Smoke-check employment-package editing/preview/signatures and the shared modal's other callers. (R8)
10. The top bar shows the active applicant's application number and working My Page control; no duplicate number/My Page card remains in the application body. Hide this applicant information in officer mode and clear it on returning home or when no application is active. (R9)
11. Steps remain below the top bar, keep their current/complete/waiting states and navigation rules, and use substantially less vertical space. At a normal desktop viewport, the PDF upper area appears without scrolling through repeated application/workspace headings. Narrow screens wrap controls without overlap. (R9)
12. Four circular markers sit on a connected horizontal line, with captions/names/statuses below and no stage card backgrounds. In step 2, identity verification visibly reads as completed, form writing is unmistakably current, and upload/final submission visibly read as upcoming. Text and state distinctions remain readable without relying only on color, at desktop and narrow widths. Preserve counts, accessible current state, navigation restrictions and compact overall height. Already-passed stages must not appear waiting after draft restoration. (R10)
13. The applicant header and main content share a deliberate horizontal alignment. The overview, stage track, sidebar and document actions use a consistent color/type/spacing system; primary save/continue actions are distinguishable from preview/reset/download. Form contents remain unchanged and the document remains near the top. Narrow layouts remain usable; applicant-only styling must not unintentionally redesign officer screens. (R11)
14. Even if the savings API supplies internal form 1/public form 2 before internal form 2/public form 1, the visible list is public forms 1, 2, 3, 4, 5 and the initial inline document is public form 1. Switching preserves existing values and internal IDs. The sidebar uses a simple list rather than rounded selected cards, avoids awkward mid-word wrapping and keeps selection/focus/status legible at narrow widths. Employment-package ordering is unchanged. (R12)
15. Draft status remains visibly stronger than empty status. The progress area matches the Save toolbar width, excluding sidebar/gap. Its line joins the four near-endpoint markers without a visible tail before marker 1 or after marker 4. Stacked screens retain the same area/marker relationship. Other stages, form order/counts, behavior, sizes and PDF contents remain unchanged. (R13)
16. With the approved rail bounds unchanged, marker 1 sits near its left end and marker 4 near its right end; marker 2 and 3 have equal center-to-center gaps. First/last captions remain inside the panel and do not overlap neighboring text, including narrow layouts. Completed connector styling follows the new marker locations. All other UI/state/ordering/PDF behavior is unchanged. (R14)
17. The application title uses the original base heading typography, with no remaining compact/mobile 16px override. Diagram rules, wording, form behavior and other text styles are unchanged. (R15)
18. Only stage 2/3 text alignment and savings title/header layout change: stage 2 text starts beneath its circle's left edge and stage 3 text ends beneath its circle's right edge on desktop, with safe readable narrow wrapping. The title wraps naturally in the left column while the progress area retains the same PDF-column width/bounds. No font/color/marker/rail/order/handler changes occur. (R16)

## Out of scope

- Redrawing PDFs, changing templates or coordinate maps, rewriting document wording, or changing the form-number mapping.
- Backend APIs, storage schemas, eligibility rules, new application routes, or persisting the selected individual form in the URL.
- Redesigning employment-package forms, identity verification, upload, or officer review. The user-requested shared applicant header/step presentation is included in the follow-up; document contents and business behavior remain unchanged.

## Planning status

Requirements are resolved. No blocking product questions remain. The user explicitly approved the final planning summary and implementation on 2026-11-13. Relevant technical evidence and implementation risks are recorded in `research/current-behavior.md` and `design.md`; actual validation is recorded in `verification.md`.
