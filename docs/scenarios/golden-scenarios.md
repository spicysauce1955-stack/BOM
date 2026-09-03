# Golden scenarios

Concrete, numeric scenarios that every architecture and implementation decision must survive.
Each scenario becomes an automated test (`tests/scenarios/`) walking the full spine:
**Topology → Knowledge → Strategy → Decisions → Requirements → Fulfillment → BOM.**

All lengths in **integer millimeters**. All scenarios use the shared demo catalog and
knowledge base defined below unless stated otherwise.

## Shared demo catalog

| SKU | Kind | Consumption semantics | Key data |
|---|---|---|---|
| POST-S | ground post (soil) | indivisible discrete | set in concrete footing |
| POST-S-HD | heavy-duty ground post | indivisible discrete | substitutable for POST-S (rule-gated) |
| POST-M | masonry post/bracket | indivisible discrete | required on masonry base |
| POST-CAP | post cap | indivisible discrete | 1 per post |
| RAIL-3000 | rail stock | divisible linear | purchase length 3000, kerf 3, min reusable remnant 300 |
| SCREW-S10 | screw | packaged discrete | engineering unit: 1 screw; box of 20 |
| CONC-25 | concrete bag 25 kg | volume/coverage | 0.5 bag per soil post footing (policy) |
| GATE-KIT-1000 | gate assembly | assembly/kit | contains: 1 gate leaf 1000 mm, hinges, latch; requires reinforced posts both sides |

Demand model per generated span: 2 rails cut to span clear width; 4 screws per rail end (2 rails × 2 ends × 4 = 16 screws/span... **fixed: 4 screws per rail-end connection, 2 rails × 2 ends = 4 connections = 16 screws/span** — scenario fixtures use 8/span with 2 screws per connection; the exact policy is a knowledge FACT, not code).

## Shared demo knowledge base

| ID | Type | Statement |
|---|---|---|
| K-MAXSPAN | HARD CONSTRAINT | span width ≤ 1800 (manufacturer, non-overridable) |
| K-MASONRY | HARD CONSTRAINT | masonry base segment ⇒ masonry mounting (POST-M) |
| K-GATE-REINF | COMPANY RULE (hard authority) | gate opening ⇒ reinforced/HD posts on both sides |
| K-EQUAL | PREFERENCE | prefer equal span widths within a run |
| K-SLIVER | PREFERENCE | avoid spans < 500 |
| K-STEP-SLOPE | HEURISTIC | slope > 15% ⇒ prefer stepped panels over raked |
| K-REMNANT | FACT (policy) | rail remnant reusable if ≥ 300 |

## Scenarios

### S01 — Straight fence
6000 mm straight run on soil, height intent 1800.
Expect: 4 equal spans of 1500 (not 3×1800+600), 5 posts (POST-S), decisions cite K-MAXSPAN + K-EQUAL.

### S02 — 3 m construction with nominal 1.8 m sections
3000 mm run. 1×1800+1×1200 is feasible; 2×1500 preferred via K-EQUAL.
Expect: 2 spans of 1500; the decision node lists the rejected alternative `[1800, 1200]` with the preference that demoted it.

### S03 — Angles / corners
L-shape: run A 4000 mm, 90° corner, run B 3000 mm.
Expect: shared corner post (one physical post serving both runs), span layout computed per run; corner post decision cites the corner topology node.

### S04 — Uphill installation
6000 mm run, elevation 0 → 1000 mm (16.7% slope).
Expect: stepped vertical behavior chosen citing K-STEP-SLOPE; per-span step heights recorded; posts get per-post ground elevation.

### S05 — Part ground / part brick wall
7000 mm run: 0–4000 soil, 4000–7000 existing brick wall (base interval attribute).
Expect: base transition creates a structural boundary at 4000 (post there), POST-S on soil side, POST-M on masonry side; mounting decisions cite K-MASONRY + the base interval.

### S06 — Changing wall elevation + privacy-height constraint
Run on a wall whose top varies (interval data); user intent: minimum privacy height 1800 above ground on the far side.
Expect: per-span fence heights differ to satisfy intent; height decisions cite the intent annotation + wall profile facts.

### S07 — Cutting 3 m rails including kerf
Spans of widths 1500, 1500 (S01-style 2-span run). Rails: 2 per span → cuts [1500×4].
From RAIL-3000 stock (kerf 3): one stock gives 1500 + 3 + 1497 → NOT two 1500s. Expect: 4 stock rails? No — expect cut plan where each stock yields one 1500 plus a 1497 remnant that is *not* reusable as another 1500; plan needs 4 stock… **Expected result computed by the cut planner, verified by invariant: total cut lengths + kerf ≤ stock length per stock bar; remnants ≥ 300 recorded as reusable.** Fixture pins the exact plan.

### S08 — Individual screws, packaged purchase
Demand 48 screws.
Expect: purchase 3 boxes (60), overage 12 recorded; BOM line pegged to the span connection demands.

### S09 — Inventory remnants
Inventory holds one RAIL remnant 1250 mm. Demand includes a 1200 cut.
Expect: remnant allocated (1200+kerf ≤ 1250), one fewer new stock bar; allocation honors the catalog's remnant-reuse policy (min_reusable_remnant_mm — catalog data, not a KB object; see review response).

### S10 — Gate with contextual structural rule
5000 mm run with a 1000 mm gate opening at 2000–3000.
Expect: GATE-KIT-1000 selected; both flanking posts upgraded per K-GATE-REINF; spans laid out on the remaining 2000+2000; gate decisions cite the gate topology node + rule — `governed_by` K-GATE-REINF on the POST upgrade, while the kit SKU cites the gate event it came from (no rule chose it).

### S11 — User override
S01 topology; user pins a post at station 2000.
Expect: regeneration preserves the pinned post (spans 2000 side: 2×1000 or per preference; remaining 4000 laid out independently); pinned decision marked `pinned`, generator output cites the override as input.

### S12 — Expert correction → rule candidate
Expert moves a generated post onto an existing concrete foundation point (marked as topology obstacle/feature) and comments "always use existing foundations when within 300 mm".
Expect: correction stored as project override; system proposes a KNOWLEDGE CANDIDATE (with triggering example, scope, condition sketch); candidate is **inactive** until human approval.

### S13 — Conflicting preference and hard constraint
Company preference "spans exactly 1800 for series X" (soft) on a 5000 mm run where equal spans would be 1667.
Expect: hard K-MAXSPAN cannot be violated; conflict between K-EQUAL and the 1800 preference is *surfaced* in the decision node (both cited, winner + why), not silently resolved.

### S14 — Text annotation → structured intent
Annotation on run: "keep the top aligned with the neighbour's fence (approx. 1750)".
Expect: AI (or stub) proposes structured intent `top_line = level @ 1750` with confidence + original text preserved; intent is `proposed` until confirmed; once confirmed, height decisions cite it.

### S15 — Two eligible stock lengths, chosen by the objective
Own catalog (not the shared demo catalog above — see note): two divisible-linear rail
stocks eligible for the same slot, RAIL-3000 (3000 mm, kerf 3, 1800c, priority 1) and
RAIL-3050 (3050 mm, kerf 3, 1850c, priority 2). Demand: 4 rails cut to 1500 mm.
A 1500 mm piece costs 1503 mm against capacity (stock + kerf) per the kerf model
(cutplan.py: `n·(piece+kerf) ≤ stock+kerf`). RAIL-3000 capacity is 3003 mm, so only
one 1503 mm piece fits per bar (2 × 1503 = 3006 > 3003) → 4 new bars → 4 × 1800c =
7200c. RAIL-3050 capacity is 3053 mm, so two pieces fit per bar (2 × 1503 = 3006 ≤
3053) → 2 new bars → 2 × 1850c = 3700c. The nominal lengths alone (3000 vs 3050)
give no reason to expect a different piece-per-bar count; only planning the cuts
does.
Expect: under `least_cost`, RAIL-3050 is chosen for all 4 lines (3700c < 7200c)
despite its lower stated priority and higher per-bar price — cost beats priority.
Under `honour_priority`, RAIL-3000 is chosen (priority 1 wins regardless of cost),
buying 4 bars. Either way one product answers the whole group — a demand is never
split across two SKUs (that is SAP's usage-probability model, deliberately
rejected). The decision records the rejected candidate for the explanation.
Note: this scenario intentionally uses its own two-rail catalog fixture rather
than the shared demo catalog, because giving RAIL a second, cheaper-per-cut stock
in `demo_catalog()` would change S07's answer (S07 depends on RAIL-3000 being the
only rail stock) and break the compatibility gate S01–S14 established.

### S16 — A routed vinyl line: the post is part of the panel
6000 mm straight run on soil, height intent 1800, built to **M-VINYL** (a
built-in model, and the products below are in the shared demo catalog).

A routed vinyl fence is the case a panel-only model cannot express: the rails do
not sit on the post, they go **through** it, into holes punched at the factory.
So M-VINYL declares a `PostSlot` whose eligibility is a PREDICATE rather than a
list of SKUs — `item.material == "vinyl"` **and**
`item.routed_at_mm == panel.rail_positions_mm` **and** a `post.kind` → routed-face
mapping (below) — and its cap is matched against the post already chosen
(`item.fits_face_mm == post.face_width_mm`).

The factory cuts before the post ships, so it decides two things and both are
the fence's, not the post's: at what HEIGHTS to punch, and WHICH FACES to cut.
The catalog therefore carries six routed posts, two heights × three positions,
each declaring `routed_at_mm` and `routed_faces`:

| position | `routed_faces` | 1800 | 2100 |
|---|---|---|---|
| line (2 faces, 180°) | `opposite` | POST-V-1800 (9800c) | POST-V-2100 (11 500c) |
| end (1 face) | `single` | POST-V-1800-END (9500c) | POST-V-2100-END (11 200c) |
| corner (2 faces, 90°) | `adjacent` | POST-V-1800-CORNER (9800c) | POST-V-2100-CORNER (11 500c) |

All six are the same extrusion: 90 mm face, 2600/2900 mm long. A variant is a
different CUT, so mixing positions along a run does not change the bay — only
the price of the routing that was skipped moves.

M-VINYL maps position to routing as data, in the predicate: `end` and `gate` take
`single` (one panel meets the post; a gate leaf hangs off hardware, not through a
hole), `line` and `transition` take `opposite` (a bay each side, at 180°), and
`corner` takes `adjacent`. `junction` is deliberately unmapped — three runs
meeting needs a post cut on three faces and this line does not make one, so the
generator refuses that fence by name (see the refusals below) instead of standing
a two-face post where three panels have to land.

Expect, in order (this is the resolution DAG, and the scenario exists to pin it):

1. **height** 1800 per bay, from the height intent.
2. **rail positions** [150, 1650] — `placement_positions` over the panel's one
   horizontal frame slot (2 rails, `rails_per_span`, 150 mm inset top and bottom)
   placed up that height.
3. **post** — the height picks the routing and the POSITION picks the faces, so
   the 5 stations are **not one SKU**: POST-V-1800-END at stations 0 and 6000
   (each is the end of the run, routed on one face) and POST-V-1800 at 1500, 3000
   and 4500 (routed on two opposite faces). POST-V-2100 and its variants are not
   a worse buy: their holes are already punched 300 mm from where this panel puts
   its rails, so they are a fence that cannot be assembled. This is the fact a
   manufacturer states outright — the layout has to be known before the posts can
   be ordered, because a 14-post run is 2 end + 11 line + 1 corner.
4. **cap** CAP-V-90 at all 5, because every variant's face is 90 mm — the cap
   reads the post already chosen, and here the three variants agree.
5. **clear opening** 1500 − 90 = **1410** per bay (one whole face is lost across
   the two ends).
6. **panel**: 4 bays of 1500; rails cut 1500 (centre_to_centre — a routed rail
   runs to the post centreline, which is what the hole is for); 9 slats per bay
   cut **1470** and starting at 165 in panel coordinates
   ((1650 − 150) − (30 + 30) + 15 + 15, the two 60 mm rail faces less what seats
   into each 18 mm channel); 9 × 150 = 1350 of the 1410 opening, and the 60 mm
   residual halves into **30 mm at each edge** (`center` × `truncate`) where the
   post's own routed channel takes it up — never into the gaps between boards,
   which are 0.

BOM: 3 × POST-V-1800 (29 400c), 2 × POST-V-1800-END (19 000c), 5 × CAP-V-90,
3 × CONC-25 (5 posts × ½ bag, rounded up), 8 × RAIL-V-3000 (8 cuts of 1500; two
1503 mm pieces need 3006 mm against a 3003 mm capacity, so one cut per bar — the
S15 arithmetic), 9 × SLAT-V-150 (36 cuts of 1470; 4 × 1473 = 5892 ≤ 6003, so four
per 6000 mm bar). Total **119 300** agorot. **No screws at all**: a board held in
a channel top and bottom is not fixed, and a model carrying a fixing rule for
symmetry would put real money on a real BOM.

At height intent 2100 the same model and the same catalog give rails at
[150, 1950], POST-V-2100 mid-run with POST-V-2100-END at the two termini, and a
1770 mm slat — which is what makes step 3 an answer rather than a lookup.

On an L-shape (runs 0→4000 and 4000→3000, one model) the corner node resolves to
**POST-V-1800-CORNER**, the two far termini to POST-V-1800-END, and every
interior station to POST-V-1800: one topology, three products, and the position
is the only thing separating them.

**The two refusals**, which stay distinct because the position term and the
routing term are separate conjuncts and `sole_excluding_term` names only the ONE
that excluded everybody:

* height intent 2000 → rails at [150, 1850], nothing is routed there →
  `post_routing_mismatch` at station 0, `wanted = "150, 1850"`,
  `routed = "150, 1650; 150, 1950"`. Routing alone is the discriminator, so the
  sentence can name both position sets.
* a junction where three runs meet → the position term alone excludes everybody
  and it says nothing about rail positions, so the honest answer is the generic
  `no_item_covers_part_spec` at that station rather than a routing sentence about
  heights that are not the problem.

### S17 — A section is asked why, and answered; then argued with
Three topologies, because the scenario asks three different things. A **6000 mm straight
run** on soil for the decisions and the conversation, an **L-shape** (runA
4000 mm, 90° corner at n2, runB 3000 mm) for the two expectations that only
exist when there is more than one section — isolation, and the corner post they
share — and an **8000 mm straight run with a 1000 mm gate asked for at station
3000** for the run-level fact that names no element at all.

This is roadmap step 5 — *"focus on specific sections of the fence and get only
the decisions related to the selected section. change, comment or start a
conversation about it!"* — and it is a scenario rather than a unit test because
the property it defends spans the whole spine: the decision graph, the topology
that defines what a section IS, the learning store, and the boundary between a
human's words and what gets built.

Expect:

1. **Only this section's decisions.** Every returned decision settled something
   about run1. On an L-shape, asking about `runA` returns no `@runB` element.
   And it says WHAT was decided, not merely that something was — a scenario
   asserting non-emptiness is a slower unit test. On the straight run: three
   equal bays (`[0,2000]`, `[2000,4000]`, `[4000,6000]`), the four posts that
   carry them, and the layout sentence naming both the alternative it beat and
   the rules that decided it — "Alternative [2438, 2438, 1124] was rejected
   because of K-EQUAL@v1. Governed by K-EQUAL@v1, K-MAXSPAN@v2."
2. **The run-level decisions are included.** `run_geometry` and
   `choose_vertical_mode` decide for the SECTION and name no element; they are
   what a person asking about a section wants first, and a scope-refs-only
   reading would drop exactly those. **A gate fact is one of them.** On the
   gated run the section's story contains the `gate_event` for `ev_gate` — "A
   gate was asked for between 3000 mm and 4000 mm." — ahead of the two gate
   posts at 3000 and 4000 that it forced. The gate names no element (the posts
   and the opening do), so it reaches its section through `run_id` in its
   payload or not at all; without it the reader is shown the effects and never
   the cause. These sentences are rendered in the READER's language, so a count
   inside one is grammar and not a number: at an end node, where one section
   stops, Hebrew reads «צומת n1 בשרטוט, שבו מסתיים קטע אחד», never the plural
   «נפגשים 1 קטעים» — and at the L-shape's corner, where two really do meet,
   the plural is the correct form.
3. **A shared corner post reaches both sections.** It is decided once and stands
   on both, so neither section's story has a post that appeared from nowhere.
4. **Causal order.** Decisions arrive by graph ordinal, which is causal order by
   construction — every edge points from a lower ordinal to a higher one.
5. **The section view refuses a moved drawing** (409 `topology_changed`), because
   a section is a topology object and "the decisions for section A" stops being
   true when A may no longer be that stretch. `/explain/{element}` does **not**
   refuse: an element id is self-identifying, and the asymmetry is the difference
   between the two questions.
6. **A comment is stored verbatim against the decision**, in
   `Correction.decision_ref` — scoped by `generation_run_id`, because a decision
   node id means what it means only within the run that generated it
   (`core/ids.py`: generated ids may not be referenced across runs).
7. **The conversation reads back in the order it was said**, with a timestamp on
   every turn.
8. **Commenting changes no fence.** The stored run is byte-identical before and
   after. A comment is evidence; it becomes an interpretation, an interpretation
   becomes a PROPOSAL, and only a human confirms — the same boundary S12 draws
   for a correction and S14 for an annotation. **AI never decides.**

9. **The section explains exactly what the setting-out sheet lays on it.** Every
   element the structure report puts in a section — its setting out and its bays
   — appears in that section's decision trail. Two independent read models over
   one run, joined: if the sheet lays out a post the trail never explains, one of
   them is describing a fence the other did not build. This is the spine's own
   consistency check, and it is asserted as containment rather than equality
   because the trail legitimately explains more than the sheet draws.

### S18 — The same rail, continuous in one colour and per-bay in another
Boundary contract obligation 14, in its own words: *whether a member runs
continuously through an intermediate post is **derived** from stock length
against the resolved spacing, not authored.*

Own catalog and own model (the shared demo catalog has one rail stock, and giving
it a second would move S07 exactly as S15 records). **M-BOARD**: one horizontal
frame slot, `length_rule="centre_to_centre"`, `joint="through"`, a `colour` option
axis, and a `layout_policy` contribution of `max_span_mm = 2464` (97 in). Two
products behind the axis: `RAIL-16FT-WHITE` (4877 mm stock, kerf 3) and
`RAIL-12FT-BLEND` (3658 mm, kerf 3). Topology: 9600 mm straight run on soil,
which lays out as four 2400 mm bays with three intermediate line posts.

**Nothing in the model says "continuous".** `post_joint="through"` says the rail
is detailed to pass the post rather than stop at it — a capability, on its own
field because `joint` already names the housing a frame member gives the infill.
The behaviour is derived, and the two colours derive differently from the
identical document:

| colour | stock | two bays (4800 mm) | pieces | 16 ft/12 ft bars |
|---|---|---|---|---|
| White | 4877 mm | fits | 2 runs × 2 rails, each 4800 mm | **4** |
| Blend | 3658 mm | does not | 4 bays × 2 rails, each 2400 mm | **8** |

Expect:

1. **Two `MemberRun`s in White, none in Blend.** Each White run covers two bays,
   threads exactly one line post, and records the stock length it was derived
   against (`basis="stock_length"`, `authored="derived"`).
2. **The demand line is emitted once for the run, pegged to every bay it
   crosses** — `engineering_qty` 2, not 2 per bay. Four rail pieces in White
   against eight in Blend is the over-ordering the obligation exists to stop; the
   cut plan then buys 4 bars against 8, because a 2400 mm piece and its kerf
   cannot be paired inside 3658 mm.
3. **A rail cut for rolling terrain is per-bay on the graded bays only.** With
   elevations 0 mm at 0 and 4800 and 800 mm at 9600, the two flat bays are one
   piece and the two climbing ones are cut per bay. The *mode* (`Span.vertical`)
   is resolved for a whole run, so it cannot be the test; the bay's own
   elevations are.
4. **`continuity` survives as an authored override, and never decides in
   silence.** Authored `per_bay` against a derived two-bay piece is built per bay
   and carries `warning.continuity_override_disagrees` with both answers in its
   params. Authored `continuous` on a butt-jointed rail is built continuous —
   the case the contract keeps it for, *"a guide states the behaviour outright
   and gives no length"* — and carries the same warning. The one thing it cannot
   do is order a piece longer than the bar: 12 ft stock against a 2400 mm bay
   gives `warning.continuity_override_unbuildable` and a per-bay cut.
5. **The structure sheet and the bill agree.** A continuous rail appears under
   every bay it crosses, because the crew meets it in each, and its row carries
   `shared_with` — the demand line's own pegs, inverted — so four bays of one
   continuous rail do not read as four rails. Nothing in `report/` recomputes it.
6. **Both `derive_continuity` and all three warnings render in Hebrew and
   English** from `decisions/explain.py` templates, not from the generic payload
   dump.

Authoring refusals (`validate_model`): continuity on a vertical frame member, and
continuity under a length rule with no registered `CONTINUITY_JOINS` entry. Both
are carried-and-never-read otherwise, which is what that table exists to close.

S18's fence is also a fixture in the cross-scenario invariant battery
(`through_rail`) with its own committed gate file, because no other fixture puts a
`MemberRun` in front of the traceability, determinism and cut-plan-conservation
invariants. It carries its own catalog and model library, for the reason S15
records: two more rail stocks in `demo_catalog()` would move S07.

**S16 is not a counter-example.** A routed vinyl rail "goes through the post" in
S16's prose, and `RAIL-V-3000` over two 1500 mm bays is exactly 3000 mm — yet
M-VINYL derives per bay, correctly. Its rail is `centre_to_centre`, *"cut to the
post centrelines, each end seats half a face deep into the hole it was punched
for"*: one bay long, with two rails meeting inside each intermediate post. The
hole passes through the post; the rail does not.

### S19 — A footnote at the foot of fourteen pages, in the annexe once
Boundary contract obligation 10 and §3.3.5: *every warning declares what it
attaches to, and its text is primary* — and it is rendered **where its
`attaches_to.kind` says**, which for `document`, `warranty` and `maintenance` is
once in the plan's annexe and never on a line.

The obligation exists because v0.1's rule was falsified by a census of all 81,794
elements: only **19.9%** of 1,038 warning instances sit inside a step that does
something, while about **68%** are document-scoped — the front safety box,
"BEFORE YOU BEGIN", a freeze-thaw footnote printed at the foot of fourteen pages.
Enforced literally, "a warning lives on its step" publishes one warning in five
and misattributes the rest.

6000 mm straight run on soil, height intent 1800, built to **M-VINYL** — the
shared demo model and the shared demo catalog, because this scenario adds no
product and moves no price. M-VINYL's document carries four quoted warnings, one
per rendering:

| `attaches_to` | the sentence, in short | renders |
|---|---|---|
| `document` | CAUTION, footings below the frost line | the annexe |
| `step` → `cure` | WARNING, do not load an uncured footing | on that step |
| `product` → `SLAT-V-150` | not rated as a pool barrier | that BOM line |
| `warranty` | void on substituted components | the annexe |

Expect:

1. **Four bays, and the safety box once.** The run lays out as four 1500 mm bays
   — M-VINYL's own maximum span, as S16 records, and not the 2000 mm the straight
   demo run gets from `K-MAXSPAN`; the annexe carries exactly two entries, and
   neither appears against any bay, post or BOM line. A freeze-thaw footnote
   printed against four bays is already noise; against a forty-bay job it is what
   teaches a reader to skip warnings.
2. **83 printings, one entry, and the count published.** The same sentence
   repeated — the corpus's own number — collapses to one annexe entry carrying
   `instances`, so "shown once" is a decision the reader can see rather than
   something that looks like all there was. Two documents quoting the same
   sentence stay two entries, because which document said it is half of what a
   reader needs in order to check it.
3. **Nothing is dropped:** `Σ instances + not_in_plan ≡ the warnings carried`,
   the same shape as `Σ(parts) ≡ BOM` and `unplaced`. A warning about another
   document's sku is counted and not printed — a stranger's safety notice does
   not belong on this plan — and a warning attached to a `procedure` this engine
   does not model is reported as unplaceable rather than filed away as somebody
   else's.
4. **The text is never localized and never translated.** `text_raw` + `lang` are
   carried verbatim through the annexe, the step and the BOM line; the
   publisher's `severity_lexeme` (`CAUTION` beside `WARNING`) is not mapped onto
   this engine's `info | warning | error`, because the two words carry different
   legal weight. A publisher's optional `code` is carried and never becomes the
   sentence — it gets no entry in either locale bundle, which is the registry
   split obligation 10 forces (`core/warnings.py`).
5. **An unattributed warning says so.** §1.1 makes `SourceRef.id` opaque and
   forbids building one, so a curator authoring a warning here cannot mint a
   citation and one of M-VINYL's four has none. It renders as unattributed: a
   sentence nobody can trace must not look like one an engineer confirmed against
   a drawing.
6. **No cost, no line and no decision moves.** The BOM, the requirement lines and
   the decision graph are byte-identical to the same run before the document
   carried any warnings. A warning is a note on an answer, not an input to one.

Authoring refusals (`validate_model`): a warning on a step this model has not
got, about a sku the catalog has not got, or about another product line —
because at render time a target that is not in the plan is indistinguishable from
another document's warning, and the author is the only person who can tell those
apart.

## Invariants checked across all scenarios

- span width ≤ applicable hard maximum, **or** a `lock_bay` override placed that bay
  and the run carries `span_placed_over_maximum` naming it (see below)
- Σ(cuts + kerf) ≤ stock length for every stock bar in a cut plan
- package purchases ≥ engineering demand
- every BOM line traces to ≥ 1 requirement line, every requirement to ≥ 1 strategy element, every element to ≥ 1 decision
- every decision's inputs reference existing objects
- hard constraints never overridden silently (violations always surface as conflicts/errors)
- original annotation text preserved verbatim alongside any structured interpretation
- knowledge candidates never active without human approval
- **a run is never failed over a gap** — absence produces a warned plan and a `Gap`, never a refusal (see below)

### Never-block — a run is never failed over a gap

*Added 2026-08-25, when the integration contract was ratified at v1.1. It reverses
what the invariant suite asserted until that day, and the reversal is the point:
`tests/scenarios/test_invariants.py::test_missing_hard_knowledge_is_generation_failure`
asserted that an empty knowledge base **must** raise.*

Contract §3.2.4 binds this repo to *"never fail a run over a gap — warned, named,
unfulfilled lines instead."* Read the old way, an exposure category no published row
covered produced no plan at all, on `max_span_mm`, the single most important
parameter in the system; and the exposure grew with every row the other team
published. A bill of materials that visibly lacks something is more useful than no
bill of materials.

- **Absence is a `Gap`, never a failure.** A parameter no rule covers, a default
  nobody stated: the plan is generated, the lines it affected are warned, and the
  gap carries `would_close` — one sentence naming the row that would resolve it, so
  a curator reads a work item rather than a filing.
- **Every gap is visible three ways**: on the drawing (a `StrategyWarning` with
  `code + params` in both locale bundles), in the trail (a `gap` node, confidence
  `uncertain`, governed by nothing — which *is* the explanation), and in the report
  (`Strategy.gaps`). **`POST /gaps` (§3.2.6) is not built** — the gaps are
  produced, stored and readable on the run, and the route that reports them back
  to the Knowledge Platform is a named seam, not a shipped feature.
- **The never-block gaps, in full.** Four today, and the list is the point — a
  silent default that is not on it is a defect, not a design:
  `uncovered_max_span` (nobody stated the span basis for a product line),
  `uncovered_rails_per_span` and `uncovered_screws_per_span` (nobody stated the
  per-bay counts), `no_default_post` (nobody named the ground-post product).
- **Reporting a default never MOVES it.** The three uncovered parameters keep the
  numbers they always had — 1800 mm, 2 rails, 8 screws — because changing one
  would silently reprice every job that ever relied on it, which is a different
  and much larger change. The defect closed is narrower: the engine answered a
  question nobody had answered and said nothing. A run whose knowledge stops
  stating `rails_per_span` still builds two rails a bay, at the same cost, and
  now carries the gap, the warning and the graph node that say where the number
  came from (`test_reporting_the_count_moved_no_quantity_and_no_price`).
- **Aggregated per section and per model line, never per bay.** These parameters
  resolve under the segment's model scope, so the row that would close the hole
  is one row: a 40-bay fence is ONE work item with all 40 bays named in
  `element_refs` and their count in `params["n"]`. Forty identical warnings
  naming no bay between them is the failure mode this rule exists to avoid, and
  a per-run summary that dropped the bay list is the other one.
- **A hard tie fails only between two `authored` rules.** One touching a published
  row is a `Conflict`: a warned line and a review task.
- **What still refuses is unchanged**: a violated `hard_constraint`, and input that
  cannot be carried out (a model id that does not exist, an authored model naming a
  SKU nobody stocks). A gap is *something nobody told us*; neither of those is.

The audit of all thirteen refusal sites, with the verdict and the reasoning on each,
is `docs/reviews/generation-failure-audit-2026-08-25.md`. Asserted by
`tests/strategy/test_never_block.py` and by the invariant suite.

### The hard maximum's one authorized exception — a bay somebody placed

*Added 2026-09-03 with `lock_bay` (design §11). Until that day the hard-max
invariant read "unless authorized exception exists — none in demo KB", and there
were none: a bay wider than the resolved maximum meant no plan at all.*

The engine used to win this argument in silence. Pin two posts 3 m apart under a
1.8 m maximum and `layout_segment` put a post back in the middle — the person
measured one thing and the drawing showed another. So a bay a person placed by
hand is now built **as placed**. The exception is exactly one, and it is stated as
a conjunction so that the guard got *narrower* rather than absent:

- **A bay may exceed the resolved maximum only when a `lock_bay` override put it
  there.** Anything else — a layout bug, a knowledge rule with a wrong number, a
  boundary the layout mishandled — still raises `GenerationFailure`. That is the
  whole point of the restatement: the danger was never the locked bay, it was an
  *accidental* over-wide bay quietly ceasing to fail and shipping as a warned line
  that looks like somebody meant it.
- **Allowed, marked, attributed.** The run carries
  `span_placed_over_maximum` — `{run_id, placed_mm, max_mm, over_mm, author}`, so
  every surface that draws the bay has the approved figure, the placed figure and
  the difference — and the decision graph carries an `override_applied` /
  `lock_bay` node with the `author` on it, because a departure with no name on it
  reads as the engine's own choice.
- **The authorization is scoped to the locked interval, not to the run.** The bays
  the engine laid out beside a locked one are still under the maximum, and one
  lock in a section authorizes one bay.
- **A lock the layout could not honour authorizes nothing.** A corner, a gate edge
  or a terrain step inside the interval means this is no longer the bay that was
  signed off on: the lock is not applied (`orphaned_override` reports it) and the
  gap is laid out normally.
- **A locked bay *narrower* than a `prefer_min_span_width` rule keeps the existing
  `sliver_span`** and gets no second code — a 400 mm bay against a wall is a thing
  people want.
- **An unlocked gap is still subdivided.** That gap is what was left to the
  engine.

Asserted by `tests/strategy/test_lock_bay.py` and by the invariant suite
(`test_span_width_within_hard_max_unless_a_lock_placed_it`).
