# Exact Drawing and Correction After the Sale

Accessed: **2026-09-06**. Scope: salesperson transcribes a signed contract, rough measured drawing, and WhatsApp promises/photos into a saved structured fence layout. Pricing, quotation, and office engineering are excluded.

**Recommendation:** extend the existing editor with explicit fixed/moving endpoints, visible edit scope, touch-accessible precision controls, and a preview of affected measurements. Preserve the existing fence-specific gate and interval tools. A general CAD constraint solver is outside this MVP.

## Evidence and Method

Tavily search located official ArcSite, SketchUp, and magicplan help pages; Tavily Extract retrieved their page bodies. Research branches ran concurrently; no subagent tool was available. No competitor was operated, no account created, and no downloaded code installed. This is documentation research plus a focused read of Fence AI source, not a usability test or broad product ranking.

**Documented** below means an official help page describes the interaction. **Proposal/inference** means an adaptation for Fence AI. Marketing claims about accuracy or efficiency are not treated as measured outcomes. **Unknown** means the retrieved material does not establish the behavior; it does not mean the product lacks it. Every competitor claim has its source beside it; all links share the access date above.

## Six Transferable Patterns

### 1. Edit an Existing Measurement With an Explicit Moving End

**Documented, ArcSite:** select an existing object, tap its displayed length or angle, enter the measurement, and accept with the green checkmark. An orange arrow identifies the side that grows or shrinks; Change Direction reverses it. This goes beyond numeric creation by exposing the direction of an existing-object correction. [Official guide](https://support.arcsite.com/en/articles/7258187-edit-lengths-angles-manually).

**Documented, SketchUp desktop:** an existing line can be edited through context-click > Entity Info > Length, or by using Move on an endpoint. The guide qualifies line-length editing as applying when the line does not bound a face. It does not explain how Entity Info chooses the fixed endpoint. [Official drawing guide](https://help.sketchup.com/en/sketchup/introducing-drawing-basics-and-concepts).

**Fence AI proposal:** select run AB > tap its length > enter `6.20 m` > choose fixed endpoint A or B > inspect a ghost preview > Apply. Label both endpoints on canvas. Highlight every connected run affected by moving the shared node. If the selection contains multiple segments, show whether the value is one segment's length or the run total.

**Fit/size:** medium. Existing numeric editing is reusable; choosing the other endpoint and previewing connected geometry require additional logic. **Unknown:** ArcSite's behavior for locked neighbors or closed-loop conflicts is not established by its number-pad guide.

### 2. Make the Angle's Reference Visible

**Documented:** ArcSite accepts a number through a displayed angle. Its guide does not define every angle convention or which adjoining geometry rotates. Magicplan instead documents room > corner > blue directional arrow > drag > tap outside to finish; that page does not establish a numeric angle-entry control. [ArcSite](https://support.arcsite.com/en/articles/7258187-edit-lengths-angles-manually), [magicplan angled walls](https://help.magicplan.app/how-to-create-angled-walls).

**Documented, SketchUp iPad:** choose Line and optionally lock the next line parallel or perpendicular to a selection/previous line, or to an axis. These locks reset after one operation. Tap the dimensions box for a number pad. Finger input uses long-press/drag/release; Pencil has separate drawing modes. Inferences are shown while dragging, but not when lifting and moving to the endpoint. [Official iPad Line guide](https://help.sketchup.com/en/sketchup-ipad/line-tool).

**Fence AI proposal:** select corner B and the outgoing leg BC > show incoming leg AB as the reference > choose left/right turn and enter the measured turn > enter BC length. Show an angle arc and preview. For example, explicitly distinguish a `30 degree right turn` from the corresponding `150 degree inside angle`; do not expose an unlabeled degree field. Offer a perpendicular control for a recorded right angle. If no angle was measured, preserve the rough direction with an unresolved note rather than treating an automatic snap as verified evidence.

**Fit/size:** medium for a next-leg direction control; large if later angle edits must preserve arbitrary connected lengths. Keep plan angles separate from fence height and post tilt.

### 3. Select the Exact Object or Range Before Correcting It

**Documented, ArcSite:** tap for a single object; cumulative mode retains successive selections. A selection box dragged left-to-right includes fully enclosed objects, while right-to-left includes touched objects. Multiselect also offers a lasso. These are whole-object selections, not documented distance intervals along one fence. [Official selection guide](https://support.arcsite.com/en/articles/7258186-single-and-multiple-selection-options).

**Documented, ArcSite:** making a break can involve drawing two temporary crossing lines, trimming the intervening segment, and deleting the temporary lines. Extend uses a finger path across two segments. [Official trim/extend guide](https://support.arcsite.com/en/articles/7258195-trim-or-extend-lines).

**Fence AI proposal:** tap a run, then expose Whole run / Range. Range shows two handles plus exact From/To distances measured from a named endpoint. Highlight the selected stretch in both plan and elevation before applying height/base/model. On overlap, present the candidate run IDs and highlight the chosen one. Retain the gate tool: select its run, specify opening position, width, and the signed kit/model. Do not require temporary construction lines for a semantic gate opening.

**Fit/size:** small-to-medium for range highlighting and controls over existing interval data; medium for overlap selection and precise gate position editing. Direction-sensitive box selection and lasso are lower priority for this task.

### 4. Expose What Snapping Is Doing and What Override Disables

**Documented, ArcSite:** object snap is enabled by default; settings provide individual snap-type toggles and a global off switch. An X in the magnification indicator confirms a snap. The guide recommends disabling snapping temporarily or zooming into dense geometry, then restoring it. [Official snapping guide](https://support.arcsite.com/en/articles/7258215-using-snapping-to-make-objects-snap-or-not-snap-together).

**Documented, SketchUp desktop:** after beginning a line, Alt on Windows or Command on Mac cycles linear inference modes. Even the mode called All Inferences Off retains other inference types, including midpoints and guide points. This is not a universal disable-all-snaps command. [Official drawing guide](https://help.sketchup.com/en/sketchup/introducing-drawing-basics-and-concepts).

**Fence AI proposal:** show the active target, such as endpoint B, and provide visible controls for direction/grid assistance and endpoint connection. A one-operation Free placement control should explicitly bypass both when needed, then restore the prior mode. Numeric length must remain exact after snapping. On touch, place controls outside the finger's contact area; keyboard modifiers may supplement them on desktop.

**Fit/size:** small-to-medium. Existing snapping and feedback are reusable, but a touch control and a true endpoint bypass need changes. Confirming a connection should identify the shared node, since later corrections can move its neighbors.

### 5. Protect Transcribed Measurements and Explain Conflicts

**Documented, magicplan:** manually edited dimensions lock and show a lock icon. Dragging a locked wall produces a confirmation to unlock it; alternatively tap the dimension > Unlock > change measurement > Apply. [Official lock guide](https://help.magicplan.app/how-to-lock-and-unlock-dimensions).

**Documented, magicplan:** room > corner > Set Diagonal > opposite corner > tap the diagonal measurement. Set Diagonal appears at the left on tablet and in the bottom menu on phone. The guide says wall lengths should be established and locked first; without locks, the application prioritizes adjusting wall lengths over corner angles. It does not specify how an impossible fully locked configuration is resolved. [Official diagonal guide](https://help.magicplan.app/magicplan-diagonal-measurements).

**Fence AI proposal:** distinguish measured values from provisional drawing geometry. Before committing a correction, list affected measured lengths, gate offsets, and range boundaries. Example: a recorded 6.00 m straight run contains a 1.00 m gate starting 5.50 m from A. Flag that the gate ends at 6.50 m; offer editing the run length, gate position, or width against the source, or cancel. Save unresolved work as draft and require resolution before submission. Do not silently shrink the gate or reinterpret the signed value.

**Fit/size:** medium for focused validation and a before/after preview; large for persistent geometric locks or diagonal-driven constraint solving. The MVP can reject a conflicting edit without solving it. Measurement provenance and unresolved status are capture features, not engineering judgments.

### 6. Treat Partial Height as a Scoped Property, Not a Generic Wall Type

**Documented, magicplan:** Partial Walls attach to existing walls and accept doors/windows, but their height follows the room and cannot be customized. Partition Walls are objects with adjustable height/depth, but cannot host wall objects. Neither is documented as an arbitrary height interval on an existing wall. [Official comparison](https://help.magicplan.app/partial-wall-vs.-partition-wall).

**Documented, magicplan:** floor height supplies room heights, while an explicitly changed room is exempt from a later floor-height change. The guide also warns that individual room heights are not represented individually in the 3D view, which displays the highest room height. [Official height guide](https://help.magicplan.app/setting-the-ceiling-height-for-a-specific-floor).

**Fence AI proposal:** retain one fence run and its existing interval model. Set whole-run height `1.80 m`, then Range > From `2.00 m` > To `4.50 m` > Height `1.20 m` > preview > Apply. Show the same boundaries and values in side elevation. Preserve explicit exceptions when changing a default, or ask which existing intervals to replace. Define height's reference, such as above local base, separately from base elevation.

**Fit/size:** small-to-medium for interval selection and preview; medium if overlapping-interval precedence or default/exception persistence needs changes. Do not adopt a room/object workaround for fence height changes.

## Proposed Salesperson Workflow

This is a Fence AI design proposal, not a tested competitor sequence. Illustrative measurements are not a customer case.

1. Open the sold job. Attach the signed contract, drawing, and exported WhatsApp screenshots/photos. Identify sources as contract, measured sketch, or promise. Attachment capture is a stated gap; keep a source visible beside the drawing on desktop, or in a switchable sheet on tablet.
2. Choose units. Draw A > B, aim approximately, enter `6.00 m`, and confirm. At B, choose a recorded right turn and enter `3.00 m` for BC. On tablet, an explicit length field opens the numeric keyboard; desktop also keeps existing type-while-drawing input.
3. Select AB's dimension to correct it to `6.20 m`. Choose A fixed. Inspect the preview of B and adjacent BC. Apply only after affected measured values are resolved; Undo reverses the complete correction.
4. Choose Gate, tap AB, and enter opening start `4.80 m from A`, width `1.00 m`, and the kit/model stated in the contract. Verify the displayed opening spans 4.80-5.80 m. Exact opening position is a proposed addition to the existing click-placement flow.
5. Choose Height, tap AB, apply `1.80 m` to Whole run. Select Range `2.00-4.50 m from A`, enter `1.20 m`, and inspect side elevation. Use the existing separate Base and Model tools for other recorded exceptions.
6. For a crowded corner, zoom, select the named endpoint, or use Free placement for the current edit. Confirm the intended connection. Do not allow snapping to overwrite an explicitly entered measurement.
7. Attach a promise or photo to its run, gate, or range and record unresolved contradictions explicitly. Compare the plan, elevation, and structured list against the sources; saving must retain both entered values and unresolved items.
8. Save draft, then use a distinct Submit transcription action after capture validation passes. Confirmation identifies the saved revision and its included sources. Submission records the salesperson's transcription; it does not imply engineering approval. Attachment linkage and explicit submission are cross-cutting additions, outside the drawing-control size estimates.

## Local Fit and Implementation Judgment

Focused source inspection supports these estimates; no app execution was performed:

| Existing code | Consequence for the proposal |
| --- | --- |
| [editor.js:1019](../../references/repository/src/fenceai/web/static/js/editor.js.txt#L1019) opens a run-total number field; Enter commits and blur closes it. [editor.js:1046](../../references/repository/src/fenceai/web/static/js/editor.js.txt#L1046) changes the final segment by moving the shared end node. | Reuse numeric parsing, but add visible Apply, fixed-end selection, segment/run scope, and connected-run preview. This is more than changing a label. |
| [geom.js:122](../../references/repository/src/fenceai/web/static/js/geom.js.txt#L122) checks nearby nodes before Alt; Alt bypasses angle/grid processing only. | A true free-placement mode needs a separate endpoint-snap decision. Existing behavior must not be described as all snaps off. |
| [editor.js:865](../../references/repository/src/fenceai/web/static/js/editor.js.txt#L865) already exposes height, start, and end fields initialized to the whole run. | Prioritize visual interval selection and existing-value editing over a new wall abstraction. |
| [geom.js:169](../../references/repository/src/fenceai/web/static/js/geom.js.txt#L169) resolves segment-local anchors with proportional default or rigid offset behavior and clamps to segment length. | Audit affected anchors before accepting length edits. A measured gate offset must not silently become proportional or clamp; existing generic anchor support alone does not establish the correct policy for every event. |

**MVP order:** explicit Apply and selection scope; fixed-end feedback and correction preview; touch snap controls; range highlighting; focused conflict checks. Keep existing exact drawing, connected runs, gate semantics, side elevation, and Undo/Redo. Persistent locks across arbitrary graphs, geometric diagonal solving, general trim/extend tools, 3D face editing, and CAD selection conventions are later work. Live pricing and office engineering remain excluded by scope.

Sizes are qualitative engineering judgments: small means local control/rendering work; medium means coordinated geometry, selection, persistence, or history behavior; large means new graph-wide constraints or substantial data semantics. They are not delivery-time or human-performance claims. Validate eventual changes with a shared-corner correction, a gate invalidated by shortening, a range extending past a corrected endpoint, and a touch-only correction with no keyboard modifier.

## Limits and Visual Reference

- ArcSite's dimension guide explicitly lists iOS, Android, and Windows availability, with Web/User Site marked N/A; toolbar positions differ. Do not generalize its native interactions to a browser editor. [Platform details](https://support.arcsite.com/en/articles/7258150-how-to-manually-or-automatically-show-measurement-dimensions).
- Magicplan's measurement menu differs on phone (bottom sheet) and tablet (information icon). Its dimension guide describes a scrolling measurement picker; the lock guide also says to enter a new measurement, without fully documenting that input widget. Desktop parity was not established. [Measurement workflow](https://help.magicplan.app/change-dimensions-of-your-floor-plan).
- No inspected guide established arbitrary fence intervals with gate-preserving constraint resolution. ArcSite angular propagation and impossible magicplan lock conflicts remain unknown. The magicplan Add Corners extraction omitted instructional steps, so no detailed interaction claim relies on it. [Incomplete extraction source](https://help.magicplan.app/add-corners).
- Official SketchUp iPad prose contains apparent copy errors, such as referring to a lasso in its Line guide. Only coherent Line instructions were used. No videos, image pixels, accessibility behavior, error recovery, or offline behavior were tested. [Source](https://help.sketchup.com/en/sketchup-ipad/line-tool).
- Useful official image URL, retrieved from ArcSite's number-pad help page: [number-pad screenshot](https://arcsite-e780de917482.intercom-attachments-1.com/i/o/709730308/9e4bb3c1da4af91f4482674d/numberpad.png?expires=1788691500&signature=bc6588b7fae1ad2b12e25ce8e728dd929f56177253f917a3e319378f22c81d1f&req=cyAuEcp%2BnoFXFb4f3HP0gBhOKoThk47NyvUiLwVeMKLVkzIu96VCZcNgmz0D%0A0wbkMRs09fehCz1GqQ%3D%3D%0A). This signed CDN URL can expire; reopen the [official parent guide](https://support.arcsite.com/en/articles/7258187-edit-lengths-angles-manually) for its current image. Image content was not independently inspected.
