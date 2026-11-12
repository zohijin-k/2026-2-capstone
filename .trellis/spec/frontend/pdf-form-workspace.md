# Applicant PDF Workspace

## Scope and ownership

`demo/frontend/src/forms/PdfFormsWorkspace.tsx` serves both application programs. Double savings (`program.code === 'double_savings'`) uses an inline document panel; the employment package retains the form viewer modal. Keep document rendering shared between these shells.

`ApplyFlow` owns the controlled `form1`, `answers`, `consent`, and `form5` values. A document selection or edit/preview change must not reset those values. Keep applicant data out of navigation URLs, as specified in [state management](./state-management.md).

## Original document contract

- Render the existing form-page image endpoint with the existing layout fields and masks. Scale the PDF background, masks, inputs, check hit areas, and page height using the same `pageWidth / pageSize.width` ratio. A narrow viewport may scroll the document; do not reflow its cells into a replacement form.
- Reuse the existing field renderer and validation helpers for both shells. Updating the surrounding layout is not a reason to edit templates or coordinate maps.
- Public form numbers/order come from the API/layout `public_form`, backed by `demo/form_numbers.py`. Internal `서식1` is public form 2; internal `서식2` is public form 1. Explicitly sort the savings display list by the same public metadata used for labels, then initialize the active document from that ordered list; response order alone is not a guarantee. Do not sort internal identifiers or duplicate the mapping client-side. Preserve employment-package response order and use a stable fallback after known public forms if metadata is absent.

## Saving before transitions

The component's existing boundary is:

```typescript
onFlush: () => Promise<void>
```

Flush before switching documents or requesting a written preview. Ordinary field patches do not persist every consent: `ApplyFlow` posts the selected consents and signature metadata in `onFlush`. Removing a modal's close action must not remove this persistence step.

| Condition | Required behavior |
| --- | --- |
| Current form incomplete | Allow document navigation; keep upload/eligibility validation unchanged |
| Flush pending | Prevent conflicting transitions and edits to the outgoing snapshot |
| Flush rejects | Keep the current document and values, display the error, allow retry |
| Application/program changes or component unmounts | Ignore stale asynchronous UI completions |
| Read-only or paper-submission mode | Preserve existing editing restrictions and payload rules |

For example, selecting public form 4 from public form 1 must save the existing values before changing the selected document. Do not clear `active` or navigate in a `finally` block: that would also navigate after a failed save.

## Signature dialog lifecycle

Form 5's signature portal remains a dialog above the inline PDF. It must own its Escape handling, body-scroll lock/cleanup, keyboard focus containment, and focus return to the signature trigger. Those effects previously came partly from the parent viewer modal and cannot be assumed after removing that modal. Preserve drawing, image-upload validation, clearing, confirmation, and signature-mode behavior.

## Compact workspace chrome

Savings step 2 uses the application title/compact step strip above a document heading in the panel; do not restore a second workspace heading/subtitle or an always-reserved save-guidance row. Keep downloads in the document actions, including read-only and paper modes. The selected original PDF remains in the existing independently scrolling viewport, with a viewport-based height and the same coordinate scale. Changing the surrounding spacing must not change the PDF renderer. The shared top-bar application controls are owned by `ApplyFlow` through a portal as specified in [state management](./state-management.md).

The compact stage strip uses a connected horizontal line with circular markers and captions/names/statuses below. Keep current/passed/upcoming stages distinct through explicit status text, a current ring/dot and completed checks; do not replace this with per-stage cards or faint underline-only labels. Current styling and `aria-current` take precedence when a stage is also complete. A stage before the restored current stage is visually passed even if child-reported upload counts have not loaded yet; do not change actual upload completion or navigation/gating rules to implement this presentation. Preserve counts when available. Keep the track continuous and labels readable at narrow widths, wrapping text rather than overlapping it.

In savings step 2, the progress area spans the right-hand PDF toolbar's width, excluding sidebar/gap. Share sidebar-width/gap variables between overview and workspace columns; title occupies the left overview column and progress fills the right column (do not subtract sidebar width again). At 800px the overview stacks and progress uses panel width. Marker 1/4 sit near the area's ends with safe insets, marker 2/3 at equal center gaps; edge captions align inward. Keep the non-interactive base rail bounded by `--stage-edge-center` on both sides, without tails. Completion connectors match marker centers and vertical midpoint. Do not restore a 700px cap or affect other stages. Sidebar draft text remains accent/heavier than neutral regular empty text, without badges.

Applicant visual polish is scoped to the applicant shell and workspace chrome: keep its light top bar and bounded inner alignment coordinated with the main flow, use separate application accent/surface styles, and preserve the officer interface. Do not change global `--brand`, document fonts, PDF field colors/coordinates or assets to restyle navigation. Keep primary save/continue actions distinguishable from secondary preview/download and quiet reset actions. Preserve the download menu's positioned header stacking context and right-edge anchoring when changing panel spacing or corners.

The application title keeps the original `.flow__head h1` typography (22px and original tracking/inherited color/line height). Compact layout should not reintroduce separate 16px desktop/mobile title overrides.

Balance-wrap the unchanged savings title within its left overview column. Stage 2 copy is left-aligned from its circle's left edge and stage 3 copy right-aligned to its circle's right edge; align only copy blocks/caption justification, never buttons/nodes. Narrow screens may use the full local text cell for safe wrapping, preserving alignment direction and all counts.

## Verification

Run frontend lint and build. Check direct nonsequential form navigation, consent persistence, save failures, stale transitions, every original field type, all PDF pages, preview/edit/reset, paper mode, and completion gating. Verify background/overlay alignment after resizing and narrow-screen scrolling, plus signature dialog keyboard/pointer workflows. Regression-check the employment-package modal because it shares rendering and save helpers. Static checks alone do not establish visual or interaction correctness; record unavailable browser checks explicitly.
