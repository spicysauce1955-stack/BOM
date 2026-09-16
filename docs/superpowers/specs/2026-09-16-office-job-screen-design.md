# The office opens a job

> *"lets decide how the backoffice sees the work of the agent after he chose the
> job — a map in the center, can choose sections to see the sideview, notes,
> heights, … everything is shown, intuitive and simple."*
>
> *"by default the backoffice doesnt need to do changes on the work from the agent
> but see the overall result of the agent's work and work on that as read only
> (can edit, but needs to toggle something for it and then choose which step he
> wants to edit)."*

## Why this document exists

`2026-09-15-backoffice-design.md` gave the office a queue and a road. The road
works, and it is the wrong thing to land on. Today an office person who takes a
job arrives on step 1 of an editing road — *the sale* — holding the salesperson's
drawing tools, with her customer and address in an editable form and a Save button
under them. Nothing on that screen tells him what he is looking at.

This document specifies the screen he lands on instead: **a plan of the job, every
section open beside it, and editing behind a switch.** The office road is not
replaced. It becomes what you enter when you turn editing on, which is what §6
below is about.

The product owner chose this shape from three drawn candidates against the real
demo job. The chosen one is *map centre, sections open, layers as emphasis only*.

---

## 1. What the office is actually doing

Yossi has taken Dana's job. He is not going to redraw it — he needs to decide
whether it can be built and what it costs, which means four questions in this
order:

1. What did she sell, and what did she promise?
2. What does the ground do along each stretch?
3. What did the engine make of it, and what is it complaining about?
4. What do I have to answer before this can be priced?

Every one of those is answered **per stretch of fence**, and every one of them has
a place on a drawing. That is the whole argument for the map being the centre
rather than a tab.

### What the demo job looks like, because it is the test case

`proj_2a4089f5752c` — 28 000 mm in three sections around a house, one gate,
generated on 2026-09-16:

| | Run | Length | Stands on | Bays | Fence height |
|---|---|---|---|---|---|
| A | `run1` | 8 000 mm | masonry wall | 6 × 1 333–1 334 | 0–860 mm |
| B | `run2` | 12 000 mm | masonry wall | 7 × 1 714–1 715 | 0–1 655 mm |
| C | `run3` | 8 000 mm | the ground | 5 × 1 600 | 0–1 598 mm |
| G1 | `gate1` | — | — | — | 3 041 mm opening |

It generates five problems, and **each one names its own place**:

| Where | Code | What |
|---|---|---|
| `post@run1:4000` | `excessive_step` | a 1 120 mm step in the wall, over the 600 mm maximum |
| `gap:run2:0` | `choices_unanswered` | bay widths not chosen |
| `gap:run3:0` | `choices_unanswered` | bay widths not chosen |
| node `n8` | `node_surface_disagreement` | B and C disagree about what they stand on |
| `gate@gate1` | `gate_kit_width_mismatch` | the kit fits 1 000 mm; the opening is 3 041 |
| whole job | `height_assumed` | nobody measured; 28 m built at the 1 800 default |

Section A is the case that proves the screen. Its wall steps up 1 120 mm at 4.0 m
and the fence top does not follow, so **three of its six bays carry no fence at
all** — `height_mm: 0`. That is visible in one glance at an elevation and invisible
in every list of numbers we currently render.

---

## 2. The screen

```
┌──────────────────────────────────────────────────────────────┐
│  Fence AI                        Yossi   [משרד אחורי]        │
├──────────────────────────────────────────────────────────────┤
│  🔒 Reading — Dana's job                      Edit ›         │  ← §6
├───────────────────────────────────┬──────────────────────────┤
│                                   │  SECTIONS                │
│                                   │  ┌─────────────────────┐ │
│          the plan                 │  │ A  8 m · masonry    │ │
│      flags drawn on it            │  │ ▁▁▁▃▃▃  elevation   │ │
│      sections lettered            │  │ bays / fence / posts│ │
│                                   │  └─────────────────────┘ │
│                                   │  ┌ B ┐ ┌ C ┐ ┌ G1 ┐ …   │
└───────────────────────────────────┴──────────────────────────┘
```

Two panes, one selection. The map keeps the centre; every section is **already
open** beside it with its own elevation. Nothing about a section is behind a click.

**Selecting is symmetrical and it is one concept.** Clicking a stretch on the map
selects that section's card; clicking a card highlights that stretch. Hovering a
card glows the stretch without pinning it. This is not new machinery:
`state.selection.runId` exists, emits `selection-changed`, and five surfaces
already follow it — including the side view, which already has an all/one-section
scope.

At phone width the panes stack, map first.

### Decided: the sections do not scroll away from the map

On a wide screen the map is sticky and the cards scroll beside it. The map is the
index; a card you are reading with the index gone has lost the half of the link
that makes it legible. Stacked at narrow widths the map scrolls away like anything
else, because there is no room for both and the cards are then the whole screen.

### Decided: a section card carries cut pieces, never bars and never money

Quantities per section are real. **Bars purchased and prices are not** — both are
pooled across the whole job. The codebase already refused per-section prices in as
many words (`js/tabs.js`: a per-section price *"would be an apportionment nothing
measured"*), and the same is true one level down: a `Part` carries `from_bars` —
its cut-plan bar provenance — and `shared_with`, the elements it was cut alongside.
An offcut shared between two sections cannot be attributed to one of them by
re-sorting.

So the card shows **cut pieces** (SKU, count, cut length) and links to the BOM for
what gets bought. A number with a currency sign on a section card would be a number
nobody measured.

### Decided: the gate is its own card, not a flag on section C

A standalone gate has `run_ref is None` and belongs to **no** section in the read
model — `report/section_decisions.py` excludes it deliberately, and its decisions
are reachable only through `/explain/{element}`. Hanging G1 off section C would
contradict the data to make the screen tidier.

---

## 3. The unit of selection is the run, and that is a decision

This system has **three** sub-run granularities and they are not the same
partition:

| | What it is | Addressable today? |
|---|---|---|
| geometric segment | between consecutive points of `run_points` | **No.** Exists only as `Anchor.segment_index`; no read model, no route |
| layout segment | between structural boundaries — corners > 15°, base transitions, pinned posts, gate edges, steps | Only by reaching into decision payloads. It is what a choice's scope names: `gap:{run_id}:{seg_start}` |
| bay (`Span`) | between two adjacent posts | **Yes** — stable `element_id`, in the structure report, the grouped BOM, `/explain`, and panel preview |

The handles that exist are the **run** (= section, via `Section.run_id` and
`/sections/{run_id}/decisions`), the **bay**, and the **post or gate**.

**The section is the click unit.** It is the only granularity that exists both
before and after generation, it is what the side view already scopes to, and it is
what the office thinks in — *"the bit along the road"*.

**The bay is the next level down and it is a named seam, not this slice.**
Selecting a bay is where the panel drawing and the *why is this part here* sentence
live. The card's elevation is drawn from `Section.bays[]`, each bay already
carrying its `element_id`, so the handler has somewhere to go the day it is wired.
Nothing else in this design depends on it.

*Trigger to build it: an office person asking why a specific bay came out the width
it did — which is a question `/explain/{span_id}` already answers.*

### Two asymmetries that will bite

* A **shared node post** belongs to every run touching its node
  (`Post.run_ref == "node:<id>"`). It must not be counted twice across cards, and
  the structure report already solves this: a corner post has ONE tag and is
  cross-referenced by `Station.shared_from`.
* A **standalone gate** belongs to no section — see §2.

---

## 4. The flags are the reason he opened the job

Every warning, every unanswered question and every missing measurement is drawn on
the map at the place it names, and listed beside it. Two rules:

**Every flag clicks through to its geometry.** A list that does not is the
documented way a review surface dies: the cautionary tale in the industry is a BIM
tool whose review dialog accumulates thousands of unlinked warnings, where *"a
thousand warnings make the dialog useless — which is precisely how critical
problems hide for months."*

**A flag is never on a layer.** See §5.

The places are already carried and mostly already unrendered:

| Source | Place it names |
|---|---|
| `HandoverGap.params.run_ids` | the runs it covers — *"CARRIED, never rendered: the road's gap row uses it to select the stretch, while the sentence in both bundles still says 2 stretches"* (`report/handover.py`). The precedent for flag-to-geometry already exists on the road; this screen extends it to the map |
| `ChoiceSet.scope` | `gap:{run_id}:{seg_start}` — run and start station |
| `StrategyWarning.element_refs` | `post@run1:4000`, `gate@gate1` |
| `StrategyWarning.params.node_id` | `n8` |

### Decided: the mark is placed like a note pin, in a layer of its own

`js/notes.js` already draws one marker per *target* with a count badge when a thing
has more than one note, and `anchorPointFor` already resolves `run:<id>` to the
midpoint of that stretch and `event:<id>` through `stationOfAnchor`. A flag mark is
the same shape with a different glyph.

It goes in a **new group, not in `#g-notes`**. That subtree is notes.js's, and a
second concern written into it is the coupling this repo keeps paying for.

### Decided: severity is a property of the flag, not of the renderer

Three bands, and the third is not a colour:

| Band | Drawn | Means |
|---|---|---|
| blocking | red `!` | this cannot be built or priced as drawn |
| open | amber `?` | somebody has to answer this |
| answered | grey, no mark | requires nothing from you |

Colour never encodes alone — every mark carries its glyph, and every list row names
its state in words. A `severity` of `error` on a `StrategyWarning` is what makes a
mark red; the screen does not decide.

### Not in this slice: dismissing a flag with a reason

The pattern worth having, from insurance estimating: a middle tier that can be
bypassed *only by writing why*, which turns a dismissal into a captured human
decision instead of destroying it. This system has the machinery for it — verbatim
human text is immutable, and the decision graph wants exactly this row.

It is deferred because it is a new stored fact and a new command, and this slice
adds neither. **Named seam:** the flag list's row is the place it attaches, beside
the existing click-through.

*Trigger: the first office person who tells us a warning is not a fault on this job
and wants to stop seeing it.*

---

## 5. Layers emphasise; they never hide

The screen offers layer switches — ground, heights, notes, materials — and they
**highlight what is already on screen**. Nothing disappears when one is off.

This is the one place the product owner's three words pull against each other. A
toggle that can hide a fact makes the screen simpler and makes it possible to miss
the 1 120 mm step that stops this job being buildable.

The precedent is not a style opinion. Marine navigation **regulates** decluttering:
a chart has a Display Base that cannot be removed from the display, and the
standard display is restorable by a single operator action. It is regulated because
of a 2016 grounding whose investigation found the standard view had hidden the
depth that mattered. A read-first screen's first frame must be complete and honest.

So: **the protected base of this screen is the runs, the gates, the house, the
street, the section letters and every flag.** No control hides any of them.

---

## 6. Reading and editing

**The office lands in reading.** A switch turns editing on, and turning it on is
what opens the office road — the seven steps of `2026-09-15-backoffice-design.md`
§8, entered deliberately by choosing one, rather than landed on.

### This changes the posture, not the permission

`2026-09-15-backoffice-design.md` §8 decided that *"the backoffice may edit the
drawing, and the log is what makes that safe"* — that Yossi is the one who will
discover the gate cannot open where it was drawn, and a tool that makes him phone
the salesperson is a tool he works around. **That decision stands and this design
does not touch it.** He may still change anything. He now does it on purpose.

The difference it makes is that he turns editing on *because of something he saw*.

### Say plainly what the switch is and is not

**The switch is presentation. It is not protection.** `js/view.js` and
`identity/model.py` both insist on that line: hiding is CSS, `localStorage` is
editable, and a locked pencil stops nobody who types their own requests. What
actually gates a mutation is a capacity check on the server, and 73 routes still
have none (`2026-09-15-backoffice-design.md` §3's recorded trigger).

**Named seam:** every mutating call this screen can reach goes through one place,
so that when route-level capacity arrives it has one client-side counterpart to
agree with.

### Three things the lock must actually cover

* **`js/profile.js` never checks `drawingLocked()`.** The CSS lock covers the
  toolbar, undo, redo, clear and the draft actions — not the side view. Read-only
  today leaves the base-height buttons live.
* **`drawingLockedFor(view, status)` answers only for `sales`.** It gains the
  office's answer, which is a mode rather than a status.
* **Read mode must look like a document, not a form of greyed-out inputs.** A
  disabled control is skipped by screen readers and fails contrast; a value that has
  no editable state should be rendered as text, not as a dead field.

### Decided: two GETs write, and we are not pretending otherwise

`GET /runs/{id}/bom` and `GET /runs/{id}/structure` both call `save_supply_run(...)`,
and `/bom` writes an audit row. They are idempotent by digest, so this is safe — but
"read-only" on this screen means *the office is not changing the job*, not that no
row is written. Said here so nobody discovers it and thinks the lock is broken.

---

## 7. A derived number has three states

Every figure on this screen is derived, and the screen says which of three it is:

| State | Drawn | Means |
|---|---|---|
| current | plain | computed from the drawing as it stands |
| **stale** | marked, and recomputed only when somebody presses the button | the drawing moved under it |
| overridden | badged, one click back to the calculated value | a person asserted this |

The stale state is this project's own rule showing itself: generation never
auto-fires. The overridden state is override-as-patch made visible — an override is
anchored to `(run_id, station, kind)` and already survives regeneration.

The refusals that produce the stale state already exist and are typed:
`/structure` answers 409 `topology_changed` and 409 `site_conditions_changed`;
`/sections/{run_id}/decisions` does the same; `/bom` deliberately does not, being a
working view. `js/structure-data.js` already renders these through `refusalKey()`
and is the model to follow.

---

## 8. Two rest states, and the empty one must not lie

**Before Generate has run, half of this screen does not exist.** Without a run
there are no posts, no bays, no prices, no warnings and no open questions — those
are made by generation.

What *is* available per section with no run, all of it pure and already written in
`topology/station.py`: `run_length`, `segment_lengths`, `corner_stations`,
`ground_samples`, `max_slope_permille`, `ground_step_stations`, `base_surface_at`,
`base_transition_stations`, `base_top_at`, `base_top_step_stations`,
`fence_model_at` — plus the authored intent on the run's own events, and the whole
of `handover_gaps`.

### Decided: the pre-generation screen is a different state, not a half-empty one

The cards show what exists — length, what it stands on, the ground, the heights as
authored — the flag list shows handover gaps only, and **Generate is the one
obvious thing to do.** It never renders as "nothing wrong here".

That failure has a precedent in this repo: a 500 on `/handover` once rendered as
*"Nothing missing — this job is ready to hand over"* on a project with zero runs
(audit finding B01). Three states, never two: not yet looked, looked and empty,
looked and failed.

### The plumbing cost this creates

`topology/station.py` **has no HTTP route**, and `js/geom.js` mirrors only a subset
— `runLength`, `pointAtStation`, `stationOfAnchor`, `anchorFor`, `groundSamplesFor`,
`groundZAt`. It does **not** mirror `base_surface_at`, `base_top_at`,
`corner_stations`, `fence_model_at`, `max_slope_permille` or any transition-station
function.

**Decided: a new derived-view route, not more mirrored maths.** `GET
/api/projects/{id}/sections` answers the per-section facts that need no run. The
repo has mirrored geometry across that boundary before and says why it must stay
rare: `geom.anchorFor` mirrors `make_anchor` because it is a two-line formula, and
`report/elevation.py` is served from the server precisely because it is not.

---

## 9. The station axis does not mirror

The side view is a chart whose horizontal axis is **station along the run**, and
`CLAUDE.md` already rules that the plan canvas and the profile SVG are never
mirrored in RTL. The new elevation inherits that: **station 0 stays on the left in
Hebrew**, and only the labels and the bands localise.

This is also the domain convention — stationed elevations read left to right from
0+00 in every civil and retaining-wall tool — and it is what keeps the elevation
geometrically consistent with the unmirrored plan beside it.

---

## 10. What this reuses, and what is new

**Reused unchanged:** `state.selection.runId` + `selection-changed`; the derived
section tags A, B, C and the post/bay tags `A/P3`, `A/B1`; the grouped BOM keyed by
`run_ref`; note-marker anchoring and its count badge; `handover_gaps` and
`readiness`; `refusalKey()`'s 409 handling.

**New:**

1. **`GET /api/projects/{id}/sections`** — per-section facts with no run (§8).
2. **Flag marks on the plan**, in their own group (§4). Warnings render as text
   lists today; nothing draws them on the map.
3. **`fitToRun(runId)`** — an export from `js/editor.js`. `fitView` is private,
   takes no argument and always fits the whole job.
4. **`js/section-elevation.js`** — a pure module that returns a detached SVG for
   one section, in `js/elevation.js`'s house style: creates and returns the
   element, imports no state, subscribes to nothing, interactivity opt-in.

   **Decided: the card draws a thumbnail, and `js/profile.js` is not refactored.**
   The obvious move is to extract `drawProfile(svg, …)` from `profile.js` and
   reuse it read-only. It is the wrong first move. `profile.js` exports one
   function, keeps five module-level mutable singletons whose projection helpers
   close over them, and attaches its listeners *inside* its draw calls — so
   extracting it is a refactor of the most tangled module on the page, in the
   same slice as a new screen.

   What a card needs is also genuinely a different drawing: base top and panel
   rectangles per bay, straight off `Section.bays[]` and `Section.ground`, at
   thumbnail scale. That is a small pure function of the structure report, the
   way `report/elevation.py` is a small pure function for a panel. It recomputes
   nothing — every rectangle is a stored bay's `bottom_z_*`, `height_mm` and
   width.

   *Trigger to extract `drawProfile`: the office asking for the FULL side view —
   dimensions, intent dashes, ground samples — inside reading mode. Until then
   the full profile stays the road's step-2 surface, where editing lives anyway.*
5. **The screen itself** — new DOM ids, which is also how it escapes
   `step-surfaces.js`: that machinery is a deny-list of known ids, so an id in none
   of its four maps is in no step's hide list.

### The one coupling to design around

`road.js: showStep()` calls `setTab(...)` and `setTool(...)` on every step change,
so a new tab is switched away from whenever the step moves. The screen is not a
road step and must not be driven by one.

---

## 11. Out of scope, with triggers

| Deferred | Trigger to build it |
|---|---|
| Selecting a bay (§3) | an office person asking why one bay came out that width |
| Dismissing a flag with a written reason (§4) | the first "that warning is not a fault on this job" |
| Route-level capacity (§6) | unchanged from `2026-09-15-backoffice-design.md` §3 |
| A "field capture vs now" diff — what the office changed from what she drew | a salesperson disputing a measurement |
| An overview strip marking attention across all runs independent of zoom | a job with enough runs that zooming into one hides the others |
| Per-section quantities as a printable handout | somebody asking to take one section to the yard |
| **Attributing `grouped.unresolved` per section** — a stretch that is one part short currently reads as COMPLETE on its card | the first job where a missing part matters and nobody can see which stretch it belongs to. `DemandLine` carries `pegs`, so the same `section_of` inversion answers it with no new arithmetic; it changes `BomGroup`'s shape, so it wants its own test and a JS surface |
| **Summing lines across section cards** — a piece with a non-empty `shared_with` is in more than one group, so `Σ(section groups) > BOM` for it | nothing to build: it is a rule the office screen must KEEP, written here because the temptation is a "total for this job" beneath the cards. Today the live sharing case is the bay one (`MemberRun.run_ref` is a single run), so no section line is shared yet — which is exactly when a wrong total would go unnoticed |
