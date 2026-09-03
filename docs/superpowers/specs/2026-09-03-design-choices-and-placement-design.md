# Two right answers, and a pointer for when neither is yours

**Date:** 2026-09-03 · **Status:** DESIGN, not started
**Contract:** §1.3 (`paired`), §1.4, §2.2 · ADR-0004 (overrides), ADR-0007 (layout,
cut planning), ADR-0002 (int mm at rest)
**Supersedes nothing.** Extends `2026-08-31-source-admissibility-design.md` (item 6)
and closes the `paired` gap `2026-09-03-spec-field-provenance-design.md` §7 names.
**Drawing set:** the visual companion to this spec is an artifact, rev C, twelve
sheets. Where a number here has a picture, the sheet is cited as `S-04`.

---

## 1 · The problem, in one paragraph

Sometimes more than one fence is right, and this engine hides it. A published
`footing_schedule` states *"24″ holes with posts up to 66″ apart, **or** 30″ holes
up to 97″"* — both stamped by the same engineer — and we refuse the whole table
(`parameter_paired_unsupported`). A 5 m run with 2 m panels can be three equal bays
or two panels and a stub, and the engine picks one by a flag nobody set. And when a
person places a post by hand, the layout puts another one back in the middle
without a word. Three shapes of one problem: **the engine decides where nothing
entitles it to decide, and says nothing about the answer it discarded.**

## 2 · What changes for the person

**Today:** a plan says *"bays 1667, 1667, 1666"*. Nothing says why, or that
`2000 · 2000 · 1000` was computed and thrown away, or that a sealed approval offered
a footing schedule that needs three fewer posts.

**After:** the plan carries its open questions. Each shows the answer it wasn't and
what the difference is in things you can count:

```text
Section A · 5.0 m · 2 open questions · 1 pinned · 2 posts placed by hand

BAY WIDTHS                                        2 of 5 candidates survived
▸ 2000 · 2000 · 1000    two bays uncut, one stub          built
○ 1667 · 1667 · 1666    every bay equal        same posts · same boards · +20 cuts

WHERE THE SHORT PANEL SITS                              no material change
▸ 2000 · 2000 · 1000    at the far end                   built
○ 2000 · 1000 · 2000    centred
○ 1000 · 2000 · 2000    at the start

FOOTINGS                                       pinned for this job — not asked
  610 mm deep · posts ≤ 1676 mm
```

...and when none of the offered answers is the one you want, **you drag the post
where it goes**, in the plan or in the side view, and the engine re-flows only the
gaps you left alone.

## 3 · The concept, and its name

A **choice set** is a question: two or more **design points** that are all
admissible, where nothing in the data prefers one. A person answering it makes a
**selection**.

This is a fifth kind beside the four the foundation already keeps apart, and it
belongs beside them rather than inside one:

| Kind | Says | Resolved by |
|---|---|---|
| hard constraint | must | the evaluator, or the run fails |
| preference | nicer if | the evaluator, by precedence |
| objective | minimise this | supply resolution, by price |
| override | the engine got this wrong, here | a person, at a station |
| **choice set** | **two right answers** | **a person, or a stated default** |

Nothing was wrong, so it is not an override; neither point is *nicer*, so it is not
a preference. The distinction is what lets the plan say *"a sealed approval stated
two answers and you picked the second"* instead of *"overridden by bob"* — and it is
why a selection is anchored to a **scope** (this section, this fence model) while an
override is anchored to a **station**. An override dies when the fence is redrawn; a
choice should not.

**A choice set is defined by admissibility, not by provenance.** It may come from a
published row, from a model declaration, or from the geometry itself. What keeps it
honest is the dominance filter in §5, not where the ambiguity came from.

## 4 · Where design points come from

Three sources, all present in data we already hold.

**4.1 · A `paired` parameter row (§1.3).** `footing_schedule` binds
`(footing_depth_mm, max_span_mm)` and states several pairs per condition. Each pair
is one design point: a set of parameter bindings. On a 12.192 m run at exposure B
the two published points are 9 posts in 610 mm holes against 6 posts in 762 mm holes
— 400 L of concrete against 334 L (`S-05`).

**4.2 · Bay widths.** `layout.py` already computes an equal-width layout and an
exact-tiling layout and returns the loser as `rejected_alternative`. Both are design
points; a third is generated (§5).

**4.3 · Stub placement.** Where a layout leaves an odd bay, its position is a design
point in its own right — and today it is an artifact: `exact_layout` returns the
remainder last, so the stub lands at the far end of the run **as the person happened
to draw it** (`S-02`). Redrawing the same fence the other way moves it.

## 5 · How many options appear: generate, then filter by dominance

For bay widths, exactly three candidates are generated:

1. **fewest posts** — equal widths at `n = ceil(L / max_span)`;
2. **manufactured tiling** — `floor(L / exact_span)` full bays plus the remainder,
   where the model declares `exact_span_mm`;
3. **best yield** — the largest bay width at or below the next
   whole-pieces-per-board threshold, `(stock + kerf) / k − kerf`.

Then any candidate worse on **every** measure than another candidate is dropped and
never shown. Four measures, all of which the engine already computes:

| Measure | Source |
|---|---|
| posts | the layout |
| boards bought | `plan_cuts()` — kerf-aware, remnant-first, optimality-certified |
| cut operations | the same plan |
| odd bays | widths differing by more than `NUMERIC_TOLERANCE_MM` (1 mm) |

**The odd-bay measure uses the engine's own tolerance on purpose.** `equal_layout`
spreads a remainder one millimetre at a time, so `1667 · 1667 · 1666` must count as
equal — a naive `len(set(widths)) > 1` calls it odd and the filter then offers a
question nobody asked.

Measured through `plan_cuts()`, for a 5 m run with ten slat rows per bay out of 2 m
stock. **`gen` marks which of the three generators proposes each layout** — the other
two rows are measured only to show that the filter would have dropped them anyway:

| Layout | gen | Posts | Boards @ 3 mm kerf | Boards @ 0 kerf | Cuts | Odd bay |
|---|---|---|---|---|---|---|
| 3 × 1667 | fewest posts | 4 | 30 | 30 | 30 | no |
| 2000 · 2000 · 1000 | tiling | 4 | 30 | 25 | 10 / 5 | yes |
| 6 × 833 | best yield @ 3 mm | 7 | 30 | 30 | 60 | no |
| 5 × 1000 | best yield @ 0 | 6 | 50 | 25 | 50 / 25 | no |
| 4 × 1250 | — | 5 | 40 | 40 | 40 | no |

**Two survive with a saw; three survive without one** (`S-04`). With a 3 mm kerf,
`5 × 1000` — the intuitive "one board makes two panels" layout — is dominated
outright: two 1000 mm pieces cost `2 × (1000 + 3) = 2006` against a capacity of
`stock + kerf = 2003`, so each 1 m piece still consumes a whole board. With no kerf
it survives, because it then buys the fewest boards *and* keeps every bay equal, at
two extra posts. **The option count comes out of the data, not out of a cap.**

`waste_mm` is deliberately **not** a measure. A 333 mm offcut clears
`min_reusable_remnant_mm` (300) and becomes inventory, so every layout above reports
zero waste and the differences would be invisible. Reusable remnants are not a
measure either: an offcut is an asset if the yard reuses it and clutter if it
doesn't, and that is not the engine's call to make.

## 6 · What the engine still decides on its own

**Never money.** The engine does not spend the customer's money on its own
initiative; it shows what the alternative saves and waits.

- **Where the engine has an answer today, that answer stays the default.** The
  layout and placement defaults are exactly today's behaviour, so no golden number
  moves and this lands without re-baselining the release gate.
- **A `paired` row, refused today, defaults to the shortest `max_span`** — most
  posts, stiffest fence, cheapest option one click away.
- **A stale point is never a silent fallback.** They re-cut the snapshot and the
  30″/97″ pair is gone: the default applies **and** the plan carries
  `choice_unavailable`, naming the point that vanished and who had chosen it.
- **A set with one surviving point is not a question.** A 6 m run tiled by 2 m
  panels divides exactly, so there is no stub, no placement question, and
  `rejected_alternative` is already `None`.
- **A dependent set whose parent moved is dropped, not orphaned.** Choose equal
  widths and the placement question disappears along with any stored answer to it.

## 7 · Costing the alternatives

Deltas are measured **one choice at a time against the baseline**, never as a cross
product: two questions cost a baseline plus two probes — three passes, not four
combinations. **Each probe is a full `generate()`**, never a cheaper parallel
calculation; a second way of counting posts is how a read model comes to disagree
with the bill of materials.

**Placement questions cost zero probes.** Reordering widths changes no bay width, so
the demand lines and the cut plan are identical — same posts, same boards, same cuts,
only the stations move. The panel says *"no material change"* and means it.

**The run stores physical deltas only** — −3 posts, −3 caps, −66 L, −5 boards.
Money is derived where prices live (the BOM and quote layer), so a price change can
never leave a stale figure on a stored run.

**No silent cap.** Pinning (§8) is what keeps the probe count down rather than a
number we picked, but the count per generation is logged so a runaway is visible.

## 8 · Four things a person can do, coarse to fine

| Act | Says | Anchored to | Mechanism |
|---|---|---|---|
| **choose** | centre the stub on this section | a scope | `project.choices` (new) |
| **place** | that post, there | a station | `pin_post` / `suppress_post` (exist) |
| **lock** | this bay, as I placed it | an interval | `lock_bay` (new directive) |
| **pin the question** | we always dig 610, stop asking | a scope | `project.choices`, `asked: false` |

**Pinning is not choosing.** Choosing answers *this* project and keeps offering the
alternative; pinning says *this is how we work* — no panel entry, no probe, not
counted as an open question. And because a `paired` row binds depth and span
together, **pinning either bound parameter resolves the point**: *"we always dig
610"* and *"posts never beyond 1676"* select the same schedule from opposite ends.

### 8.1 · Five directives exist. One is reachable from the screen.

| Directive | In the UI today |
|---|---|
| `pin_post` | click a station, popover, save |
| `suppress_post` | **no button anywhere** |
| `force_post_sku` | no button, no locale key |
| `force_mounting` | no button, no locale key |
| `force_vertical` | no button, no locale key |

The layout already treats a pin correctly — `fixed = {0, length} | corners |
transitions | pinned | gate_edges | steps`, and `layout_segment` only fills the gaps
between fixed stations. **So the architecture for hand placement is already here;
what is missing is the pointer.** Most of this slice is surfacing what the engine
already accepts, plus one new directive.

## 9 · Dragging a post, in both views

The plan canvas and the side-view profile are separate modules that communicate only
through `state.js`. Putting the drag in both without letting them drift means the
decision cannot live in either one.

### 9.1 · One pure module, two adapters

**`js/post-drag.js` — pure: no DOM, no state, no imports from a view.** The same
role `base-top.js` plays for the profile's base actions, and tested the same way, in
node (`tests/web/test_post_drag_module.py`, after
`tests/web/test_base_top_module.py`).

```text
layoutWithPin(fixedStations, length, station, {maxSpanMm, minSpanMm})
        -> { widths, fixed }                     what the layout becomes
snapCandidates({station, prev, next, maxSpanMm, displayUnit,
                stock: {lengthMm, kerfMm}, rowsPerBay})
        -> [{ station, kind: "round"|"equal"|"yield", label }]
violations(widths, {maxSpanMm, minSpanMm})
        -> [{ index, code, over_mm }]
yieldThreshold(stockMm, kerfMm, pieces)   -> (stock + kerf) / pieces - kerf
```

**Adapter A — the plan canvas (`editor.js`).** The pointer is 2D and the post is
constrained to the run's polyline, so the projection is
`geom.stationAtPoint(run, xMm, yMm)`, which already exists and already mirrors the
backend's station math. The existing drag session (`drag = {kind: "dot" | "ghost"}`)
gains `kind: "post"`; everything else — the 4 px threshold, `pushSnapshot` once at
drag start, the pointer-capture idiom — is reused unchanged. Dragging past a corner
moves the post onto the next segment, which is exactly why §10 has to land first.

**Adapter B — the side-view profile (`profile.js`).** Here the horizontal axis
already *is* the station, so the projection is one division. The module already
drags top dots with a proximity snap (`STEP_SNAP_PX`), so the gesture idiom exists;
the new drag reuses it and delegates its arithmetic to `post-drag.js` rather than
inlining it, which is the rule `base-top.js` exists to enforce.

**Neither adapter touches the other's DOM.** On drop, both write the same override
through `state.js` and both re-render from state, so a post dragged in the plan
appears moved in the profile without either module knowing the other exists.

### 9.2 · What you see while dragging, and what you see on release

**During the drag — geometry only, and free:** a ghost at the original station, both
neighbouring bay widths live in the display unit, and the snap rail. Three snap
kinds, and the third is the one a person cannot judge:

- **round** — a whole unit in the current display preference, via `units.snapStep()`,
  so a centimetre-preference user snaps to centimetres;
- **equal** — the station that makes this bay match a neighbour;
- **yield** — the station that drops the bay to the next whole-pieces-per-board
  threshold. On 2 m stock with a 3 mm kerf the threshold is 998.5 mm, so a 1000 mm
  bay takes 10 boards for ten slat rows and a **998 mm bay takes 5** (`S-07`).
  Two millimetres of post, half the boards.

**On release — one generation, and the bill.** Not during the drag: a generation per
pointer frame is not affordable, and a half-priced drag is worse than none.

**The frontend never claims a quantity it computed itself.** `yieldThreshold` decides
where a *snap tick* goes; the board count on the panel always comes from the backend
generation after the drop. One arithmetic in two places would eventually disagree,
and the read-model rule (never recompute a quantity) is the same rule pointed at the
browser.

### 9.3 · Gesture discipline

The mutation order is the frontend contract's, unchanged:

1. `pointerdown` on a post records the start; **nothing else happens yet**;
2. past 4 px, `pushSnapshot("move-post")` **once**, and the drag begins;
3. `pointermove` draws into a preview layer only — it never touches
   `state.project` and never pushes history;
4. `pointerup` POSTs the override, then `reloadProject()` — not `openProject`,
   which would wipe the undo stack;
5. a pointer that never passes the threshold is a **click**: select the post and
   open its inspector, which is where `force_post_sku` and `force_mounting` finally
   get a control.

Drop a post onto its neighbour and the gesture is a `suppress_post` rather than a
`pin_post` — the delete that has never had a button.

## 10 · A defect this work has to fix first

`PinPost.station_mm` is an **absolute station on the run**, while every point event
in the topology uses a segment-local
`Anchor{segment_index, offset_mm, seg_len_at_authoring_mm}` — a shape that exists
precisely so the system can tell that a segment changed underneath it.

Pin a post 800 mm past a corner, then drag the corner 1500 mm along the first leg,
and station 3800 now lands on the **first** leg, 700 mm *before* the corner. The
post changed legs (`S-09`). With one pinned post nobody notices; with a hand-built
layout it is the first thing that happens.

**The fix is to give a pin the anchor every point event already has**, honouring the
frontend contract's own words: *author with `geom.anchorFor`, resolve with
`geom.stationOfAnchor`, never read `anchor.offset_mm` as a station.* Where a segment
shrinks past its own anchor the override orphans, which the run already reports as
`orphaned_override` — visible rather than silent.

Migration: `station_mm` stays readable for stored overrides and is resolved as
segment 0's offset when no anchor is present, so existing projects keep working and
nothing needs a data migration to be correct on a single-segment run — which is
every run the demo and the golden scenarios use.

## 11 · When a placement breaks a rule

Today the engine wins this argument in silence: pin posts 3 m apart under a 2 m
maximum and `layout_segment` puts a post back in the middle. The person asked for one
bay and got two, with nothing said. **That is the wrong failure** — not a silent
number, a silently ignored instruction.

**Decided: allow it, mark it, attribute it.** The drag succeeds and the post goes
where the pointer went. A locked bay wider than the resolved `max_span_mm` is built
as placed, and:

- the bay renders in the warning treatment on every surface that draws it;
- the plan and the quote both carry `span_placed_over_maximum` with the approved
  figure, the placed figure and the difference (`2438` against `1676`, `+762`);
- the decision graph records that **a person** placed it, with the actor and the
  date, so nothing reads as the engine's own choice (`S-08`).

The engine never silently complies and never silently refuses. That is the standard a
declined published value is already held to, pointed the other way: there we refuse a
number and say so; here we accept one and say so.

The same treatment covers the other direction: a locked bay **narrower** than a
`prefer_min_span_width` rule allows is built as placed and reported through the
`sliver_span` warning that already exists — a person may well want a 400 mm bay
against a wall, and the plan simply says that they asked for one.

An **unlocked** gap is different — the engine may still add posts inside it, because
that gap is what was left to it.

## 12 · The mechanism

```text
published row ─┐
the geometry ──┼─► candidates ─► dominance ─► generate() ─► the run ─► the plan
plan_cuts() ───┘   (3 generated)  (2-3 left)   baseline +    widths ·   alternatives
                                               1 probe/point  physical    with money
                                                    ▲          delta      derived
                    your placements ───────────────┤
                    pin · suppress · lock          │
                                                    │
                    project.choices ───────────────┘
                    scope · point · who · when · pinned?
```

`project.choices` is an **input** to `generate()`, read like any other, and part of
the run digest — which needs `RUN_DIGEST_VERSION` bumped to `digest-v5`. The digest's
own rule decides this: *anything that changes what the run MEANS belongs in the
digest*, and `objective_preset` was removed from it because *a design is what it is
regardless of how it will be bought*. A choice changes the design. So the same
project with the same choices produces the identical run forever, and a new choice
mints a new run id rather than patching an old run's output.

Rendering: a `choice` node in the decision graph, with the losing point on a
`defeated` edge — the existing convention, which already cites the loser. Both
sentences are templated per language, so `he.json` and `en.json` stay key-identical,
and dimensions render through `tu()` so a centimetre preference reads in
centimetres while storage and the wire stay integer millimetres.

## 13 · Three slices

**Slice 1 — the machinery and the two geometry questions.** No boundary work at all:
the candidates come from `layout.py` and `plan_cuts()`, both already here. Choice
sets, `project.choices`, pinning, `digest-v5`, the dominance filter, the panel, the
graph node. Every golden number holds, because every default is today's answer.

**Slice 2 — direct placement.** The anchor fix first, then the drag in both views:
`post-drag.js`, the two adapters, `lock_bay`, `span_placed_over_maximum`, the
suppress gesture, and controls for the three directives that have none.

**Slice 3 — the `paired` row.** Extract design points from the published table and
delete `parameter_paired_unsupported`. Small once slice 1 exists, and it closes the
only thing the Knowledge team is waiting on us for (`conversation.md` T44).

All three are one implementation plan, in this order. Slice 2 depends on slice 1 for
the panel it hangs its controls on; slice 3 depends on slice 1 for the choice-set
types and on nothing in slice 2.

## 14 · Files

| File | Slice | What |
|---|---|---|
| `strategy/choices.py` | 1 | new — `ChoiceSet`, `DesignPoint`, candidate generation, the dominance filter |
| `strategy/layout.py` | 1 | expose the three candidates rather than one chosen layout + one loser |
| `project/model.py` | 1 | `Project.choices` |
| `strategy/generator.py` | 1 | read the choices, probe the alternatives, record physical deltas, `digest-v5` |
| `decisions/graph.py`, `decisions/explain.py` | 1 | the `choice` node and both templates |
| `api/app.py` | 1 | choices CRUD; the alternatives on the run |
| `web/static/js/choices.js` | 1 | new — the panel |
| `strategy/overrides.py` | 2 | `PinPost.anchor`, `SuppressPost.anchor`, new `LockBay` |
| `topology/station.py` | 2 | resolve an override anchor (mirrors `make_anchor`) |
| `web/static/js/post-drag.js` | 2 | new — pure drag arithmetic, snaps, violations |
| `web/static/js/editor.js` | 2 | adapter A: `drag.kind === "post"` |
| `web/static/js/profile.js` | 2 | adapter B: the station axis it already has |
| `web/static/js/inspector.js` | 2 | the post inspector: sku, mounting, vertical |
| `knowledge/parameters.py` | 3 | `paired` rows become design points |
| `web/static/i18n/{en,he}.json` | 1–3 | every new code, both bundles, key-identical |

## 15 · How we will know it works

- **The golden gate does not move in slice 1.** Every default is today's answer; a
  moved number means a default changed by accident.
- `tests/web/test_post_drag_module.py` runs the pure module in node: the yield
  threshold at 998/1000, an equal-snap, a violation at 2438 against 1676, and a drag
  past a corner changing `segment_index`.
- A dominance test over the measured table in §5: two survivors at 3 mm kerf, three
  at zero, and `5 × 1000` dominated in the first and not the second.
- A stale-choice test: remove the chosen point from the snapshot, assert the default
  applies **and** `choice_unavailable` names it.
- An anchor test: pin a post, lengthen the first segment, assert the offset from the
  corner is unchanged — the test that fails today.
- One golden scenario at a run length where the **shallow** footing option wins, so
  the panel is exercised in both directions rather than only the one the 40 ft run
  happens to show.

## 16 · What this deliberately does not do

- **It does not price a design during a drag.** Geometry live, money on release.
- **It does not let the frontend compute a quantity.** The yield threshold places a
  snap tick; every count on the panel comes from the backend.
- **It does not move the stub default.** Centred is the better look and moving it
  re-baselines the gate; it is one click away instead.
- **It does not add a company-level pin.** *"We always dig 610"* is not a fact about
  this fence, and its honest home is a company default a project can depart from.
  Slice 1 records pins per project and leaves that seam named.
- **It does not touch the boundary contract.** Consuming a `paired` row needs no
  amendment: the shape is ratified and correct, and what was missing was ours.

## 17 · Open

1. **Are those the right four measures?** Posts, boards, cuts, odd bays. Remnants
   were left out on purpose (§5).
2. **Does the post inspector belong in this slice or the next?** Three directives
   have no control at all; giving them one is cheap once a post is selectable, and
   it is also scope this design did not set out to cover.
