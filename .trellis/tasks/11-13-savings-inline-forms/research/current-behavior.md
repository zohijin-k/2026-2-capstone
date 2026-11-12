# Current implementation evidence

Inspected on 2026-11-13. This task is planning only; no product source was changed.

## Rendering and navigation

- `demo/frontend/src/forms/PdfFormsWorkspace.tsx:176`: `active` currently starts null and only becomes a form when a list action is clicked.
- `:190`: form availability and field layouts load from existing API calls, together with paper-mode configuration.
- `:241`: the `ResizeObserver` measures `scrollRef`; `:251` derives current layout/page dimensions and a shared scale.
- `:700`: public labels come from `layout.public_form` and the original title.
- `:711`: root form-list UI; `:775`: modal wrapper; `:795`: scroll viewport and original PDF background; the following overlay contains masks, missing groups and `renderField` controls.
- `:840`: internal form 1 has transfer-in/employment date helpers after the PDF.
- `demo/form_numbers.py:10`: internal form 2 is public form 1 (self-check); internal form 1 is public form 2 (participation application). Do not change this mapping or the API's order.

## Saving and state

- `PdfFormsWorkspace.tsx:496`: preview calls `onFlush` before showing the rendered written page.
- `:512`: `saveAndClose` flushes values, refreshes thumbnails, and clears the active form/signature target. An inline viewer cannot rely on this close operation for persistence.
- `:523`: continue delegates to existing form-completion/parent validation.
- `demo/frontend/src/pages/applicant/ApplyFlow.tsx:255`: field patches use a parent-owned save queue.
- `:391`, `:482`, `:484`: form 1, self-check, and form 5 changes patch their existing payloads. `:483` only updates consent React state; the `onFlush` callback at `:486` posts selected consents and signature data. Form switching must preserve this flush path.
- `:261`: continuation checks eligibility and required consent/signature choices before proceeding. Keep these rules unchanged.

## Signatures and paper mode

- `PdfFormsWorkspace.tsx:217`: `changePaperMode` handles online/paper confirmations, stored doc context, and scan cleanup.
- `:423`–`:466`: signature mode switching and JPG/PNG upload/delete helpers; upload size limit is 10MB.
- `:858`: form 5 has a separate `createPortal` dialog with drawing/file tabs, clear and confirm buttons.
- `demo/frontend/src/components/Modal.tsx:28`: the parent modal currently supplies Escape handling and body-scroll locking. The standalone signature portal has no equivalent effect in the current component. Removing the parent requires replacing those lifecycle effects for form 5.

## Shared scope and layout

- `PdfFormsWorkspace.tsx:170`: the same component serves the employment package using `program.has_subsidy_items`.
- `demo/frontend/src/pages/applicant/ApplyFlow.tsx:395`: only the upload stage currently receives the fluid container class.
- `apply-flow.css:3`: the default application width is 940px; its comment describes a previous fixed-layout constraint. A sidebar needs a scoped container adjustment, while the PDF coordinates still use proportional scaling.
- `pdf-forms-workspace.css:86`: viewer sizing depends on `.modal--viewer`; inline sizing needs an explicit scoped replacement.

## Guidelines and verification environment

- Read `.trellis/spec/frontend/index.md`, component, state-management, and quality guidelines, and the code-reuse thinking guide. Most component/quality sections are placeholders; use observed code conventions rather than inventing requirements.
- State-management guidance prohibits applicant data/IDs in URLs. Individual form selection can stay local; no new routing/storage contract is required.
- `demo/frontend/package.json`: configured checks are `lint` (oxlint) and `build` (`tsc -b && vite build`); dependencies are present locally. Browser verification remains necessary for PDF alignment and signature interaction.
- Python task scripts could not run: `python` is not on PATH, and `py --version` reports no installed Python. Existing tasks such as `11-13-identity-signature-ui/task.json` document the same manual metadata approach.
- Working tree was clean at the planning baseline. No implementation/build/browser tests were run during planning.

## Follow-up evidence: excessive header height

The user supplied a screenshot of the initial result and requested a compact top area. `App.tsx` owns the global `.shell` navigation bar and deliberately keeps applicant/officer surfaces mounted while toggling their visibility. `ApplyFlow.tsx` owns `appNo`, current stage, and the My Page handler. Before this refinement it renders a separate application title/subtitle and number/My Page card above the four-step progress indicator.

The original `.flow` starts with 28px top padding. `.flow__head` has a 20px bottom margin; `.flow__stages` has 30px vertical padding, a 69px minimum button height, and a 28px bottom margin. Savings forms then add a workspace heading/subtitle and panel heading/save-status strip before the PDF. This repeated vertical chrome explains the supplied screenshot without needing to change PDF contents.

The change boundary now includes `demo/frontend/src/App.tsx` and `app-shell.css`. Preserve the intentional mounted-but-hidden surfaces: an applicant portal host in the shared bar must be hidden in officer mode, and its content must disappear on home/program selection. Do not lift application data into a duplicate store just to relocate controls. The user has requested this refinement directly; it does not authorize a commit.

## Follow-up evidence: stage contrast and restoration

The user's next screenshot shows the compact stepper's 10–12px labels and fine bottom rules as insufficiently visible. The requested refinement is stronger current/passed/upcoming hierarchy while retaining the reduced header footprint.

`ApplyFlow` derives the current index from the stage (or `stageBeforeMypage` for a draft My Page visit). Its earlier upload display special-cased `uploadComplete` before considering whether the upload stage had already been passed; restored final-stage applications can temporarily have zero child-reported upload progress. Stage presentation must therefore recognize already-passed stages independently of fresh child progress reports. This does not authorize changing upload completion, validation, or navigation conditions. A current step can also be complete (for example, completed upload or final submission), so current visual treatment and `aria-current` must remain consistent in that overlap.

## Latest reference: connected track

The latest user image replaces the separated stage boxes with a single horizontal track, circular nodes and small stage captions above stronger stage names. The image's unrelated labels, annotation dot and oversized black counter are not application requirements. Adapt this visual structure to the existing four steps, with completed checks, a brand-colored current ring/dot, pale future nodes and existing status/count text. Preserve the last refinement's state/status derivation and navigation handler exactly; this round changes markup and styles only. Keep the track connected at narrow widths while allowing text to wrap.

## Latest review: coherent visual system

The user rejects the visual quality after the connected-bar iteration and asks for a more polished contemporary UI. Current code combines a full-width dark top bar with a separately bounded workspace, very small context/status typography, small square outer panels, and near-identical document actions. This latest pass addresses their composition together rather than changing the stage shape again. Keep the connected track and all existing behavior, and scope visual changes to the applicant interface.

The CUA inventory was rechecked for this pass: no browser connection is available (`The browser access host is unavailable`). No native browser action was attempted; computer-use completion was recorded. The implementation can be checked through source/layout review, lint and build, but no observed browser render or interaction result can be asserted.

## Sidebar correction evidence

The user's latest screenshot visibly lists public form 2 before public form 1. `PdfFormsWorkspace` currently sets `formNos` from `availableForms.map(form_no)` and initializes `active` from `availableForms[0]`; neither step enforces the public-label order. The repository backend's `available_forms` already calls `order_form_numbers`, but that does not establish the actual runtime response order shown in the screenshot. Enforce the display invariant in the savings frontend using loaded layout `public_form`, which also supplies visible labels. The fixture mapping is internal1/public2 and internal2/public1; do not change it. Use the same sorted ID sequence for rendering and initial selection, with employment-package ordering left intact.

The screenshot also shows a filled rounded selected row, a trailing chevron, long small status copy and a mid-word break in the participation title. The authorized UI correction is a plain contents list: subtle row separators/selected edge, no card/chevron, lighter titles with natural wrapping, and a short sidebar-only draft status. The full missing-field message remains in the document panel.

## Status contrast and progress centering

The next user screenshot shows draft/empty status in nearly identical muted colors. Distinguish the existing state classes through text color/weight only. The current overview's title and track share a flex row, with an auto left margin on the track; consequently the track is centered in leftover space rather than the full content. A compact title row plus a full-width/capped track row with symmetric margins resolves the actual layout cause. Remove obsolete medium-width flex/left-margin overrides so the same centering applies there.

## Width reference clarification

The user clarified that the target width is the right-hand PDF panel, not the entire sidebar-plus-document workspace. The earlier full-width implementation used the wrong reference area. Align savings-stage progress by sharing the form grid's sidebar width and column gap, subtracting them from the full content width and aligning right. At the stacked breakpoint, both diagram and document use full width. This geometry must be shared rather than inferred from a screenshot or duplicated pixel offsets.

The next clarification distinguishes the visible line from its container. With four equal cells, marker centers lie at 12.5%, 37.5%, 62.5% and 87.5%, so the original connectors alone span only 75% of an otherwise correctly aligned panel-width container. A form-stage full-width base rail reaches both toolbar edges while retaining inset markers/captions and completed connector overlays. Checking container width alone does not verify the requested visible rail length.

The user approves the full rail length, then annotates marker relocation near the endpoints. The current four equal caption cells still leave endpoint markers deeply inset. Redistribute marker centers, not rail width: keep a small safe endpoint inset and divide the remaining center span into three equal gaps. Use narrower endpoint caption areas and equal middle areas, align endpoint text inward, and update completed connector lengths to meet the new centers. The blue handwriting is not intended as UI content.

The user then requests removal of the small line tails outside marker 1/4, allowing existing circle positions to stay. The full-width base pseudo-element is the cause: its left/right zero extend beyond the endpoint circles. Set both bounds to the existing endpoint-center variable P; the base and completed connectors then cover the same center-to-center interval, with opaque circles hiding their ends. Preserve the approved overall area and grid geometry rather than moving markers again.

The latest request targets text only: stage 2 left, stage 3 right, and a balanced title break/spacing without restyling other elements. Align copy blocks rather than buttons to preserve marker centers. A shared two-column overview lets the unchanged title balance-wrap in the sidebar-width column while progress remains aligned to the PDF column; after placing progress inside that column its width must be 100%, not the old full-parent-minus-sidebar calculation. Stacked screens restore one overview column. This avoids both double subtraction and an unnecessarily tall title-plus-progress stack.
