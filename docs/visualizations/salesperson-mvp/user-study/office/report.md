# Office handover usability study

This is an agent simulation, not a human participant. Study date: 2026-09-06. Persona: a technically comfortable office recipient, not a developer, receiving a salesperson's saved job.

Session used only http://127.0.0.1:8824, headless Chrome with --no-sandbox, a fresh persistent office profile, and a 1440 x 900 viewport. Evidence came from rendered text, visible form values, screenshots, and normal UI interaction. No application source, earlier findings, other participants' reports, APIs, network bodies, runtime state, or databases were inspected. No server was started or stopped. Sold specifications were not edited. The only content added was the requested clarification comment.

## Outcome

**Partial handover review; office acceptance blocked.** I could reconstruct the recorded fence, customer, salesperson, date, relative site layout, gate dimensions, and sales notes. I could not substantiate a signed sale, identify a submitted version versus a draft, or find a visible acceptance workflow. A clarification was saved and survived reload, but delivery to sales was not substantiated.

My initial expectation was a saved handover containing the sold configuration, sales identity, approved drawing/contract, outstanding questions, and a way to accept it or return it to sales. The assignment supplied the claim that the sale was signed; the app did not independently substantiate that claim.

## Task evidence

| Task and initial expectation | Actual action and resulting visible feedback | Outcome and completion belief | Evidence |
| --- | --- | --- | --- |
| Open the named job in English and use Office mode. Expected an identifiable saved job. | Opened the assigned URL. The example customer job was already selected, in Hebrew and Everything mode. Switched language to English and selected Office. Job fields showed Example customer, 18 Example Street, Sam, and Sold on 09/06/2026 (the visible date control's value was 2026-09-06). | Complete for locating the recorded job and sales identity. Populated fields supported an existing saved record, not signature or submission. I did not press Save job details. | [Initial screen](01-initial.png), [Office](02-office.png) |
| Find what was sold. Expected 8 m street plus 5 m side, 1.8 m high, soil, Slat panel. | Read the drawing and strategy; scrolled to Run editing and selected run2. Drawing labeled run1 8000 mm and run2 5000 mm. Model said Slat panel, M-SLAT. Run1 showed height intent 1800 mm over 0-8000 and soil; run2 showed 1800 mm over 0-5000 and soil. Strategy showed 13000 mm, 10 posts, 8 spans, 1 gate. | Complete for recorded specifications; partial for proving these were the signed specifications. No sold values were changed. | [Model and plan](04-site-orientation.png), [Run1](07-gate-events.png), [Run2](08-side-run.png) |
| Establish site orientation and gate width/location. Expected a readable site plan with a clear measurement origin. | Turned off the strategy overlay and read the cleaner plan, then the side view and gate event. House sat above the horizontal 8 m run; Street below it; 5 m run extended upward from its right corner. Gate event said 1000 mm @ 2000, and side view placed the opening between 2000 and 3000. | Complete for relative layout and numerical gate position. I interpreted the origin as the left endpoint of the street run using the plan and side-view stations. Exact on-site endpoint identity and hinge side were not explicitly documented in the views inspected, so requested confirmation. | [Clean plan](04-site-orientation.png), [Dimensioned elevation](06-assumptions.png), [Gate event](07-gate-events.png) |
| Find finish, opening direction, and site instructions in notes. Expected sales instructions attached to this job. | Opened Annotations. One run1 note said: "Customer agreed anthracite finish. Gate should open inward. Retain existing garden edging." It was labeled with an annotation ID, run:run1, and user. | Complete for the stated finish, inward opening, and edging instruction. Exact finish code and hinge side remained unanswered. The note did not visibly identify Sam or provide signature evidence. | [Sales note](03-annotations.png) |
| Understand assumptions and warnings before accepting responsibility. Expected readiness to reflect missing decisions. | Read Site conditions, Open questions, run decisions, and For the office. Site conditions were unstated; explanatory text said dependent rules stand aside. Bay-width alternatives remained open with one marked built. Decision text described level geometry, the default Slat model, and 600 mm post embedment governed by a rule. Meanwhile Strategy said nothing flagged, Gaps said nothing unresolved, and For the office said nothing missing. | Partial. Assumptions were discoverable, but neither site confirmation nor office acceptance was substantiated. I did not treat calculation readiness as sufficient authority to proceed. | [Missing conditions and alternatives](06-assumptions.png), [Assumptions and readiness](09-handover-readiness.png) |
| Find signed contract/original drawing and distinguish submitted handover from draft. Expected source documents, version, submission identity/time, or explicit draft label. | Inspected Office job and Annotations, compared Salesperson mode including For the office, then checked BOM as the visible quote-related location. Salesperson reduced navigation to The job and Notes and repeated the readiness message. BOM offered Save quote and material/cut tables. No contract, original drawing attachment, signed version, submitted/draft label, submission action, or acceptance control was found in these inspected views. | Blocked after three sensible search areas: job/handover views in both modes, notes, and BOM. The current editable drawing was visible; its approval provenance was not. Save quote was not used because it would not establish an existing signed sale. The estimate explicitly said it was not a quote or order. | [Salesperson](10-salesperson.png), [Sales readiness](11-sales-handover.png), [BOM](12-bom.png), [Estimate disclaimer](09-handover-readiness.png) |
| Request clarification without changing what was sold. Expected a request addressed to sales with a pending state. | Returned to Office topology, found the 600 mm embedment decision, and clicked Start a conversation. Scrolled to the revealed Comment field, entered the clarification below, and clicked Comment. The text appeared with role expert and timestamp 2026-09-06 10:17. A Propose a rule from this conversation control appeared. Reloaded and scrolled back; the comment remained. | Partial: saving the clarification was complete and visibly substantiated after reload. Routing to Sam, notification, response ownership, and pending acceptance were not substantiated. No acknowledgment from sales appeared. The readiness text still said nothing missing. | [Comment entry](14-clarification-entry.png), [Posted comment](16-clarification-visible.png), [After reload](17-clarification-after-reload.png) |

## Questions the UI answered

- Customer/address: Example customer, 18 Example Street.
- Salesperson/date: Sam; 6 September 2026 from the date control. The screen formatted this as 09/06/2026.
- Recorded fence: two connected runs, 8000 mm and 5000 mm; both 1800 mm high on soil; Slat panel M-SLAT.
- Relative layout: 8 m across the street side, with a 5 m return on the right in the displayed plan; house inside the corner.
- Gate: 1000 mm wide, from station 2000 to 3000 on run1.
- Notes: anthracite finish, inward opening, retain existing garden edging.
- Calculation assumptions: site conditions unstated, level geometry in the displayed decisions, 600 mm post embedment by rule, default bay-width choices with alternatives.

## Questions not answered by the inspected UI

- Where is the signed contract or original customer-approved drawing?
- Is this a submitted handover or an editable draft, and who submitted which version when?
- Did the customer approve this exact geometry, material specification, finish, and gate arrangement?
- What exact anthracite finish code and hinge side should production use?
- What physical site landmark defines the start of the gate measurement?
- Who confirmed the site conditions and applicability of the embedment assumption?
- Has Sam received the clarification, who owns the response, and is office acceptance on hold?

Absence statements describe this bounded UI journey; they are not claims about uninspected implementation or storage.

## Clarification actually recorded

> Office clarification for Sam: please provide the signed contract and original customer-approved drawing, and confirm whether this job has been submitted for handover or is still a draft. Please confirm the site conditions and the 600 mm post embedment assumption, the exact anthracite finish code, and the gate hinge side as viewed from the street. I read the note as inward opening with existing garden edging retained. Please confirm that the 1 m gate starts 2 m from the left end of the 8 m street run in the displayed plan. Office acceptance is pending these confirmations; do not change the sold specifications.

The phrase "Office acceptance is pending" is my comment, not an application status. The UI substantiated persistence of the words, not a workflow transition or delivery to Sam. The displayed comment timestamp is an application label, not a measured session duration.

## Highest-impact friction and proposed changes

Observed issues and inferred suggestions are explicitly separated below. Suggestions were not tested.

| Observed issue | Effect on this office task | Inferred UI change that would help |
| --- | --- | --- |
| For the office said "Nothing missing" while site conditions were unstated, bay choices remained open, and later my clarification was recorded. | Readiness initially sounded like completion, but could not support taking responsibility. | Show calculation readiness separately from handover approval; list unresolved office questions beside a status such as Awaiting clarification. |
| No signed contract/original drawing link or submitted/draft identity was found across the inspected job, notes, sales, and BOM views. Office still exposed drawing/editing controls. | I could inspect the current plan but could not tie it to the signed sale or an approved version. | Provide a handover header with Draft/Submitted/Accepted state, submitter/date/version, and links to the signed contract and approved drawing. |
| Start a conversation was attached to individual design decisions. Posting produced an expert comment and a rule-proposal option, without a sales recipient or delivery state. | I could save a request, but could not tell whether sales would receive or act on it. | Add a job-level Request clarification action with recipient, question status, delivery acknowledgment, and response history. |
| Anthracite, inward opening, and edging were only found in a separate annotation; exact finish code and hinge side were absent there. | Production-relevant instructions required a separate visit and remained incomplete for execution. | Bring original sales notes into the office summary, with explicit finish code, inward/outward direction, hinge side, and unanswered fields. Preserve the original wording and author. |
| Strategy labels crowded the gate and run labels; turning the overlay off improved the plan. Detailed assumptions and readiness required scrolling through a narrow right column while much of the left side was blank. | I had to combine separate views and scroll extensively to connect geometry, assumptions, and readiness. | Offer an office review layout with a clean site plan, named Street/Side runs and start-point marker, plus a compact adjacent specification/assumptions summary. Keep detailed decision trails expandable. |

## Useful existing features

- Customer, address, salesperson, and date are grouped together and populated on opening the example job.
- House and Street context make the L-shaped fence understandable; hiding the strategy overlay makes the original geometry much clearer.
- Run events and the dimensioned side view substantiate gate width/location and both heights without changing specifications.
- The original sales note is readable verbatim, including the garden-edging instruction.
- Site-condition omissions and default/alternative decisions are visible rather than silently omitted from all screens.
- A comment can be saved without changing the design, and the saved words survive reload. The estimate also explicitly distinguishes itself from a quote or order.

## Recorded decision/action sequence

25 meaningful UI actions were completed, below the 30-step limit. Reads and screenshots are evidence capture, not additional decisions. No task used more than three sensible search areas when blocked. Two automation locator attempts failed without a UI action (Office was a select option, and an unfiltered select locator did not target the visible run selector); these are not treated as product defects or counted as clicks. An attempted scroll to an already visible Site conditions heading caused no meaningful change and is also excluded.

| Step | Actual UI action | Observed result |
| --- | --- | --- |
| 1 | Open assigned URL. | Example job already selected; Hebrew, Everything mode. |
| 2 | Click language toggle. | English UI appeared. |
| 3 | Select Office. | Office navigation and editable job view appeared. |
| 4 | Open Annotations. | Read anthracite/inward/edging note. |
| 5 | Return to Topology & Strategy. | Drawing and job details returned. |
| 6 | Uncheck show strategy overlay. | Plan became easier to read around the gate. |
| 7 | Scroll down. | Site-condition omissions, open choices, and side-view dimensions visible. |
| 8 | Scroll to Run editing. | Run1 gate, height, and soil events visible. |
| 9 | Select run2 in Run editing. | Side-run height and soil events visible. |
| 10 | Scroll to For the office. | Embedment/default decision text and ready-to-hand-over message visible. |
| 11 | Scroll to top navigation. | Mode selector accessible. |
| 12 | Select Salesperson. | The job and Notes navigation; simpler toolbar. |
| 13 | Scroll to For the office. | Same readiness and estimate disclaimer; no submission control found. |
| 14 | Scroll to top navigation. | Mode selector accessible. |
| 15 | Select Office. | Office tabs returned. |
| 16 | Open BOM. | Save quote and material quantities visible; no signed document found. |
| 17 | Open Topology & Strategy. | Returned to current plan. |
| 18 | Scroll to embedment decision. | 600 mm rule and Start a conversation visible. |
| 19 | Click its Start a conversation. | Comment/Cancel controls were revealed below the decision. |
| 20 | Scroll to Comment. | Clarification input and explanatory text visible. |
| 21 | Fill clarification input. | Entered the request reproduced above. |
| 22 | Click Comment. | Request appeared as timestamped expert comment; rule-proposal control also appeared. |
| 23 | Scroll to posted clarification. | Full saved text visible. |
| 24 | Reload. | Job reappeared; clarification remained in rendered decision content. |
| 25 | Scroll to clarification again. | Persistent comment visibly confirmed; no delivery/acceptance confirmation. |

No time-to-completion or emotional quotations were invented. Screenshots in this directory are first-hand captures; the linked images above provide the primary evidence. The app browser was closed at the end; the parent-managed server was left running.
