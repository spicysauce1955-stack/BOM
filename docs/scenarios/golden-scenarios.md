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

## Invariants checked across all scenarios

- span width ≤ applicable hard maximum (unless authorized exception exists — none in demo KB)
- Σ(cuts + kerf) ≤ stock length for every stock bar in a cut plan
- package purchases ≥ engineering demand
- every BOM line traces to ≥ 1 requirement line, every requirement to ≥ 1 strategy element, every element to ≥ 1 decision
- every decision's inputs reference existing objects
- hard constraints never overridden silently (violations always surface as conflicts/errors)
- original annotation text preserved verbatim alongside any structured interpretation
- knowledge candidates never active without human approval
