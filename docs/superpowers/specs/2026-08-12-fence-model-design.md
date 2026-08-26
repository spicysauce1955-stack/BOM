# Fence models: what a section is made of, and which items may make it

Status: phase 1 implemented · 2026-08-12 · revised after adversarial review
(`docs/reviews/fence-model-design-review.md` — 7 blockers, 8 major, 9 minor, all dispositioned)

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
researched. The mechanism is jurisdiction-agnostic — knowledge objects scoped by `context`,
carrying params (`max_clear_gap_mm`, `max_ground_gap_mm`, `min_rail_separation_mm`) checked
against the resolved panel. Replacing the numbers is a data change.

**The tier decides the consequence, not the check.** ADR-0005 is explicit that a violated
hard constraint is a generation failure, and that is what `generator.py:956` does for
`max_span`. It would be incoherent for a 1801 mm span to be fatal while a 130 mm child-head
gap is a note. So the panel checks raise `GenerationFailure` when the governing knowledge
object is a `hard_constraint`, and emit a warning when it is a `company_rule`, `preference`
or `heuristic` — the same object, the same check, the consequence read off the tier. The
demo seeds these as `company_rule` (advisory) precisely because the numbers are foreign; a
jurisdiction pack would seed them as `hard_constraint` and they would then stop a job.

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
  variants: [Variant]             # authored order; first satisfied condition wins

Variant     condition: Expr, spec: PanelSpec
PanelSpec   frame: [FrameSlot], infill: InfillSpec | None, fixings: [FixingRule]

FrameSlot   key, orientation, placement, length_rule, requirement
InfillSpec  orientation, pattern: [Member], justification, excess, edge_margin_mm, supply
Member      key, width_mm, thickness_mm, face_offset_mm, gap_after_mm,
            base_ref, top_ref, requirement
FixingRule  key, basis, qty_per_basis, requirement

LayoutPolicy  [PolicyContribution]      # each: param, value, knowledge_type, authority?

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

That context carries two namespaces: `panel` (the bay's own facts) and `site` (the
project's `SiteConditions.facts()`, added 2026-08-26). "In a hurricane zone, five rails"
is the same one `Cmp` node. A `site.` key that is not a real dimension is refused by
`validate_model` — the context would never carry it, so the variant would be dead and the
bay built to the default spec with nobody told, which is the failure the binding closed.

Precedence is **authored order, first satisfied condition wins** — deliberately not
"specificity". Knowledge specificity is well defined as `len(scope)`
(`knowledge/model.py:146-147`); a `Variant` has a bare `Expr` and no scope dict, so
"specificity" would mean counting AST nodes or field refs, two implementers would choose
differently, and a different panel would get built. Ordering is the model author's
responsibility and is visible in the data.

Note that `Variant.condition`, `Axis.available_when` and `Eligibility.predicate` are AST
evaluations happening **outside** the knowledge evaluator, so they produce no firing/defeated
trace events. They are product structure, not defeasible rules, and each emits its own
decision node instead — but the distinction has to be understood, or someone will look for a
`defeated` edge that was never going to exist.

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

Clear width needs two things that do not exist yet. Products need a face width —
`attrs.face_width_mm`, catalog data like `length_mm` and `opening_width_mm` already are — and
a span needs to know its two flanking posts, which today are recovered by station matching
(`report/structure.py:290-296`, `generator.py:1114-1118`). On S05 the flanking posts are
different products (POST-S and POST-M), so clear width is **asymmetric** and no object owns
the pair; `resolve_panel` therefore receives the two resolved flanking posts explicitly
rather than re-deriving them.

There is also a live doc⇄code disagreement here that this field would otherwise decide
silently: `docs/scenarios/golden-scenarios.md:23` says rails are "cut to span clear width"
while `demand/derive.py:63` cuts to `span.width_mm`, which is centre-to-centre. CLAUDE.md
forbids reconciling that quietly. **M-LEGACY declares `centre_to_centre`** so behaviour does
not move, and resolving the scenario text is a separate task run through the
`golden-scenarios` skill. It matters numerically: at clear width an S07 rail drops from 1500
to ~1420 mm, and `2 × 1423 ≤ 3003` means two pieces per bar instead of one — half the rail
BOM.

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

Interpolating a sloping datum is float arithmetic, and ADR-0002 requires a *single documented
rounding point*. That point is `member_length_mm()`: it takes the two datum elevations and
the member's position, and returns the rounded integer length. Nothing upstream of it rounds
and nothing downstream re-rounds — otherwise two implementations differ by a millimetre,
which then changes how many pieces fit a bar.

### Fitting the pattern

`fenceai/fencemodel/fit.py::fit_pattern()` is pure, mirroring `strategy/layout.py`:

```
fit_pattern(axis_len_mm, pattern, justification, excess, edge_margin_mm)
  -> FitResult { count, gaps_mm: [int], edge_margin_start_mm, edge_margin_end_mm,
                 residual_mm, member_lengths_mm, rejected_alternative }
```

`gaps_mm` is a **list**, not one number, and that is forced by ADR-0002. Clear width 2000,
member 100, gap 20 gives 16 members and 17 gaps with 400 mm to distribute — 23.5 mm each,
which integer millimetres cannot express. The real fence has 24 mm six times and 23 mm eleven
times. A single rounded `actual_gap_mm` of 23 would let `clear_gap_exceeded` pass against a
23 mm limit while six openings exceed it — the sphere test defeated by a return type.
Spreading follows the rule `strategy/layout.py:22-23` already uses for spans (remainder one
millimetre at a time from the start), and the gap check runs against `max(gaps_mm)`.

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
PartRequirement  role, length_mm?, length_basis?, qty, option_axis?, sku_by_option?,
                 eligibility
Eligibility      group?: str, members: [EligibleItem], predicate?: Expr
EligibleItem     sku, priority, approval
                 approval = auto | suggest_only
```

A member declares **no** consumption semantics of its own: how a SKU is consumed already
lives on the product (`Consumption`, foundation §5), and a second declaration beside it would
be a lie waiting to happen. Model validation at load asserts that every member's
`Consumption` can satisfy the requirement — a `length_mm` requirement needs
`DivisibleLinear`, or `IndivisibleDiscrete` with an `attrs.length_mm` that covers it.

There is deliberately **no** `conversion: Ratio` on a member. A ratio is exactly the nominal
division the kerf table below disproves; `DivisibleLinear.purchase_length_mm` and `kerf_mm`
already own the true answer.

### The resolved SKU has to flow back

This is the mechanism the whole feature turns on, and it must be stated rather than implied.
The parts ledger keys on `(sku, unit)` — `report/structure.py:180` builds the *asked* side
from `RequirementLine.sku` and `structure.py:191-193` the *purchased* side from
`BomLine.sku`, and `fulfill()` groups demand by `r.sku` before it does anything
(`fulfillment/fulfill.py:71-75`). A SKU-free requirement line would make every `asked` key
`("", unit)`, so a 40-slat panel would report 40 cuts unassigned **and** 40 from stock at
once, print a blank SKU column on the setting-out sheet, and satisfy A3's both-directions
property vacuously while being maximally wrong.

Therefore:

- `RequirementLine` keeps `sku`, but it becomes **resolved, not authored**: demand emits the
  line with `sku=""` plus `eligibility`, and `fulfill()` returns
  `resolved_requirements: list[RequirementLine]` in which every line's `sku` is the chosen
  member. `build_structure` is called with the **resolved** lines (`api/app.py:307-310`
  already passes `requirements` through; it passes the resolved ones instead).
- The ledger keys, `Part.sku`, `_merge_parts` and the per-element index are unchanged,
  because by the time they run every line has a SKU.
- A line whose eligibility could not be resolved carries `sku=""` and is reported through
  `no_eligible_item`; it never reaches the ledger silently.

`Part` also gains `slot_key`, and `_merge_parts` keys on it. Without it a shadowbox panel's
front and back members — same SKU, same length, differing only in `face_offset_mm` — collapse
into one row, and the promise that clicking a drawn slat selects its part line is
unimplementable. Pegs stay at element granularity (`span@…`); `slot_key` supplies the
sub-element identity, so no new peg dimension is needed.

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
a company chasing margin want opposite answers.

**The preset is resolved at generation time**, recorded on `GenerationRun`, included in the
run-id digest, and passed to `fulfill()` explicitly. `objective_preset` exists today at
`generator.py:57` and nothing reads it; `fulfill(requirements, catalog, inventory)` receives
neither policy nor knowledge, and that is deliberate (`demand/derive.py:5-7`: "demand needs
no knowledge access"). Fulfillment must not acquire a knowledge lookup, so the
`DefaultComponent(role)` fallback is resolved during generation and frozen onto the
requirement as an eligibility member — fulfillment only ever chooses among members it was
handed. Without this, flipping a preset changes `/bom` for a stored run with nothing
recording why.

**Fulfillment needs a warnings channel.** `no_eligible_item` and
`substitute_needs_approval` are fulfillment-time facts, and `Bom` has no warnings field
(`fulfillment/fulfill.py:56-61`) while `StrategyWarning` lives on `Strategy`
(`strategy/model.py:70`). `Bom` gains `warnings: list[StrategyWarning]`, so these carry
`code + params` like every other user-visible warning.

**When nothing fits**, report minimal relaxations rather than a bare failure — "no eligible
product: relax the finish, or allow 2500 mm stock, or permit suggest-only substitutes". This
is model-based diagnosis (minimal conflict sets); the configuration literature names
explanation as the standing weakness of commercial configurators, and we already have a
decision graph to hang it on. A list of alternative relaxations does not fit
`StrategyWarning.params` (`dict[str, str | int]`, `strategy/model.py:59`) without
stringification, which would defeat the code+params localisation contract — so the warning
carries `relaxations: list[Relaxation]`, each a `code + params` pair in its own right.

### Approval has to be recordable

`approval = suggest_only` is inert unless a human can approve it and have that persist —
§15 requires user overrides to be explicit first-class state. The override vocabulary today
is closed and post-centric (`strategy/overrides.py:44-47`: pin, suppress, force SKU, force
mounting, force vertical), so an estimator who approves POST-S-HD for a run has nowhere to
put it and sees the same warning after every regeneration. That is exactly how
`SubstitutionRule.policy` became a field nothing applies.

Two new override directives, anchored per ADR-0004 to `(run_id, anchor, kind)` and never to
generated element identity:

```
approve_substitute   anchor: run | interval, requirement_role, sku
force_slot_item      anchor: interval, slot_key, sku          # "use 2 m stock in this bay"
set_slot_count       anchor: interval, slot_key, count        # "nine slats here, not ten"
```

`slot_key` is a new anchor dimension, and slot keys are model-authored data that can change
between model versions. An override whose `slot_key` no longer exists is reported as an
orphan through the existing `orphaned_overrides` mechanism — never silently dropped, never
silently re-bound.

## Two touch points with generation

**The model owns product structure; knowledge owns numbers that can conflict.** Structure —
what a panel is made of, in what pattern, with what fixings — is product data and conflicts
with nothing. Numbers — max span, preferred span width, post embedment, the post SKU for a
height band, allowable gaps — are exactly what manufacturer constraints, company rules and
site overrides already fight over.

So the model gets **no private channel into the generator**. Its `layout_policy` is emitted
as knowledge-shaped contributions scoped to `series=<model_id>`, entering the same evaluator
and resolving by the same tiers.

**Authority is per contribution, not per model.** An earlier draft emitted the whole policy
"at manufacturer authority" and claimed a company rule could outrank it. That is impossible:
`DEFAULT_AUTHORITY` puts `hard_constraint` at 1 and `company_rule` at 3
(`knowledge/model.py:19-27`), so either the contribution is a hard constraint and can never
be beaten, or it is beatable and a manufacturer's maximum span is now losing to a company
preference — a safety regression. Lumping `max_span_mm` (hard), `preferred_span_mm`
(preference) and product defaults (selection) into one object at one authority guarantees one
of those two wrong answers. Each contribution therefore declares its own `knowledge_type`:
a manufacturer maximum span is a `hard_constraint`, a nominal panel width is a `preference`,
a default product is a `fact`.

**Rail count is a number, not structure, and must stay defeasible.** `rails_per_span` is
`SetParam` knowledge today (`knowledge/demo.py:31-35`), resolved with full precedence at
`generator.py:848`, recorded as `resolve_span_quantities` with `governed_by` refs
(`generator.py:1071-1078`), and beatable on scope specificity — pinned by
`tests/strategy/test_scope_binding.py`. If a frame slot authors a fixed integer, a company
rule such as "three rails on commercial jobs" binds to nothing and loses **with no contest
and no `defeated` edge**. So `distributed()` placements name a knowledge param rather than
an integer — `distributed(count_param="rails_per_span", default=2)` — and the model
contributes the default as a `fact`. The structure is the model's; the count remains
knowledge's.

**A model change forces a structural boundary.** Model selection is an interval event, and
the boundary set that forces posts today is `{0, length} | corners | base transitions |
pinned | gate edges | step stations` (`generator.py:620-621`) — no model stations. Span
properties are sampled at the mid-point (`generator.py:929`, `_interval_at`). On a 5000 mm
run with M-SLAT to 2500 and M-LEGACY beyond, equal layout gives 1667/1667/1666 and the middle
bay straddles the boundary, sampling mid = 2500 and silently becoming one model's panel where
the fence visibly changes. Model-change stations therefore join `fixed`, exactly as base
transitions do.

Consequently **`max_span_mm` and its siblings resolve per segment, not per run.** They are
resolved once at `generator.py:490` before any segmentation, so a per-interval model cannot
be honoured at all without moving that resolution inside the segment loop. Where two models
meet at a shared post, the post is generated once and each side's panel resolves under its
own model; if the two disagree about the post's product, that is a `knowledge_conflict`
surfaced the way conflicts already are.

**Height-banded post selection is deferred, and this is why.** Posts are constructed before
spans exist (`generator.py:111-113`, `627-712`; spans at `886-940`), and a post's exposed
height is unknowable until its neighbours exist — which is precisely why
`_check_post_lengths` runs last. `_make_post`'s contract is that every selection is resolved
*before* the decision node is recorded and elements are never mutated afterwards
(`generator.py:332-333`). A `post_role_by_height` contribution cannot be honoured without
breaking that, so it is out of phases 1–2. The trigger for revisiting it: a real model whose
post product genuinely changes with height, which then justifies a second post-construction
pass with its own decision node.

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
formula and this is not. **Geometry is served from the server** as a derived read model;
`profile.js` draws what it is given. One implementation, one set of tests.

Concretely: it is a **field on `StructureReport`**, not a second endpoint. `structure-data.js`
is already the shared, run-keyed cache with an in-flight guard built specifically to fix A7
(`structure-data.js:29-45`), and `profile.js` reads it rather than fetching
(`profile.js:20`). A second endpoint fetched by `profile.js` would reintroduce exactly the
stale-fetch bug A7 closed: switch run A → B mid-flight and A's slats land on B's bays. Riding
on `StructureReport` also inherits the `topology_changed` 409 and the `inventory-saved`
invalidation for free.

Four more frontend contracts this read model must honour, none of them optional:

- **Display units.** Slat gaps and member lengths are a new length surface, so they convert
  through `toDisplayValue`/`toMm` and render via `tu()`, round-tripping losslessly in mm and
  cm. Storage and payloads stay int mm.
- **Colour injection.** An `Axis` enum value's `swatch` flows into an SVG `fill`. That is a
  style context, where `esc()` is not sufficient — `swatch` is validated against a strict
  pattern at model load and rejected there, not escaped at render.
- **RTL.** The elevation joins the standing rule that the plan canvas and profile SVG are
  never mirrored, or Hebrew reverses slat order relative to the plan.
- **Enum words.** `decisions/explain.py` needs `_ENUM_WORDS` entries (`explain.py:31-42`) for
  `justification`, `excess` and the fixing bases — not only `TEMPLATES` — or Hebrew prose
  renders `trim_last` in Latin.

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
LinearPrice(cents_per_m)     # phase 2
AreaPrice(cents_per_m2)      # deferred — see below
BandPrice([(max_mm, cents)]) # deferred — see below
```

Integer discipline holds per ADR-0002: `(cents_per_m * length_mm + 500) // 1000`, one
documented rounding, no float.

**Only `FlatPrice` and `LinearPrice` are in phase 2**, because the other two cannot be
represented by the current BOM line. `BomLine` carries a single `unit_price_cents` with
`total_cents = price × purchase_qty` (`fulfillment/fulfill.py:214-221`), and `fulfill()`
emits **one line per SKU** across all requirements (`fulfill.py:71-75`). Two bays of the same
panel SKU at different heights, priced per m², collapse into one line for which no single
unit price gives the right total. `BandPrice` needs a length the discrete branches never see.
`LinearPrice` works only because divisible-linear purchase units are whole bars.

Area and band pricing therefore have a stated prerequisite: `fulfill()` groups per
`(sku, price_basis, size)` rather than per SKU, and `BomLine` gains a computed-total variant.
The mm²→m² rounding is a second rounding point and must be named when that lands. Until then
a per-m² model is priced by a `FlatPrice` per panel size, and the spec says so rather than
pretending.

This is not "the only change outside the new module": `fulfillment/fulfill.py`,
`fulfillment/quote.py`, `demand/derive.py`, `report/structure.py`, `strategy/generator.py`,
`strategy/model.py`, `store/db.py` and `api/app.py` all move. The new module is where the new
*concepts* live, not the whole diff.

## Selection, snapshots and reproducibility

Model selection is a topology interval event, so a fence may change model partway along a
run just as it changes base or height:

```
FenceModelPayload(kind="fence_model", model_id, version_pin: int | None,
                  options: {axis_key: value})
```

with a project-level default (a typed field replacing the relevant part of
`Project.policy`'s bare dict).

**The run id must change when the model does.** `run.id` is content-addressed over exactly
four inputs — `[topology, knowledge_snapshot, overrides, policy]` (`generator.py:145-151`) —
and `save_run` is `INSERT OR IGNORE` (`store/db.py:180`). Neither the model version, the
chosen option values, nor the catalog is in that digest. Edit M-SLAT's slat gap from 20 to 25
and regenerate: the digest is unchanged, the insert is ignored, the POST response shows the
new strategy and `/api/runs/{id}/bom` serves the **old stored document** — two views of one
run id, disagreeing permanently. So the digest gains the resolved model snapshot, the option
values, the selection preset, and a catalog content hash. `GenerationRun` also carries them
as fields, but a field on the object being hashed is not an input to the hash, and only the
digest prevents the collision.

**Stamping is not checking.** `inventory_hash` is stamped today (`app.py:313-315`) and
compared to nothing; the only guard on the read path is `topology_revision`
(`app.py:298-304`). `/bom`, `/structure` and `/quote` each re-run `derive_requirements` +
`fulfill` against **today's** catalog (`app.py:281-283`, `307-310`, `334-337`). With a
property predicate that is a live wound: add a cheaper matching SKU, reopen the same stored
run's Structure tab, and selection re-resolves to a different product with nobody told. Two
things follow:

- The **resolved eligibility member list per requirement is frozen into the strategy**, which
  is persisted with the run — not merely hashed. Fulfillment then chooses among the members
  the run recorded, so re-reading a stored run cannot discover a product that did not exist
  when it was generated.
- `/structure` and `/bom` compare the stamped catalog hash and refuse with a
  `catalog_changed` 409, the same shape as `topology_changed`, rather than quietly serving a
  different answer.

A correction to an earlier draft of this spec: **accepted quotes were never at risk.**
`Quote` persists `requirements` and `bom` in full (`fulfillment/quote.py:31-32`), so it is
already immutable. The object at risk is the stored *run*, re-read through `/bom` and
`/structure`. `Quote` still gains the model snapshot for provenance, but that is
documentation, not a fix.

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

New codes, each needing `warning.<code>` in **both** locale bundles:

| Code | When |
|---|---|
| `height_not_supported` | height outside a `Discrete` model's ladder |
| `no_eligible_item` | the eligibility group is empty — nothing is a candidate at all |
| `no_feasible_item` | candidates were tried and not one fits (typically: every stock length is shorter than the piece). Distinct from `no_eligible_item` because the two send the reader to different places — the model, or the catalog |
| `substitute_needs_approval` | only a `suggest_only` member fits, and no approval override exists |
| `clear_gap_exceeded` | resolved gap exceeds `max_clear_gap_mm` for the context |
| `rail_separation_insufficient` | anti-ladder rule violated |
| `pattern_residual_large` | residual beyond the model's tolerance under `truncate` |
| `span_not_exact` | `exact_span_mm` cannot tile the segment (see below) |
| `catalog_changed` | stored run re-read against a different catalog (409, like `topology_changed`) |

**The guard that supposedly enforces this does not cover any of them.**
`tests/web/test_locale_bundles.py:60-70` regexes `code="..."` out of exactly two files —
`strategy/generator.py` and `ai/stub.py` — and asserts set equality against a hand-maintained
list. Every code above originates in `fencemodel/` or in fulfillment, so all of them would
ship untranslated with the test green. Extending the scanner's file list is part of the same
slice that adds the first code, not a follow-up.

Two behaviours these codes imply, stated so they are not invented twice:

- **`exact_span_mm`** has no implementation today — `layout_segment` has no exact mode and
  `nominal_layout` always emits a remainder span (`strategy/layout.py:26-34`). Defined
  behaviour: tile the segment with exact spans; if the segment is not a whole multiple, lay
  out `floor(L / exact)` exact spans plus one remainder span and raise `span_not_exact`
  naming the remainder. A panel model that cannot tolerate a remainder is a `hard_constraint`
  contribution and fails generation instead.
- **`height_not_supported` aggregates per section, not per bay.** Heights are computed per
  span (`generator.py:929`), and `top_line: level` on a slope makes every span a different
  height (S06) — a discrete-height model there would emit one warning per bay and drown the
  list. One warning per section, with the offending heights in `params`.

## Landing it without breaking anything

A built-in `M-LEGACY@v1`: two evenly-spaced rails, no infill, eight screws per panel. A run
with no `fence_model` event resolves to it. `derive_requirements` prefers `span.panel` when
present and falls back to `rail_count`/`screws_count` otherwise; the legacy fields are
removed only once nothing reads them.

**The acceptance test is that S01–S14 produce identical requirement lines and an identical
BOM** with the composition path switched on. Not byte-identical output: `Span` gains `panel`,
so the strategy JSON necessarily differs, and the graph gains `select_model`,
`select_variant`, `fit_pattern` and `select_product` nodes per span. Stating the gate loosely
would let an implementer either weaken it quietly or chase an impossible target.

Removing `rail_count`/`screws_count` needs a migration statement, not a "once nothing reads
them". Runs are stored as whole JSON documents and re-read with
`GenerationResult.model_validate_json` (`store/db.py:191`). A run generated when K-RAILS said
3, re-read after field removal, has no `panel` and no `rail_count`, so Pydantic supplies the
default `2` (`strategy/model.py:42`) and the stored run's BOM silently changes. The fields
stay until a migration back-fills `panel` onto stored runs, or they never go.

Only then does a demo `M-SLAT` model arrive, with new scenarios written through the
`golden-scenarios` skill.

**Model edits must be impact-analysable.** `FenceModel` is catalog-side rather than a
knowledge object, so it does not inherit versioning, review and
`/api/knowledge/preview-impact` (`api/app.py:509`) for free. Editing M-SLAT's slat gap is a
portfolio-wide change, and foundation §11 requires impact to be exposed before it. So
`learning/impact.py` gains model-version cases in the same slice that makes models editable —
otherwise the feature ships a change nobody can preview.

## Phasing

| Phase | Content | Behaviour change |
|---|---|---|
| 1 | `fencemodel` module, `PanelSpec`, `fit_pattern`, `resolve_panel`, `M-LEGACY`, run-id digest and snapshots, the SKU write-back, **and one two-member eligibility group carried end to end** | S01–S14 requirements and BOM unchanged |
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
- Locale bundle parity for every new code, **with the scanner's file list extended** — a test
  that proves the guard now sees `fencemodel/` and fulfillment codes, verified by adding a
  code and watching it fail.
- `explain.py` en/he key identity, including `_ENUM_WORDS` for the new enum vocabularies.
- Run identity: editing a model version, an option value or the catalog changes `run.id`,
  so `INSERT OR IGNORE` cannot serve a stale document under a reused id.
- `catalog_changed` 409: a stored run re-read after a catalog edit refuses rather than
  re-resolving, mirroring the `topology_changed` test.
- `fit_pattern` gap spreading: `gaps_mm` sums with the members to the axis length exactly,
  and `clear_gap_exceeded` fires on `max(gaps_mm)` — pinned with the 2000/100/20 case where a
  single rounded gap would hide six violations.
- The preset is recorded on the run and changing it cannot alter a stored run's `/bom`.
- Approval overrides survive regeneration; an override whose `slot_key` no longer exists is
  reported as orphaned, not dropped.
- Elevation read model geometry, and a browser check that clicking a drawn slat selects its
  part row.

## Extension seam: the workshop

Not built here. Recorded because the shape of eligibility decides whether it can be added
later without rework, and it can be — if phases 1–2 respect four constraints.

The missing concept is what the **shop can do**: the operations available (cut, drill,
splice, weld, bend, coat), the rules governing them ("we never splice a rail under 2 m",
maximum handled length, minimum usable offcut), their costs (setup plus per-unit) and their
consequences. Manufacturing calls this a routing or a bill of operations; the configuration
literature calls it a generic Bill of Functions, Materials and Operations. Today the system's
only piece of process knowledge is `DivisibleLinear.kerf_mm`, which sits on the product when
a kerf is a property of the saw.

Once it exists, **"fabricate it" becomes a third answer alongside "buy it ready-made" and
"cut it from stock"** — which is precisely an eligibility member. That is the whole reason
this seam is cheap, and the four constraints that keep it cheap:

1. **`Eligibility.members` is a discriminated union, not a list of SKUs.** Phase 1 ships one
   variant, `CatalogItem`. A later `FabricatedRoute` variant carries an operation list rather
   than a single SKU. No code outside the resolver may read `member.sku` directly — it asks
   the resolver what a member yields.
2. **A `PartRequirement` stays functional** — role, length, quantity — and never names a
   product. Already true, and it is what lets an operation satisfy the same requirement a
   purchase would.
3. **Selection stays a named lexicographic preset** (ADR-0007), so labour and machine time
   enter as an additional tier or an additional term in the cost tier, not as a rewrite of
   the objective.
4. **Selection decision nodes record the route chosen and the routes rejected**, not "the SKU
   chosen". A new route type then appears in the existing explanation without a new node
   kind, and the structure sheet can say "fabricated: 2 cuts + 1 splice" in the same place it
   says "POLE-3000 ⟲inv_rem1".

The related advisory — telling a user that a 3 mm change in span width would halve their rail
bill — is recorded in `docs/v1-known-limitations.md` with its trigger. It belongs to the same
future: both are cases of the system reasoning about *how* something gets made rather than
only what it is made of.

## Out of scope, stated plainly

- **2D sheet and mesh infill.** Welded mesh and sheet panels must be `ready_made` or a
  made-to-measure assembly; 2D cutting remains the documented non-goal it is today.
- **Waste factor.** The trade's 10–15 % on pickets is a purchasing concern, not engineering
  demand, and it is deferred entirely. It does **not** simply "surface through `unassigned`":
  for a divisible-linear product a BOM line's `engineering_qty` is the count of cuts, not of
  bars (`fulfillment/fulfill.py:130-132`), and the ledger compares engineering quantities
  (`report/structure.py:191-198`) — so a waste factor that buys extra *bars* is invisible on
  both sides and the ledger balances regardless, while one that adds extra *pieces* shows up
  as unassigned. Which of the two it is has to be decided when it is designed; guessing here
  would produce two incompatible implementations.
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
