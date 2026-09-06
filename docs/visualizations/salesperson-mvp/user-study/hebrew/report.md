# Hebrew-First Salesperson: Agent Simulation

This is an agent simulation, not a human participant. The session used only the rendered UI at http://127.0.0.1:8823 in headless Chrome, with a 1440x900 viewport and Hebrew/RTL throughout. No application source, previous findings, other participants' reports, APIs, network bodies, runtime state, or databases were inspected. No application changes were made. Screenshots are full-page captures; their heights exceed the browser viewport. No timings or emotional quotations are claimed.

## Initial Expectation

As a salesperson comfortable with ordinary forms but unfamiliar with CAD, I expected to enter the signed sale details, copy centimetre measurements from paper, choose a fence model, mark the existing wall and surroundings, and save a job that the office could confidently pick up. I interpreted the requested 180 cm as fence height on the existing 40 cm wall. The UI's later treatment of that height made this interpretation uncertain.

Requested job: customer ישראל לדוגמה; address רחוב הדוגמה 10; salesperson דנה; sale date 2026-09-06; one 600 cm fence, height 180 cm, on masonry with wall top 40 cm above ground; a 100 cm gate starting 200 cm from the fence start; Slat panel; house and street context; note לשמור על הקיר הקיים.

## Outcome by Task

| Task and expectation | Actual action and visible feedback | Outcome and saved/complete confidence | Evidence |
| --- | --- | --- | --- |
| Record the signed sale using ordinary Hebrew fields. | Created a project, chose איש מכירות, entered the four requested values and clicked שמירת פרטי העבודה. The project selector changed to the customer and address; missing-detail prompts disappeared. | Details complete and visibly persisted after reopening/reload. No signed-status field, signature capture, or signed confirmation was encountered. The initial project name containing עבודה חתומה did not substantiate a signed state. | [Initial](01-initial.png), [Details](02-cm-job-draw.png), [Reload](14-reloaded.png) |
| Copy 600 cm without converting to millimetres. | Clicked the units button once to ס"מ. Started a right-to-left fence, aimed left, typed 600 and pressed Enter twice. Result: run1 (600 ס"מ). | Length complete and persisted. Initially distrusted the hint, which said 420 = 42 metres while claiming centimetres; the resulting 600 cm label substantiated the actual entry. | [Hint](02-cm-job-draw.png), [Entry](03-enter-600.png), [Result](04-fence-created.png) |
| Place a 100 cm gate exactly 200 cm from start. | First placement missed the line. Second opened a dialog showing station 201.4 cm and width 100 cm. Cancelled and tried a slightly adjusted point; it still showed 201.4. Saved that width and approximate position. | Partial. The visible event and side-view station substantiate 100 cm at 201.4 cm, not the requested 200 cm. No editable station field appeared in the placement dialog. Stopped after three placement attempts. | [Miss](05-gate-attempt.png), [Dialog](06-gate-cm-dialog.png), [Side view](12-calculated-side.png) |
| Set 180 cm fence and existing masonry wall, top 40 cm above ground. | Saved height 180 over range 0-600; selected קיר בנוי in the base form. In the separate side-view field entered 40 and clicked אופקי. Events showed requested height 180, masonry base and a two-point base-top line. | Wall setting complete and persisted. Fence-height intent partial: after calculation the summary said height 140 cm, while the event still said requested 180 cm. The side drawing showed panels above the wall with their top near 180 on the ground-referenced axis. I could not call this a confirmed 180 cm panel above a 40 cm wall. | [Wall controls](07-wall-side-before.png), [40 cm](08-wall-40.png), [Calculated](12-calculated-side.png) |
| Choose available Slat panel. | Clicked מה נמכר, then the fence; selected פאנל שלבים (M-SLAT) over 0-600 and saved. Segment event showed M-SLAT, and the missing-model handover warning disappeared. | Segment assignment complete and persisted. Confidence weakened because the separate דגם הגדר section continued to say no model selected and referred to a legacy panel and a panel tab absent from salesperson navigation. | [Assignment and conflicting summary](09-house-street.png), [Reopened](13-reopened.png) |
| Show which side has the house and street. | Clicked polygon points plus Enter for house and line endpoints plus Enter for street; neither produced context. Retried each with a drag. A labelled house rectangle above the fence and street line below it appeared, along with matching sidebar entries. | Complete after two attempts per context tool; persisted. No precise property dimensions were supplied, so context is schematic. | [Unsuccessful clicks](09-house-street.png), [Successful drags](10-context-drag.png), [Calculated context](12-calculated-side.png) |
| Preserve the existing-wall instruction. | Opened הערות, left scope at כל הפרויקט, typed לשמור על הקיר הקיים and clicked הוספה. The exact note appeared beside an annotation identifier and English project/user text. | Note complete and visibly persisted on revisiting after reload. I did not use פירוש עם AI; the visible note alone does not substantiate an enforced construction constraint. | [Added note](11-note.png), [Reloaded note](15-note-reloaded.png) |
| Save, reopen, and determine readiness for handover. | Calculated, checked side view, clicked save job details, selected the sample project, selected this customer again, and reloaded. All requested entries except exact gate placement remained visible. The UI said לא חסר דבר — העבודה מוכנה להעברה and estimated ₪1,037.00, explicitly not a quote or order. | Persistence complete by visible verification. Actual handover/signing unconfirmed; task overall partial because gate position and height intent remain unresolved. I initially had a reason to believe the checklist meant complete, but the dimensions and estimate disclaimer did not substantiate a fully agreed signed job. | [Readiness](12-calculated-side.png), [Reopened](13-reopened.png), [Reloaded](14-reloaded.png) |

## Recorded Decision Steps

30 meaningful decision steps were performed. A step groups one task decision and its ordinary field entries, clicks or drawing gesture; it is not an individual keystroke count. Screenshot capture and reading visible feedback are evidence collection, not additional task decisions.

| # | Observed UI actions | Resulting visible feedback |
| --- | --- | --- |
| 1 | Opened the assigned URL. | Hebrew default sample, millimetres, role הכול, job form and drawing tools. |
| 2 | Entered עבודה חתומה - ישראל לדוגמה as a new project name and clicked יצירה. | New empty project selected. |
| 3 | Selected איש מכירות. | Navigation reduced to העבודה and הערות; tool wording changed to salesperson language. |
| 4 | Clicked the units button. | Header and dimension labels changed to ס"מ. |
| 5 | Entered customer, address, דנה and 2026-09-06; clicked save job details. | Customer/address became project selector label; missing-detail prompt cleared. |
| 6 | Selected שרטוט גדר and read its hint. | Keyboard length-entry instructions appeared, including inconsistent 420 = 42 m example. |
| 7 | Clicked a start point on the right, aimed left, typed 600, pressed Enter twice. | One run1 labelled 600 cm. |
| 8 | Selected שער and clicked near the intended location, below the fence line. | No gate form or new event appeared; this was a placement miss, not evidence of a broken tool. |
| 9 | Retried on the line near one-third of its length from the right-hand start. | Gate form: station 201.4 cm, width 100 cm; kit option retained 1000 mm in its product name. |
| 10 | Cancelled and clicked a slightly adjusted point. | Gate form still said station 201.4 cm. |
| 11 | Saved the displayed 100 cm gate. | Event: שער, 100 cm @ 201.4; gate added to plan. |
| 12 | Selected גובה, clicked the fence, entered 180 over 0-600 and saved. | Requested-height event appeared and missing-height prompt cleared. |
| 13 | Selected מונחת על and clicked the fence. | Surface form offered ground, concrete and masonry wall. |
| 14 | Selected קיר בנוי, saved, and brought side-view controls into view. | Masonry event and a field for base-top height above ground appeared. |
| 15 | Filled that field with 40 and clicked אופקי. | Field displayed 40; base-top event had two points; red line appeared above ground. |
| 16 | Selected מה נמכר. | Help area displayed literal hint.model. |
| 17 | Clicked the fence, selected פאנל שלבים (M-SLAT), retained 0-600 and saved. | M-SLAT event appeared; separate model summary still said no model. |
| 18 | Selected בית, clicked four rectangle corners, pressed Enter. | No house shown; tool hint was hint.house. |
| 19 | Selected רחוב, clicked two endpoints, pressed Enter. | No street shown; context warning remained; tool hint was hint.street. |
| 20 | Retried בית with a diagonal drag. | House rectangle and sidebar item appeared. |
| 21 | Retried רחוב with a horizontal drag below the fence. | Street line and sidebar item appeared; handover panel now said nothing missing. |
| 22 | Opened הערות. | Project-scope note form with הוספה appeared. |
| 23 | Entered לשמור על הקיר הקיים and clicked הוספה. | Exact note appeared with project/user metadata and an AI interpretation button. |
| 24 | Returned to העבודה and clicked חשבו את הגדר. | Calculation subsequently produced six posts, four spans, one gate and an estimate. |
| 25 | Brought side view into view and scrolled to inspect it and handover text. | Summary height 140 cm versus requested 180 event; wall field 40; gate station 201.4; estimate ₪1,037.00; ready-to-transfer text. |
| 26 | Clicked שמירת פרטי העבודה again. | Job fields remained populated; no whole-job signed or handover confirmation appeared. |
| 27 | Selected פרויקט לדוגמה in the project selector. | Selector visibly changed to the sample; no sample edits were made. |
| 28 | Selected ישראל לדוגמה — רחוב הדוגמה 10 again. | Saved job, geometry, context, height/base/model events and estimate reappeared. |
| 29 | Reloaded. | Job data, centimetres and salesperson selection persisted; navigation/tool labels changed back to more technical wording, including טופולוגיה ואסטרטגיה and חישוב אסטרטגיה. |
| 30 | Opened הערות again. | Exact Hebrew note remained visible after reload. |

## Five Highest-Impact Observed Friction Points

1. **Height reference is unclear at the point of entry.** The form said גובה הגדר לאורך הקטע and גובה (ס"מ). Saving 180 with a 40 cm wall produced a summary height of 140, while the event retained 180. This directly affects what the salesperson believes was sold. The observed UI is consistent with a top elevation of 180 above ground, but that interpretation is an inference, not a verified implementation rule. [Evidence](12-calculated-side.png)
2. **An exact paper gate offset was not discoverable as an editable value.** The gate dialog exposed width but displayed station as text. Three placement attempts ended at 201.4, and the final side view confirmed that discrepancy. The first miss was my pointer placement; the inability to type 200 was the relevant workflow limitation encountered. [Evidence](06-gate-cm-dialog.png)
3. **Missing Hebrew hints made context drawing trial-and-error.** hint.house and hint.street gave no instruction to drag, so I first reused the fence's click/Enter pattern unsuccessfully. Dragging worked. hint.model also appeared instead of a useful instruction. These are observed localization gaps, without any source-level diagnosis. [Before](09-house-street.png), [After](10-context-drag.png)
4. **Model and completion feedback conflict.** A persisted M-SLAT event coexisted with a summary saying no model selected. The handover checklist said nothing was missing even though the UI could not substantiate the requested gate offset or the salesperson's height interpretation. The estimate was explicitly not a quote or order; no signed or transferred state was encountered. [Evidence](13-reopened.png)
5. **Centimetres and salesperson language are not fully consistent.** The drawing hint's 420 = 42 m example contradicted the cm label, although entering 600 correctly yielded 600 cm. The date visibly rendered as 09/06/2026 despite the entered ISO value 2026-09-06, leaving day/month interpretation ambiguous to this Hebrew-first role. After reload, איש מכירות stayed selected but העבודה became טופולוגיה ואסטרטגיה and simple tool labels became technical ones. [Units/date](02-cm-job-draw.png), [Reload](14-reloaded.png)

## Direction and Useful Existing Features

The interface stayed Hebrew/RTL: form labels and text were right-aligned, with navigation and the drawing toolbar on the right. I could enter the requested Hebrew names and note without a visible character-order problem. The date used left-to-right numeric presentation, and identifiers such as run1, M-SLAT, POST-M, project and user remained English. After drawing right-to-left, the plan's start was at the right, but the side view's station zero was at the left. This was observable; a labelled start marker would make the relationship easier to follow. Generated plan labels clustered over the short fence, while the side view separated the dimensions more clearly.

Useful features were the global cm toggle with converted field labels, precise keyboard entry for fence length, the ordinary customer form and descriptive project selector, salesperson-specific tool wording before reload, explicit wall-top-above-ground label, persistent segment event list, schematic house/street tools once their gesture was discovered, side-view gate dimensions, a checklist that removed answered prompts, and a clear estimate-not-order disclaimer. Reopening and reloading gave tangible evidence that the entries and note were saved. Undo/redo and event deletion controls were visible but were not used or evaluated.

## Inferred UI Suggestions

These are proposed improvements derived from the observations, not additional observed behavior or claims about implementation.

- Label height as either panel height above wall or total top height above ground, show both values together, and annotate the side view with wall 40, panel 140 and total 180 for this recorded state. This would expose the interpretation before calculation or handover.
- Add an editable gate field labelled מרחק מתחילת הקטע (ס"מ), plus a visible תחילת הקטע marker in both views. Keep width and start offset in the same placement form.
- Replace untranslated context/model hints with Hebrew instructions that explicitly identify drag versus click. Correct the cm arithmetic example and render the sale date unambiguously for Hebrew readers.
- Show the effective segment model in the model summary and provide a saved-state indicator covering geometry, context and notes. Distinguish information completeness, measurement confirmation, signed sale and actual handover in the visible status wording.
- Preserve the selected salesperson vocabulary after reload, and let the handover panel expose unresolved dimension confirmation alongside missing-data prompts.

## What Remains Before Handover

The visible job is saved, but I would not represent the requested signed job as fully completed. The gate must be confirmed or corrected from 201.4 to 200 cm. The salesperson and office must resolve whether 180 cm means panel height above the wall or total height above ground; the current calculated display says 140 cm panel height with a 40 cm wall. The Slat assignment is visible in the segment event, but its conflicting summary needs reconciliation for a reader relying on that summary. The existing-wall note is saved as text; preservation of the wall is not visibly confirmed as an enforced decision.

No site exposure, authority or other site facts were supplied, and I left them blank rather than inventing them. The UI explicitly said rules depending on these facts would abstain; the office must determine which facts are relevant. The estimate is not a quote or order, and no signature or completed-transfer confirmation was encountered in this bounded salesperson workflow. The ready-to-transfer sentence therefore substantiates only the UI's checklist assessment, not an independently confirmed signed handover.
