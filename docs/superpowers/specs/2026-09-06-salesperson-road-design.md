# The salesperson's road, as steps

**Status:** SPEC. Nothing here is built.

Supersedes nothing. Extends `2026-09-04-sales-mvp-design.md`, which cut the road;
this document makes it visible.

## Why this document exists

`docs/visualizations/salesperson-mvp/` arrived from another session as a 186-file,
24 MB interactive storyboard of a proposed salesperson screen, with two rounds of
studies, a five-agent adversarial review and an audit of the app as it stands. It
was committed at `9de94eb` without a decision about what it was for.

This is that decision, for one of the five things it contains.

**What the package is, stated once so the spec does not overclaim it:** the
studies are AI-agent simulations and the review is five AI reviewers. It is a
well-argued design proposal, not user evidence. Its audit half is different and
stronger — that half drove a real browser against this repository and reproduced
what it found, which is why `handover.py` already cites it by path.

### What the storyboard turned out NOT to propose

The storyboard presents Ground, Base and Fence as three separate editors, with a
planned 600 mm masonry wall, a 300 mm ground rise and "finished levels remain
unconfirmed." Read quickly, that is a domain proposal. It is not one — every part
of it except the last clause is already in the model:

| Storyboard | Already in the code |
|---|---|
| ground rise along a stretch | `Node.z_mm`, `ElevationSamplePayload`, `station.py: ground_z / ground_samples / local_slope_permille` |
| a base the fence stands on | `BasePayload.surface` — `soil`/`concrete`/`masonry_wall` |
| the wall's top, stepped or sloping | `BaseTopPayload.points`, each `BaseTopPoint.lock` = `level`/`step` |
| fence height above that base | `BaseTopPoint.z_mm` is commented, in the type, *"height of the base top ABOVE local ground"* |

The separation the storyboard argues for is one the domain model already makes
and the SCREEN blurs. So step 3 below is a presentation change, and it is cheap.

**The one thing genuinely missing is the last clause** — nothing can say *this
300 mm is planned per construction drawing rev 3, not measured.* Every `z_mm`
reads as measured fact. That is its own spec (below, "Not claimed"), because it
adds a field to the topology and this document adds none.

## The problem in one sentence

The road exists and nothing shows it.

Every step of `2026-09-04`'s seven-step road now works — four of them built by
slices 1–4, the rest already there — and they all landed on one screen as a long
sidebar of panels that are simultaneously present.
A salesperson entering a job after the visit has no answer to *where am I, and
what is left* except to read the whole page. The audit's U01 is exactly this
finding from the other direction: the handover status sits below a long sidebar.

And **three surfaces already answer "what is left", differently**:

| Surface | Answers | Agrees with the others? |
|---|---|---|
| `js/checklist.js` | 3 hardcoded items: a run exists, a gate exists, a strategy was computed | No — it has no idea whether a height was ever stated |
| `js/handover.js` + `report/handover.py` | the 9 `HANDOVER_CODES`, coverage-checked | This is the real answer |
| `#gaps` | what the KNOWLEDGE cannot answer for any job | Different question entirely; already hidden from sales |

That is the B03 defect at a larger scale, and `e77883b` just fixed the small
version of it. A fourth surface would be malpractice. **The road replaces
`checklist.js` and absorbs the handover panel's list; it does not join them.**

## The design

### The road is a map, never a wizard

Steps are free to enter in any order, and no step gates another.

This is not a preference. The salesperson works on a laptop after the visit, from
paper: they may hold the sketch and not the address, or do the gates before the
heights because the gates are what the customer talked about. A wizard that
demanded order would be defeated by entering junk to get past a step — which
turns a completeness report into a completeness *lie*, the one failure this whole
MVP exists to prevent.

It is the same rule `handover.py` already states for itself: *reported, never
enforced. A sheet that refused to hand over an incomplete job would be worked
around within a week.* The road inherits that sentence.

### A step's state is DERIVED from the handover gaps

The road computes nothing about completeness. It groups what `handover_gaps()`
already returns.

```
road(project, handover) -> [ Step { key, state, gaps[], target } ]

state = "blocked"   any gap on this step is blocking
      | "missing"   this step owns at least one gap
      | "done"      this step owns no gaps and its precondition is met
      | "empty"     nothing has been entered here yet
```

**`GAP_STEPS` maps every handover code to exactly one step.** A code with no step
would vanish from the road while still being reported by the panel — the silent
class of failure this repo has shipped green four times. So a test asserts the
mapping is total against `HANDOVER_CODES`, in the shape `test_role_sync.py`
already uses for a list that exists in two languages.

| Step | Gap codes it owns |
|---|---|
| 1 · The job | `customer_missing`, `address_missing`, `sold_by_missing`, `sold_on_missing` |
| 2 · The layout | `no_fence_drawn`, `no_property_context` |
| 3 · The details | `height_assumed`, `base_assumed`, `no_model_chosen` |
| 4 · Gates | — |
| 5 · Notes | — |
| 6 · Review | — |

Steps 4, 5 and 6 own no codes today, and that is recorded rather than hidden: no
gap reports a missing gate, because a fence with no gate is a fence with no gate
and not an incomplete job; no gap reports a missing note, because a promise
nobody made is not an omission. Step 6 owns none because it IS the report.

### A step SHOWS only its own work (decided 2026-09-07)

Navigating to a step is not enough. Built as navigation alone, the road moves an
underline while the screen underneath stays identical: in `sales` today every
step shows all nine tools and every side panel at once — the job fields, house,
street, ground, base, height, model, gates, site conditions, the side view and
the handover sheet, simultaneously, whichever step you are on. A map over an
undifferentiated screen is a label, not a workspace, and the user's verdict on
seeing it was exactly that.

**So a step owns a surface list, and the road applies it.** What each step shows:

| Step | Tools | Panels | The drawing |
|---|---|---|---|
| 1 · The job | — | job identity | visible, **read-only** |
| 2 · The layout | Select, Draw, House, Street | property context | editable |
| 3 · The details | Select, Ground, Base, Height, Model | fence model, stretch events, side view | editable |
| 4 · Gates | Select, Gate | stretch events | editable |
| 5 · Notes | — | annotations | not shown (its own panel) |
| 6 · Review | — | what the office still needs, warnings, the estimate | visible, read-only |

**The drawing stays on screen in step 1** rather than being hidden with the
tools. A salesperson entering a job is describing a place, and the place is the
thing they are looking at on paper; a form floating on an empty screen is the
"project 7" problem the job slice existed to fix, one layer up. It is read-only
there because step 1 offers no drawing tools, and a canvas that edits without a
tool selected would make the scoping a lie.

**The mechanism is `role.js`'s, reused rather than reinvented.** A step list on
`<html data-step>`, CSS obeying it, and the list owned in one module — the same
shape as the role hide-list, and it inherits the same guard, which is the point:
*a hide-list is the one kind of list that fails silently*. A selector that
matches nothing hides nothing and looks fine, so every step's selectors are
resolved against the real page, and the JS and CSS copies must be **equal**, not
overlapping (`test_role_sync.py`'s rule, applied again).

**Role and step compose, they do not merge.** `data-role` answers *who is
looking*; `data-step` answers *what they are doing now*. A surface hidden from
the salesperson by role must stay hidden in every step, so the two lists are
independent and the role list always wins. Merging them would make "is the
inspector visible?" a question with six answers.

**Only `sales` has steps.** `office` and `all` have no road, so `data-step` is
absent for them and every step rule is inert — the same way `data-role="all"`
has no rules at all.

### Where it lives: the frontend, and why

`js/road.js`, a pure function over `(project, handoverResponse)`, node-tested the
way `projectModelState` and `estimateNoteKey` already are.

**Not a `report/road.py` read model with its own route**, which was the other
candidate and is what `report/`'s discipline would suggest at a glance. The
argument against it is that a step is not a fact about the fence. It is a
grouping of one role's screen — the office person's road and the super user's are
different roads over the same gaps, and neither is written. A backend read model
would put a presentation decision behind an API and make the second role's road
an API change.

The domain rule stays exactly where it is. `road.js` may never compute a gap, and
the test that holds this is that it imports no coverage arithmetic: the moment it
computes `uncovered_mm` there are two answers to *is this job complete?*

### The six steps

Lifted from the storyboard's chapters, reconciled with `2026-09-04`'s seven-step
road. The storyboard's chapter band — number, short title, one sentence of
purpose, one sentence of takeaway — is worth taking as-is; it is the thing that
made a stranger able to read the flow.

| | Step | What the salesperson does | Existing surfaces |
|---|---|---|---|
| 1 | **The job** | Customer, address, who sold it, when | `js/job.js`, `PUT /projects/{id}/job` |
| 2 | **The layout** | Draw the fence to typed measured lengths; place house and street | `editor.js` draw tool, `context.js`, `#tool-house`/`#tool-street` |
| 3 | **The details** | Per stretch: the ground, what it sits on, how tall, which model | `#tool-ground`, `#tool-base`, `#tool-height`, `#tool-model`, `profile.js` |
| 4 | **Gates** | Where, how wide | `#tool-gate` |
| 5 | **Notes** | Promises made during the sale | `tabs.js` annotations |
| 6 | **Review** | What the office still needs, and the ballpark | `handover.js` |

Six, not seven: the estimate lives inside Review rather than standing as its own
step. The MVP already argues why — entry happens after the visit, so the number
is written confirmation and never what won the deal.

Step 5 is Notes and not the storyboard's evidence pane, because attachments are a
different spec. The notes surface exists today and is the seam that spec plugs
into. It is also the step that decided the navigation question below: it is the
one step whose surface is a different tab.

### Step 3, in detail: Ground, Base, Fence

The tools are already separate — `#tool-ground`, `#tool-base`, `#tool-height`,
`#tool-model` are four buttons on the rail today. What is missing is that nothing
on the screen says how they RELATE, so a salesperson has no reason to think the
order matters, and the side view is the only place the relationship appears.

Step 3 groups the four under one panel, in the order the physical thing is built
— ground, then what sits on it, then the fence above that — with the unfolded
side view beside them. The storyboard's own takeaway sentence is the right one
and should be a locale string: *fence height is above its base.*

Nothing about the geometry changes. `base-top.js` stays the pure point-list
module it is, and any new profile math goes there so it stays node-testable.

### Silent defaults must LOOK silent (audit U05)

The Height popover opens seeded with 1800 mm. The Base form opens with `soil`
preselected. These are precisely the two silent defaults `handover.py` was
written to catch:

> a fence nobody measured reaches the office indistinguishable from one confirmed
> at 1.8 m.

The popover is where that indistinguishability is manufactured. A seeded field
that a salesperson tabs past writes an explicit `height_intent` event at 1800 —
and the handover sheet then correctly reports nothing missing, because somebody
did say 1800. The number was never measured; it was never even read.

**The fields open empty, with the default shown as a ghost value that is not a
value.** Saving an untouched field writes nothing, so the run stays uncovered and
`height_assumed` fires. This is a small change with an outsized effect: it is the
difference between the handover sheet reporting what was measured and reporting
what was tabbed past.

The same rule for `base` (no preselected `soil`) and for anything else a future
gap code names as assumed. The gap codes and the popover defaults must name the
same set, and a test asserts it.

### The stretch summary, and gaps you can act on (U02, U03)

Each step renders its gaps as rows, and **a gap row is a control**: it names the
stretch it is about and selects it, opening the editor that fixes it. Today the
panel names a count — *"height assumed on 2 runs, 4000 mm uncovered"* — and the
salesperson has to go and find which two.

`HandoverGap.params` already carries `runs` and `uncovered_mm`. It does not carry
WHICH runs. Adding the run ids to the params of `height_assumed` and
`base_assumed` is the one backend change this spec needs, and it is additive.

Beside the steps, a per-stretch summary card: length, height, base, model, gates,
each with the editor behind it. Derived, never stored.

### What else to lift from the storyboard

Small, and each fixes something the adversarial review found in its own prototype
— which makes them free lessons:

- **Zoom is labelled with its scope.** The review's findings 12 and 14: zoom
  controls that changed only the plan while the side view sat beside them. Label
  the control *Plan zoom*.
- **The elevation says it is unfolded, and marks the corner.** Finding 13: a
  perpendicular stretch drawn at full length beside its neighbour under a caption
  claiming a single viewpoint.
- **A drawing legend.** Which line is recorded fence, which is the selected range.
- **A persistent job bar** — customer, address, and that this is a signed sale —
  so every screen after the first reads as a real job. `display_name()` exists.
- **The selected range is visible and reversible**: preview a partial-height
  change, apply or restore. The storyboard's chapter 4, and the review's finding 3
  is the bug to avoid — restore must clear the preview.

## Invariants, held by tests rather than by care

1. **`GAP_STEPS` is total over `HANDOVER_CODES`.** A new gap code with no step
   fails here, not on screen.
2. **`road.js` computes no coverage.** One answer to *is this complete?*, and it
   is `handover.py`'s.
3. **No step gates another.** Asserted on the model, not the CSS: the function
   returns every step as reachable regardless of state.
4. **Popover defaults and assumed-gap codes name the same set.** A seeded field
   whose gap code was never written is a silent default that reports as measured.
5. **Every new string is in both bundles**, and every tool hint key resolves —
   `test_every_tool_on_the_rail_has_a_hint_in_both_bundles`, added in `e77883b`
   after three of the tools a salesperson keeps were found printing their own
   key under the canvas, in both languages, in the browser smoke's own
   screenshot.
6. **`checklist.js` is deleted, not left dormant.** A dismissible surface that
   still disagrees is a surface that will be re-enabled by somebody.
7. **`road.js` reaches no panel's DOM.** It calls `tabs.js: setTab`, and the
   test is that it queries nothing inside a tab panel — the module map's rule,
   and the one this navigation change is most likely to break.
8. **Every step resolves to a panel `SALES_TABS` allows.** A step naming a panel
   the role cannot reach is a dead end on the only navigation the role has.

## Seams left named

- **`road(project, handover, role)`** takes the role and refuses one it has no
  road for, rather than defaulting to the salesperson's. The office person's road
  and the super user's are unwritten, and this is where they attach.
- **Step 5 (Notes) is where the evidence package attaches.** Attachments become a
  source list under the same step, and `Annotation.target_ref` is the field that
  grows targets.
- **Measurement confidence adds gap codes, not steps.** When a `z_mm` can say it
  is planned rather than measured, the road shows it under step 3 with no
  change to the step model.
- **`GAP_STEPS` is a registry**, in `handover.py`'s sense: adding a code and its
  step is a one-line change and needs no discussion.

## Not claimed

- **The evidence package** (audit G01) — contract, sketch, amendment, photo,
  message as attachments, with notes carrying a target and a separate
  provenance. Its own spec; needs decisions about file storage this one does not.
- **Office transfer** (G02) — submit, inbox, acceptance, clarification. This is
  the OFFICE person's MVP, which `2026-09-04` explicitly leaves unwritten. The
  storyboard's office screen is a preview and reads as more than it is; building
  a real inbox from it would start a second MVP by accident.
- **Measurement confidence** — planned vs measured vs unconfirmed. Its own spec,
  and the only genuinely new domain concept the package contains.
- **Flipping `role` to default `sales`.** Still its own change, with the browser
  smoke updated on purpose. The road is what makes it defensible; it is not this
  document.
- **Audit observations 3–6** are recorded, not scheduled. Observation 5 is worth
  naming because it is visible in `tools/smoke-out/50-sales-mode.png` today: the
  generated summary offers *"see the priced BOM →"* while the BOM tab is hidden
  from the role.

## The road IS the navigation (decided)

**For `sales`, the six steps replace the tab strip.** `#tabs` is hidden for the
role and the road is the only navigation on the screen. Decided 2026-09-06; the
alternative was keeping today's strip and putting the steps inside the canvas
tab.

The reason is step 5. Sales keeps exactly two tabs — canvas and annotations — and
with the strip kept, Notes would be reached by a TAB while every other step was
reached by the road. The road could then never say anything about whether a
promise made during the sale was written down: the surface would not be on it.
A promise is the one thing in this MVP that travels to the office as a sentence
rather than as a quantity, and leaving it off the map is how it gets forgotten.

Two navigations on one screen is also the smaller version of the same fault this
spec exists to fix — a second place answering *where am I*.

### What that costs, concretely

- **`role.js` hides `#tabs` itself**, not eight individual `[data-tab=…]`
  entries. Those entries stay on the list regardless: they are what makes the
  strip correct if it is ever shown, and removing them would make the hide-list
  quietly wrong rather than shorter. Both copies of the list must stay equal —
  `test_role_sync.py`.
- **`tabs.js` gains `setTab(name)`.** It has no such export today; switching is
  wired to the buttons' click handler, which emits `tab-changed`. `initTabs`
  should call `setTab` from that handler so there is one path, and `road.js`
  calls `setTab("annotations")` for step 5 and `setTab("canvas")` for the rest.
  **`road.js` must never touch a panel's DOM** — that is the module rule, and
  the reason this needs an export rather than a `click()`.
- **`SALES_TABS` stops being a navigation list and becomes a reachability list**:
  the set of panels the road is allowed to activate. Same two names, different
  job, so its comment has to change or it will be read as the old thing.
- **The office role is untouched.** It keeps the strip. The road does not exist
  for it, which is the whole reason `road()` takes the role and refuses one it
  has no road for.
