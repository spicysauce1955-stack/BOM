# Salesperson simulation: source-driven entry

Independent AI user simulation, not a human participant. Scenario: after-sale entry by a nontechnical salesperson on a 1440 x 900 laptop viewport. App: http://127.0.0.1:8831. Only the rendered supplied source packet and visible app interactions were used. No source code, APIs, network responses, database, runtime state, other reports or hidden DOM were inspected. Browser closed at completion. No application fixes were made.

## Outcome

Partial completion. Created and reopened **Lee Example — 24 Sample Lane**. Customer identity, seller, sale date, measured L-shaped fence, heights, soil bases, Slat panel selections and four attributed source notes persisted. The requested gate station was not achieved exactly. Original documents were not attached. The later message was preserved as an unapproved request without changing the agreed height.

The source packet establishes 1.8 m on both stretches. Its later WhatsApp asks about 1.6 m on the side; no reply or amendment establishes acceptance. The photo description locates the driveway beside A but supplies neither a photo file nor a driveway width.

## Entered Versus Retained

| Item | Entry or intended value | Reopened result |
|---|---|---|
| Initial project name | `Lee Example - 24 Sample Lane` | Display became `Lee Example — 24 Sample Lane` after saving job details |
| Customer | `Lee Example` | Exact text retained |
| Address | `24 Sample Lane` | Exact text retained |
| You / seller | `Taylor` | Exact text retained |
| Sold on | `2026-09-06` | Displayed `09/06/2026` |
| Street A-B | Drawn horizontally left to right, intended 6000 mm | `run1 (6000 mm)` |
| Side B-C | Connected upward at right angle, intended 4000 mm | `run2 (4000 mm)`; L geometry retained |
| Street height | `1800`, start `0`, end `6000` mm | `Height intent · 1800 mm · 0–6000` |
| Side height | `1800`, start `0`, end `4000` mm | `Height intent · 1800 mm · 0–4000` |
| Base, both stretches | Saved displayed `soil` selection | `Base · soil` on both |
| Model, both stretches | Selected `Slat panel (M-SLAT)` over full default ranges | `M-SLAT · 0–6000` and `M-SLAT · 0–4000` |
| Gate width | Accepted displayed `1000` mm | `Gate · 1000 mm @ 1991` |
| Gate start | Intended 2000 mm from A; first placement dialog showed 1969, canceled; second showed 1991, saved | 1991 mm, not 2000; discrepancy explicitly recorded in run1 note |
| Gate hardware | Form default `Gate assembly 1000 mm`, displayed price ILS 185.00 | Default accepted for placement; specific kit not established by packet and not independently verified after reopening |
| Finish | `Anthracite finish; exact colour code not recorded.` in Source A note | Exact text retained; no structured finish entered |
| Gate operation | `Gate opens inward; hinge side not recorded.` in Source A; repeated unknown hinge in D | Text retained; no structured swing/hinge selection found in placement form |
| Requested side height | Quoted 1.6 m request, explicitly marked unapproved in run2 note | Text retained; structured side height stayed 1800 mm |
| Driveway | Beside A, identified as left/start endpoint of run1; keep gate clear; width unknown | Run1-linked text retained; no point anchor or driveway shape established |
| House and street | Relative placement described in Source B note | Text retained; no house/street geometry drawn |
| Unstated site conditions | Left unstated | Reopened page confirmed nobody had stated site conditions |

The generated result displayed 9 posts, 7 spans, 1 gate, 10000 mm of fence, height 1800 mm and an estimate of ILS 1,942.00. This was observed UI output, not a verified quote or customer promise.

## Exact Saved Source Notes

These four entries were read back after reload and explicit project reselection. The app surrounded each note with quotation marks and displayed project/run ownership. The note bodies below match the entered and retained text.

**Source A, whole project:**

> Source A - signed agreement summary: Customer: Lee Example. Address: 24 Sample Lane. Salesperson: Taylor. Sold on: 2026-09-06. Street stretch 6.0 m, connected side stretch 4.0 m, right-angle corner. Slat panel on both stretches, on soil, height 1.8 m. One 1.0 m pedestrian gate on the street stretch, starting 2.0 m from endpoint A. Anthracite finish; exact colour code not recorded. Gate opens inward; hinge side not recorded.

**Source B, whole project:**

> Source B - measured sketch, not drawn to scale: run1 is street stretch A-B, 6.0 m, left to right; run2 is side stretch B-C, 4.0 m, turns inward at B at a right angle. House inside the L; street outside A-B. Gate: 1.0 m wide, 2.0 m from A. Field note: keep the gate clear of the driveway. Do not infer any unlabelled distance from this schematic. Original rendered source packet held at file:///home/user/.superset/projects/BOM/docs/visualizations/user-study-round2/source-packet.html; original file not attached.

**Source D, run1:**

> Source D - photo description only: driveway beside endpoint A, the left/start endpoint of street stretch run1 (A-B). Keep the gate clear of the driveway. No photo file supplied or attached; driveway width unknown. Agreed gate start is 2000 mm from A; canvas placement retained 1991 mm, so exact placement needs correction before office handover. Gate opens inward; hinge side unknown.

**Source C, run2:**

> Source C - later WhatsApp, 2026-09-06 after signing: "Could we make the side fence 1.6 m, not 1.8 m? Please confirm whether that changes our agreement. Also keep the gate clear of the driveway." UNAPPROVED REQUEST: no reply or approved amendment supplied. Retain agreed 1800 mm on run2 pending confirmation; requested 1600 mm is not an agreed specification. Office to confirm effect on agreement and respond.

## Observed Gaps and Useful Features

- **Precise gate location:** The placement form exposed width and kit but only displayed station. The canvas cursor showed 2000 mm near the second attempt while the dialog showed 1991 mm. Exact agreement placement remains unresolved; no more than two placement attempts were made.
- **Original sources:** Notes retained transcription and a plain local file path. No upload/file-retention control was found in the visited salesperson pages. This does not establish that attachments are absent elsewhere. The original sketch itself and signed source artifact are not stored in this job. No photo was supplied or claimed attached.
- **Physical location:** Stretch-scoped annotations let the driveway note stay with run1. Identifying A within prose preserves the intended place for a reader, but it is not a verified point-level link. A/B/C are source labels explained in notes, not renamed canvas endpoints. House and Street drawing tools exist but were not exercised within the bounded study.
- **Agreement versus request:** Attributed free text made the distinction retainable. No dedicated pending request/approval mechanism was found in the visited view. `Interpret with AI` was visible but not used; the app showed `AI: stub`.
- **Readiness feedback:** Generated strategy said `nothing flagged`; the office checklist mentioned only missing house/street geometry. It did not visibly surface the annotated gate discrepancy or pending request. This observation does not prove how later office workflows handle them.
- **Model feedback conflict:** After both stretches retained M-SLAT, the separate Fence model panel still said `No model chosen — this project builds to the legacy panel` and referred to a Panel tab absent from the salesperson tabs. The run event lists and estimate offer more specific feedback, but a salesperson has to reconcile them.
- **Persistence/navigation:** Job data and notes survived reload and manual reopening. Reload selected the empty `untitled` project and changed labels to `Create`, `Topology & Strategy`, `Annotations`, etc., although the role dropdown still displayed Salesperson. Reselecting Lee's job recovered the data.
- **Useful existing features:** Dedicated job form, simplified salesperson tools, grid-based exact stretch lengths, explicit full-range height/model settings, per-stretch soil selection, readable run events, scoped notes, side elevation and a missing-information checklist all supported entry and checking.

## Automation Failures and Corrections

These are distinct from evidence of ordinary human difficulty.

- Initially targeted Salesperson as a button rather than a select. Then used the previous view's project-name placeholder after the salesperson role had changed it to `customer or address`. Visible inspection corrected targeting. An empty `New job` click created an unintended `untitled` project; it was left in place and not used as the sale record.
- A numeric-field sequence mistakenly counted the offscreen frost-depth input before the height popup fields. It entered an unsaved frost depth of 1800 and saved incorrect zero-height, zero-length end events (`0 mm · 6000–6000` and `0 mm · 4000–4000`). Discarded the unsaved site condition, saved the correct 1800 mm ranges, and removed both erroneous events with their visible delete controls. Final reopened screenshots confirm the corrected events and unstated site conditions.
- Discarding site changes scrolled the page, so one subsequent coordinate click missed the fence. Restored the viewport and completed the correction. No more than three attempts were used for the height operation.
- Rapidly entering four notes without waiting after each Add retained A and D but not B and C. This sequence is confounded by automation pacing and cannot establish a human data-loss rate or its cause. Re-entered B and C once each with visible-note confirmation before proceeding; all four survived reopening.
- Reload verification initially waited for old tab names and once matched an option rather than the rendered canvas label. Corrected the visible navigation and verified through screenshots and displayed note/run text. No persistence conclusion relies on those failed waits.

## Decision Record

27 meaningful decisions, with related field entry grouped and bounded retries included under their operation: (1) read supplied packet; (2) switch English; (3) select Salesperson; (4) create named job, including creation targeting retries; (5) save identity/date; (6) draw measured L; (7) place gate with two attempts; (8) enter heights; (9) save soil on both; (10) discard accidental site-condition draft; (11) retry height correction after scrolling; (12) correct both height ranges; (13) select Slat on both; (14) remove erroneous street-height event; (15) remove erroneous side-height event and open Notes; (16) add A; (17) first B entry; (18) add D; (19) first C entry; (20) retry B after visible inspection; (21) retry C with visible confirmation; (22) reload; (23) explicitly reopen named job; (24) verify all source notes; (25) verify job and street data; (26) generate and inspect fence/checklist; (27) verify side run and close browser.

## Screenshot Evidence

Primary evidence: [09-handover-check.png](09-handover-check.png), visually inspected after generation settled. It visibly shows the generated elevation, saved street events including the 1991 mm gate station, unstated site conditions, the missing-house/street checklist and estimate. [10-side-verified.png](10-side-verified.png) visibly confirms the reopened side's soil, 1800 mm height and M-SLAT range. These conclusions come from image inspection, not filenames.

All nine retained screenshots were inspected with view_image. Screenshots are viewport captures; the source packet's later message and photo description were read as rendered text below the first screenshot. Intermediate captures reused filenames while investigating; the descriptions here refer only to the final retained images. Capture 05 was removed because it caught scrolling and did not show a settled specification state. No office-receipt test was performed. Exploration ended at the 27 decisions recorded above.

| Screenshot | Visible evidence |
|---|---|
| [01-source-packet.png](01-source-packet.png) | Supplied signed summary and labeled measured sketch |
| [02-app-entry.png](02-app-entry.png) | English initial Everything view and unrelated sample layout |
| [03-job.png](03-job.png) | Named job, saved customer/address/Taylor/date, empty new layout |
| [04-layout.png](04-layout.png) | Exact 6000/4000 mm connected L |
| [06-notes.png](06-notes.png) | Four attributed notes visible before reload |
| [07-reopened-notes.png](07-reopened-notes.png) | Same four notes and project/run associations after reopening |
| [08-reopened-job.png](08-reopened-job.png) | Retained identity/date and geometry; conflicting global model text |
| [09-handover-check.png](09-handover-check.png) | Reopened street events, 1991 mm gate station, generated elevation, checklist and estimate |
| [10-side-verified.png](10-side-verified.png) | Reopened side events: soil, 1800 mm across 0–4000, M-SLAT across 0–4000 |

No completion/approval of the sale amendment or office handover is claimed. Exact gate placement, source-file retention and a stronger physical driveway association remain partial or unverified.
