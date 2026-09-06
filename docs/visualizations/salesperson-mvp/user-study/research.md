# Layout Interaction Research

Researched 2026-09-06 with Tavily search/extraction. Sources below are official product documentation or the GOV.UK Design System. These are transferable interaction patterns, not proof that a competing product or a proposed redesign will work better for this business.

## R1. Keep exact measurements available while drawing

SketchUp documents entering precise lengths through its Measurements Box and specifying a unit with the value. [Official documentation](https://help.sketchup.com/en/using-measurements-box).

Fence AI already supports typed lengths, an mm/cm display toggle, endpoint snapping and 45-degree inference. The opportunity is discoverability: a persistent visible measurement field and a clear endpoint confirmation could expose the existing capability without replacing it.

## R2. Make the moving endpoint explicit

ArcSite shows which end of a selected line will grow or shrink and lets the user reverse that direction before accepting a dimension change. [Edit lengths and angles](https://support.arcsite.com/en/articles/7258187-edit-lengths-angles-manually), [change segment direction](https://support.arcsite.com/en/articles/7258189-change-line-or-wall-segment-direction).

Candidate for Fence AI: when changing a measured run, show which corner stays fixed, which moves, and which connected geometry is affected. Add a visible choice of fixed endpoint rather than a surprise after Enter. The image in `research/arcsite-direction.png` is an attributed illustration from the second official article, downloaded for this research artifact.

## R3. Protect explicitly measured dimensions

magicplan documents locking manually adjusted dimensions so connected edits do not automatically change them; unlocking is an explicit action. [Official dimension-locking guide](https://help.magicplan.app/how-to-lock-and-unlock-dimensions).

Candidate: distinguish approximate sketch geometry from confirmed measurements, and preview conflicts before moving a shared corner. Constraint solving is a domain change, not just an icon. Prototype endpoint choice and impact feedback before committing to a general constraint engine.

## R4. Offer a reference image, with calibration only where valid

magicplan's import workflow places an image under the authored plan and calibrates it against a known dimension. The image can be hidden or shown. [Import and digitize](https://help.magicplan.app/import-and-digitalize-an-existing-floor-plan).

Bluebeam similarly calibrates a drawing by selecting two endpoints of a known length and entering its real-world value and units. [Set page scale](https://support.bluebeam.com/revu/how-to/set-the-page-scale-on-drawing.html).

Application to this project is an inference: a scaled survey can support calibrated tracing; an unscaled paper sketch should serve as a reference while each run is entered from its written measurement. A single calibration cannot make an arbitrary rough sketch proportionally accurate. Treat typed field measurements as authoritative; never silently derive sold dimensions from image pixels.

## R5. Review recorded facts with direct change links

GOV.UK's check-answers pattern provides direct change links, restores previous answers in the edit form, and returns the user to review afterward. [Check answers](https://design-system.service.gov.uk/patterns/check-answers).

Candidate: a selected-stretch summary and job handover summary with direct edits for each value, including explicit unknowns and notes. This can sit beside the existing canvas; it does not require replacing the app with a multi-page wizard.

## R6. Connect an error to its affected input

GOV.UK's error summary links each validation error to the corresponding answer. Its error-message guidance distinguishes a user-correctable input problem from a service failure. [Error summary](https://design-system.service.gov.uk/components/error-summary), [error message](https://design-system.service.gov.uk/components/error-message).

Candidate: name the affected run, highlight it and open its editor from a missing-information item. A failed handover request needs an unavailable/retry state, never a ready state or a demand that the salesperson change valid data.

## Design Options To Compare

| Option | Useful input | Main benefit | Main risk | Current status |
| --- | --- | --- | --- | --- |
| Guided measured drawing | Paper sketch with written lengths | Accurate dimensions with existing drawing logic | Still requires entering the layout | Core drawing exists; guidance and summaries proposed |
| Calibrated tracing | Genuinely scaled survey or plan | Reuses the source's layout | False precision from distortion or an unscaled sketch | Not in current salesperson flow |
| Upload and annotate only | Original signed drawing | Least redrawing work for sales | Office must turn it into structured geometry later | Attachments and workflow boundary not implemented |

Compare these with the same signed-job task and office-review task. Measure exact task completion, mistaken dimensions, recovery from corrections and whether the recipient can answer the sale questions. Do not judge only visual preference or speed.

## Preserve Existing Strengths

The app already has measured drawing, geometry handles, undo/redo, site context, catalog-backed models, side views and immutable source notes. Research suggests making these easier to discover and verify. AR capture, full CAD replacement and live quotation remain outside the current after-sale MVP exercise.
