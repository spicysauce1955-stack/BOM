# Existing Salesperson UI Audit

Date: 2026-09-06. Scope: inspect the actual application and correct the visualizations, not implement a new sales UI.

## Method

- Ran the repository application on port 8813 against a separate temporary SQLite database with its seeded catalog and stub AI adapter.
- Used Chrome through Playwright at 1600 x 1000. Entered and modified the example job through visible UI controls; read state/API data to verify the results.
- Original customer projects and the existing server on port 8000 were not edited.
- Screenshots in `sales-ui-evidence/` are actual browser captures, not reconstructed mockups. Full-page captures include content below the initial viewport.
- Small `*-dialog.png` captures show forms reopened for inspection and then cancelled. Their defaults and clicked stations are not a readback of the previously saved event. The full-screen captures record the original entry sequence.
- The earlier speculative `sales-workspace.html` was replaced with a screenshot walkthrough. `sales-handover.html` now maps the existing workflow and labels the unimplemented transfer boundary.

## Verified Interactions

| Area | Action and observation |
| --- | --- |
| Mode | Switched to Salesperson. The job and Notes remain; engineering tabs including Panel and BOM are hidden. |
| Identity | Created a job and saved customer, address, salesperson and signed date. Header label changed. |
| Drawing | Clicked a start, aimed, typed 5000, pressed Enter and Finish run. Added a 3000 mm run from the shared corner. |
| Editing | Clicked a run label and changed 5000 to 5500 mm. Undo restored 5000; redo restored 5500; undo returned the example to its original geometry. |
| Bends | Dragged a hollow midpoint handle to insert an interior vertex, then undid it. |
| Property | Dragged a house rectangle and street line; named the house. Both persisted. |
| Height | Saved 1800 mm on run1 and 1600 mm on run2 using the Height popover. |
| Base | Saved masonry wall on run1 and soil on run2. The base form also exposes post orientation. |
| Model | Used What was sold to assign the seeded M-SLAT model to both runs. Events contain the assignments. |
| Gate | Placed a 1000 mm gate at station 3000 mm using GATE-KIT-1000. The form provides width and kit, not opening direction. |
| Ground | Used Slope at the far corner to save 300 mm ground elevation. |
| Side view | Set a 400 mm base-top height, added a step, undid it and applied Horizontal. Match-neighbour controls were inspected but not exercised. |
| Site | Saved exposure B, HVHZ false, frost depth 0 and an example jurisdiction. Code edition remained unstated. |
| Notes | Added a verbatim run1 note. Added `height 1600` on run2; interpreted it with the stub and explicitly confirmed the height intent. |
| Generation | Work out the fence produced a plan/side view, warnings and a qualified estimate of 1481.00 ILS for this seeded example. |
| Handover | For the office reached Nothing missing. No submit/inbox/acceptance action exists in this salesperson flow. |
| Preferences | Switched mm to cm and back; switched to Hebrew RTL and back. |
| Persistence | Reloaded and reopened the project; verified identity, runs, landmarks and the first saved note persisted. |

## Observed Gaps

The visualization now groups all findings as B01-B04 (reproduced bugs), G01-G03 (MVP gaps), and U01-U06 (proposed UI improvements). The additional readiness checks below were performed after the initial screenshot walkthrough.

## Additional Readiness Reproductions

### B01: A failed checklist request displays ready

- Started the repository application against the same isolated temporary database.
- Intercepted `**/api/projects/*/handover` in Playwright and returned HTTP 500 with a simulated error response.
- Created an empty project through the visible New job control.
- Read the rendered panel and actual run count. The project had **0 runs**, while the panel displayed **Nothing missing — this job is ready to hand over.**
- The same panel also said no estimate was available because no model was chosen.
- Cause: the request failure sets `cache = null`; rendering uses `cache?.gaps || []` and interprets the empty list as ready. See `js/handover.js:59` and `:85`.
- Proposed fix: distinguish loading, failed/unavailable and successfully checked states. Only a successful current-job response may establish readiness.

### B02: Partial specification coverage passes

Used the existing `_complete()` fixture in `tests/report/test_handover.py` for two independent, direct domain-function checks:

| Fixture change | Actual result |
| --- | --- |
| Shorten the height event to cover only 0-1000 mm of the 5000 mm run | `handover_gaps(project)` returned `[]` |
| Remove the project model and add a model event covering only 0-1000 mm | `handover_gaps(project)` returned `[]` |

The first case leaves four metres without an explicit height; the second leaves four metres without an assigned model or project default. The current checks test event existence rather than full coverage. See `report/handover.py:84` and `:95`.

These results are direct function reproductions, not browser screenshots. The coverage strip in the visualization is an explanatory diagram of the tested inputs.

## Other Observations

1. **Misleading model summary.** The project-level model summary says no model chosen and directs the salesperson to Panel, which this role hides. Per-run selection works through What was sold. Even with both example runs assigned M-SLAT, the project-default summary still says no model chosen. See `22-model-summary.png` and `23-events.png`.
2. **Role wording after reload.** Salesperson remains selected and role visibility persists, but static labels revert to Topology & Strategy, Annotations, Generate strategy and other generic wording. Switching role or language reapplies sales wording. `app.js` initializes i18n before role; `initRole()` does not call `applyStatic()`, whereas `setRole()` does. See `13-generated.png` for the observed screen and `17-overview.png` after reapplying the role.
3. **Source-package gap.** No visible file-upload control was found in Salesperson mode. The current checklist reached ready without a signed contract, original drawing, photo or message attachment. Readiness must not be visualized as evidence-package validation.
4. **Handover lifecycle gap.** The current role exposes a derived checklist and optional estimate, not a submitted version, office inbox, acceptance or clarification loop. Those were proposals in the earlier visualization.
5. **Technical information remains visible.** Site conditions, base orientation, raw event terminology and AI intent names remain in the salesperson UI. The generated summary also links to a priced BOM despite the BOM tab being hidden. The walkthrough records these surfaces without deciding whether to remove them.
6. **Ready with a warning.** The example's adjoining wall and soil bases caused a `node_surface_disagreement` warning while the handover checklist said ready. That warning and checklist answer different questions; neither should be presented as office approval.

## Proposed UI Improvements

These recommendations are not implemented features or ratified scope:

- **U01: Visible handover status.** Put a compact status near job identity rather than relying on a panel below the long sidebar.
- **U02: Actionable missing items.** Name/select the affected stretch and open its editor from the checklist.
- **U03: Readable stretch summary.** Present saved height, base, model and gate information together with direct editing actions.
- **U04: Ownership of technical inputs.** Decide which site facts belong to sales and which construction decisions belong to the office; simplify exposed jargon accordingly.
- **U05: Saved values versus defaults.** Distinguish adding a new event from editing an existing one. The Height popover seeds 1800 mm and Base initially selects soil; reopened inspection dialogs were cancelled, not used to demonstrate data loss.
- **U06: Pricing after signing.** Define the internal purpose of the estimate and adjust its prominence; live quoting remains outside the MVP.

Suggested sequence: fix B01-B04, agree the source package and office transfer, then improve the existing screen in small reviewed changes.

## Sources

- `src/fenceai/web/static/index.html`: header, tabs, tool rail, canvas, side view and side-panel layout.
- `src/fenceai/web/static/app.js`: startup order and header wiring.
- `src/fenceai/web/static/js/role.js`: sales visibility and vocabulary refresh.
- `src/fenceai/web/static/js/editor.js`: canvas gestures, length editing and event popovers.
- `src/fenceai/web/static/js/job.js`: actual four job fields and explicit save.
- `src/fenceai/web/static/js/context.js`: house/street naming and removal.
- `src/fenceai/web/static/js/profile.js`: base-top/step/level controls.
- `src/fenceai/web/static/js/panel.js`: project model summary and Panel-tab instruction.
- `src/fenceai/web/static/js/site.js`: technical site fields and explicit unknown values.
- `src/fenceai/web/static/js/tabs.js`: annotation target, verbatim text, interpretation and confirmation.
- `src/fenceai/web/static/js/handover.js` and `src/fenceai/report/handover.py`: completeness and estimate semantics.
- `docs/superpowers/specs/2026-09-04-sales-mvp-design.md`: existing product scope.

## Limits

This is a focused interaction audit, not a full regression suite, domain-accuracy review, or exhaustive test of every catalog model. The temporary seeded catalog does not establish the contents of the user's working catalog. Live AI, every profile gesture, and real office operations were not tested. No application fixes were made as part of this visualization task.
