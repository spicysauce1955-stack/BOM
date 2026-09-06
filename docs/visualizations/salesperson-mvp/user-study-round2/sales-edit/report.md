# Fence AI salesperson simulation: signed amendment

Outcome: PARTIAL. The amendment ranges and explanatory note were saved and survived reload. The requested effective fence could not be calculated: the offered Routed vinyl model rejects the 1400 mm height because of factory-routed post holes. Reload restored an earlier calculated strategy that still draws the street panels at 1800 mm, beside the correctly amended events. Do not treat that displayed strategy or estimate as fulfillment of the amendment.

This was an independent automated salesperson simulation, not a human participant study. Only the assigned app at http://127.0.0.1:8832 was navigated. Chrome/Playwright used a 1440 x 900 viewport. App evidence came from rendered text, normal UI interactions, screenshots, and a native browser alert. All ten saved screenshots were opened with view_image and inspected. No app source, previous reports, APIs, databases, hidden DOM, or response bodies were consulted. No application fixes or server changes were made. Browser and automation session were closed.

## Job and original promise

The app opened on Example customer, 18 Example Street. The original plan identified the street as run1, 8000 mm, left to right toward the corner; the side was run2, 5000 mm. The gate occupied stations 2000-3000 mm on run1. Initial events showed 1800 mm over 0-8000 and soil. The project model was Slat panel, M-SLAT. Customer fields showed Example customer, 18 Example Street, salesperson Sam, and sold date 09/06/2026; none was edited.

Original run1 note, preserved verbatim after reload:

> Customer agreed anthracite finish. Gate should open inward. Retain existing garden edging.

## Entered Versus Retained

| Item | Exact entry/action | Visible retained result after reload |
| --- | --- | --- |
| Street lower section | Height 1400; start 3000; end 8000, in mm | Height intent: 1400 mm, 3000-8000 |
| Street first section | Removed original 1800 mm, 0-8000 event after it overrode the intended result; entered height 1800, start 0, end 3000 | Height intent: 1800 mm, 0-3000; old full-run event absent |
| Street last 2 m model | Selected Routed vinyl privacy fence (M-VINYL); start 6000; end 8000 | Fence model: M-VINYL, 6000-8000 |
| Street first 6 m | Left project Slat default unchanged; no additional model event | M-SLAT remains the project model; only the final 2 m has an override |
| Street and side lengths | No length or geometry edits | Plan labels remain run1 (8000 mm), run2 (5000 mm); total 13000 mm |
| Gate | No edit | Gate: 1000 mm @ 2000; side view shows gap from 2000 to 3000 |
| Side height/base | No edit; selected run2 after reload to inspect events | Height intent: 1800 mm, 0-5000; Base: soil; no model override listed |
| Street base | No edit | Base: soil |
| Amendment note | Added at whole-project scope, exact text below | Entire text retained; original separate run1 promise also retained |

Exact entered amendment note, matched against rendered text after reload:

> SIGNED amendment: On the 8 m street stretch (run1), measured from its original start, stations 0-3000 mm remain 1800 mm high and stations 3000-8000 mm are 1400 mm high. Stations 0-6000 mm remain Slat; stations 6000-8000 mm use Routed vinyl privacy fence (M-VINYL), available in the model selector. The side stretch (run2) remains 5000 mm long and 1800 mm high, Slat. Keep soil base, all lengths, and the 1000 mm gate starting at station 2000 mm unchanged. Original customer promise remains: Customer agreed anthracite finish. Gate should open inward. Retain existing garden edging.

## Effective Result and Blocker

Adding the 1400 mm range initially appended an event alongside the original 1800 mm event over the entire street. Calculation succeeded but the solid side-view panels remained at 1800 mm across the street. A dashed lower intent line was visible from 3000 to 8000. This made event retention insufficient evidence of effective compliance. Screenshot 06 shows the discrepancy.

I removed the overlapping original height event and entered 1800 mm specifically over 0-3000. The uncalculated side view then showed the requested dashed height steps: 1800 for the first 3 m, 1400 for the remaining 5 m, and 1800 on the side. Screenshot 07 shows these corrected events and intent lines, not a successful calculation.

Three actual calculation attempts with the corrected ranges did not produce a new strategy. On the last attempt, after reload, I captured this native browser alert through the normal browser dialog interface:

> The panel at station 8000 puts its rails at 150, 1250, and the posts of model M-VINYL@v1 are routed at 150, 1650; 150, 1950. The holes are punched at the factory, so this fence cannot be assembled — change the height, the rail count, or the post product.

The alert was dismissed. Its exact text is transcribed here; no screenshot of the native alert was captured. Earlier alerts, if any, were automatically dismissed by Playwright before a dialog handler was installed, so the first two attempts alone cannot establish their error text.

After reload, the saved events were correct, but an earlier strategy returned: 11 posts, 9 spans, 1 gate, 13000 mm, summary height 1800 mm, estimate ILS 2,605.50. The side view again showed solid panels at 1800 with the lower dashed intent line. The first calculation had visibly introduced vinyl post products and a station boundary at 6000, but no valid calculated result combining vinyl and the corrected lower height was obtained. The reloaded calculation therefore remains outdated relative to the saved amendment. Screenshots 08 and 09 show this state.

No substitute model, height, post, rail configuration, or altered customer promise was entered. No live quote or order was produced. The initial estimate was ILS 2,514.50; the later ILS 2,605.50 belongs to the earlier successful calculation and is not a verified amendment estimate.

## Decision Log

27 meaningful decisions, grouping field entry and its save as one decision; observation-only captures and harness cleanup are not additional app decisions.

1. Open assigned URL and identify the already-selected Example job.
2. Switch from Hebrew to English; attempted a salesperson button that did not exist.
3. Inspect header and select Salesperson in the actual role dropdown.
4. Open Notes to inspect the original customer promise.
5. Return to The job, choose Height, and click the street stretch.
6. Enter and save 1400 mm for 3000-8000; inspect events and side intent lines.
7. Choose What was sold and attempt to return to the plan; first coordinate click did not open the editor.
8. Scroll the header into view and click the street again; inspect offered models.
9. Select Routed vinyl privacy fence and save 6000-8000.
10. Open Notes and add the exact whole-project amendment note.
11. Return to The job and calculate.
12. Inspect calculated side view and events; identify overlapping height intent versus solid panels.
13. Delete the original 1800 mm, 0-8000 height event.
14. Reopen street Height and save 1800 mm for 0-3000.
15. Attempt calculation with corrected nonoverlapping ranges.
16. Inspect corrected side intent and events; no strategy present.
17. Retry calculation; no new strategy appears.
18. Reload to verify saved state and prepare one final calculation attempt.
19. Attempt the prior salesperson calculation label; it is no longer present after reload.
20. Inspect rendered labels and reselect Salesperson to restore salesperson wording.
21. Make the third actual calculation attempt; read and dismiss the factory-hole mismatch alert.
22. Inspect and capture reloaded plan, lengths, gate, and restored strategy summary.
23. Scroll to run events and select run2.
24. Verify run2 retains 1800 mm over 0-5000 and soil, with no model override.
25. Return event selection to run1.
26. Inspect and capture reloaded side view and amended street events together.
27. Open Notes and verify both exact notes after reload.

## Useful Features and Friction

- Explicit numeric start/end fields allowed precise ranges without dragging approximate plan points. Millimetre units were visible.
- The plan, station-labelled side view, and run-event list together exposed an error that a saved note alone would not reveal.
- Model selection offered Legacy panel, Slat panel, and Routed vinyl privacy fence. Routed vinyl was available and accepted as a saved event. The salesperson editor did not show an explicit publication badge, so publication status was not independently established through a catalog page.
- Notes supported separate project and run scopes and preserved the original promise without replacement. AI interpretation was available but was not invoked.
- Overlapping height events were accepted without a visible precedence explanation. A later saved height event did not override the existing full-run height in the successful calculation. Explicitly replacing the full-run event was necessary to express the intended disjoint ranges.
- The vinyl mismatch alert is useful validation, but its suggested rail/post changes require knowledge beyond this salesperson scenario and authority beyond the signed amendment.
- The page still said "Nothing missing — this job is ready to hand over" and the restored strategy said "nothing flagged" despite the calculation blocker. No visible outdated-strategy warning appeared in the captured reloaded view.
- The global Fence model panel continued saying the project builds to Slat, without summarizing the vinyl range. It directed the salesperson to a Panel tab that was not present in the salesperson navigation.
- The model tool displayed the untranslated text "hint.model". Reload changed the navigation/action wording to "Topology & Strategy", "Annotations", and "Generate strategy" until Salesperson was selected again.
- No signed-document attachment or amendment approval workflow was established in the inspected screens. The scenario's signed amendment was recorded as a note; this study did not independently verify a signature.

## Automation Limitations

These are distinct from product behavior: the first role lookup incorrectly treated a dropdown option as a button; one scroll failed when the page rerendered after saving and succeeded on retry; a coordinate click before the plan was scrolled into place had no editor effect; the post-reload calculation-label lookup timed out before role reselection; Playwright initially auto-dismissed native alerts; the first browser-close expression had a syntax error and was corrected successfully. No unintended app field change was observed from these failures. Undo was visible but not used; the mistaken overlapping height was corrected by removing its original event and entering the proper range.

The initial REPL navigation expression inadvertently echoed a Playwright response object. No response content was queried or used as evidence, and subsequent navigation return values were suppressed. All reported app findings derive from the visible UI evidence described above.

## Screenshots

Each image was captured after the relevant visible screen had settled and then actually inspected. Filenames describe context, not proof of success.

1. [Existing job](01-existing-job.png): initial English Everything view, customer, 8 m street, 5 m side, gate, Slat default.
2. [Original promise](02-original-promise.png): salesperson Notes and original run1 wording.
3. [Height editor](03-height-range-entry.png): height/start/end controls, initial values 1800/0/8000 before entry.
4. [Saved overlapping height](04-height-saved-events.png): retained 1400/3000-8000 alongside original full-run event; dashed intent lines.
5. [Model editor](05-model-range-entry.png): model range controls before selection; visible default Legacy. Offered vinyl option was observed in rendered selector text, not pictured expanded.
6. [First calculated side](06-calculated-side-events.png): vinyl event and lower height event retained, but solid panels remain 1800.
7. [Corrected intent](07-corrected-side-events.png): disjoint height events and stepped dashed lines; no strategy, so not an effective calculated result.
8. [Reloaded plan](08-reloaded-plan.png): unchanged geometry and restored earlier strategy.
9. [Reloaded side/events](09-reloaded-side-events.png): exact saved amendment ranges beside outdated solid panel heights and estimate.
10. [Reloaded notes](10-reloaded-notes.png): original promise and complete amendment note both preserved.
