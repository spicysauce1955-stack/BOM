# Two right answers, and a pointer for when neither is yours

**Date:** 2026-09-03 · **Status:** DESIGN, rev 2 — **rewritten after four adversarial
reviews**. §0 records what changed and why; the reviews' verdicts on rev 1 were
RETHINK and INADEQUATE, and they were right.
**Contract:** frozen at **v1.3**. §13 is the boundary analysis: **no amendment**, two
registry additions, three of our eight obligations bind the design.
**Also:** ADR-0002 (int mm at rest), ADR-0003 (anchoring), ADR-0004 (overrides),
ADR-0007 (layout, cut planning), ADR-0011 (design vs supply identity)
**Plans:** `plans/2026-09-03-choice-sets-backend.md` and
`plans/2026-09-03-choice-sets-frontend.md` — two tracks, one seam (§14).

---

## 0 · What the review changed, and why rev 1 could not be patched

Every measured number in rev 1 was correct — 30 of 30, re-derived independently. The
wiring was not. Four things changed shape; everything else follows from them.

| Rev 1 assumed | The code says | Rev 2 |
|---|---|---|
| A design point can bind `max_span_mm` directly | One resolution path exists — `resolve_param` — carrying authority precedence, hard-tie collapse, a declined-source ceiling and a `governed_by` ref. Bypassing it makes the run report *"no rule states max_span_mm"* about a sealed engineering table | **A parameter point becomes synthesized `KnowledgeVersion`s** (§12), as a model's `layout_policy` already does. A *layout* point binds no parameter and needs none — §5.1 |
| A candidate can be measured at the layout site | `resolve_panel` runs **after** the span loop and consumes the bay width the layout produces. Circular. The three fields rev 1 read (`sm.infill_stock_mm`, `_kerf_mm`, `_rows`) do not exist | **Nothing is measured outside a real generation** (§7). `strategy/measure.py` is deleted before it is written |
| The scope of a question is the section | The block sat inside a **per-segment** loop. Any corner, gate, step — or one pinned post — emitted duplicate questions and applied one answer to a segment it was never measured for | **One pass decides default and alternatives, over gaps between fixed stations.** Scope is the gap |
| Two questions cost three generations | A probe called full `generate()`, which probed again: `G(n) = 1 + n·G(n-1)`. Two questions cost **5**; six sections cost **1957** | **`offer_alternatives` is an input flag** (§7). `n` questions cost `1 + n` by construction |

Six more findings that each killed a claim rev 1 made in print:

- **Placement is not free.** `continuity._greedy_extent` walks bays *in station order* —
  *"how many of these bays one piece covers, starting at the first."* Reordering
  `2000·2000·1000` into `1000·2000·2000` changes a continuous rail from `4000+1000` to
  `3000+2000`: **+2 boards on 4**. A terrain step or gate edge can make it ±1 post.
- **The yield cliff was on the wrong length.** An infill piece is cut to the *clear
  opening*; `clear_opening_mm` subtracts a whole post face. With a 90 mm post a 1000 mm
  bay yields a 910 mm slat and two already fit, so there is no cliff at 1000 at all.
- **"Odd bay" was a preference wearing a filter's clothes.** Drop it and the tiling
  layout dominates *the layout this engine ships today* on posts, boards and cuts.
- **Four fixed measures do not fit every question.** On a 3 m run both footing points
  give identical posts, boards and cuts — the panel would print "same everything" for
  answers 25% apart in concrete, which §4.1 quotes and never measured.
- **`"choice"` is not a `NodeKind`** (closed `Literal` of 12), and `defeated=` mints an
  `input_fact` node per ref — a design-point id would have **invented a fake knowledge
  fact**, against that method's own comment.
- **A selection keyed on a generator name is not an identity.** `fewest_posts` is
  *defined relative to* `max_span`, so answering a footing question silently turned
  "three equal bays of 1667" into two bays of 2500.

And two that would have failed on the first run: `plan_cuts` **raises** on a piece longer
than its stock, so measuring the deep-footing point (2439 mm bays) crashed a generation;
and the yield snap tick at station 4002 made the *previous* bay 2002 mm — 2 mm over the
maximum passed into the same function call.

## 1 · The problem, in one paragraph

Sometimes more than one fence is right, and this engine hides it. A published
`footing_schedule` states *"24″ holes with posts up to 66″ apart, **or** 30″ holes up to
97″"* — both stamped by the same engineer — and we refuse the whole table
(`parameter_paired_unsupported`). A 5 m run with 2 m panels can be three equal bays or two
panels and a stub, and the engine picks one by a flag nobody set. And when a person places
a post by hand, the layout puts another one back in the middle without a word. Three
shapes of one problem: **the engine decides where nothing entitles it to decide, and says
nothing about the answer it discarded.**

## 2 · What changes for the person

The plan carries its open questions. Each shows the answer it wasn't and the difference in
things you can count — with the publisher's own words on the row, because obligation 5
requires it (§13):

```text
Section A · gap 0–5000 · 2 open questions · 1 pinned · 2 posts placed by hand

BAY WIDTHS
▸ 2000 · 2000 · 1000    two bays uncut, one stub      built
○ 1667 · 1667 · 1666    every bay the same width      same posts · same boards · +20 cuts

WHERE THE SHORT PANEL SITS
▸ 2000 · 2000 · 1000    at the far end                built
○ 2000 · 1000 · 2000    centred                       −2 boards
○ 1000 · 2000 · 2000    at the start                  −2 boards

FOOTINGS · exposure B                            pinned for this job — not asked
  24″ deep (610 mm) · posts ≤ 66″ (1676 mm)
```

...and when none of the offered answers is the one you want, **you drag the post where it
goes**, in the plan or the side view, and the engine re-flows only the gaps you left alone.

## 3 · The concept

A **choice set** is a question: two or more **design points**, all admissible, where
nothing in the data prefers one. A person answering it makes a **selection**. A fifth kind
beside the four the foundation keeps apart:

| Kind | Says | Resolved by |
|---|---|---|
| hard constraint | must | the evaluator, or the run fails |
| preference | nicer if | the evaluator, by precedence |
| objective | minimise this | supply resolution, by price |
| override | the engine got this wrong, here | a person, at a station |
| **choice set** | **two right answers** | **a person, or the default** |

Nothing was wrong, so it is not an override; neither point is *nicer*, so it is not a
preference. That distinction is why a selection is anchored to a **scope** while an
override is anchored to a **station** — an override dies when the fence is redrawn, a
choice should not. It is also why **a selection is not a correction** (obligation 7): a
correction says the engine got it wrong; a selection picks between answers that are all
right.

## 4 · Where design points come from

**4.1 · A `paired` parameter row (§1.3).** `footing_schedule` binds
`(footing_depth_mm, max_span_mm)` and states several pairs per condition. On a 12.192 m run
at exposure B: 9 posts in 610 mm holes (400 L of concrete) against 6 posts in 762 mm holes
(334 L).

**4.2 · Bay widths.** The layout the engine builds, plus the manufactured tiling where the
model declares `exact_span_mm`, plus a yield-driven width where the baseline's resolved
infill has a stock length.

**4.3 · Stub placement.** Where a layout leaves an odd bay, its position is a design point
— and today it is an artifact: `exact_layout` returns the remainder last, so the stub
lands at the far end of the run *as the person happened to draw it*.

## 5 · Which points are offered

### 5.1 · Two kinds of point, and only one needs synthesizing

- A **parameter point** asserts parameter values (`footing_depth_mm`, `max_span_mm`). It
  becomes synthesized `KnowledgeVersion`s and is resolved by `resolve_param` like any
  rule — so precedence, hard ties, defeat edges and `governed_by` all keep working.
- A **layout point** is a width list for one gap. It binds no parameter and bypasses no
  evaluator: `layout_segment` is a function the generator calls, and every offered width
  list already honours the *resolved* `max_span_mm` and `min_span_mm`.

Keeping these apart is what makes the fix precise rather than blanket.

### 5.2 · The default is always offered and never eliminated

Whatever the engine builds is a point, first in the list, exempt from filtering. That one
rule retires four separate failures: the built layout being absent from its own panel, a
`choice_unavailable` firing for a point being built on the same screen, a `min_span` rule
that only *warns* in `layout_segment` while *rejecting* in candidate generation, and
`prefer_equal=False` producing a baseline no generator proposes.

### 5.3 · Dominance over commensurable axes only

A point is dropped when another point is at least as good on **every axis both carry** and
strictly better on one. Axes are **open** — a point carries what it differs on:

| Axis | Where it comes from | On which questions |
|---|---|---|
| `posts` | the probe's own post elements | every layout point |
| `boards`, `cuts` | the probe's own cut plans, per product | any point whose pieces change |
| `concrete_l`, `holes` | the probe's own BOM | footing points |

**"All bays equal" is printed on the row, not filtered on.** It is taste, and taste does
not eliminate. `odd_bay` as a filter axis was the only thing hiding that our own default
is dominated on posts, boards and cuts.

Nothing is measured that a generation did not produce. There is no second cut packer, no
`rows_per_bay` guess, and no candidate measured on a length the planner will never see.

## 6 · What the engine decides on its own

**Never money.** It shows what the alternative saves and waits.

- **Where the engine has an answer today, that answer stays the default** — so no golden
  number moves and the release gate needs no re-baselining.
- **A `paired` row, refused today, defaults to the shortest `max_span`** — most posts,
  stiffest fence, cheaper option one click away.
- **A stale point is never a silent fallback.** The widths a selection names are no longer
  offered → the default applies **and** `choice_unavailable` names the widths and their
  author. **Including when the question was pinned**, which then reopens: telling a person
  to choose again through a control that pinning removed is not a report.
- **A set with one point is not a question.** A 6 m run tiled by 2 m panels divides
  exactly; there is no stub and no placement question.
- **A dependent set whose parent moved is dropped, not orphaned.**

## 7 · Costing, and the order that makes it possible

```text
phase 1   lay out every gap by default-or-selection            → the baseline strategy
          panels resolved, products chosen, cut plans built
phase 2   per gap, derive alternative width lists FROM the baseline
          (the model's exact_span; the resolved infill's stock + kerf)
          probe each: generate(..., offer_alternatives=False)
          diff the physical counts; filter; attach to the run
```

**Candidate generation moves after the baseline too**, not only measurement — the
yield-driven width depends on the resolved infill product, which does not exist until the
panel is resolved.

`offer_alternatives=False` inside a probe bounds depth at 1, so **`n` questions cost
`1 + n` generations**. Each probe is a full `generate()`: a cheaper path needs a second
implementation of post counting, and the moment it disagrees the panel advertises a saving
the cut list does not deliver.

**The run stores physical deltas only.** Money is derived where prices live (ADR-0011:
what a fence *costs* belongs to a `SupplyRun` against one yard), so a price change can
never leave a stale figure on a stored run. `boards` and `cuts` are physical counts from
the probe's own plan, not a purchase promise — the panel labels them as such.

## 8 · Four things a person can do

| Act | Says | Anchored to | Mechanism |
|---|---|---|---|
| **choose** | centre the stub in this gap | a scope | `project.choices` |
| **place** | that post, there | an anchor | `pin_post` / `suppress_post` |
| **lock** | this bay, as I placed it | an anchor + a width | `lock_bay` |
| **pin the question** | we always dig 610, stop asking | a scope | `asked: false` |

Pinning is not choosing: choosing answers *this* project and keeps offering the
alternative; pinning says *this is how we work*. And because a `paired` row binds depth and
span together, **pinning either bound parameter resolves the point**.

**Five directives exist; one is reachable from the screen.** `pin_post` has a
click-and-popover; `suppress_post`, `force_post_sku`, `force_mounting` and
`force_vertical` have no control and no locale key. The layout already treats a pin as a
hard boundary — `fixed = {0, length} | corners | transitions | pinned | gate_edges | steps
| model_transitions` — so most of "full control" is surfacing what the engine accepts.

## 9 · Dragging a post, in both views

### 9.1 · One pure module, two adapters that are NOT symmetric

**`js/post-drag.js` — no DOM, no state, no view imports, and no `units.js`** (it imports
`state.js`). The role `base-top.js` plays for the profile's base actions, tested the same
way in node.

```text
layoutWithPin(fixedStations, length, station, {maxSpanMm, minSpanMm})  -> {widths}
snapCandidates({station, prev, next, maxSpanMm, minSpanMm,
                displayUnit, stock: {lengthMm, kerfMm}, piecesPerBay})
        -> [{station, kind: "round"|"equal"|"yield", label}]   already filtered
violations(widths, {maxSpanMm, minSpanMm}) -> [{index, code, over_mm}]
yieldThreshold(stockMm, kerfMm, pieces)    -> (stock + kerf) / pieces - kerf
```

**Adapter A — the plan canvas.** `geom.stationAtPoint(run, x, y)` returns
`{station, dist}`, not a number, and discards which segment won — so the anchor is
re-derived with `geom.anchorFor`. The post `<circle>`s carry **no** `data-*` attributes
today and need them, and the existing `click`→`inspect` handler needs a suppress latch so
a completed drag does not also open the inspector.

**Adapter B is not the trivial one.** `profile.js buildChain()` chains **several runs**
with `GAP_MM` spacers and a `reversed` flag; `gsOf = offset + (reversed ? L - s : s)`. So
the x axis is a *global chain* coordinate: a naive division moves a post the wrong way on
a reversed run and into the wrong run on a chain. It uses `localStationOf(entry, x)`.

**Snap candidates are filtered through `violations()` before they are drawn.** The rev-1
yield tick made the neighbouring bay 2 mm over the maximum passed into the same call.

**The yield tick is labelled per bay, never as a board count.** The threshold is on the
*clear opening*, so it converts through the resolved post face; and `plan_cuts` packs
globally, pairing a 998 with a 1002 across bays, so per-bay yield is not decomposable into
a run-level promise. The browser computes a *position*; every count comes from the backend.

### 9.2 · Gesture discipline

1. `pointerdown` on a post records the start; nothing else happens.
2. Past 4 px, `pushSnapshot("move-post")` **once** — from `history.js`, not `state.js`.
3. `pointermove` draws into a preview layer only: never `state.project`, never history,
   never a fetch.
4. `pointerup` **DELETEs the pin this drag started from, then POSTs the new one.** There is
   no `PUT /overrides` in the frontend, so without the delete a second drag leaves two pins
   and a bay nobody asked for.
5. Under 4 px it is a **click**: select the post and open its inspector, which is where the
   three unreachable directives get their controls.

**The dropped post stays where it was dropped, as a PENDING marker.** The posts on the
plan are drawn from the last generation, and a drop does not regenerate — so without this
the post springs back to where the old run put it and a working feature reads as a broken
one. The marker is drawn from `state.project.overrides`, visibly distinct from a generated
post, and it is telling the truth rather than papering over it: **a pin is a fact about the
project and is saved immediately; a post position is a fact about the run and has not been
recomputed.** Showing them as two kinds of thing is the honest rendering of that.

Dropping a post onto its neighbour is a `suppress_post` — but only a **line** post can be
suppressed; a corner, gate edge, step or pinned post cannot, so the gesture is refused at
the pointer rather than creating an override that immediately reports itself orphaned.

## 10 · One anchor resolver, two behaviours

`anchor_station` re-anchors **proportionally** when a segment's length changed (ADR-0003),
and `geom.stationOfAnchor` mirrors it. Rev 1 added a second resolver that kept the offset
rigid — putting the same pin 800 mm apart in the two views.

**The policy goes on the anchor:** `Anchor.reanchor: "proportional" | "rigid"`, honoured
inside `anchor_station` itself and mirrored in `geom.stationOfAnchor`. A post is `rigid`
(800 mm from the corner stays 800 mm from the corner); an elevation sample stays
`proportional`. One resolver, one semantics per anchor, no divergence.

`PinPost.station_mm` stays readable for stored overrides — every golden scenario is
single-segment, where both readings agree — and a directive carrying neither an anchor nor
a station orphans loudly rather than pinning at station 0.

## 11 · When a placement breaks a rule

Today the engine wins this argument in silence: pin posts 3 m apart under a 2 m maximum and
`layout_segment` puts a post back in the middle. **Decided: allow it, mark it, attribute
it.** A locked bay is built as placed, and:

- the bay renders in the warning treatment on every surface that draws it;
- the plan and the quote carry `span_placed_over_maximum` with the approved figure, the
  placed figure and the difference (`2438` against `1676`, `+762`), plus the actor — which
  lives on `Override.author`, not on the directive;
- the decision graph records that **a person** placed it;
- a locked bay *narrower* than a `prefer_min_span_width` rule uses the existing
  `sliver_span`, because a 400 mm bay against a wall is a thing people want.

**This is not a contract matter** (§13) but it *is* the first authorized exception to
`golden-scenarios.md`'s hard-max invariant, which already anticipates one: *"unless
authorized exception exists — none in demo KB."* The invariant is restated as a
conjunction and `tests/scenarios/test_invariants.py` enforces the new form, so the next
accidental over-max span does not look authorized.

An **unlocked** gap is different: the engine may still add posts inside it, because that
gap is what was left to it.

## 12 · The mechanism

`project.choices` is an input to `generate()`, threaded exactly as `site` and `parts` were
— `generate()` takes no `Project` and a fitness test forbids a domain module loading its
own data.

A `Selection` carries **the widths it chose**, not the name of the generator that proposed
them: `fewest_posts` is *defined relative to* `max_span`, so a name is not an identity.

**The digest is not versioned.** `choices` joins the hashed positional list **only when
non-empty**, so every existing run id stays stable and the first recorded choice still
mints a new one. Over-splitting is safe; under-splitting serves the wrong fence under a
reused id, which is what a `RunMeta` field would have done. `digest-v5` is not needed.

`NodeKind` gains `"choice"` — it is a closed `Literal`. The losing point rides a
`defeated` edge **only for a parameter point**, whose synthesized version has a real ref;
a layout point's loser goes in the node payload, because `defeated=` materialises a
knowledge node per ref and a design-point id there would invent a fact.

## 13 · Effect on the boundary contract

**No amendment.** Consuming a `paired` row is amendment **006**, ratified and in force at
v1.3. Nothing here edits either copy of `contract.md`.

**Two registry additions**, explicitly not amendments (§2: routing them through
ratification *"would destroy the property that lets the two teams move at different
speeds"*):

- the platform codes `choice_unavailable` and `span_placed_over_maximum` — §2's table says
  *"whoever raises it; both locale bundles required"*;
- one `EntityRef.kind` value where a gap's subject is a section — an open registry on the
  same terms as `TaskCode` and `SourceClass`.

**Three of our eight obligations bind the design:**

| | Obligation | Effect |
|---|---|---|
| 4 | **Never fail a run over a gap** | `plan_cuts` raising on a 2439 mm bay would have failed a run over a published table. §7's ordering removes it |
| 5 | **Convert units once, keep the source lexeme for display** | The panel shows `24″ (610 mm)`, not `610 mm`. `Quantity.value_raw` carries the lexemes and rev 1 discarded them |
| 6 | **Report gaps back with evidence, via `POST /gaps`** | `choice_unavailable` crosses the boundary, so the code is declared to them — the registry mechanism, not a courtesy. It is also useful to them: a re-cut removed a point a customer had chosen |

Obligations 1, 2, 3, 7 and 8 are unaffected. **Choice sets and selections never cross** —
derived per run, or stored on the project.

**And one thing that looks like a contract matter and is not.** A person building a bay
wider than a published, sealed maximum breaches **no obligation**: none of the eight
requires Planning to honour a published hard constraint. Reading it the other way would
have sent the other team a false amendment.

## 14 · Two tracks, one seam

**Backend — ~70% of the work and all of the risk.** `strategy/choices.py` (new),
`layout.py`, `topology/station.py`, `overrides.py`, `decisions/graph.py`,
`generator.py` (the four shape changes), `explain.py`, `project/model.py`, `api/app.py`,
`knowledge/parameters.py`, and the invariant in `docs/scenarios/` +
`tests/scenarios/`.

**Frontend.** `js/post-drag.js` (new, pure), `js/choices.js` (new), `editor.js` and
`profile.js` (the two adapters), `inspector.js`, `history.js` (choices are not in
`snapshot()`), both locale bundles, and `tools/ui_smoke.py` cases that assert through
`check()` — the harness does no image diffing, so a screenshot-only case reports PASS
while the anchor bug ships.

**The seam:** two JSON surfaces — the run's `choice_sets`, and the overrides endpoint —
plus exactly one arithmetic in both languages, `yieldThreshold`, pinned by a node test
against the Python reference. `post-drag.js` is pure and needs nothing from the backend,
so the tracks are independent for most of their length.

## 15 · How we will know it works

- **The golden gate does not move** while every default is today's answer. Asserted by
  literals derived from the demo knowledge (`max_span_mm = 1800` → a 5 m run is
  `[1667, 1667, 1666]`), not by a fixture attribute that can only be produced by calling
  the thing under test.
- **`n` questions cost `1 + n` generations**, asserted on a count carried on the result
  rather than a cross-test accumulator.
- **Two runs agree on the questions too** — `strategy`, `graph` *and* `choice_sets` dumps
  equal, extending `test_determinism` rather than re-asserting that a digest equals itself.
- **A pin resolves exactly as every other anchor does** — `override_station(...) ==
  anchor_station(...)` on a segment that changed length, which is the one case rev 1's
  tests avoided.
- **The two yield thresholds are one formula** — a parametrised grid emitted by node and
  compared against the Python function, including the degenerate `pieces = 0` row where JS
  gives `Infinity`.
- **A reversed declaration reverses the bindings** — the `paired` column names are read
  from the declared `value_type`, and the test that claims it uses a fixture whose declared
  order differs from its value order.
- **The default is shown even when dominated**, and a choice never fires
  `choice_unavailable` for a point being built.
- **One golden scenario at a run length where the shallow footing wins**, so the panel is
  exercised in both directions and not only the one the 40 ft run happens to show.

## 16 · What this deliberately does not do

- **No pricing during a drag.** Geometry live, money on release.
- **The frontend never computes a quantity.** It computes a snap position.
- **The stub default does not move.** Centred is the better look and moving it re-baselines
  the gate; it is one click away instead.
- **No company-level pin.** *"We always dig 610"* is not a fact about this fence; its home
  is a company default a project can depart from. Recorded per project, seam named.
- **No auto-generation.** Generation stays behind the explicit button. A drop shows the
  placement as a pending marker (§9.2) rather than firing a run — the rule is kept without
  the feature looking defective.
- **The contract is not touched.**
