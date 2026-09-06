# Novice Salesperson Study

Agent simulation, not a human participant. Conducted on 2026-09-06 at http://127.0.0.1:8821 with headless Chrome, Playwright, a 1440x900 viewport, and an isolated browser profile. This report uses first-hand UI observations. No application source, earlier studies, API endpoints, network response bodies, databases, or application runtime state were consulted. No app fixes or server operations were performed.

**Outcome: partial.** Dana's job, the 8 m and 5 m fence stretches, explicit 1.8 m heights, soil, Slat assignments, house/street context, and the requested note were recorded. The 1 m gate was saved at **1992 mm**, not the requested 2000 mm. The UI said **"Nothing missing - this job is ready to hand over"** and produced an estimate of **ILS 2,514.50**. That establishes the app's readiness assessment, not exact fulfillment of the paper measurements or receipt by the office.

## Initial Expectation

As a first-time, nontechnical salesperson after a signed sale, I expected to start a named job, copy measurements from paper, identify the sold panel, add a gate and site note, and see whether the office needed anything else. I expected dimensions to be enterable as numbers, and a saved job to reopen where I left it. I had no additional site-condition information and did not invent any.

## Recorded Decision Steps

There were **29 meaningful decision steps**. A step groups one purposeful interaction, such as filling and saving a form or placing one fence stretch; it is not a count of individual keystrokes. Screenshots and passive reads are supporting observations. No participant timings or emotional quotations were collected.

| # | Expectation and actual action | Resulting visible feedback |
| --- | --- | --- |
| 1 | Open the assigned app and identify a starting point. | A Hebrew sample project with an existing fence and many technical tabs opened. |
| 2 | Switch the language using the English/Hebrew button. | Controls became English; the sample project name remained Hebrew. Everything was selected. [01](01-initial.png) |
| 3 | Choose Salesperson in the role selector. | Navigation became The job / Notes; Create became New job, and tools included Sits on and What was sold. [02](02-salesperson.png) |
| 4 | Enter Dana Example - 12 Sample Road in the customer/address field and click New job. | A new project appeared and the canvas was empty. |
| 5 | Fill Customer, Address, You and Sold on, then click Save job details. | The first three entries did not remain visible; the date did. The missing-details text still asked for those fields. Saving was not substantiated. [03](03-job-saved.png) |
| 6 | Choose Draw fence to find how to copy the measurements. | The hint explained aiming and typing a length, including 4 = 4 m, then Enter. [04](04-draw-start.png) |
| 7 | Re-enter Dana Example, 12 Sample Road, Alex and 2026-09-06, then save again. | All four values remained visible, the blank-field warning disappeared, and the project title reflected Dana and the address. [05](05-job-confirmed.png), [06](06-first-stretch.png) |
| 8 | Place a starting point, aim horizontally right, type 8, press Enter to place the endpoint and Enter to finish. | The horizontal stretch was labeled run1 (8000 mm). [06](06-first-stretch.png) |
| 9 | Start at its endpoint, aim vertically upward, type 5, and finish with Enter. | The connected-looking vertical stretch was labeled run2 (5000 mm), forming an L. [07](07-gate-dialog.png) |
| 10 | Choose Gate and click about two grid squares from the street stretch's start. | Place gate showed station 1970 mm, width 1000, and a gate assembly selector. There was no visible editable station field. [07](07-gate-dialog.png) |
| 11 | Cancel and click slightly farther along the same stretch, then save the 1000 mm gate. | The pointer hint said station 2000 mm, but the dialog said 1992 mm. The saved event later read Gate / 1000 mm @ 1992. Exact placement remained partial after two attempts. [14](14-office-estimate.png), [16](16-reopened-job.png) |
| 12 | Choose Height, click the street stretch, and save the displayed 1800 mm across start 0 to end 8000. | The dialog covered the entire first stretch; a Height intent event appeared. [08](08-height-dialog.png), [14](14-office-estimate.png) |
| 13 | Click the house-side stretch with Height and save 1800 across 0 to 5000. | The dialog displayed those values; subsequent events confirmed the full second stretch. [17](17-second-stretch-confirmed.png) |
| 14 | Choose Sits on, click the first stretch, and save the displayed soil selection. | A Base / soil event appeared; the office's missing-base count decreased. [14](14-office-estimate.png) |
| 15 | Apply Sits on / soil to the second stretch and save. | The missing-base warning disappeared; the second stretch later showed Base / soil. [17](17-second-stretch-confirmed.png) |
| 16 | Choose What was sold, click the first stretch, select Slat panel (M-SLAT), and save its full range. | The selector offered Slat, Legacy and Routed vinyl. The event became M-SLAT / 0-8000, but the separate Fence model summary continued to say no model was chosen. [09](09-model-dialog.png), [16](16-reopened-job.png) |
| 17 | Apply Slat panel to the second stretch and save its full range. | Its later event list showed M-SLAT / 0-5000. [17](17-second-stretch-confirmed.png) |
| 18 | Choose House and drag a rectangle inside the L, beside the vertical stretch. | A rectangle labeled House appeared, with a House entry in What's around it. [10](10-property.png) |
| 19 | Choose Street and drag a horizontal line outside the 8 m stretch. | A line labeled Street appeared on the opposite side from the house; the sidebar listed both context objects. [10](10-property.png) |
| 20 | Open Notes to record the driveway requirement. | A whole-project target, note field and Add button appeared under Attach annotation. [11](11-notes.png) |
| 21 | Enter Keep the gate clear of the driveway and click Add. | The exact note appeared as a project annotation, accompanied by an identifier and Interpret with AI. I treated the displayed note as recorded and did not request interpretation. [12](12-note-added.png) |
| 22 | Return to The job and scroll to For the office. | It said Nothing missing and ready to hand over, followed by a prompt to work out the fence for an estimate. [13](13-office-before-compute.png) |
| 23 | Click Work out the fence as prompted. | Posts, spans and a gate appeared in the plan and side view; the getting-started checklist completed. |
| 24 | Scroll to review the computed result and office summary. | The app showed 10 posts, 8 spans, 1 gate, 13000 mm, height 1800 mm, nothing flagged, and ILS 2,514.50. It explicitly described the estimate as not a quote or order. [14](14-office-estimate.png) |
| 25 | Reload to check whether the job remained saved. | The sample project's 9000/6000 mm fence returned. Salesperson remained selected, but several controls read Create, Topology & Strategy, Annotations and Generate strategy. [15](15-reloaded.png) |
| 26 | Select Dana's job again from the project dropdown. | The 8000/5000 mm job, house/street, saved events and generated result reappeared. |
| 27 | Select Salesperson again to restore the expected vocabulary. | New job, The job, Notes and What was sold returned. The first stretch retained its gate, height, soil and Slat events. [16](16-reopened-job.png) |
| 28 | Select run2 in This stretch and scroll to its events. | Height 1800 / 0-5000, soil and M-SLAT / 0-5000 were all present after reopening. [17](17-second-stretch-confirmed.png) |
| 29 | Open Notes once more to check persistence. | Keep the gate clear of the driveway was still displayed. [18](18-note-after-reload.png) |

## Task Outcomes and Save Confidence

| Task | Status | What I believed versus what the UI substantiated |
| --- | --- | --- |
| Find Salesperson experience | Complete, with reload friction | The simplified experience was found through the role selector. Reload required selecting it again to recover its vocabulary. |
| Create Dana's signed job | Complete after retry | The first Save did not substantiate the entered details. The second retained Dana Example, 12 Sample Road, Alex and the date displayed as 09/06/2026 after entering ISO 2026-09-06. The project could be reopened after reload. |
| Draw 8 m + 5 m L | Complete at visible-plan level | Both exact length labels and a horizontal/vertical L were visible. There was no numeric 90-degree confirmation inspected, so exact angular or structural-junction correctness is not independently established. |
| Record both heights and soil | Complete | Both explicit full-range 1800 mm events and soil events survived reopening; these were not left as unstated defaults. |
| Record Slat on both stretches | Complete in event lists; summary contradictory | Both M-SLAT assignments survived reopening. The Fence model summary still said no model was chosen and that it builds to a legacy panel. I could not reconcile those messages from the UI. |
| Add 1 m gate 2 m from the street start | Partial | The width was 1000 mm. The stored, visibly reported start was 1992 mm, 8 mm short. No tolerance was supplied, so I did not declare this exact task complete. |
| Supply house/street context | Complete as a schematic | House was inside the L and Street outside the horizontal stretch. No dimensions for the house or driveway were supplied, so the context was illustrative, not a measured site survey. |
| Add driveway note | Complete | The exact note was displayed after Add and still present after reopening. No visible feedback established that it had been interpreted or enforced in the layout. |
| Determine office readiness | Assessment complete; requested handover only partial | The app explicitly declared readiness and supplied an estimate. The office has a recorded job to review, but exact gate placement still needs correction and the model summary needs clarification. No send/submit action or office-receipt confirmation was observed in the Salesperson views used. This study does not establish delivery. |

## Highest-Impact Friction: Observed Evidence

1. **Precise gate placement depended on clicking the drawing.** The dialog exposed width and kit, but station was text. A second attempt showed 2000 mm in the pointer hint and 1992 mm in the dialog. This directly prevented exact completion of the supplied measurement. [07](07-gate-dialog.png), [16](16-reopened-job.png)
2. **The model summary contradicted the saved stretch assignments.** M-SLAT appeared for both full stretches while Fence model said no model was chosen, referred to a legacy panel and instructed me to use a Panel tab absent from Salesperson mode. That made it unclear whether the sold product was actually being used. [16](16-reopened-job.png), [17](17-second-stretch-confirmed.png)
3. **Reload did not restore the current job or consistent role vocabulary.** The sample fence returned; Salesperson was selected but several technical labels returned. Re-selecting the job and role recovered the work. This could initially look like lost work, although the subsequent UI established that the job and note persisted. [15](15-reloaded.png), [18](18-note-after-reload.png)
4. **Readiness was stronger than the task evidence.** Nothing missing and nothing flagged appeared with the 1992 mm gate and the contradictory model summary. I found no visible distinction between information being present, measurements matching the sale, and the office actually receiving the job. The estimate disclaimer was clearer. [14](14-office-estimate.png)
5. **Technical and incomplete wording remained in the novice workflow.** The model and street tools displayed hint.model and hint.street. The form included HVHZ, authority having jurisdiction and code edition above the office section. Notes used Attach annotation and a machine identifier. These were visible distractions while recording ordinary sales information. [10](10-property.png), [11](11-notes.png), [14](14-office-estimate.png)

The first job-details entry also disappeared during the create-and-fill sequence. This is a lower-confidence usability observation because automation entered the fields immediately after New job; the study does not establish how often a person would encounter it. A single re-entry succeeded. No cause is inferred.

## Useful Existing Features

- Salesperson mode reduced navigation to two tabs and supplied practical tool names such as Sits on and What was sold.
- The drawing hint explained typed metric lengths, enabling exact 8000 and 5000 mm stretches without prior CAD knowledge.
- Height and model dialogs defaulted to the whole selected stretch, reducing range entry for this uniform fence.
- The office checklist identified unstated height and soil separately from their defaults, then removed those requests after explicit entry.
- House and Street drags made the drawing readable as a property. Notes accepted the exact requirement without requiring AI interpretation.
- Event lists and the side view provided concrete dimensions. Reopening the job substantiated persistence, and the estimate clearly distinguished itself from a quote or order.

## Suggested UI Changes: Inferences, Not Tested Findings

1. Add an editable gate distance-from-start field beside width, identify the start on the plan, and use the same displayed position in the pointer hint, dialog and saved event. Support meters as well as millimeters.
2. Make Fence model summarize effective stretch selections, for example Slat panel on both stretches, and link directly to What was sold within Salesperson mode.
3. Restore the selected job and complete Salesperson vocabulary on reload. Show a clear saved state after New job and Save job details, and prevent transient initialization from accepting entries that will disappear.
4. Replace the single readiness assertion with an understandable review summary covering recorded information, outstanding measurement confirmation and office handover status. Show an explicit receipt state if delivery is part of the workflow; do not imply it from an estimate.
5. Replace untranslated hints and internal annotation identifiers with ordinary task language. Keep advanced site questions available under a clearly labeled office-review area so the salesperson can finish the supplied facts without guessing.

## Method Limits

This is one agent simulation, not evidence of human prevalence, speed, emotion, or preference. Browser automation makes fine pointer placement easier than it may be on a laptop; even that did not yield a saved 2000 mm gate here. Two gate-placement attempts and two job-detail entries were made; no blocked subtask received more than three attempts.

Two automation locators failed before performing their intended action: clicking the native Salesperson option directly and targeting the old project-name placeholder after the mode changed. Those are not counted as observed app actions or app defects. A visible-input inspection also printed those inputs' HTML attributes, and the Node REPL automatically echoed navigation-response metadata on reload. Neither was used to infer application behavior; no response body was read. All reported findings are grounded in the displayed UI and screenshots.

The app server was left running. Only this report and its screenshots were written in the assigned novice study folder. The browser was closed after the final note check.
