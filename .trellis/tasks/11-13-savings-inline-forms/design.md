# Technical design

## Boundaries and reuse

Limit the new inline shell to the double-savings branch of `PdfFormsWorkspace`. Continue using the same PDF image endpoints, layout fields/masks, `renderField`, missing-field calculation, page-size scaling, and controlled values supplied by `ApplyFlow`. Factor the existing viewer body and necessary actions for reuse by the savings inline panel and the employment-package modal; do not maintain a copied field renderer.

Expected product files:

- `demo/frontend/src/forms/PdfFormsWorkspace.tsx`: selected-form navigation, shared viewer content, inline shell, save transitions, signature-dialog lifecycle.
- `demo/frontend/src/forms/pdf-forms-workspace.css`: sidebar, selected/completed states, document panel and responsive arrangement.
- `demo/frontend/src/pages/applicant/ApplyFlow.tsx` and `apply-flow.css`: a savings-forms-specific width modifier if needed. Do not widen other stages or the employment-package flow implicitly.

No backend, PDF asset, field-map, or shared `Modal` behavioral changes are planned.

## Layout

- Desktop: a compact sidebar (approximately 240px) plus the existing PDF canvas (up to its current 794px display width), with a modest gap and a bounded wider application container.
- Sidebar entries use the API's existing public order/labels and current completion state. Reuse `layout.public_form`; never sort internal `formNo` lexically because forms 1 and 2 are swapped internally.
- The main panel has a title/status header, preview/edit/reset/save actions, page controls, the original PDF canvas, and existing date helpers where applicable.
- Replace savings-only “save and close” behavior with saving inside the panel. Keep preview/edit transitions in the same panel. Keep the workspace continuation action and bulk downloads accessible.
- Narrow layouts move navigation above the document. All sizing must keep the same scale for the background, masks, input positions, and page height. Derive available width from the actual viewer container using the existing `ResizeObserver`; allow document scrolling where needed without shifting field coordinates.
- Loading and failed-load states must be visible; never show an editable canvas without its layout.

## Selection and save transitions

1. Once the forms/layout request succeeds, initialize the savings selection to the first available public form. Do not reset an existing valid selection on incidental rerenders or callback identity changes. Reset selection for a different application/program.
2. Selecting another form sets a pending transition, flushes current values with the existing `onFlush`, then updates the active form, resets its page to zero, clears signature state, and resets the document scroll position.
3. While a transition is saving, prevent conflicting navigation/preview/reset actions. Ignore stale async completions after unmount or application/program changes.
4. If flushing fails, retain the previous active form and controlled values, clear the pending transition, and display the error inside the workspace. Missing required fields do not block navigation.
5. Preview continues to flush before requesting the server-rendered written page and refreshes its cache key. Keep form values in `ApplyFlow`; changing the inline viewer must not recreate or clear them.
6. Preserve existing read-only behavior and continuation checks. A paper-mode form shows its existing download/submission guidance in the panel instead of an editable PDF overlay.

Do not change serialized form/consent keys, signature upload endpoints, `saveQueue`, or eligibility logic. The modal's old close-time flush is the specific lifecycle dependency being replaced.

## Signature dialog lifecycle

The form 5 `createPortal` dialog remains. Removing the outer form viewer modal also removes its Escape handler and body-scroll lock, so the signature dialog must own those effects while open, restore body overflow on cleanup, and restore focus to its trigger. Keep keyboard focus inside the open dialog. Clicking its backdrop/close or pressing Escape closes only the signature dialog. Keep all current signature drawing/upload state and validation behavior.

## Compatibility and rollback

The shared component also serves the employment package. Keep its form list/modal behavior and per-form signatures operational through the shared viewer content. The savings branch must preserve form 5 paper mode and the backend's read-only protection.

Rollback consists of reverting the savings shell/navigation and its scoped CSS/container changes; no schema or asset migration is involved.

## Risks and deferred items

- Highest risks: internal/public number confusion, lost consent flushing, stale async navigation, signature keyboard/scroll effects previously supplied by the modal, and PDF/overlay scaling mismatches.
- Very small screens contain a dense original PDF. Preserve document fidelity and reachable controls; do not redesign the PDF to simplify its contents.
- There is no configured browser test suite in `package.json`. Use existing project checks plus focused browser verification; add only targeted behavior coverage if necessary during implementation.
- Current shell has no usable Python interpreter (`python` is missing; `py --version` reports no installed Python). Planning metadata was created manually, matching existing task precedent. Before activation, use an available configured interpreter if found; otherwise record manual lifecycle handling without claiming `task.py start` succeeded.

## User-directed follow-up: compact application header

The user reviewed the result and explicitly requested implementation of a more compact top area, moving application number/My Page to the shared bar and retaining steps below it. This is a refinement of the active task, not approval to commit.

- Additional boundary: `App.tsx` and `app-shell.css` own the shared navigation bar. Add an applicant-only host for application controls and pass the host to `ApplyFlow`, which may render its existing number/My Page controls there with a React portal. Keep application state and the existing My Page handler in `ApplyFlow`; do not duplicate state via window events, document queries, or a second application store.
- The host is hidden in officer mode. Unmounting/returning to program selection removes portal content automatically. Keep applicant/officer mounting, navigation history and home behavior unchanged.
- Present the application title and step navigation as a compact strip under the bar where practical. Reduce circle sizes, status rows, vertical padding and connecting decorations; retain accessible current-step state, progress and navigation behavior. Keep smaller-screen wrapping usable.
- Savings step 2 should not stack application title/subtitle, workspace title/subtitle, panel title/status and a reserved save-status row before showing the PDF. Retain a clear accessible main heading; place downloads with the relevant panel controls, shorten surrounding padding and show save notices only when meaningful. Do not alter the actual PDF, renderer, toolbar navigation, save logic, or signature dialog.
- Prefer plain inline labels and simple borders consistent with the existing service, without adding cards, gradients, large badges, or promotional wording.
- Verify top-bar content cleanup/mode visibility and unchanged handlers through code review, then run frontend lint/build. Report browser verification limitations accurately.

## User-directed follow-up: step visibility

The user supplied a connected-bar reference after reviewing the stage boxes. The final presentation is a single horizontal track with four circular markers and captions/names/statuses below. Completed markers contain checks, the current marker has a clear brand-colored ring/dot and emphasized name, and upcoming markers are pale neutral circles. Remove per-stage card borders/backgrounds. Use restrained line contrast and readable text, and retain a compact desktop height (approximately 60–72px rather than the original tall circles/large gaps). Keep the bar continuous at narrow widths, allowing labels/captions to wrap rather than overlapping. Ignore the example's unrelated labels and annotation dot/oversized counter.

Limit this refinement to step markup in `ApplyFlow.tsx` and styles in `apply-flow.css`. Keep top-bar relocation, state derivation, counts and navigation/gating intact. Current treatment must win even when also complete; passed stages remain complete after restoration before child counts load. No PDF renderer, save, portal, API or routing changes are needed.

## User-directed follow-up: coherent visual polish

The user finds the incremental styling insufficient and explicitly requests a substantial visual polish. The implementation boundary returns to the six existing frontend files, covering the applicant shell, overview/stepper and savings workspace chrome as one composition. This supersedes the earlier two-file-only presentation limit; business behavior and PDF content remain out of scope.

- Direction: a clean light applicant header, dark ink/navy typography, one restrained blue accent, a quiet neutral work surface and white document/navigation surfaces. Keep the application frame crisp and useful; no gradients, oversized circles, decorative cards, fake avatars, promotional text or new information sections.
- Align the applicant top-bar inner content with the bounded main workspace. Keep number/My Page in the bar and existing mode/home/history handlers. Scope applicant visual changes so officer mode retains its existing appearance and applicant controls remain hidden there.
- Use a readable type hierarchy and a deliberate spacing scale across the compact title, continuous four-node stage track, sidebar and panel. Keep the connected-bar reference and original stage-state/navigation derivation. A slightly stronger current node/label is preferable to tiny low-contrast captions.
- Make the sidebar and document panel feel like one workbench: consistent subtle borders/corners, restrained selection state, readable form titles/statuses, and clear primary versus secondary document actions. Keep downloads available in all current modes and retain its positioning/stacking fixes.
- Keep document coordinates, background/overlay scaling, masks, field renderer, saving, paper mode and signature dialog unchanged. Do not modify global form typography/color tokens or add dependencies/web fonts.
- Preserve the compact vertical budget. Improve spacing through alignment and hierarchy, not a new hero/header or large padding above the PDF. Retain sensible responsive wrapping and viewport-based document height.
- Current browser inventory was rechecked and still reports the browser access host unavailable. Do not claim an observed visual result; use source/layout review and existing automated checks, and record this verification limit accurately.

## User-directed correction: public form order and plain sidebar

The user's latest screenshot shows public form 2 first. The current loading effect relies on `availableForms` response order for both `formNos` and the initial selection. Although the repository backend sorts public numbers, the UI must not rely on that response order. Sort savings layouts by `public_form` (the same metadata used in `formLabel`), then use one ordered ID array for the list and initial active form. Do not sort internal IDs or duplicate the form1/form2 mapping; keep the employment package's response order unchanged. Unknown/missing public metadata should have a deterministic stable fallback after known public forms.

Limit product edits to `PdfFormsWorkspace.tsx` and `pdf-forms-workspace.css`. Remove the sidebar's selected rounded/color-filled card and trailing cue. Use a flat contents list with thin separators, a restrained selected edge/text treatment, lighter title weight, and natural word wrapping. A sidebar-only short status such as '작성 중' can replace the long remaining-field sentence while the panel retains full remaining-field feedback. Keep form selection, state, completion progress, save/preview/reset/paper/read-only/signature behavior intact. Adapt the flat selection treatment to the existing narrow horizontal navigation without clipping.

## User-directed refinement: status distinction and centered track

Limit this correction to `pdf-forms-workspace.css` status selectors and `apply-flow.css` overview/track layout. Draft and empty status currently use similar muted shades; give draft a readable accent and weight 600, retaining neutral regular-weight empty text. Do not add badge backgrounds or change status derivation/copy.

The latest clarification corrects the width reference: in savings forms, the progress area must align to the right-hand PDF panel, excluding the sidebar and gap. Keep the title in its own compact row. Share sidebar-width/column-gap CSS variables between `.flow--forms` progress positioning and `.pdf-forms__workspace` columns so there is one geometry source for desktop (currently 244px/20px) and medium widths (218px/16px). Scope the diagram's width/offset to savings form stage; keep other stages unchanged. When the workspace stacks at 800px, reset the progress area to the same full width as the document panel. Preserve all four equal steps, no overflow, existing node/text/height/status/handler/PDF behavior. Avoid guessed fixed offsets duplicated across files, DOM measurement or absolute positioning.

The user further specifies the visible rail itself must span the Save toolbar's width. Existing four equal cells place markers at 12.5/37.5/62.5/87.5 percent; their three connectors therefore cover only 75 percent even with a correctly aligned container. Add a form-stage-only full-width base rail behind the existing markers/connectors, sharing their vertical midpoint variables and using non-interactive pointer handling. Keep markers/captions inset to avoid edge clipping and preserve existing completed connector colors. No marker relocation, JSX changes or additional layout measurement is needed.

## Approved rail length; endpoint marker redistribution

The user approves the current line length and now requests marker relocation only. Scope new CSS to savings form-stage children in `apply-flow.css`; preserve the area's shared panel-width calculation and the full-width base rail's bounds/midpoint. Place endpoint circles near the ends (small safe inset) and divide their center-to-center span into three equal gaps. Keep edge captions inward-aligned and in non-overlapping areas, with normal wrapping at narrow widths. Completion connector segments must meet the repositioned circles, not retain the old quarter-cell endpoints.

A CSS grid with narrower endpoint caption areas and two equal middle areas can provide exact geometry without JSX or absolute marker placement. For panel width W, node size S and safe edge inset I, endpoint centers are P=I+S/2 and W-P, and gap G=(W-2P)/3. Endpoint area width A=P+G/2; middle areas each have width G. Align endpoint button contents left/right with inset I and middle contents centrally. The first connector spans G, with width expressible as 2A-2P; middle connectors each span their G-width area. Reuse existing node variables. An equivalent simple CSS solution is acceptable if it keeps equal spacing and safe labels. Other stages and all state/handlers/PDF markup remain unchanged.

## Final tail removal

The user requests removal of the short line beyond marker 1/4 and allows preserving the current marker positions. Keep all approved area width/grid/marker/caption geometry. Trim only the base rail's `left` and `right` from zero to the existing `--stage-edge-center` P, so it runs from first center P to last center W-P under opaque circles. Existing connector segments already span exactly that interval and remain unchanged. This final request supersedes the earlier edge-to-edge base-line rule only for those unwanted tails. One CSS-selector edit is sufficient; responsive insets are inherited automatically.

## Heading typography restoration

The user requests the application title's original text styling. Remove the desktop compact h1 override and its narrow-screen 16px override from `apply-flow.css`. Reuse the unchanged base `.flow__head h1` style instead of duplicating it. All progress geometry, text content, state and PDF styles remain unchanged.

## Targeted text alignment and title wrapping

The user explicitly limits the refinement to stage 2 left-aligned copy, stage 3 right-aligned copy, and title line wrapping/header spacing. Keep circle positions/rail/dimensions and all other elements unchanged. Scope CSS to savings forms in `apply-flow.css` only; no JSX or wording changes.

Align only the middle `.flow__stage-copy` blocks, not their buttons/nodes: a half-content-width-plus-node-radius copy block aligned toward the appropriate side anchors stage 2's left edge and stage 3's right edge to their circle edges. Set caption flex justification accordingly. Allow a narrow-screen local-cell fallback if necessary to preserve counts/readability; do not move nodes or shrink text.

Use the existing sidebar-width/gap variables for a two-column savings overview: title in the left column, progress in the right PDF-width column. Change the progress element to width 100% of that right column to avoid double-subtracting the sidebar; its actual horizontal bounds remain identical. Balance-wrap the unchanged h1 within the left column using CSS (`text-wrap: balance`, natural word breaks), retaining original 22px typography. At the existing 800px stacked breakpoint, overview returns to one column. Do not add manual title strings, other styling changes or global spacing changes.
