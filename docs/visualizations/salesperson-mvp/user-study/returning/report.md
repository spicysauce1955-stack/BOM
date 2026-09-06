# Returning salesperson: corrected sold-job sketch

Agent simulation, not a human participant. Conducted on 2026-09-06 at http://127.0.0.1:8822 using headless Chrome, Playwright, and a 1440x900 viewport. Only rendered UI, accessibility text, visible drawing geometry, pointer/keyboard actions, navigation, and refresh were used. No application source, prior reports, APIs, network response bodies, runtime state, or databases were inspected. No app fixes or server operations were performed.

## Outcome

Completed the requested revisions and verified their retention after refresh. The visible UI supports handing the recorded job to the office: it says "Nothing missing — this job is ready to hand over" and shows an estimate of ILS 2,550.50. No actual transfer to an office workflow was performed or substantiated. The estimate is explicitly described as neither a quote nor an order.

The final saved scope is street/run1 8400 mm at 1800 mm high, side/run2 5000 mm at 1600 mm high, soil base, Slat panel, and one 1000 mm gate starting at street station 3000 mm. The original promise and a separate anthracite clarification both survived refresh. The original inward-opening and garden-edging promises were verified as retained notes; their physical implementation was not established by the UI checks.

## Expectations, Actions, and Results

| Task | Initial expectation | Actual action and visible feedback | Completion and save confidence | Evidence |
| --- | --- | --- | --- | --- |
| Open sold job in Salesperson mode | Find the existing customer and familiar revision controls. | Job was already selected. Switched Hebrew to English and Everything to Salesperson. Drawing showed street/run1 8000 mm, side/run2 5000 mm; events showed gate 1000 mm at 2000 mm and street height 1800 mm. | Complete. Customer, address, salesperson Sam, and sale date were populated. | [Initial job](01-open-salesperson.png) |
| Preserve promise; clarify finish | Add a note without replacing what the customer already agreed. | Notes showed "Customer agreed anthracite finish. Gate should open inward. Retain existing garden edging." Added a whole-project clarification: "Clarification from corrected paper sketch: finish remains anthracite. The original customer promise remains unchanged." Both appeared as separate entries. | Complete. Initially appeared added; refresh later substantiated retention of both. | [Original](02-original-promise.png), [added](03-clarification-added.png), [retained](17-refreshed-promises.png) |
| Street 8.4 m; side stays 5 m | Editing street length should preserve the other stretch and gate position. | Clicking the street length opened a number field. Entering 8400 also changed side length to 5016 and gate start to 2100. Undid and redid that edit, then entered 5000 on the side length label. | Complete after correction. Initial edit was visibly incomplete for the requested scope. Final lengths survived refresh. | [Side effect](05-street-change-side-effect.png), [Undo](06-undo-restored.png), [Redo](07-redo.png), [refreshed scope](15-refreshed-street.png) |
| Side height 1.6 m | Height tool would revise the existing full-stretch height. | Height tool on side run opened a 0–5000 mm range at 1800 mm. Saved 1600. Later inspection showed both 1800 and 1600 height entries for that same range. Removed the old 1800 entry. | Complete after correction. Save initially suggested the new height was applied; the event list showed the old instruction remained too. Refresh substantiated one 1600 mm instruction across the full side. | [Height dialog](08-height-dialog.png), [duplicate heights](13-side-final-events.png), [retained side](16-refreshed-side.png) |
| Move gate to 3 m; keep width 1 m | Select the gate and edit its start distance and width. | Clicking its label in Gate mode opened no editor. Clicking its line opened Place gate at 2620 mm with width 1000 but no start-distance field. Canceled, positioned the pointer using the visible station readout, and opened placement at 3000 mm. Saved the 1000 mm gate and removed the old 2100 mm gate event. | Complete by replacement. Final event shows 1000 mm @ 3000; refreshed side view shows a single gate from 3000 to 4000. | [Placement controls](10-gate-placement.png), [replacement events](11-replace-gate-events.png), [single gate event](12-street-final-events.png), [final side view](19-final-side-view.png) |
| Correct a mistake with Undo/Redo | Recover the previous sketch if changing the street affects another measurement. | Undo restored 8000/5000 and gate start 2000. Redo restored 8400/5016 and gate start 2100. Corrected the side separately afterward. | Complete. Undo and Redo visibly restored the corresponding values. They did not themselves isolate the unwanted side effect. | [Undo](06-undo-restored.png), [Redo](07-redo.png) |
| Recalculate, refresh/reopen, assess handover | Revised geometry, notes, and estimate should agree and persist. | Work out the fence produced 13400 mm total, 10 posts, 8 spans, one gate, and ILS 2,550.50. Refreshed; inspected both runs and notes; reopened the job view and scrolled to the elevation. | Complete for visible persistence and readiness assessment. UI substantiated retained scope. No separate submission/receipt was observed. | [Recalculated](14-recalculated.png), [refreshed street](15-refreshed-street.png), [refreshed side](16-refreshed-side.png), [notes](17-refreshed-promises.png), [final view](19-final-side-view.png) |

## Recorded Decision Steps

30 meaningful UI decision steps. A step can include the typing/confirmation or scroll needed to carry out one decision; this is not a count of individual keystrokes, screenshots, or observation-only tool calls. No task timings or participant emotional quotations were collected.

1. Opened the assigned URL; existing customer job was selected, in Hebrew/Everything mode.
2. Clicked the language toggle; English labels appeared.
3. Selected Salesperson; navigation became The job and Notes.
4. Opened Notes; read the original customer promise.
5. Typed the clarification and clicked Add; saw both entries.
6. Returned to The job; existing sketch appeared.
7. Clicked the street line; selected-run handles and station feedback remained visible, without a length input.
8. Clicked the street length label; an 8000 number field opened.
9. Entered 8400 and pressed Enter; saw street 8400, side 5016, gate start 2100, and no calculated strategy.
10. Clicked Undo; saw street 8000, side 5000, gate start 2000.
11. Clicked Redo; after the UI updated, saw street 8400, side 5016, gate start 2100 again.
12. Clicked side length label, entered 5000, and pressed Enter; both requested lengths were then shown.
13. Selected Height; instruction changed to setting height for a range.
14. Clicked the side run; dialog showed run2, height 1800, range 0–5000.
15. Entered 1600 and clicked Save; dialog closed.
16. Selected Gate; instruction said to click a position on a run to place a gate.
17. Clicked the visible gate label; no editing dialog appeared.
18. Clicked the existing gate line; Place gate opened at station 2620, width 1000.
19. Canceled and moved the pointer along the drawing; visible station feedback showed 3000 mm.
20. Clicked that point; Place gate showed run1, station 3000, width 1000.
21. Saved and scrolled to Run events; the old and replacement gate entries were present.
22. Clicked the removal control beside the old 2100 gate; only 1000 mm @ 3000 remained.
23. Selected run2 in This stretch; saw both full-range 1800 and 1600 height events.
24. Removed the old 1800 height event; retained soil and the full-range 1600 event.
25. Clicked Work out the fence; calculated layout and ILS 2,550.50 estimate appeared.
26. Refreshed; revised lengths, street height, gate event, and estimate remained. Salesperson remained selected but several labels changed.
27. Selected run2 and scrolled to its events; only soil and 1600 mm over 0–5000 remained, alongside the handover message.
28. Opened Annotations, the renamed Notes tab; original promise and clarification both remained.
29. Reopened Topology & Strategy, the renamed job tab; revised drawing remained.
30. Scrolled the side view into view; inspected 8400 and 5000 totals, the lower side fence, and the single 1000 mm gate between 3000 and 4000.

Automation limitation: one attempted exact-text click resolved to a closed select option and timed out before any UI action. It is excluded from the decision count and is not treated as product friction. The subsequent drawing click used screenshot geometry. Exact gate placement benefited from fractional pointer coordinates derived from the visible grid and confirmed by the visible 3000 mm readout; this success should not be treated as evidence that a person can easily place a gate precisely with a mouse. There were three gate-target attempts: label, existing line, and corrected placement point.

## Highest-Impact Observed Friction

1. **A street-length correction also changed other sold dimensions.** Entering 8400 changed the side to 5016 and the gate start from 2000 to 2100. No explicit warning naming those changes was observed. The drawing exposed the side change, while the gate change required inspecting events. This required Undo/Redo and separate corrections. [Length change](05-street-change-side-effect.png), [Redo](07-redo.png).
2. **Saving a revised height retained the old height instruction.** Both 1800 and 1600 covered 0–5000 on run2. The lower dashed height was already visible, but the event list retained two competing instructions without explaining precedence. I initially treated Save as the revision being applied, then removed the old entry after inspecting the stretch. [Both entries](13-side-final-events.png).
3. **Precise gate revision required placement and deletion.** The encountered dialog offered width and kit, but no editable start station. Clicking the existing gate led to Place gate; exact positioning depended on the drawing readout, followed by removing the old event. I did not establish that no other editing route exists. [Placement](10-gate-placement.png), [events](11-replace-gate-events.png).
4. **Readiness wording was stronger than the current evidence.** "Nothing missing" remained visible when the strategy was absent and when both side-height instructions existed. The same region asked for calculation to see an estimate. I could only regard the requested revision as complete after inspecting the events and recalculating. [Premature readiness alongside conflicting entries](13-side-final-events.png).
5. **Refresh changed the salesperson vocabulary.** Salesperson stayed selected, but The job became Topology & Strategy, Notes became Annotations, Work out the fence became Generate strategy, and This stretch became Run editing. This required recognizing renamed destinations during the retention check. [Before](01-open-salesperson.png), [after refresh](15-refreshed-street.png), [renamed notes](17-refreshed-promises.png).

## Useful Existing Features

- Exact length entry on drawing labels enabled both measurements to be corrected without dragging endpoints repeatedly.
- Undo/Redo restored the observed length and gate values, making the unexpected change recoverable.
- Run events exposed precise gate width/start and height ranges, including the obsolete height that needed removal.
- Separate project/run notes preserved the original promise while allowing a clarification.
- The final whole-fence side view made gate position, both total lengths, and the lower side height inspectable together.
- Geometry, notes, calculated layout, and estimate survived refresh; the estimate's non-quote/non-order qualification was explicit.

## Inferred UI Suggestions

These are proposals based on the observations above, not claims about the implementation or results of testing alternative designs.

- When editing a connected length, preview every affected run and gate station. Offer an explicit choice to preserve the adjacent stretch length and the gate's absolute start distance.
- Let a salesperson select an existing height event and replace its value. When saving an overlapping range, ask whether to replace the existing instruction and show which value will apply.
- Give an existing gate an Edit control with numeric start distance and width, plus a visible run-start marker on the drawing.
- Distinguish "details recorded," "calculation needed," and "ready for office review." Surface unresolved or overlapping instructions beside the readiness result and show a saved confirmation for sketch edits.
- Keep Salesperson labels stable after reload. Descriptive stretch names such as Street and Side would also make the correction and final review easier to follow.

## Handover Judgment and Limits

I would hand the revised record to the office after the final checks: all requested values were visibly retained, a fresh estimate existed, and both customer notes remained. The blanket readiness message alone would not have been enough during editing. This judgment concerns the requested sales record; it does not certify structural suitability, turn the estimate into a quote, establish gate swing from the drawing, or prove an office recipient received anything.

Screenshots are stored beside this report. Some are full-page captures to preserve the drawing and below-fold event/readiness evidence together; browser interaction remained at 1440x900 throughout. Screenshot filenames describe capture stages and are not independent completion claims; in particular, 09 did not show a gate dialog and 13 still showed both side-height entries.
