# Domain model

All lengths int mm (ADR-0002). All entities have stable string IDs (`prefix_ulid`). Pydantic
v2 models are the single schema source (domain = API = LLM validation).

## Topology (user-authored reality; never mutated by generation)

```
Project      { id, name, created_at, topology, annotations[], overrides[], inventory_ref, policy }
Topology     { revision (int, bumped per edit), nodes[], runs[] }
Node         { id, x_mm, y_mm, kind: terminal|junction }        # identity for shared posts
Run          { id, start_node_id, end_node_id, interior_vertices[(x_mm,y_mm)],
               point_events[], interval_events[] }
```

Stationing: derived per run — cumulative plan (chord) length over [start_node, *interior,
end_node]. Corner classification derived from turn angle (> 15° ⇒ corner) with per-vertex
override event. Straight segments only (ADR-0003; `segment_kind` reserved).

Events (station-addressed attributes; ADR-0003):

```
Anchor        { segment_index, offset_mm, seg_len_at_authoring_mm }   # proportional re-anchor rule
PointEvent    { id, kind, anchor, payload }
   kinds: gate{width_mm, kit_sku?}, obstacle{desc}, existing_foundation{},
          elevation_sample{z_mm}, corner_override{is_corner}
IntervalEvent { id, kind, start_anchor, end_anchor, payload }
   kinds: base{surface: soil|concrete|masonry_wall}, height_intent{height_mm, source: user|interpretation_id},
          top_line{mode: follow|level|stepped, z_mm?}, wall_profile{top_z_start_mm, top_z_end_mm},
          base_top{points: [BaseTopPoint]}, post_tilt{mode, tilt_deg}
BaseTopPoint  { pos_permille (0..1000 along the interval), z_mm (ABOVE local ground),
                lock: level|step|null }
```

`base_top` is the general top profile of a BUILT base (wall/concrete); `wall_profile` is
the 2-point linear special case that predates it. Two consecutive points at one position
are a vertical STEP (the right side wins at the boundary). `lock` is an AUTHORING
constraint on the segment that starts at its point — `level` holds that segment at one
absolute elevation (z compensates the ground underneath), `step` holds it vertical. The
editor re-imposes locks after every edit, so "make this horizontal" survives later
dragging until the user frees it; `base_top_at()` and the generator read the resulting
geometry and never the lock itself.

`ground(s)`: piecewise-linear interpolation over elevation_sample events (default z=0).
Fence top-line is derived, never stored (ADR-0003).

```
Annotation   { id, target: ref(project|run|node|event|span-interval), text (VERBATIM, immutable),
               author, created_at, interpretations: [InterpretationRecord] }
```

## Catalog

```
Product { sku, name, price_cents (per purchase unit), consumption, attrs{} }
consumption (discriminated union):
  IndivisibleDiscrete {}
  DivisibleLinear     { purchase_length_mm, kerf_mm, min_reusable_remnant_mm }
  PackagedDiscrete    { engineering_unit, qty_per_package }
  CoverageBased       { engineering_unit, purchase_unit, qty_per_application: Ratio, application: per_post_footing|per_span|... }
  AssemblyKit         { components: [{sku, qty}] }
SubstitutionRule { id, from_sku, to_sku, policy: auto|suggest_only, condition: Expr? }
```

`attrs` carries the physical facts the generator checks a product against. A SKU is an
opaque id — **never** parse dimensions out of it, or the system only works for one
catalog's naming convention. Attributes read today:

| attr | read by | meaning |
|---|---|---|
| `length_mm` | `_check_post_lengths` | physical length of a post product |
| `opening_width_mm` | gate kit selection + `gate_kit_width_mismatch` | the opening a kit fits; a product that declares nothing is never second-guessed |

A gate event with no `kit_sku` selects the kit whose `opening_width_mm` equals the
opening; if no product declares a fit, the strategy says so (`no_gate_kit`) rather than
inventing a SKU.

## Knowledge  (details: knowledge-system.md)

```
KnowledgeObject  { id, current_version }
KnowledgeVersion { object_id, version, type: fact|hard_constraint|company_rule|preference|
                   heuristic|override|candidate, authority (derived; explicit field),
                   scope: {project_id?, series?, base?, context?...}, condition: Expr?,
                   actions: [Action], source_text?, derived_from: [ref], author, created_at,
                   status: draft|active|retired|proposed|rejected, examples[], counterexamples[] }
```

## Strategy (generated proposal; regenerated wholesale — ADR-0004)

```
GenerationRun { id, project_id, topology_revision, knowledge_snapshot: [(object_id, version)],
                snapshot_hash, overrides_applied: [id], policy, demand_skus: {role: sku},
                objective_preset, model_snapshot: [(model_id, version)], catalog_hash,
                created_at }
Strategy      { id, run_id, status: proposed|accepted|superseded,
                posts[], spans[], gates[], warnings[] }
Post  { id, run_ref (topology run id | node id), station_mm?, kind: end|corner|line|gate|junction,
        reinforced: bool, mounting: ground|masonry, sku, ground_z_mm, base_z_mm?, tilt_deg,
        pinned: bool }
Span  { id, run_ref, start_station_mm, end_station_mm, width_mm (plan),
        slope_len_mm, vertical: level|stepped|raked, height_mm,
        bottom_z_start_mm, bottom_z_end_mm, rail_count }
Gate  { id, run_ref, start_station_mm, end_station_mm, kit_sku }
Warning { code, severity, message, element_refs[], decision_ref? }
```

`GenerationRun.id` is content-addressed over topology, knowledge_snapshot, overrides, policy,
model_snapshot, catalog_hash and objective_preset — anything that changes what the run
*means* has to be in that list, or `INSERT OR IGNORE` (append-only runs table) would serve a
stale stored document under a reused id. `catalog_hash` is also checked (not just stamped) on
every later read: `/bom` and `/structure` refuse with 409 `catalog_changed` if today's catalog
no longer matches it.

Element IDs are content-addressed within a run (`post@{run}:{station}`) so regenerated
identical elements keep identical IDs; overrides never reference them anyway (anchors only).

```
Override { id, anchor: {run_id, station_mm | [start,end], kind: post|span|mounting|vertical|product},
           directive: PinPost{station_mm} | ForcePostSku{sku} | ForceMounting{m} |
                      ForceVertical{mode} | SuppressPost{} | SetSpanBoundary{...},
           status: active|orphaned, origin: user|correction{id}, author, created_at }
```

## Decisions  (details: decision-model.md)

Per GenerationRun: append-only `DecisionNode` / `DecisionEdge` document.

## Demand & fulfillment  (details: material-optimization.md)

```
RequirementLine { id, run_id, sku, engineering_qty, unit: each|mm|application,
                  cut_length_mm?, pegs: [element_id] }
InventoryItem   { id, sku, kind: full_stock|remnant{length_mm}|opened_package{remaining},
                  qty }
CutPlan   { bars: [{source: new|inventory_item_id, stock_length_mm,
                    pieces: [{length_mm, requirement_id}], kerf_total_mm,
                    leftover_mm, leftover_reusable: bool}],
            lp_lower_bound, lower_bound, certified_optimal: bool }
BomLine   { sku, purchase_qty, purchase_unit, engineering_qty, engineering_unit,
            unit_price_cents, total_cents, overage_qty, pegs: [requirement_id], notes[] }
Bom       { id, run_id, lines[], cut_plans{sku: CutPlan}, allocations[], totals,
            projected_remnants: [InventoryItem] }   # projection only, never stored
```

## Learning

```
Correction { id, project_id, run_id, decision_ref?, element_ref?, before, after,
             comment?, author, created_at }
```
Knowledge candidates are `KnowledgeVersion` records with `status: proposed`,
`derived_from: [correction ids]` — inactive until review (knowledge-system.md).

## AI interpretation records

```
InterpretationRecord { id, annotation_id, interpreter: stub|claude{model}, created_at,
                       candidates: [CandidateIntent], unparsed_spans[] }
CandidateIntent { id, kind: height_intent|top_line|post_request|material_preference|other,
                  params{}, source_text (verbatim span), confidence: high|medium|low,
                  status: proposed|confirmed|rejected, confirmed_by? }
```
Only `confirmed` intents feed generation (they materialize as events/knowledge with
provenance back to the record + annotation).

## A fence on a built base stands ON it (2026-08-11)

Where a wall or concrete base carries the fence (`BUILT_BASES`), the panels rest on the
base top — span bottoms already included it — and so does the post: `Post.base_z_mm` is
the elevation the post STANDS on, while `ground_z_mm` stays the true ground, which is what
embedment is measured into. `base_z_mm = None` means "same as the ground" (soil, and every
strategy generated before the field existed). Consequences: the post-length check measures
the exposed length from `base_z_mm`, not through the wall, and only a `ground`-mounted post
spends length on embedment — a masonry-mounted post is bolted to what it stands on.
See tests/strategy/test_built_base_posts.py.

`Post.embed_mm` (2026-08-14) records that embedment on the post itself, written by
`_check_post_lengths` from the `post_embed_mm` it already resolves — one number, so the
elevation cannot draw a footing deeper than the length check paid for. It is recorded for
every post BEFORE the check's adjacency skip: a post with no bay to measure against (the
node post of a run whose first bay is a gate) is buried all the same, and 0 there would
draw it standing on the ground. 0 is therefore a fact — masonry — not a blank. The
structure report carries it to the wire as `Station.embed_mm`, alongside
`Station.post_length_mm`, the post product's declared catalog `attrs.length_mm`; that one
is `None` when the product declares none, and a client then draws no embed dimension
rather than a guessed one. `build_structure` takes the catalog as a fifth GIVEN for it —
read, never recomputed, and without one every station simply reports `None`.

## Post orientation: plumb by default, tilt supported (2026-08-11)

Posts are PLUMB by default — vertical to earth (construction reality). A section
may opt into tilted posts via a `post_tilt` interval event: `perpendicular`
(derived from the local ground gradient, clamped ±45°) or `custom` (explicit
degrees). Gate posts and node (corner/end) posts always stay plumb — gates must
hang plumb to swing, corners are braced plumb. Tilt lengthens the post axis
(exposed/cos θ in the length check) and combining tilt with stepped panels is
surfaced as a design-intent warning (tilted_stepped). Sloped/vertical terrain is absorbed by panels (raked or
stepped), never by tilting structure. Modeled consequences, all rule-driven:
downhill post length checks (K-POST-EMBED + catalog `length_mm`), stepped-panel
gaps (K-MAX-GAP), plumb max-height at the downhill end (`max_fence_height_mm`
when a rule exists), gate openings need near-level ground (K-GATE-SLOPE),
vertical ground steps force posts (K-STEP-POST) and buildability ceilings
(K-MAX-STEP). See tests/scenarios/test_vertical_ground.py.

## Key invariant restatements

- Topology never references strategy. Overrides/annotations anchor to topology coordinates.
- `generate()` inputs are all captured in GenerationRun; same inputs ⇒ identical output.
- Every BOM line pegs → requirements → elements → decisions → knowledge versions/topology.
- Verbatim text is immutable wherever it appears.
