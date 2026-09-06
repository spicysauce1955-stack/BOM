# Adversarial Review: Salesperson Walkthrough

Date: 2026-09-06. Target: [interactive proposal](../index.html).

## Follow-Up Implementation

The visualization was subsequently updated to address this review. The findings below
are retained as the original record; their line numbers refer to the pre-fix version.

| Findings | Change |
| --- | --- |
| 1-2 | Per-stretch drafts survive navigation; untouched chapter presets no longer replace edited measurements; saved lengths can be corrected. |
| 3, 11 | Restore clears the active partial preview; valid saves clear prior errors. |
| 4-5 | The office preview shows saved facts and diagrams, with inspectable contract, sketch, amendment, WhatsApp and illustrative photo records. |
| 6-8 | Amber overlays select the street; the reference house adapts to lengths; plan zoom scrolls with the legend outside the viewport. |
| 9-10 | Step controls stay mounted, replaced controls regain focus, and dialogs expose their titles as accessible names. |
| 12-14 | Zoom is explicitly scoped to Plan; elevations are labeled unfolded with corner B marked; orientation/legend colors are darker. |

Verification: the original browser checks and [review regression suite](review-regression.cjs)
pass at 1280, 1440, 1600 and 1920 px. Screenshots of the revised chapters and office
package were inspected. This is targeted verification, not a repeat five-agent review,
human usability study, or full screen-reader audit. Production application code is unchanged.

## Original Review

Five independent AI reviewers examined the visualization. These are agent reviews, not
human usability sessions. Four reviewers returned 14 findings; the evidence auditor
reported no actionable mismatch between the proposal/current-app disclosures and the
inspected evidence. No P0/P1 issue was established within this local demo's scope.

This review does not change the visualization or production app. P2 means a meaningful
interaction or workflow problem in the prototype; P3 means lower-impact clarity/polish.
No production deployment or backend functionality is assumed.

## Reviewers and Method

| Reviewer | Scope | Result |
| --- | --- | --- |
| Franklin | Post-sale sources and office recipient | 3 findings |
| Jason | Drafts, navigation, saves and restore | 4 findings |
| Carver | Geometry, selection, zoom and desktop rendering | 4 findings |
| Lagrange | Keyboard, accessible names and contrast | 3 findings |
| Copernicus | Current-app evidence and proposal boundaries | No actionable findings |

All listed behavioral findings were browser-reproduced by their reviewer. Visual
findings were inspected at 1280 and 1440 px. Accessibility checks used keyboard actions,
Chrome's accessibility tree and computed colors, not a real screen-reader speech test.
The evidence audit inspected repository source but did not freshly reproduce the archived
production-app defects. The lead reviewer independently reproduced findings 1-3 and
inspected the zoom screenshot and source references.

The original automated checks still pass at 1280, 1440, 1600 and 1920 px with no console
errors or warnings. They cover the happy path and numeric bounds but miss interruption,
draft recovery, geometric annotation bounds and accessibility. Passing them is not
evidence that the issues below are absent.

## P2 Findings

### 1. Next replaces and locks an unfinished measurement

Source: [app.js:29](app.js#L29), `go()`.
Reproduce: Restart > Draw > place street > enter side length 4.5 > Next > Previous.
Actual: The side becomes 5 m, recorded and read-only. The chapter snapshot overwrites
the user's unfinished input. Preserve the draft or explicitly resolve it before advancing.
Prepared examples are intentional; overwriting a field the user has edited is the defect.

### 2. Step navigation silently discards stretch-detail drafts

Source: [app.js:79](app.js#L79), `inspector()`; save handler at line 89.
Reproduce: Set details > enter height 2.2, Routed vinyl and Concrete > Next > Previous.
Actual: All fields revert without a dirty-state or discard indication. Range/gate drafts
are retained, so the rules differ between editors. Preserve drafts or make discard explicit.

### 3. Restore leaves a stale partial-height preview

Source: [app.js:92](app.js#L92), restore handler; `shownRange()` at line 48.
Reproduce: Edit section > Apply > Restore full height > Set details > save street height
2.2 > Edit section. Actual: The last 5 m previews at stale 1.8 m while the rest is 2.2 m.
Next shows the correctly saved uniform height again. Clear the active preview on restore;
do not confuse this display bug with corruption of the saved height.

### 4. Office package preview does not expose the recorded specification

Source: [app.js:100](app.js#L100), `showPackage()`.
Reproduce: Review > Preview office package. Actual: Categories such as saved details
and sources are listed, but neither their contents nor links are provided. The recipient
cannot inspect the 3-8 m amendment, model/base, unchanged height or gate dimensions/swing
inside the package. Show a compact saved-facts summary and inspectable attachments.
This is a preview-content gap, not a request to implement actual sending.

### 5. Contract and photo inputs are missing from the scenario

Source: [HTML:12](../index.html#L12), source tabs; [app.js:18](app.js#L18).
Reproduce: Inspect all sources and the package inventory. Actual: A signed sketch,
amendment and text message are present, but the requested separate signed contract and
photos have no visible place. Add representative contract/photo examples or explicitly
identify the contractual document where the sketch is intended to serve both purposes.

### 6. Highlighted fence section cannot be selected directly

Source: [app.js:55](app.js#L55), amber overlay; `selectDrawing()` at line 109.
Reproduce: Place the gate > click the amber street section > click the green section.
Actual: Amber does nothing; green opens the stretch inspector. The overlay intercepts
events outside a `data-run` target. Pass pointer events through or associate the overlay
with the same street selection target.

### 7. Accepted dimensions place a fence through the illustrative house

Source: [app.js:53](app.js#L53), fixed house coordinates.
Reproduce: Restart > Draw > place a 4 m street stretch and 5 m side stretch.
Actual: B-C crosses the house and its label. Keep the illustrative house spatially
coherent with the entered geometry, or clearly separate the unmeasured reference.

### 8. Zoom clips gate dimensions without a way to pan

Source: [app.js:53](app.js#L53), centered scale; [style.css](style.css), plan viewport.
Reproduce: Place the gate > zoom to 140%. Actual: C's label disappears above the
viewport and the offset annotation is clipped below/obscured by the legend. Fit annotation
bounds, add panning, or restrict zoom so measurement labels remain reachable.

### 9. Replacing controls drops keyboard focus

Source: [app.js:39](app.js#L39) and [app.js:79](app.js#L79), DOM regeneration.
Reproduce: Tab to Set the details > Enter > Tab; separately activate Side B-C.
Actual: Focus falls to BODY and the next Tab returns toward earlier controls. SVG
selection has the same focus loss. Preserve DOM nodes or restore focus deliberately.

### 10. Source and handover dialogs have no accessible names

Source: [HTML:19](../index.html#L19) and line 20.
Reproduce: Open each dialog and inspect its accessibility-tree name. Actual: Both
names are empty despite visible titles. Associate title IDs using `aria-labelledby`.
Escape and return focus worked in the review; those are not reported as broken.

## P3 Findings

### 11. A successful save leaves an old validation error visible

Source: [app.js:89](app.js#L89), stretch save handler.
Reproduce: Set details > height 4 > Save > height 2 > Save. Actual: The valid value
saves and the drawing updates, but the earlier height error remains. Clear it on success.

### 12. Side-view zoom still changes only the plan

Source: [app.js:66](app.js#L66) and line 108.
Reproduce: Select Side view > zoom from 100% to 140%. Actual: The plan enlarges while
the elevation is pixel-identical. Scope the controls explicitly to Plan or zoom the
selected view.

### 13. The elevation label describes the wrong viewpoint

Source: [HTML:13](../index.html#L13), elevation heading;
[app.js:63](app.js#L63), unfolded side stretch.
Reproduce: Compare Review's plan and recorded heights. Actual: The perpendicular
B-C stretch is drawn at full length alongside A-B under "From the street, facing the
house." Label the diagram as unfolded elevations and mark the corner break.

### 14. Small orientation labels and legend text are too faint

Source: [app.js:53](app.js#L53); [style.css](style.css), `.canvas-key`.
Reproduce: Inspect the initial plan at 1440 px. The reviewer calculated approximately
2.38:1 for Garden, 3.43:1 for STREET and 3.57:1 for the 9 px legend against the drawing
background. Darken the labels and improve small-text legibility without changing layout.

## Recommended Fix Order

1. Preserve draft measurements and specifications; clear stale range previews/errors.
2. Make the office preview display the actual saved facts and missing source types.
3. Repair selection and geometry/zoom behavior while retaining the current composition.
4. Restore keyboard focus, name dialogs and correct diagram labeling/contrast.

Keep the single-customer, six-step presentation. The findings call for more reliable
controls and clearer evidence, not a return to the research-heavy main page.
