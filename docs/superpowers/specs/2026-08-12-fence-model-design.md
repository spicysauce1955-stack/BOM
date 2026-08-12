# Fence models: what a section is made of, and which items may make it

Status: proposed · 2026-08-12

Today the structure of a fence is two integers. `Span.rail_count` and `Span.screws_count`
are resolved from `K-RAILS`/`K-SCREWS` during generation, `derive_requirements` turns them
into two lines, and the side view draws the bay as a plain rectangle. There is no picket,
slat, board, channel, clip or spacer anywhere in the repository, and no way to say that one
product line is built differently from another.

This spec introduces the missing object: a **fence model** — a named, versioned product
line ("דגם הייטק") that owns the structure of a normal panel, its variants, its material
and colour options, and the set of items eligible to supply each of its parts.

Two neighbouring pieces are deliberately **not** in this spec: **ground clearance** (its own,
smaller spec, and a prerequisite — it defines the panel's bottom datum) and **gates**
(handing, swing arcs, sliding and cantilever, which will reuse the composition mechanism
defined here). See *Sequencing* at the end.

## What the trade and the adjacent industries actually do

Estimating engines for fencing already work exactly this way: they take a run length, a
fence type and a height, and apply the type's spacing rules to compute posts, rails, panels,
fittings and hardware. Fence Cloud's breakdown engines are per fence type; Visual Fence Pro
ships "dozens of fence-style specifications". So "a named type owns the structure" is the
industry's unit of organisation, not an invention.

The concrete rules that a model has to be able to express, all of them observed:

1. **Rails are a function of height** — roughly one per 600 mm (4 ft → 2, 6 ft → 3,
   8 ft → 4). Post size and embedment ladder with height too (4×4 to 5 ft, 5×5 above;
   18–24″ deep at 4 ft, 30–36″ at 8 ft). Variants by height are the norm, not an edge case.
2. **Infill count is a fit, not a multiplication** — `n ≈ L / (member + gap)`, with a
   residual that has to go somewhere.
3. **The fixing method changes the BOM more than the count does.** Real slat systems split
   three ways: slats slide into U-channels and are held by the frame ("channels hold the
   panels securely without the need for individual fasteners… each four-piece panel
   assembles with just four bolts", FenceTrac); every slat is screwed (2 per rail crossing);
   or only the top and bottom slats are screwed and **spacers** hold the rest apart. In the
   third case the gap between slats is itself a purchased part.
4. **Board-on-board and shadowbox are patterns, not new concepts** — overlapping and
   alternating boards, costing 30–40 % more material, fall out of a repeating member
   sequence if a member may carry a *negative* gap and a face offset.
5. **A panel model constrains the layout.** "Installed slat width determines spacing for
   2nd post" (Home Depot slat kit instructions); Ultra Fence ships pre-assembled 6 ft
   sections in six discrete heights. For panel-based models the span layout is not free and
   a height off the ladder is unquotable.
6. **The Israeli market names models and configures three axes.** דגם הייטק, דגם אוריין,
   דגם 2411, גדר פסים דגם 121; one shop's configurator asks exactly *גוון עמודי הגדר*,
   *גוון השלדה*, and *גובה הגדר והמרווח בין השלבים* — post finish, frame finish, and
   height-plus-slat-gap, as independent axes. Prices are quoted both ₪/מטר רץ and ₪/מ״ר.

For the *shape* of the data model, the closest engineered precedent is Revit's railing type:
a **rail structure** (non-continuous rails, each with height, offset, profile and material)
plus a **baluster placement pattern** with a justification (Beginning / End / Center /
Spread Pattern To Fit), an excess-length-fill policy, base/top constraints per member, and
**posts as a separate concept from pattern members**. That vocabulary is adopted here rather
than reinvented.

The closest *industrial* analogue is aluminium window and façade fabrication software —
LogiKal (18,000 users, supplier-independent across 450+ catalogues, with automated system
checks), SchüCal, Klaes, Stolcad. Two lessons: the "system" (profile series) is the
organising object, exactly as proposed here; and bar optimisation is a headline value driver
in that trade, not a nicety.

In BOM vocabulary what follows is a **configurable BOM** (a 150 % BOM) that resolves per
span into a variant BOM.

### Safety and code rules

Every gap this feature introduces is regulated somewhere: the 100 mm sphere test on openings
(4″ in the US), 50–100 mm maximum clearance under a barrier, an anti-ladder rule requiring
the middle rail ≥ 1143 mm above the bottom rail, gates that must swing away from a pool, and
ASTM F2200's 57–406 mm entrapment zone near a moving gate.

These are **seed data in the demo knowledge base, not architecture**. All of the values above
are US/AU/UK; the shipping product is Hebrew-first and Israeli standards have not been
researched. The mechanism is jurisdiction-agnostic — they are `hard_constraint` knowledge
objects scoped by `context`, carrying params (`max_clear_gap_mm`, `max_ground_gap_mm`,
`min_rail_separation_mm`) checked against the resolved panel. Replacing the numbers is a
data change.

## Naming

`report/structure.py` already uses **Section** for a whole run (tagged A, B, …) and **Bay**
for a span, and those tags are on screen today. The model's unit of structure is therefore a
**panel** — `PanelSpec` — and "section" keeps meaning the run.

The new module is `fenceai/fencemodel/` (`model.py`, `fit.py`, `resolve.py`, `demo.py`); a
bare `models/` package would collide with the per-package `model.py` convention used
everywhere else in `src/fenceai/`.

## The shape of the thing

```
FenceModel                        # "דגם הייטק" — immutable version, like knowledge
  id, version, name_i18n, grade   # residential | commercial | industrial
  status                          # draft | active | retired
  height_support                  # Continuous(min,max,step) | Discrete([1000,1200,…])
  layout_policy                   # what it asks of span layout (see "Two touch points")
  option_axes: [Axis]
  default_spec: PanelSpec
  variants: [Variant]             # first match wins, by specificity then order

Variant     condition: Expr, spec: PanelSpec
PanelSpec   frame: [FrameSlot], infill: InfillSpec | None, fixings: [FixingRule]

FrameSlot   key, orientation, placement, length_rule, requirement
InfillSpec  orientation, pattern: [Member], justification, excess, edge_margin_mm, supply
Member      key, width_mm, thickness_mm, face_offset_mm, gap_after_mm,
            base_ref, top_ref, requirement
FixingRule  key, basis, qty_per_basis, requirement

LayoutPolicy  max_span_mm?, exact_span_mm?, preferred_span_mm?, post_role_by_height?

Axis        key, label_i18n, kind ("enum" | "numeric"), values, available_when: Expr | None
```

`role` and quantity live on the `PartRequirement` (below), not on the slot, so there is one
place that says what a part *is*. `LayoutPolicy` is the model's ask of the span layout; every
field in it is emitted as a knowledge-shaped contribution rather than read directly (see
*Two touch points*).

Three fields earn their place. `Member.gap_after_mm` **may be negative**, which is how
board-on-board and shadowbox become ordinary patterns. `face_offset_mm` places a member on
the front or back face, which is what makes shadowbox a pattern rather than a special case.
And `FixingRule.basis` is a closed vocabulary —
`per_member_crossing | per_member | per_end_member | per_gap | per_frame_member | per_panel`
— which covers every fixing method found in the research, including spacers-as-parts,
without becoming a scripting language.

`Variant.condition` reuses the closed AST in `knowledge/ast.py`, evaluated against a span
context. "Below 1200 mm, two rails instead of three" is one `Cmp` node, and the winning
variant becomes a decision node like everything else.

### The panel's geometry

A `PanelSpec` is authored in the panel's own frame so it can be laid into any bay:

- **x** runs 0 → clear width, **y** runs 0 → panel height, origin at the bottom-left of the
  *opening*.
- **y = 0 is the panel bottom** — ground plus clearance once the clearance spec lands, the
  ground (or built base top) until then. Height intent stays **ground-to-top**, so clearance
  reduces panel height and never moves the top line. This agrees with `top_line: level`,
  which already pins an absolute top elevation.
- **Clear width is not `Span.width_mm`.** That is centre-to-centre; the opening is c/c minus
  the two half post faces. Both numbers are needed for different purposes, so a frame slot
  declares its `length_rule`: `clear_between_posts | centre_to_centre | overlap(mm)`. A rail
  housed between posts is cut to clear; a rail lapped across their faces is cut to c/c.
  Getting this wrong is a wrong number on a cut list.

**Placement** is a closed vocabulary: `from_bottom(mm)`, `from_top(mm)`, `fraction`,
`distributed(count, bottom_inset, top_inset)`. Infill members take Revit's base/top
constraint — `base_ref`/`top_ref` name frame slots — so "slats between the bottom rail and
the mid rail" is expressible rather than special-cased.

**Under rake and step**, member length is constant only when a member spans between two
*parallel* frame members. In a raked bay the rails slope together, so rail-to-rail slats keep
one length and only their end cuts are angled; a member running to the panel's top or bottom
datum in a raked bay has a different length at every position. Stepped bays are rectangles
and never have this. A resolved slot therefore carries either one length × N or a length
**list**, and the spec for each slot says which. The cut planner already copes with either.

### Fitting the pattern

`fenceai/fencemodel/fit.py::fit_pattern()` is pure, mirroring `strategy/layout.py`:

```
fit_pattern(axis_len_mm, pattern, justification, excess, edge_margin_mm)
  -> FitResult { count, actual_gap_mm, edge_margin_start_mm, edge_margin_end_mm,
                 residual_mm, member_lengths_mm, rejected_alternative }
```

`justification` takes Revit's four values. `excess` decides the residual: `truncate` (leave
the gap), `space` (widen all gaps evenly — the default, and what "spread pattern to fit"
means), `trim_last` (rip the final member), or `extension_clip` (a catalogued part that
closes the last gap to the post). `space` and `trim_last` produce **different BOMs** from the
same model and the same width; that is the point of the feature.

Gaps are stored **clear** (face to face), because that is what the sphere test measures;
on-centre is derived.

## Multiple eligible items per part

A slot must not name a SKU. Three questions were tangled in that one field:

**1 · What must exist here?** A `PartRequirement` on the slot — role, length, length basis,
quantity. No product. This is the panel's business and nothing else's.

**2 · Which products may satisfy it?** An `Eligibility`, attached to the **slot**, not to the
product. (PTC Windchill documents the same choice for SAP alternate item groups: "one
alternate item group for every line number that has a substitute" — the alternates hang off
the BOM *usage link*.)

```
PartRequirement  role, length_mm?, length_basis?, qty, eligibility
Eligibility      group?: str, members: [EligibleItem], predicate?: Expr
EligibleItem     sku, priority, supply, conversion?: Ratio, approval
                 supply  = ready_made | cut_from_stock | assembly_component
                 approval = auto | suggest_only
```

Members are ordered, and the order is the company's stated priority — the shape SAP's
alternative item group has used for decades. SAP's **usage probability is deliberately not
adopted**: it splits demand across alternates (70 %/30 %) for MRP forecasting, and splitting
one fence's rails across two SKUs would be nonsense.

The eligible set may legitimately mix a ready-made 2600 mm post, 2 m tube, 3 m tube, a
competitor's equivalent profile and a yard remnant — different consumption semantics, one
requirement. The parts ledger already survives this: it balances per `(sku, unit)` precisely
so that "a tube bought as a post and cut as a rail" accounts correctly.

A **property predicate** may generate members instead of enumerating them, ETIM/eCl@ss style,
over the catalog's `attrs`. One hard rule: the predicate is resolved and **frozen into the
run's snapshot**. Property-based eligibility is dynamic by nature, and a new catalog product
silently changing what an accepted quote meant is finding A2 of the structure review
happening again.

This subsumes `SubstitutionRule`, which exists in the catalog today and is documented as
data that is never applied; its `auto | suggest_only` policy becomes `EligibleItem.approval`.

**3 · Which one is actually used?** Not a lookup — an **objective**, resolved in fulfillment,
coupled to the cut plan. You cannot rank stock lengths without planning the cuts. With the
kerf accounting already in `cutplan.py` (`n` pieces fit iff `n·(piece+kerf) ≤ stock+kerf`),
1000 mm pieces at a 3 mm kerf give **one** usable piece from a 2000 mm stick and **two** from
a 3000 mm stick — not the two and three that nominal division suggests.

Selection uses lexicographic tiers with named presets, as ADR-0007 already specifies:

| Tier | `least_cost` (default) | `honour_priority` |
|---|---|---|
| 1 | eligibility + approval policy (hard) | eligibility + approval policy (hard) |
| 2 | purchase cost | member priority |
| 3 | waste | purchase cost |
| 4 | member priority | waste |
| 5 | deterministic id order | deterministic id order |

Two presets rather than one hardcoded order, because a company with an own-brand policy and
a company chasing margin want opposite answers. Knowledge may select the preset per project
or per series.

**When nothing fits**, report minimal relaxations rather than a bare failure — "no eligible
product: relax the finish, or allow 2500 mm stock, or permit suggest-only substitutes". This
is model-based diagnosis (minimal conflict sets); the configuration literature names
explanation as the standing weakness of commercial configurators, and we already have a
decision graph to hang it on.

## Two touch points with generation

**The model owns product structure; knowledge owns numbers that can conflict.** Structure —
what a panel is made of, in what pattern, with what fixings — is product data and conflicts
with nothing. Numbers — max span, preferred span width, post embedment, the post SKU for a
height band, allowable gaps — are exactly what manufacturer constraints, company rules and
site overrides already fight over.

So the model gets **no private channel into the generator**. Its `layout_policy` is emitted
as knowledge-shaped contributions (`SetParam(max_span_mm)`, `PreferSpanWidth`,
`DefaultComponent(role=…)`) scoped to `series=<model_id>` at manufacturer authority. They
enter the same evaluator, resolve by the same tiers, and lose visibly with a `defeated` edge
when a company rule outranks them.

```
resolve model + options (per interval event)
      ↓ contributes scoped, knowledge-shaped params
   span layout            ← existing evaluator, with the model now in the fight
      ↓ per span
resolve_panel(spec, span_ctx) → ResolvedPanel { slots: [ResolvedSlot] }
      ↓
derive_requirements expands slots → pegged lines
      ↓
fulfillment resolves eligibility → BOM + cut plans
      ↓
the same slots render the elevation
```

`resolve_panel` is pure and deterministic and needs no knowledge access — the parameters are
already resolved onto the span, exactly as `rail_count` is today.

A `ResolvedSlot` carries **aggregate quantity plus fit parameters** (count, actual gap,
margins, member lengths), never a stored list of rectangles. Geometry is a pure function of
those parameters, which keeps "read models are derived, never stored" intact.

That function has two potential callers, Python and JS. The codebase has mirrored maths
across that boundary before (`geom.anchorFor` mirrors `make_anchor`), but that is a two-line
formula and this is not. **Geometry is served from the server** as a derived read model
beside the structure report; `profile.js` draws what it is given. One implementation, one set
of tests, and clicking a slat can select its part line because both came from one object.

## Options, materials, colour

An axis is a question asked of the customer, and not all of them are cosmetic:

- **enum** axes resolve products (`post_finish: RAL7016 | RAL9005 | wood-look`);
- **numeric** axes feed the fit (`slat_gap: 10 | 20 | 30`, `height`).

For product resolution, each `PartRequirement` binds to **at most one axis** —
`option_axis: str | None` plus `sku_by_option: {value: sku}` — because every real example
found binds one part to one axis: post colour picks the post, frame colour picks the rails,
slat colour picks the slats. A full cross-axis variant table is where to stop, not where to
start; `Axis.available_when` is the escape hatch for a genuine dependency.

**An enum axis narrows eligibility; it never bypasses it.** `sku_by_option[chosen]` names a
preferred member *of the requirement's eligibility set*, and a value naming a SKU that is not
an eligible member is a model-validation error at load, not a silent override. So a colour
choice can never smuggle in a product the slot does not allow, and the selection in §3 still
runs — over the narrowed set. The full chain is:

```
option value → the eligible member it names   (must be a member)
             ↓ absent
               eligibility members in priority order → selection objective
             ↓ empty
               knowledge DefaultComponent(role) → no_eligible_item
```

An enum value carries a `swatch` so the elevation draws the fence in the chosen colour. Pick
a colour, the drawing changes, and the SKU beneath it changes with it.

### Pricing

`Product.price_cents` is flat per purchase unit; the market quotes ₪/מטר רץ and ₪/מ״ר. Pricing
becomes a discriminated union defaulting to today's behaviour:

```
FlatPrice(cents)             # default — current behaviour, nothing moves
LinearPrice(cents_per_m)
AreaPrice(cents_per_m2)
BandPrice([(max_mm, cents), …])
```

Integer discipline holds per ADR-0002: `(cents_per_m * length_mm + 500) // 1000`, one
documented rounding, no float. This is the only change outside the new module, and
`fulfillment/quote.py` is where it surfaces.

## Selection, snapshots and reproducibility

Model selection is a topology interval event, so a fence may change model partway along a
run just as it changes base or height:

```
FenceModelPayload(kind="fence_model", model_id, version_pin: int | None,
                  options: {axis_key: value})
```

with a project-level default (a typed field replacing the relevant part of
`Project.policy`'s bare dict).

`GenerationRun` already stamps `knowledge_snapshot` + `snapshot_hash`. It gains
`model_snapshot: [(model_id, version)]` and `eligibility_hash` on the same footing, and
**`Quote` stamps both too** — it already carries `inventory_hash` and
`knowledge_snapshot_hash`, and without the model and eligibility snapshots an accepted quote
silently changes meaning when someone edits a model or adds a catalog product.

`bind_scope()` gains two dimensions from these facts: `series` (the model id) and `context`.
That closes the blocked-dimension problem recorded at `plan/current-status.md:105` and makes
the owner's real rule — "spans exactly 1800 for series X" — expressible for the first time.

## Explanation

Per span, generation emits: `select_model` (input: the interval event), `select_variant`
(governed by the variant's condition), `fit_pattern` (payload: count, gap, residual, rejected
alternative), and `select_product` per slot (governed by the option choice or the
`DefaultComponent` rule). Fulfillment emits `select_supply` per eligibility group, with the
chosen member, the rejected members and the reason ("POLE-3000 — 2 per pole against 1 from
POLE-2000").

**One `fit_pattern` node per span, never one per member**, or a 100 m fence buries its own
explanation.

`decisions/explain.py` TEMPLATES gain en/he entries for each new node kind, key-identical as
the bundle test enforces.

## Warnings

New codes, each needing `warning.<code>` in **both** locale bundles
(`tests/web/test_locale_bundles.py` enforces this):

| Code | When |
|---|---|
| `height_not_supported` | height outside a `Discrete` model's ladder |
| `no_eligible_item` | no member of an eligibility group can supply the requirement |
| `substitute_needs_approval` | only a `suggest_only` member fits |
| `clear_gap_exceeded` | resolved gap exceeds `max_clear_gap_mm` for the context |
| `rail_separation_insufficient` | anti-ladder rule violated |
| `pattern_residual_large` | residual beyond the model's tolerance under `truncate` |

## Landing it without breaking anything

A built-in `M-LEGACY@v1`: two evenly-spaced rails, no infill, eight screws per panel. A run
with no `fence_model` event resolves to it. `derive_requirements` prefers `span.panel` when
present and falls back to `rail_count`/`screws_count` otherwise; the legacy fields are
removed only once nothing reads them.

**The acceptance test for the engine is that S01–S14 produce byte-identical output with the
composition path switched on.** If the mechanism cannot reproduce today's two integers
exactly, it is not right yet. Only then does a demo `M-SLAT` model arrive, with new scenarios
written through the `golden-scenarios` skill.

## Phasing

| Phase | Content | Behaviour change |
|---|---|---|
| 1 | `fencemodel` module, `PanelSpec`, `fit_pattern`, `resolve_panel`, `M-LEGACY`, snapshots and hashes, eligibility groups **with one member** | none — byte-identical |
| 2 | `M-SLAT`, variants, option axes, pricing union, elevation read model, warnings, multi-member eligibility selected by running the existing FFD planner per candidate and comparing under the preset | new capability; certificate stays honest because each candidate is certified as today |
| 3 | Arc-flow over multiple stock lengths and sources with remnants, via OR-Tools | exact selection with an optimality certificate |

Phase 3 is the escalation ADR-0007 already anticipated and named ("coupled objectives"), so
it is a planned door rather than a new dependency argument. The relevant prior art is
Gilmore–Gomory's original 1961 paper (which already covers multiple stock lengths), the
arc-flow formulation (Valério de Carvalho 1999; Brandão & Pedroso 2016, with open-source
VPSolver and the BPPLIB benchmark library), and the cutting-stock-with-usable-leftovers
literature (Belov & Scheithauer 2002; Bertolini et al. 2023), which is our variant exactly.

## Testing

- `fit_pattern` in isolation: the justification × excess matrix, negative gaps, residual
  distribution, edge margins, zero and one-member degenerate cases.
- `resolve_panel` determinism: same inputs, same output, no clock, no RNG, no dict order.
- **Peg completeness**: Σ(slot parts) ≡ BOM in *both* directions per `(sku, unit)` — the
  property finding A3 established, now over a panel with dozens of members.
- Raked bays: constant length rail-to-rail, varying length to a datum; both pinned.
- Clear vs centre-to-centre cut lengths, pinned per `length_rule`.
- Eligibility: selection under both presets, `suggest_only` gating, the 2 m/3 m kerf case
  above as a fixture with its exact expected counts.
- Reproducibility: editing a model or adding a catalog product does not change a stored run
  or an accepted quote.
- Locale bundle parity for every new code; `explain.py` en/he key identity.
- Elevation read model geometry, and a browser check that clicking a drawn slat selects its
  part row.

## Out of scope, stated plainly

- **2D sheet and mesh infill.** Welded mesh and sheet panels must be `ready_made` or a
  made-to-measure assembly; 2D cutting remains the documented non-goal it is today.
- **Waste factor.** The trade's 10–15 % on pickets is a purchasing concern, not engineering
  demand. It belongs in fulfillment and surfaces through the existing `unassigned` bucket,
  or the parts-vs-BOM ledger stops balancing.
- **Israeli standards.** Deferred at the user's instruction; the seeded safety rules are
  demo data with foreign numbers, and are marked as such.
- **Model authoring UI.** Phase 1 and 2 load models as data (`demo.py` and the API). Orgadata
  sells building the equivalent database as a service, which is a fair signal that authoring
  deserves its own design round.

## Sequencing

1. **Ground clearance** (separate spec, prerequisite — defines the panel's bottom datum).
2. **This spec, phases 1–2.**
3. **Gates**: handing and swing arc, then sliding and cantilever expressed as panel
   compositions on the mechanism defined here.
4. **This spec, phase 3**, when a real catalog has eligibility groups worth optimising over.
