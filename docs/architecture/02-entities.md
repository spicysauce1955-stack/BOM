# 02 — Entities

UML class diagrams per domain, drawn from the Pydantic models. Each section names
the file it was drawn from — check it in one command before trusting a diagram.

Conventions: `Mm` is integer millimetres, `Cents` integer cents (ADR-0002). A
discriminated union is drawn as inheritance from an abstract base; the discriminator
is always a `kind` literal.

---

## Topology — authored reality

`src/fenceai/topology/model.py`

```mermaid
classDiagram
    class Topology {
        +int revision
        +list~Node~ nodes
        +list~Run~ runs
    }
    class Node {
        +str id
        +Mm x_mm
        +Mm y_mm
        +Mm z_mm
        +str kind
    }
    class Run {
        +str id
        +str start_node_id
        +str end_node_id
        +list~tuple~ interior_vertices
        +list~PointEvent~ point_events
        +list~IntervalEvent~ interval_events
    }
    class Anchor {
        +int segment_index
        +Mm offset_mm
        +Mm seg_len_at_authoring_mm
    }
    class PointEvent {
        +str id
        +Anchor anchor
        +PointPayload payload
    }
    class IntervalEvent {
        +str id
        +Anchor start_anchor
        +Anchor end_anchor
        +IntervalPayload payload
    }
    class PointPayload {
        <<abstract>>
        +str kind
    }
    class IntervalPayload {
        <<abstract>>
        +str kind
    }
    class BaseTopPoint {
        +int pos_permille
        +Mm z_mm
        +str lock
    }

    Topology *-- Node
    Topology *-- Run
    Run *-- PointEvent
    Run *-- IntervalEvent
    PointEvent *-- Anchor
    IntervalEvent *-- Anchor
    PointEvent --> PointPayload
    IntervalEvent --> IntervalPayload
    IntervalPayload ..> BaseTopPoint : base_top carries
```

**Point payloads:** `gate`, `obstacle`, `existing_foundation`, `elevation_sample`,
`corner_override`. **Interval payloads:** `base`, `height_intent`, `top_line`,
`wall_profile`, `base_top`, `post_tilt`, `fence_model`.

**Why anchors and not stations.** A station is derived. An event stores
`(segment_index, offset_mm, seg_len_at_authoring_mm)` so it **re-anchors
proportionally** within its originating segment when the geometry is edited — drag a
vertex and the gate stays where the user meant it (ADR-0003). Frontend and backend
implement the same two functions: `anchorFor` / `make_anchor` and
`stationOfAnchor` / `anchor_station`. Reading `anchor.offset_mm` as a station is a
bug in both languages.

**Duplicate ids are refused at the model boundary**, so a bad PUT is a 422 rather
than geometry that silently merges two objects downstream.

**Stationing is derived, never stored.** A run's stations are the cumulative plan
(chord) length over `[start_node, *interior_vertices, end_node]`. A vertex is a
structural **corner** when its turn angle exceeds `CORNER_ANGLE_DEG = 15.0`
(`topology/station.py:16`), which a `corner_override` point event can flip either way.
Segments are straight only — ADR-0003 reserves `segment_kind` for arcs.

**Ground is interpolated, the fence top-line is derived.** `ground(s)` is
piecewise-linear over the run's `elevation_sample` events and defaults to `z = 0`
where there are none. The top of the fence is never stored (ADR-0003) — it falls out
of the height intents, the top-line mode and the ground.

**`base_top` is the general top profile of a BUILT base** (a wall, a concrete plinth);
`wall_profile` is the two-point linear special case that predates it. Two consecutive
points at the same `pos_permille` are a vertical **step**, and the right-hand side wins
at the boundary.

`lock` is an **authoring** constraint on the segment that *starts* at its point:
`level` holds that segment at one absolute elevation, with `z_mm` compensating for the
ground underneath, and `step` holds it vertical. The editor re-imposes locks after
every edit, so *"make this stretch horizontal"* survives later dragging until the user
frees it. The generator and `base_top_at()` read the resulting **geometry** and never
the lock itself — the lock is how the shape was authored, not a fact about the built
base.

---

## Catalog — products as consumption behaviour

`src/fenceai/catalog/model.py`

```mermaid
classDiagram
    class Catalog {
        +dict~str_Product~ products
        +list~SubstitutionRule~ substitutions
    }
    class Product {
        +str sku
        +str name
        +dict name_i18n
        +Consumption consumption
        +Cents price_cents
        +Pricing pricing
        +Capabilities capabilities
        +dict attrs
        +display_name(lang)
    }
    class Capabilities {
        +Mm length_mm
        +Mm face_width_mm
        +Mm opening_width_mm
    }
    class Consumption {
        <<abstract>>
    }
    class IndivisibleDiscrete
    class DivisibleLinear {
        +Mm purchase_length_mm
        +Mm kerf_mm
        +Mm min_reusable_remnant_mm
    }
    class PackagedDiscrete {
        +str engineering_unit
        +int qty_per_package
    }
    class CoverageBased {
        +Ratio qty_per_application
        +str application
    }
    class AssemblyKit {
        +list~KitComponent~ components
    }
    class Pricing {
        <<abstract>>
    }
    class FlatPrice
    class LinearPrice {
        +Cents cents_per_m
    }

    Catalog *-- Product
    Product *-- Capabilities
    Product --> Consumption
    Product --> Pricing
    Consumption <|-- IndivisibleDiscrete
    Consumption <|-- DivisibleLinear
    Consumption <|-- PackagedDiscrete
    Consumption <|-- CoverageBased
    Consumption <|-- AssemblyKit
    Pricing <|-- FlatPrice
    Pricing <|-- LinearPrice
```

**A product is not a row, it is a behaviour.** The five consumption kinds are what
make the same pipeline buy a post, cut a bar, round up a box of screws, pour a
footing and explode a gate kit. `purchase_price_cents()` is the single read and the
one rounding point; a rate-priced product may not also carry a flat price, because
two fields that can each claim to be the price is a lie waiting to happen.

**Two places to put a product fact, and the split is the point.**
`Capabilities` is what **deterministic code** may read: `length_mm` (what
`_check_post_lengths` measures against), `face_width_mm` (the post's extent as seen,
which the clear opening is measured to) and `opening_width_mm` (the gate opening a
kit fits). Typed, optional, versioned. `attrs` is the open bag for everything read by
a *predicate* or a *person* — `material`, `finish`, `colour`, a routed post's hole
heights as a list.

The rule, in `catalog/model.py:104`: **a magic string key in Python is the defect.**
`attrs.get("length_mm")` compiles whether or not anything ever sets it, a typo is a
silent `None`, and by the time it matters the number is on a cut list. Data read by
code gets a field; data read by data stays in the bag, because an eligibility
predicate names the keys it reads and a company stocking a new kind of thing should
add a product and a rule, not a release.

`None` on a capability means **not declared**, and each reader answers that in its own
honest way — the elevation draws a flagged nominal, `clear_opening_mm` narrows by
nothing, the length check measures against no stock. A gate event with no `kit_sku`
takes the kit whose `opening_width_mm` equals the opening; if no product declares a
fit the strategy says `no_gate_kit` rather than inventing a SKU. **A SKU is an opaque
id — never parse a dimension out of it**, or the system only works for one catalog's
naming convention.

`Capabilities` is deliberately a flat record and not a union of capability kinds:
three facts is not a taxonomy.

---

## Fence model — panel structure

`src/fenceai/fencemodel/model.py`, `selection.py`, `resolve.py`

```mermaid
classDiagram
    class FenceModel {
        +str id
        +int version
        +str grade
        +str status
        +HeightSupport height_support
        +list~PolicyContribution~ layout_policy
        +list~Axis~ option_axes
        +PanelSpec default_spec
        +list~Variant~ variants
        +ref() str
    }
    class PanelSpec {
        +list~FrameSlot~ frame
        +InfillSpec infill
        +list~FixingRule~ fixings
    }
    class FrameSlot {
        +str key
        +str orientation
        +Placement placement
        +Mm thickness_mm
        +str joint
        +Mm channel_depth_mm
        +Mm insertion_margin_mm
        +PartRequirement requirement
    }
    class InfillSpec {
        +str orientation
        +list~Member~ pattern
        +str justification
        +str excess
        +Mm edge_margin_mm
    }
    class Member {
        +str key
        +Mm width_mm
        +Mm gap_after_mm
        +str base_ref
        +str top_ref
        +Mm base_engagement_mm
        +Mm top_engagement_mm
        +PartRequirement requirement
    }
    class FixingRule {
        +str key
        +str basis
        +int qty_per_basis
        +str qty_param
        +PartRequirement requirement
    }
    class PartRequirement {
        +str role
        +int qty
        +str length_rule
        +str option_axis
        +dict sku_by_option
        +Eligibility eligibility
    }
    class Eligibility {
        +str group
        +list~EligibleItem~ members
        +Expr predicate
    }
    class EligibleItem {
        +str sku
        +int priority
        +str approval
    }
    class Variant {
        +Expr condition
        +PanelSpec spec
    }
    class FenceModelChoice {
        +str model_id
        +int version_pin
        +dict options
    }
    class ResolvedPanel {
        +str model_ref
        +int variant_index
        +list~ResolvedSlot~ slots
    }

    FenceModel *-- PanelSpec
    FenceModel *-- Variant
    Variant *-- PanelSpec
    PanelSpec *-- FrameSlot
    PanelSpec *-- InfillSpec
    PanelSpec *-- FixingRule
    InfillSpec *-- Member
    FrameSlot *-- PartRequirement
    Member *-- PartRequirement
    FixingRule *-- PartRequirement
    PartRequirement *-- Eligibility
    Eligibility *-- EligibleItem
    FenceModelChoice ..> FenceModel : resolves to
    FenceModel ..> ResolvedPanel : resolve_panel(spec, ctx)
```

**A choice is not a model.** `FenceModelChoice` is a reference plus option answers,
and lives in its own import-free module because `topology` and `project` both need to
say *"this stretch is built to that"* without depending on the resolver, the catalog
or the knowledge AST. `version_pin=None` follows the newest active version; an
integer freezes it **even after that version is retired**, because a stored run must
stay reproducible.

**`_UNSUPPORTED` is a first-class mechanism, not a TODO list.** A schema field the
resolver does not honour is refused at load, by name, with the reason. Deleting an
entry is how a wave turns a feature on — and the resolver change and the entry's
removal are the same commit.

---

## Knowledge — rules as data

`src/fenceai/knowledge/model.py`, `ast.py`

```mermaid
classDiagram
    class KnowledgeVersion {
        +str object_id
        +int version
        +KnowledgeType type
        +int authority
        +dict scope
        +Expr condition
        +list~Action~ actions
        +str source_text
        +list~str~ derived_from
        +str status
        +list~RuleExample~ examples
        +ref() str
        +effective_authority() int
        +specificity() int
    }
    class Expr {
        <<abstract>>
        +str op
    }
    class Action {
        <<abstract>>
        +str kind
    }
    class SetParam {
        +str param
        +int value
    }
    class RequireMounting {
        +str surface
        +str mounting
        +str sku
    }
    class DefaultComponent {
        +str role
        +str sku
    }
    class PreferSpanWidth {
        +Mm width_mm
        +int weight
    }
    class RuleExample {
        +dict ctx
        +bool expect_applicable
    }

    KnowledgeVersion --> Expr : condition
    KnowledgeVersion *-- Action
    KnowledgeVersion *-- RuleExample
    Action <|-- SetParam
    Action <|-- RequireMounting
    Action <|-- DefaultComponent
    Action <|-- PreferSpanWidth
```

**AST ops** (closed set): `field`, `lit`, `cmp`, `and`, `or`, `not`, `in`, `between`,
`fn`. **Actions** (closed set): `set_param`, `require_mounting`,
`require_post_reinforcement`, `prefer_equal_spans`, `prefer_min_span_width`,
`prefer_span_width`, `prefer_vertical`, `default_component`, `add_note`,
`flag_for_review`. A field the context does not supply raises `MissingField`, which
means *not applicable* — never *false*.

**Seven types, four distinct handlings.** `fact`, `hard_constraint`, `company_rule`,
`preference`, `heuristic`, `override`, `candidate`. A hard constraint is not a
preference is not an objective is not an override — they have different types and
different code paths. A hard tie is a **generation failure**, not a coin flip.

**Versions are immutable and runs stamp their snapshot set**, so editing a rule
cannot change what an old run meant. `source_text` holds the human's verbatim words
next to the structured form.

**`specificity()` is `len(scope)`** — precedence is authority → specificity →
recency. Which dimensions are bound during generation is documented in
`knowledge-system.md`; `bind_scope()` derives them generically from generation facts
rather than by hand at each call site.

---

## Strategy and decisions — the proposal and its explanation

`src/fenceai/strategy/model.py`, `decisions/graph.py`

```mermaid
classDiagram
    class Strategy {
        +list~Post~ posts
        +list~Span~ spans
        +list~Gate~ gates
        +list~StrategyWarning~ warnings
    }
    class Post {
        +str id
        +str run_ref
        +Mm station_mm
        +str kind
        +str mounting
        +str sku
        +Mm ground_z_mm
        +Mm base_z_mm
        +Mm embed_mm
        +Mm exposed_mm
        +Mm top_z_mm
        +int tilt_deg
        +bool reinforced
        +bool pinned
        +str cap_sku
    }
    class Span {
        +str id
        +Mm start_station_mm
        +Mm end_station_mm
        +Mm width_mm
        +Mm slope_len_mm
        +str vertical
        +Mm height_mm
        +int rail_count
        +str rail_cut_basis
        +ResolvedPanel panel
    }
    class Gate {
        +str id
        +Mm start_station_mm
        +Mm end_station_mm
        +str kit_sku
    }
    class StrategyWarning {
        +str code
        +str severity
        +str message
        +dict params
        +list~str~ element_refs
        +str decision_ref
    }
    class GenerationRun {
        +str id
        +int topology_revision
        +list snapshot
        +str snapshot_hash
        +dict demand_skus
        +str objective_preset
        +list~ModelUse~ model_snapshot
        +str catalog_hash
        +list~str~ catalog_skus
    }
    class DecisionGraph {
        +list~DecisionNode~ nodes
        +list~DecisionEdge~ edges
    }
    class DecisionNode {
        +str id
        +int ordinal
        +NodeKind kind
        +str action
        +dict payload
        +list~str~ scope_refs
        +str confidence
        +str status
    }
    class DecisionEdge {
        +str from_id
        +str to_id
        +EdgeType type
        +str knowledge_ref
    }

    Strategy *-- Post
    Strategy *-- Span
    Strategy *-- Gate
    Strategy *-- StrategyWarning
    DecisionGraph *-- DecisionNode
    DecisionGraph *-- DecisionEdge
    DecisionNode ..> Post : scope_refs
    DecisionNode ..> Span : scope_refs
    GenerationRun ..> Strategy : identity of inputs
```

**`GenerationRun.id` is a content hash over the identity of the inputs** — topology
revision, knowledge snapshot, overrides, policy, model snapshot, catalog hash and
objective preset. Anything that changes what the run *means* has to be in that list,
because the runs table is append-only (`INSERT OR IGNORE`, `store/db.py:376`) and a
reused id would serve a stale stored document. `catalog_hash` is also **checked**, not
merely stamped, on every later read.

Node kinds: `input_fact`, `rule_firing`, `structural`, `selection`, `vertical`,
`mounting`, `quantity`, `conflict`, `assumption`, `override_applied`, `failure`.
Edge types: `derived_from`, `governed_by`, `defeated`, `input_from`,
`assumption_of`.

**The graph is append-only and acyclic by construction** — an edge may only point at
an earlier ordinal. A `defeated` edge cites the **losing** version, which is what
lets the UI say *"this rule would have applied, and this one beat it."*

**Post kinds:** `end`, `corner`, `line`, `gate`, `junction`, `transition`.

**Post fields carry the check that wrote them.** `embed_mm`, `exposed_mm` and
`top_z_mm` are written by `_check_post_lengths` from the same values it measured the
product against, so a run that warns *"this post is 200 mm short"* cannot also be
drawn with a post that looks fine. `None` means "never measured" — a different claim
from `0`.

`embed_mm` is the exception that proves the rule: it is recorded for every post
**before** the check's adjacency skip, so a post with no bay to measure against (the
node post of a run whose first bay is a gate) is still buried. `0` there is a *fact* —
masonry, bolted to what it stands on, embedding nothing — not a blank.

**A fence on a built base stands ON it.** Where a wall or concrete base carries the
fence, the panels rest on the base top and so does the post: `base_z_mm` is the
elevation the post **stands on**, while `ground_z_mm` stays the true ground, which is
what embedment is measured into. `base_z_mm = None` means "same as the ground" — soil,
and every strategy generated before the field existed. So the post-length check
measures the exposed length from `base_z_mm` rather than down through the wall, and
only a `ground`-mounted post spends length on embedment
(`tests/strategy/test_built_base_posts.py`).

**Posts are plumb by default** — vertical to earth, which is construction reality. A
section may opt into tilt with a `post_tilt` interval event: `perpendicular` (derived
from the local ground gradient, clamped ±45°) or `custom` degrees. Gate posts and node
posts always stay plumb: gates must hang plumb to swing, corners are braced plumb.
Tilt lengthens the post axis (exposed / cos θ in the length check), and tilt combined
with stepped panels is surfaced as a design-intent warning (`tilted_stepped`). Sloped
ground is absorbed by the **panels** — raked or stepped — never by tilting structure.
The consequences are all rule-driven rather than hard-coded: K-POST-EMBED with the
product's declared `length_mm`, K-MAX-GAP for stepped-panel gaps, K-GATE-SLOPE for
gate openings needing near-level ground, K-STEP-POST and K-MAX-STEP for vertical
ground steps (`tests/scenarios/test_vertical_ground.py`).

**Warnings carry structure, not a sentence.** `message` is an English *fallback*; the
contract is `code` + `params`, which each client renders in the reader's language. A
new code needs entries in **both** locale bundles or `tests/web/test_locale_bundles.py`
fails.

---

## Demand and fulfillment — from structure to purchase

`src/fenceai/demand/derive.py`, `fulfillment/*.py`

```mermaid
classDiagram
    class RequirementLine {
        +str id
        +str sku
        +int engineering_qty
        +str unit
        %% sku and unit are EMPTY until resolve_supply
        +Mm cut_length_mm
        +str length_basis
        +list~str~ pegs
        +str role
        +str slot_key
        +Eligibility eligibility
    }
    class Bom {
        +list~BomLine~ lines
        +dict~str_CutPlan~ cut_plans
        +list~Allocation~ allocations
        +list~InventoryItem~ projected_remnants
        +Cents total_cents
        +list~StrategyWarning~ warnings
    }
    class BomLine {
        +str sku
        +int purchase_qty
        +str purchase_unit
        +int engineering_qty
        +str engineering_unit
        +Cents unit_price_cents
        +Cents total_cents
        +int overage_qty
        +list~str~ pegs
    }
    class CutPlan {
        +str sku
        +list~PlannedBar~ bars
        +int new_bar_count
        +int lp_lower_bound
        +int lower_bound
        +bool certified_optimal
        +Mm waste_mm
    }
    class PlannedBar {
        +str source
        +Mm stock_length_mm
        +list~CutPiece~ pieces
        +Mm kerf_total_mm
        +Mm leftover_mm
        +bool leftover_reusable
    }
    class CutPiece {
        +Mm length_mm
        +str requirement_id
    }
    class InventoryItem {
        +str id
        +str sku
        +str kind
        +int qty
        +Mm length_mm
    }
    class Allocation {
        +str inventory_item_id
        +int qty
        +Mm length_used_mm
        +list~str~ pegs
    }

    Bom *-- BomLine
    Bom *-- CutPlan
    Bom *-- Allocation
    CutPlan *-- PlannedBar
    PlannedBar *-- CutPiece
    Allocation ..> InventoryItem
    RequirementLine ..> BomLine : pegs
    CutPiece ..> RequirementLine : requirement_id
```

**`RequirementLine` carries two lifecycle states in one type.** `derive_requirements`
emits it with `sku=""` and `unit=""` — deliberately, because only the chosen product
knows the unit and the product is not chosen yet. `resolve_supply` writes both in one
statement. The diagram shows the fields because they exist on the class; it cannot
show that they are meaningless for the first half of the line's life.

That is a genuine modelling weakness, not just a drawing limitation: nothing in the
type system stops an unresolved line reaching `fulfill()`, which is why `fulfill()`
has to *refuse* a blank sku at runtime. Splitting it into `DemandLine` /
`ResolvedSupplyLine` / `UnresolvedSupplyLine` would make the illegal states
unrepresentable. Recorded, not yet done.

**`pegs` is the traceability invariant.** Every BOM line points back to the
requirement lines that caused it, which point back to the strategy elements that
caused them, which point into the decision graph. A BOM item that cannot be traced
to structural demand is a defect, not a rounding.

**The cut plan certifies itself honestly.** `lower_bound = max(lp_lower_bound,
counting_bound)`, and `certified_optimal` is only true when the plan attains it — a
provably optimal plan is not called "heuristic", and no solver vocabulary reaches a
BOM line.

**Units and offcuts never merge.** A remnant allocation takes the **whole** offcut as
a bin, so half of one is never left over; whatever survives comes back as a
*projected remnant*, which is a different item.

---

## Read models — derived, never stored

`src/fenceai/report/structure.py`, `elevation.py`

```mermaid
classDiagram
    class StructureReport {
        +list~Section~ sections
        +list~str~ unassigned
        +list~StrategyWarning~ warnings
        +str inventory_hash
    }
    class Station {
        +str tag
        +str element_id
        +Mm station_mm
        +Mm spacing_mm
        +str kind
        +str sku
        +Mm embed_mm
        +Mm post_length_mm
        +Mm exposed_mm
        +int tilt_deg
        +list~Part~ parts
    }
    class Bay {
        +str tag
        +str element_id
        +str from_tag
        +str to_tag
        +PanelElevation elevation
        +list~Part~ parts
    }
    class Part {
        +str sku
        +int qty
        +str unit
        +str role
        +str slot_key
        +Mm cut_length_mm
        +list~str~ from_bars
    }
    class PanelElevation {
        +str span_id
        +str model_ref
        +Mm width_mm
        +Mm height_mm
        +list~ElevationMember~ members
        +list~JointDetail~ details
        +list~Mm~ gaps_mm
    }
    class ElevationMember {
        +str slot_key
        +str role
        +int index
        +Mm x_mm
        +Mm y_mm
        +Mm w_mm
        +Mm h_mm
        +bool declared
        +str kind
        +str joint
        +Mm seat_start_mm
        +Mm seat_end_mm
    }
    class JointDetail {
        +str member_slot
        +str frame_slot
        +str end
        +Mm channel_depth_mm
        +Mm engagement_mm
        +Mm margin_mm
        +bool declared
    }

    StructureReport *-- Station
    StructureReport *-- Bay
    Station *-- Part
    Bay *-- Part
    Bay *-- PanelElevation
    PanelElevation *-- ElevationMember
    PanelElevation *-- JointDetail
```

**Σ(parts) ≡ BOM is the governing property.** Parts are obtained by **inverting**
existing pegs — element → RequirementLine → BomLine — never by recomputing. Demand
not covered by a purchased line is reported as `unassigned`; demand covered by stock
gets its own `from_stock` bucket, because the identity has to hold in both
directions.

**Tags are derived, never stored** (`A`, `P1`, `B1`, `G1`), and are unique per
element — a shared corner post prints one tag, not two.

**`declared: false` is honesty in the schema.** A member whose face height is a
nominal the read model invented draws dashed and says so, rather than claiming a
precision the catalog does not have.

---

## Project, learning, AI

`src/fenceai/project/model.py`, `learning/model.py`, `ai/records.py`

```mermaid
classDiagram
    class Project {
        +str id
        +str name
        +Topology topology
        +list~Annotation~ annotations
        +list~Override~ overrides
        +dict policy
        +FenceModelChoice fence_model
    }
    class Annotation {
        +str id
        +str target_ref
        +str text
        +str author
        +list~InterpretationRecord~ interpretations
    }
    class InterpretationRecord {
        +str id
        +str interpreter_id
        +list~Candidate~ candidates
    }
    class Override {
        +str id
        +str run_id
        +Directive directive
        +str status
        +str origin
        +str origin_ref
    }
    class Directive {
        <<abstract>>
        +str kind
    }
    class Correction {
        +str id
        +str generation_run_id
        +str decision_ref
        +str element_ref
        +dict before
        +dict after
        +str comment
    }
    class ReviewAction {
        +str action
        +str reviewer
        +dict edited_scope
    }

    Project *-- Annotation
    Project *-- Override
    Override --> Directive
    Project --> FenceModelChoice
    Annotation *-- InterpretationRecord
    Correction ..> Project
    Correction ..> KnowledgeVersion : proposes candidate
    ReviewAction ..> KnowledgeVersion : approves or restricts
```

**The verbatim text is immutable and never replaced by its interpretation.** An
interpretation is a *proposal* carrying candidates; confirming one materialises a
first-class event whose `source` is the interpretation record id, so the chain back
to the human's words survives.

**An override is anchored to `(run_id, station, kind)`** — never to a generated
element id, which does not survive regeneration. The station lives on the
**directive**, which is a closed discriminated union of exactly five
(`strategy/overrides.py`):

| Directive | Says |
|---|---|
| `PinPost{station_mm}` | there is a post here, whatever the layout wanted |
| `SuppressPost{station_mm}` | there is not |
| `ForcePostSku{station_mm, sku}` | this post is that product |
| `ForceMounting{station_mm, mounting}` | ground or masonry |
| `ForceVertical{start_station_mm, end_station_mm, mode}` | level, stepped or raked |

`status` goes `active` → `orphaned` when the geometry moves out from under the anchor,
and `origin` records whether a human wrote it or a correction did.

**A correction never becomes an active rule.** It proposes a `candidate`, which is
inert until a reviewer approves, edits, restricts its scope, or rejects it.
