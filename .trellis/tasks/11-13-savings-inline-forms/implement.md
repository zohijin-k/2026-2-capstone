# Implementation plan

## Gate

- [x] User consented to task creation and planning.
- [x] Inspect current PDF rendering, save callbacks, form numbering, shared consumers, and frontend guidelines.
- [x] Prepare PRD, technical design, research, and curated context manifests.
- [x] Presented final planning summary; user explicitly approved implementation on 2026-11-13.
- [x] Manually activated before product edits because Python is unavailable; wrote the current Codex session pointer without altering other sessions. task.py start was not run.

## Ordered work

1. Record the working-tree baseline and confirm the active task/context. Read this task's PRD, design, research, and curated specs. Follow the applicable Trellis implementation/check dispatch mode.
2. Reuse the current PDF viewer content and actions so the savings inline panel and existing employment-package modal share the field renderer, images, masks, scaling, page controls, and helpers.
3. Add savings selection initialization, public-form navigation/status, inline edit/preview/save/reset actions, and loading/error/paper states. Preserve existing value ownership and payloads.
4. Replace the modal-close save dependency with guarded form-switch flushing and retained state on failure. Prevent conflicting/stale async transitions.
5. Add scoped desktop sidebar/document styles and the savings-only container width modifier; stack navigation above the document on narrow screens.
6. Preserve the form 5 signature portal and make its keyboard, focus, and body-scroll lifecycle independent of the removed outer modal.
7. Run the full-scope code review and fix findings. Review whether new frontend contract knowledge should be captured in `.trellis/spec/`; avoid unrelated documentation changes.

## Validation

Run in `demo/frontend`:

```powershell
npm.cmd run lint
npm.cmd run build
```

The build includes `tsc -b`. No separate frontend test command is configured. Do not claim browser checks or save-failure checks ran unless observed.

Use the existing local demo services if available. Verify with synthetic applicant values:

- Step 2 initial public form 1; direct 1 → 4 → 2 → 5 navigation while incomplete; every form and page; selected/completion/remaining counts.
- Original PDF versus current rendering: unchanged wording/tables and aligned masks, inputs, checks, dates, and signatures at desktop and narrow widths and after resizing.
- Text, each check/radio group type, conditional controls, identity locks, date helpers/period bands, phone/email validation, reset confirmation, read-only states, bulk download, and preview/edit mode.
- Values and consents survive switching; successful saved values survive refresh; injected save failure retains form/values with retry; rapid clicks do not activate a stale form.
- Form 5 drawing and file-signature workflows, file restrictions, clear/change-mode/reopen, backdrop/close/Escape, focus containment/return, and body-scroll cleanup.
- Form 5 paper/online switching and unchanged downstream upload requirements.
- Unchanged eligibility/consent upload gating and completion progress.
- Employment-package modal editing/preview/page navigation/signatures and unrelated modal behavior.

If local backend/browser access is unavailable, report the exact unverified behaviors and retain the browser checklist for review; static checks alone do not prove PDF alignment or signature behavior.

## Finish

- Record actual check results and any limitations.
- Present only this task's changes for review. Do not include unrelated dirty files.
- Follow Trellis's separate commit confirmation and finish-work procedure after implementation; do not commit during planning.

## Follow-up execution

The user directly requested the compact header refinement after reviewing the initial implementation. Continue the same task: move number/My Page into the top bar, compact the step strip, and remove redundant vertical chrome before the inline PDF. Add `App.tsx` / `app-shell.css` to the change boundary. Preserve existing in-progress code and all document/save behavior. Run a fresh independent full-scope check after the follow-up changes. The earlier commit plan is superseded until its file list and verification record are updated; no commit approval has been given.

The next user review requests a more legible stepper while retaining the compact header. Update only step presentation/markup in `ApplyFlow.tsx` and `apply-flow.css`, then check current/passed/upcoming states, completed-current overlap, restored stages, progress counts, navigation restrictions, narrow-screen wrapping and focus visibility. Run lint/build and an independent check; keep all earlier product changes intact.

The latest reference replaces the stage boxes with a connected horizontal bar and four circular markers, captions/names/statuses below. Implement only this presentation change in the same two files; preserve the previous stage-state fixes. Remove box backgrounds/borders and keep markers/line aligned on narrow screens. Run lint/build and the independent source check again; no commit has been approved.

The latest user explicitly requests a substantial contemporary visual polish. Treat the applicant shell, compact overview/bar and savings sidebar/document chrome as one design pass across the same six frontend files. Follow the new design direction; preserve all existing handlers/state/rendering/saving/signature behavior, the compact vertical budget and the connected track. Scope applicant-only styling to avoid unintended officer changes, and do not touch global PDF tokens, assets, APIs or dependencies. Run frontend lint/build and an independent full-scope source/layout review; browser rendering remains unavailable.

The user's sidebar review requires a public-number ordering correction and simpler list. Sort savings forms using loaded `public_form` metadata and select the same first ordered ID, preserving internal keys and job-package order. Simplify only sidebar markup/styles (flat rows, subtle selection/separators, concise status, no trailing chevrons), retaining full field feedback in the panel. Validate public1/public2 mapping with intentionally reversed response order and initial selection, then lint/build and independent check. Keep all prior changes and no-commit status.

The latest request is CSS-only: distinguish draft from empty status through color/weight, and center the progress track relative to the full content width independently of the title. Preserve compactness, connected/mobile geometry and all code behavior. Run lint/build/diff and independent source/layout check; no new persistent tests are needed for this reversible style change.

The user clarified that width means the right-hand PDF panel, not the entire sidebar-plus-document workspace. Correct only the two layout CSS files: share sidebar-width/gap variables between the form grid and the form-stage progress area, align that area with the document column, and reset it to full width when stacked at 800px. Keep the removed 700px cap removed, all four stages inside the aligned area, all other stages and all non-layout behavior unchanged. Verify matching geometry at desktop, medium and stacked widths, then appropriate checks.

The final clarification requests the actual line across the entire Save toolbar width. Keep the corrected panel alignment and add only a form-stage full-width base rail behind existing inset markers/connectors in `apply-flow.css`. Reuse node midpoint variables, preserve completed connector styling and pointer/focus behavior, and do not move/crop labels or touch JSX/functions. Verify the rail covers 100% of the aligned area rather than only the 75% marker-center span.

The user approves that rail length and now requests marker positions near the endpoints with equally spaced middle circles. Modify only form-stage child layout in `apply-flow.css`; approved outer width/base-rail geometry is frozen. Keep endpoint labels inside, match completed connector endpoints to the relocated nodes, and preserve mobile wrapping/state/functions. Check source geometry at desktop/medium/narrow widths, then minimal lint/build/diff and independent review. No new persistent tests or artwork are needed.

The user's final refinement removes tails outside the endpoint circles. Preserve marker positions and approved overall area width; change only the form-stage base rail's left/right bounds to the existing endpoint-center variable. Check desktop/mobile center bounds and pointer/stacking preservation. No new tests or broader style changes are needed.

Restore title typography by deleting only the two compact h1 overrides in `apply-flow.css`; the original base rule supplies the title style. No markup/diagram/other typography changes. Use normal quick checks without new tests.

The latest text-only request is scoped to savings form-stage CSS in `apply-flow.css`: stage 2 copy left, stage 3 copy right, and balanced title wrapping in the shared left column. Keep marker/rail geometry unchanged; move the overview to matching title/progress columns and use 100% progress width within its right column, resetting one column when stacked. Preserve the title's 22px base style and all other styles/behavior. Check actual horizontal-bound equivalence and safe text wrapping, then minimal lint/build/diff and independent review. No new tests/JSX are needed.

## Rollback points

Keep shared-viewer extraction independently reviewable before introducing the inline shell. Avoid backend/template changes so rollback only affects the scoped frontend change. Do not revert unrelated user changes.

