# Verification record

## Scope and baseline

- Approved implementation: original PDF forms inline in double-savings step 2, direct form navigation, existing input/save/preview logic and form 5 signature popup preserved. The user then requested a compact header with application number/My Page in the shared top bar and steps below it; this follow-up is included.
- Baseline: no existing tracked source changes; this task's planning directory was untracked.
- Task manually activated after explicit user approval on 2026-11-13. Python is unavailable; `task.py start` was not executed. The current Codex session pointer was written using the existing `CODEX_THREAD_ID`; other sessions were preserved.

## Browser verification limitation

Browser access inventory reported `The browser access host is unavailable`. Native computer-use inspection of the existing demo Chrome window then stopped because the tool could not determine the current browser URL confidently enough to enforce policy. Computer use ended and its completion summary was recorded; no further UI automation was attempted.

Consequently, no actual browser result is claimed for PDF/overlay alignment, viewport responsiveness, interactions, keyboard focus, signature drawing/upload, saved-value restoration, save-failure behavior, or employment-package regression. These remain manual verification items from `implement.md`.

## Implemented files

- `App.tsx`: applicant-only visual shell, aligned header wrapper and portal host; existing mode/home/history behavior retained.
- `app-shell.css`: applicant-only light header, separate workspace palette, compact number/My Page controls, hidden/empty-host handling, truncation and wrapping; existing officer appearance retained.
- `PdfFormsWorkspace.tsx`: double-savings sidebar and inline edit/preview panel; shared original PDF body/field renderer; guarded save/navigation/reset/signature operations; original form 5 signature portal with independent keyboard, focus, and scroll lifecycle.
- `pdf-forms-workspace.css`: coordinated sidebar/panel surfaces, action hierarchy, responsive navigation, viewport-based PDF-pane height, and shared viewer fieldset sizing. The PDF canvas keeps a common coordinate scale and scrolls horizontally below its minimum readable display width.
- `ApplyFlow.tsx`: existing application number/My Page controls rendered into the top-bar host; compact title/step wrapper; savings-forms-only container modifier and application/program/submission-keyed workspace state.
- `apply-flow.css`: compact one-row desktop title/step strip, responsive states, and scoped wider savings workspace.

The stage-visibility refinement fixed current/completed precedence and restored-stage presentation. The connected-bar reference then replaced the stage boxes with a horizontal track, four circular nodes and stage captions/names below. Completed nodes use checks, current has a ring/dot, and upcoming nodes are pale. N단계 and status/count share the caption above the name. This structure remains in the final visual-polish pass described below, with preserved state/status derivation, numeric progress and actual navigation/gating.

## Coherent visual-polish follow-up

After the user rejected the incremental visual changes, the applicant interface received one coordinated style pass. It uses an applicant-only light 56px header with a 1160px aligned inner wrapper, dark text on a quiet neutral canvas, a blue current-stage accent, coordinated white 10px-corner sidebar/document surfaces, and an explicit primary Save action. Sidebar metadata/title rows replace duplicate numeric decoration; Preview/Download remain secondary and Reset is visually quiet. Readable stage typography is retained on the connected bar, with shared node-size/track-position variables.

Five product files change in this follow-up: `App.tsx`, `app-shell.css`, `apply-flow.css`, `PdfFormsWorkspace.tsx` (inline navigation/action markup only), and `pdf-forms-workspace.css`. `ApplyFlow.tsx` itself remains byte-identical. `--workspace-*` variables provide applicant styling without overriding `--brand` or original document tokens. The officer shell keeps its prior appearance through the default inner wrapper's `display: contents`. Portal visibility/cleanup and the download menu's stacking/right-edge anchoring are retained.

The implementation agent passed SHA-256 preservation comparisons for App's pre-render handlers, all of ApplyFlow, PDF helpers/field rendering/viewer content, job/modal/signature content after the inline shell, and the original PDF styling section. Lint, TypeScript/build and whitespace checks passed with existing warnings only.

The independent full-scope review checked the six cumulative frontend files and required no additional fixes. Source checks confirmed applicant-only palette scoping without redefining root/PDF tokens, unchanged officer navy styling, preserved hidden/empty-host behavior, matching 1160px alignment bounds, action selectors winning over later generic button styles (including disabled/focus), track/node positioning from shared variables, uncropped responsive captions, and preserved download header stacking/right-edge anchors. Fresh lint, TypeScript/build and `git diff --check` passed with only the existing StatusBadge and Vite chunk warnings. No blocking source findings remain. These are source/check results, not an observed visual-quality or interaction guarantee.

Browser inventory was retried for this visual-polish round and still reported `The browser access host is unavailable`. No native browser action was attempted. This pass has not been observed in a live browser; neither aesthetics nor pixel layout/interaction correctness is claimed as visually verified.

## Public-order and plain-sidebar correction

The user's next screenshot shows public form 2 ahead of form 1. Savings loading now derives one internal-ID sequence by sorting the loaded layouts' `public_form` numbers, using stable incoming order for absent/unknown public metadata after known forms. That same sequence supplies both `formNos` and the initial active document. The employment package retains its response order. Internal keys and the swapped public1/internal2 mapping remain unchanged.

Only `PdfFormsWorkspace.tsx` loading/sidebar markup and `pdf-forms-workspace.css` sidebar styling change in this correction. The sidebar is now a flat contents list with row separators and a quiet selected edge/text, without the rounded selected fill or trailing cue. Titles use normal weight with stronger selected text and keep-all wrapping plus overflow fallback. The draft status is shortened to '작성 중' only in the sidebar; full remaining-field feedback stays in the panel. Narrow navigation remains horizontal with separators/bottom selection.

The implementation agent's one-off source-extracted assertions use the actual swapped form-coordinate fixtures: a response starting with internal1/public2 still displays public1–5 and initially selects internal2/public1. Read-only preview, employment-package response order, stable unknown-metadata placement, unchanged input arrays and empty lists were checked as well. No persistent test file was added.

The final independent check required no additional fixes. It confirmed that one public-metadata-ordered sequence feeds both list and first selection, internal IDs remain intact, the mapped input array is sorted without mutating the response, safe numeric parsing and stable fallback are used, and employment ordering is unchanged. Flat desktop/narrow selection selectors, inset focus and sidebar-only short status preserve the existing panel feedback. Renderer/save/paper/signature handlers are untouched by this round. Fresh lint, TypeScript/build and whitespace checks passed, with the same existing StatusBadge/Vite warnings. Browser rendering/interactions remain unverified.

## Status distinction and centered progress track

Only `apply-flow.css` and `pdf-forms-workspace.css` change in this follow-up. Draft sidebar status now uses the application accent at weight 600; empty status uses neutral `#606e82` at weight 400. No badge, wording, state or count logic changes.

The overview becomes a one-column/two-row grid with a 2px gap and compact 16px title. The progress track uses `width: 100%` and symmetric auto margins, independently of title width. The user's final width request removes the former 700px maximum so the diagram spans the available form-workspace width, with four equal stages. Old medium-screen flex-basis/max-width/left-margin overrides remain removed. Node geometry, marker/text sizes, height, connected line, mobile wrapping and flat sidebar are unchanged. All JSX/behavior/order/PDF files remain unchanged in these CSS-only refinements.

Independent review confirmed source-level symmetry and no stale responsive override, absolute positioning, title overlap or status-selector suppression. It adjusted empty text from the initial `#6e7c90` to `#606e82`: calculated contrast on canvas/hover improves from 3.95/3.75 to 4.83/4.58, preserving neutral weight 400 versus accent draft weight 600. Fresh lint, TypeScript/build and whitespace checks passed with the same existing warnings. No persistent tests were added for this reversible CSS change. Browser rendering/interactions remain unverified.

For the final one-line width-limit removal, implementation lint/build/diff checks passed. Independent source review confirmed that no progress-track width cap or responsive width override remains, the full-width overview grid supplies available content width, and four-stage/node/mobile geometry is unchanged. `git diff --check` passed; no additional edits or repeated build were needed. Browser rendering remains unverified.

## Corrected width reference: PDF panel only

The user clarified that the reference area is the right-hand PDF panel. The previous full-workspace width included the sidebar and was the wrong interpretation; it is superseded by this correction.

Only `apply-flow.css` and `pdf-forms-workspace.css` change. `.flow.flow--forms` defines shared `--forms-sidebar-width` / `--forms-workspace-gap` variables (244/20px desktop; 218/16px through 1000px). Both workspace grid columns/gap and form-stage diagram width/offset use those values. The diagram is right-aligned with width equal to content minus sidebar/gap. At 800px and below, the grid stacks and the diagram becomes 100% wide, keeping the row gap. Other stages and all JSX, state, order, marker/text dimensions, height and PDF behavior are unchanged.

Implementation source geometry checks passed: 1160px content gives 896px panel/diagram with 264px offset; medium 868px content gives 634px with 234px offset; stacked 748px content gives both widths 748px with 16px gap retained. These are source calculations, not browser pixel measurements. Lint, TypeScript/build and diff checks passed with existing warnings.

Independent review found no further fixes: shared inherited variables resolve across stylesheets, desktop/medium/stacked breakpoints match, no stale width/offset rules exist, and other stages are unaffected. At the narrowest side-by-side boundary (801px viewport), content 769px yields panel/diagram 535px and four 133.75px stage areas. `git diff --check` passed; no repeated build/tests were needed without further source edits. Browser rendering remains unverified.

## Actual rail length, not only container width

The user's next clarification requests the line itself to span the Save toolbar. The existing marker-to-marker connectors cover only 75% because four inset marker centers range from 12.5% to 87.5%. Only `apply-flow.css` changes in this final correction: the aligned form-stage list becomes positioned and receives a full-width `::before` base rail with left/right zero, the existing shared vertical midpoint, 1px height, z-index 0 and `pointer-events: none`. Existing marker positions, completed connector overlays, z-index-1 buttons, labels, dimensions and shared panel-width breakpoints remain intact. All JSX/behavior/PDF code is unchanged.

Implementation lint, TypeScript/build and diff checks passed with existing warnings. Independent review confirmed that left/right zero spans the entire panel-aligned area at all shared breakpoints, the absolute rail does not affect flex sizing, completed segments paint above the base rail and buttons/nodes paint above both. Midpoint alignment and pointer/focus handling are preserved. `git diff --check` passed with no fixes or redundant rebuild. No new files or persistent tests were added, and no browser render/interaction result is claimed.

## Approved rail preserved; markers moved toward endpoints

The user approves the line length and supplies annotated marker positions. Only form-stage child layout in `apply-flow.css` changes: a four-column grid uses narrower endpoint caption areas and equal middle areas, with 16px safe edge inset (12px on narrow screens). First/last button content and captions align inward; middle content stays centered. The first completed connector's left/width is updated to meet the relocated second marker; middle connector lengths follow the equal middle areas. Approved area width, shared sidebar/gap values and full-width base-rail rules remain byte-identical. JSX, statuses, colors, node dimensions, PDF and all behavior remain unchanged.

Source geometry assertions passed: at W896, centers are 26/307.333/588.667/870 with equal 281.333 gaps; at W535 they are 26/187/348/509 with 161 gaps; at W288 they are 22/103.333/184.667/266 with 81.333 gaps. Caption regions are inside the panel, wrapping rather than overlapping. Implementation lint/build/diff checks passed with existing warnings.

Independent source review required no fixes: endpoint column A=W/6+2P/3 equals P+G/2, middle columns each have width G, and all connectors meet the repositioned circles. Scoped endpoint padding overrides generic mobile padding, preserving the narrow inset and captions. Rail, pointer/focus stacking and other stages are unchanged. `git diff --check` passed; no redundant build/new persistent tests were needed. Browser rendering and interactions remain unverified.

## Tail removal at endpoint circles

The user requests removal of short line tails outside circles 1/4. Only the form-stage base rail's `left` and `right` in `apply-flow.css` change from zero to `var(--stage-edge-center)`. This uses P26px desktop/P22px narrow, covering the same first-center-to-last-center interval as the existing completed connectors. Opaque nodes cover the rail ends. Marker/grid/outer-area geometry, captions, height, vertical midpoint, state and all JSX/PDF behavior remain unchanged.

Implementation lint/build/diff checks passed with existing warnings, without new files/tests or UI automation. Independent review confirmed the base rail spans exactly P to W-P at every breakpoint, matching existing connectors and generating no final outgoing connector. Marker positions, outer panel alignment and click/focus rules remain unchanged; variable declaration order resolves correctly. `git diff --check` passed with no fixes or redundant rebuild. Browser rendering remains unverified.

## Original application-title typography restored

The user requested the heading text style restored. Only two rules were deleted from `apply-flow.css`: the full compact h1 override and its narrow-screen 16px override. The unchanged base `.flow__head h1` supplies 22px size, original tracking/margin and inherited original color/line-height/bold. Heading text, JSX, diagram rules and all other typography remain untouched. Implementation lint/build/diff checks passed with existing warnings. Independent review confirmed the remaining title rule is byte-equivalent to HEAD, no compact/mobile override remains, title JSX is unchanged, and progress typography is preserved. `git diff --check` passed with no fixes or redundant rebuild. No new tests/files were added; browser rendering remains unverified.

## Targeted stage-copy alignment and title spacing

Only savings form-stage CSS in `apply-flow.css` changes. Stage 2 copy uses left alignment at its circle's left edge; stage 3 copy mirrors right alignment at its circle's right edge. Copy width is half the button content plus node radius, aligned to the corresponding side; caption justification matches. Narrow screens use full local-cell copy width while preserving text direction/readability. Node/button positioning, rail rules, fonts/colors, statuses and all JSX remain untouched.

The savings overview uses the same sidebar-width/gap columns as the document workspace. The unchanged title balance-wraps naturally in the left column using only `text-wrap: balance` and `word-break: keep-all`, retaining original 22px typography. Progress fills the right column at 100% rather than subtracting the sidebar again. Horizontal bounds are unchanged: 1160px content gives left264/width896, medium868 gives left234/width634, and stacked748 gives left0/width748. The overview stacks at 800px. No global spacing or other component styles were changed.

Implementation lint/build/diff checks passed with existing warnings. Independent review confirmed exact copy-edge anchoring, safe responsive fallback precedence, unchanged marker/rail/focus styles, equivalent PDF-column bounds and preserved title typography. `git diff --check` passed without fixes or redundant rebuild. No new tests/files were added; no browser render or actual line-break observation is claimed.

Savings step 2 no longer stacks a workspace title/subtitle and default save-guidance row above the selected document. Downloads are placed with panel actions, remain available for paper/read-only modes and while loading, and use a positioned header stacking context to stay above PDF controls. Current/completed/waiting step labels and navigation rules are preserved.

The final connected bar has a 68px desktop minimum height and retains a compact surrounding header. No browser pixel measurement or PDF-start position is claimed. The actual PDF coordinates/content and existing scrolling interaction are unchanged.

PDF templates, coordinate maps, internal/public form mapping, backend APIs, storage schemas, and eligibility rules were not changed.

## Automated checks and review

Implementation and independent full-scope Trellis review completed on 2026-11-13. The implement and check agents each ran the configured checks; the final check followed the review fixes.

| Check | Result |
| --- | --- |
| `npm.cmd run lint` in `demo/frontend` | Passed; unchanged StatusBadge fast-refresh warning remains |
| `npm.cmd run build` in `demo/frontend` | Passed, including `tsc -b`; existing Vite chunk-size advisory remains |
| `git diff --check` | Passed |
| Source comparison against HEAD | Implement agent's Node assertions passed for the shared PDF body (allowing indentation and page-button aria labels) and `renderField` (allowing signature-trigger focus capture) |
| Stage presentation/source checks | 15 focused presentation assertions plus one exact navigation/gating-handler preservation assertion passed in the implementation agent's one-off source checks; no persistent test files added |
| Connected-bar source preservation | Implement agent's SHA-256 comparisons confirmed submitted/current derivation, `stepStatus`, navigation handler, and per-step completion/current/canNavigate/status expressions remain byte-for-byte identical to the preceding reviewed refinement |
| Browser interaction/visual checks | Not run; limitation above |

The independent reviewer checked the original implementation and then all six product files for the compact-header follow-up against the updated artifacts and specs. The latest lint/build/diff checks followed the follow-up fixes. Findings fixed:

- Closing the signature dialog during a pending upload/delete tried to focus a disabled PDF trigger. Focus return is now deferred until saving finishes.
- The legacy fixed-940px comment contradicted the wider savings shell; it was corrected.
- Moved download links could clip at narrow widths or sit under high-z-index PDF controls. Links now anchor to the panel header's right edge, and the positioned header creates a stacking context above the controls.
- The paper-mode subheading is now h3 under the panel's h2, matching the compact heading hierarchy.

Code review confirmed applicant-only header visibility, portal cleanup on program selection/home, existing My Page state/handler ownership, unchanged stage navigation conditions, and downloads in loading/paper/read-only states. No blocking source findings remained.

The earlier stage-visibility independent check additionally reviewed current/completed overlap, passed-upload restoration with zero reported counts, known-complete future upload, draft/submitted My Page, explicit non-color statuses, narrow-screen wrapping and focus styling. No source fixes were required in that round. Lint, build/type-check and whitespace checks passed with the same existing warnings.

The final connected-bar independent review checked equal-width marker spacing, center-to-center track segments, no outer tails, marker/track stacking, pointer-event pass-through, focus styling, status text and preserved state/navigation logic. It fixed narrow-screen caption spacing by reserving two 13px caption lines at widths up to 580px, keeping stage names aligned when a current count wraps. Desktop minimum height remains 64px and the mobile track remains continuous. Fresh lint, TypeScript/build and `git diff --check` all passed, with the same existing warnings. No blocking source findings remain. Browser visual/interaction checks remain unavailable.

Other implementation checks addressed asynchronous reset/scan races, disabled outgoing editing during pending saves, stale session completions, and preservation of the employment-package modal through shared rendering. These are code-review conclusions, not claims of executed browser scenarios.

## Spec review

Added `.trellis/spec/frontend/pdf-form-workspace.md` and its index entry to capture original document scaling/reuse, public versus internal numbering, consent flushing before selection, save-failure behavior, the independent form 5 signature dialog lifecycle, and compact workspace chrome. Updated `state-management.md` with top-bar portal ownership and applicant/officer visibility/cleanup rules. No cross-layer API or schema contract changed.

## Release status

Implementation and static verification are complete. No commit, push, deployment, or task archive has been performed. A separate user confirmation is required for the concrete file list in `commit-plan.md` under `.trellis/workflow.md` Phase 3.4. Manual browser verification remains outstanding as documented above. After a confirmed work commit, the user may run `/trellis:finish-work` for archive/journal bookkeeping.
