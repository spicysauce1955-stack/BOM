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
        +dict attrs
        +display_name(lang)
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

**`attrs` is an open bag on purpose.** What a product is made of is the catalog's
answer, not the code's — a company that stocks bamboo adds a product and a locale
word, not a release.

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
    DecisionGraph *-- DecisionNode
    DecisionGraph *-- DecisionEdge
    DecisionNode ..> Post : scope_refs
    DecisionNode ..> Span : scope_refs
    GenerationRun ..> Strategy : identity of inputs
```

Node kinds: `input_fact`, `rule_firing`, `structural`, `selection`, `vertical`,
`mounting`, `quantity`, `conflict`, `assumption`, `override_applied`, `failure`.
Edge types: `derived_from`, `governed_by`, `defeated`, `input_from`,
`assumption_of`.

**The graph is append-only and acyclic by construction** — an edge may only point at
an earlier ordinal. A `defeated` edge cites the **losing** version, which is what
lets the UI say *"this rule would have applied, and this one beat it."*

**Post fields carry the check that wrote them.** `embed_mm`, `exposed_mm` and
`top_z_mm` are written by `_check_post_lengths` from the same values it measured the
product against, so a run that warns *"this post is 200 mm short"* cannot also be
drawn with a post that looks fine. `None` means "never measured" — a different claim
from `0`.

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
        +str kind
        +Mm station_mm
        +str run_ref
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
element id, which does not survive regeneration.

**A correction never becomes an active rule.** It proposes a `candidate`, which is
inert until a reviewer approves, edits, restricts its scope, or rejects it.
