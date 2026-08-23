# Planning & BOM Engine — design against the Knowledge Platform contract

```text
Status:   Design proposal, for review
Owner:    this repo (src/fenceai/)
Contract: see "The Seam" — system overview and contract v0.1
Siblings: 2026-08-23-frontend-design.md · fence-rag owns the Knowledge Platform
```

## 0. What this changes, and what it does not

The engine keeps its shape. `generate()` stays pure, overrides stay anchored to
`(run_id, station, kind)`, rules stay typed ASTs evaluated by our own evaluator, and
S01–S14 stay green throughout.

What changes is **where knowledge comes from** and **what a requirement is named in**:

| Today | After |
|---|---|
| `knowledge/demo.py` seeds a `KnowledgeBase` in-process | A pinned snapshot is fetched by hash and adapted into a `KnowledgeBase` |
| `catalog/demo.py` seeds a `Catalog` | The snapshot carries product definitions and catalog items |
| Parameters are unconditional constants (`max_span_mm: 1800`) | Parameters are conditional tables evaluated against site conditions |
| Demand is expressed in SKUs and slot kinds | Requirements are expressed in **roles**; SKUs satisfy them at fulfilment |
| A missing input is not a modelled state | A missing input is a warned, unfulfilled requirement |

Non-negotiables from foundation §15 that constrain every decision below: no AI inside
deterministic computation; integer mm and cents at rest; the decision graph is the
explanation; rules are data.

---

## 1. Site conditions — the unblocked first move

Nothing else in this document works until a project can say what kind of site it is.
Today `exposure_category` is not expressible at any layer, so every conditional claim
the platform publishes would arrive with nothing to match against.

### 1.1 Model

```python
# fenceai/project/model.py
class SiteConditions(BaseModel):
    exposure_category: Literal["B", "C", "D"] | None = None
    hvhz: bool | None = None
    frost_depth_mm: Mm | None = None
    soil_class: str | None = None          # open vocabulary; a knowledge dimension
```

Hangs off `Project`, not off `Topology` — it describes the site, not its geometry, and
it must not invalidate a structure sheet when edited. Confirm against
`report/`'s `topology_changed` guard before wiring: a site-condition edit changes
*requirements*, so it must invalidate a **run**, not a layout.

### 1.2 Binding

Site conditions reach rules through the **evaluation context**, not through `scope`.
`scope` is structural narrowing (which rules are candidates); site conditions are
predicates over facts the run has. So:

- `strategy/generator.bind_scope()` is unchanged.
- The evaluator context gains a `site` namespace, and `FieldRef("site.exposure_category")`
  resolves from it.
- `knowledge/ast.py` needs no new node types. This is a context addition only.

### 1.3 When a condition is unknown

A project with no exposure category set must still produce a plan. The behaviour is keyed
on the table's `task`, which the source policy already classifies:

| Task class | Policy when a required dimension is unbound |
|---|---|
| Structural | **Conservative** — take the strictest row across the domain, and warn |
| Commercial | Leave unset, warn, continue |
| Descriptive | Leave unset, no warning |

Conservative selection is what makes "never block" safe rather than reckless: an unknown
exposure category yields the tightest documented spacing, not a guess and not a failure.
The warning names the dimension and the row chosen.

The engine reads `task` off the table; it does not hold its own classification and it does
not re-derive authority. Knowledge has already applied the source policy and stamped
`admitted_by` on the winning row — the engine renders that as the reason, nothing more.

**New warning codes** (both locale bundles, or `tests/web/test_locale_bundles.py` fails):
`warning.site_condition_missing`, `warning.conservative_parameter_used`.

---

## 2. The semantic spine

A new package, small and dependency-light, published from this repo because a spine role
exists precisely when this engine implements a counting rule for it.

```text
fenceai/semantic/
    roles.py           spine role ids, parents, labels
    derivation.py      the counting rule per role
    consumption.py     re-export of the closed consumption set
    refs.py            EntityRef, RoleRef, VersionRef, SourceRef, Quantity
```

### 2.1 The ten roles and their counting rules

A counting rule answers **how many, and how big**, from topology plus parameters.

| Role | How many | How big |
|---|---|---|
| `post` | one per station | fence height + `post_embed_mm` |
| `post_cap` | one per post | — |
| `rail` | `rails_per_span` per span | span width |
| `bar` | `bars_per_span` per span | span width |
| `infill` | derived from span width, element width, gap policy | span clear height |
| `reinforcement` | per post where a rule requires it | post length |
| `bracket` | per rail-to-post connection | — |
| `fastener` | `screws_per_span`, or per connection | — |
| `anchor` | per masonry-mounted post | — |
| `gate_hardware` | per gate leaf | — |
| `site_material` | **reserved** — no rule, no handler | — |

`infill` is the only one with real arithmetic, and it is the one to write first and test
hardest. Both its consumption shapes (bought finished, cut from stock) produce the same
requirement; they diverge only at fulfilment.

### 2.2 Role, product, consumption

The separation that matters, and the one the catalog already models correctly:

> **The role owns "how many and how big." The product owns "how you obtain them."**

`Product.consumption` stays where it is. A requirement is stated in roles and lengths;
fulfilment satisfies it using each candidate product's consumption model
(`IndivisibleDiscrete`, `DivisibleLinear`, `PackagedDiscrete`, `CoverageBased`, `Ratio`,
`AssemblyKit`).

### 2.3 Extension roles

Extension roles arrive in the snapshot as data. Dispatch walks the parent chain to the
nearest spine role and uses that rule. An extension declaring its own derivation is a
load error, not a warning.

---

## 3. The typed client

```text
fenceai/kplatform/
    client.py       fetch_snapshot, get_snapshot, resolve_source_ref, report_gap
    cache.py        content-addressed local store
    adapt.py        Snapshot -> KnowledgeBase | Catalog | AssemblyLibrary
    default/        a bundled snapshot, checked in
```

### 3.1 Offline is the default, not a fallback

A bundled snapshot ships in the repo. Tests, development, and a cold start all use it
without a network. **The scenario suite must never open a socket** — assert this, don't
assume it.

### 3.2 The adapter is where migration safety lives

`adapt.py` maps the wire `Snapshot` onto the domain types the engine already has, so
`generate()` and the evaluator are untouched while the *source* of knowledge changes.
That is what keeps S01–S14 green across the migration.

### 3.3 ParameterTable expands into rules

The neatest consequence of the contract. A `ParameterTable` is a compact wire format for
a family of conditioned rules, and expanding it at load needs **no evaluator change**:

```python
# one row of a ParameterTable becomes one KnowledgeVersion
KnowledgeVersion(
    object_id=f"KP-{table.parameter}-{table.scope.id}",
    version=row_index,
    type="hard_constraint" if table.task.is_structural else "fact",
    scope={"product": table.scope.id},
    condition=And(*[Cmp("eq", FieldRef(f"site.{k}"), Lit(v))
                    for k, v in row.conditions.items()]),
    actions=[SetParam(param=table.parameter, value=row.value.amount_milli // 1000)],
    derived_from=[ref.source_ref_id for ref in row.provenance],
)
```

The hit-policy check already happened on the knowledge side, so the engine's precedence
ladder never sees a tie from a single table. Ties *between* tables (a company rule against
a manufacturer table) resolve exactly as they do today.

### 3.4 Units, once, at the boundary

`adapt.py` is the only place a conversion happens. `Quantity.amount_milli` is thousandths
of the named unit; mm values divide by 1000 into `Mm`. The rounding rule is declared in
`core/units.py` beside the two existing tolerances, and `value_raw` travels with the
converted number so the decision graph quotes `88"` while the arithmetic uses 2235.

Nothing downstream sees a float. Nothing downstream re-converts.

---

## 4. Assemblies: definition versus instance

Knowledge owns `AssemblyDefinition` — slots, accepted roles, quantity rules, dimensional
formulas. Planning owns `AssemblyInstance` — this span, this width, these selected
products, these cuts.

```text
AssemblyDefinition (snapshot)      AssemblyInstance (run state)
  slots[]                            assembly_ref + version
    slot_id                          span_id, width_mm
    accepts_role: RoleRef            filled_slots[]
    quantity: QuantityRule             slot_id -> requirement_id
```

**Slot matching walks the role parent chain.** A slot accepting `role:rail` is satisfied
by a product fulfilling `role:fenceco/routed_rail`, because that role's parent is
`role:rail`. This is where the general/custom promise actually pays off, and it is
checkable rather than asserted.

The planner never redefines what a panel is. It instantiates a versioned definition and
records which version.

---

## 5. Requirements, and never blocking

`demand/` produces requirements stated in roles:

```text
Requirement
    role: RoleRef
    quantity: int | Quantity
    dimensions: {length_mm, ...}
    origin: decision node id
    status: fulfilled | unfulfilled
    unfulfilled_reason: code + params
```

Three ways a requirement goes unfulfilled, all of which produce a plan rather than an
error:

| Cause | Code |
|---|---|
| No product in the catalog fulfils the role | `warning.no_product_for_role` |
| The role has no counting rule (extension with a dead parent, or a reserved role) | `warning.role_not_countable` |
| A parameter table left this condition point uncovered | `warning.uncovered_condition` |

**The invariant**: a missing role, an uncovered condition, or an unsatisfiable requirement
produces a named, warned BOM line — never a failed run. This is what lets the two teams
iterate without blocking each other, and it is a hard requirement on this engine, not a
nicety. Assert it in the scenario suite with a snapshot that is deliberately incomplete.

Gaps discovered here are reported back via `POST /gaps` with the evidence needed to act:
the role, the conditions, the products that would have filled it.

---

## 6. Provenance in the decision graph

The chain that has to render end to end:

```text
BOM line -> decision node -> rule (object_id@vN) -> SourceRef -> crop
```

`decisions/explain.py` TEMPLATES gain a provenance slot. `SourceRef` is **opaque to the
engine** — it is a string the engine stores and hands back to the frontend, which resolves
it through the discovery API. The engine never fetches a crop and never needs to.

The `defeated` edge rule is unchanged: it cites the losing version.

**Also worth adding, and cheap**: minimal-conflict explanation. "Why can't the spans be
wider here?" should return the smallest set of rules responsible, not the whole graph.
This is a well-specified algorithm and the single most-requested thing in every
comparable system.

---

## 7. Build order

| # | Work | Proves | Blocked by |
|---|---|---|---|
| 1 | `SiteConditions` + context binding + conservative policy | One rule scoped on exposure yields two span limits on two sites | nothing |
| 2 | `fenceai/semantic/` spine + counting rules | Requirements state roles; existing scenarios unchanged | nothing |
| 3 | Requirements in roles + never-block warnings | A deliberately incomplete snapshot still produces a plan | 2 |
| 4 | `kplatform/` client + bundled default snapshot + adapter | S01–S14 pass from a snapshot, with no socket opened | 2 |
| 5 | ParameterTable expansion | `max_span_mm` becomes 2235 at Exposure C, from evidence | 1, 4 |
| 6 | Assembly definition/instance split | A shared definition instantiates against a tenant role | 4 |
| 7 | Provenance slot in explain + gap reporting | A BOM line renders its source ref for the frontend to resolve | 4 |
| 8 | Minimal-conflict explanation | "Why not wider?" returns three rules, not thirty | 5 |

Steps 1 and 2 cross no boundary and need no contract agreement. Start there.

---

## 8. Open questions

- **Does a site-condition edit invalidate a run or a layout?** Needs checking against
  `report/`'s `topology_changed` semantics before wiring. Current belief: a run.
- **`infill` counting rule.** Is the slat count derived from a target gap, or declared by
  the fence model, or either depending on the model? This decides whether the rule takes a
  gap policy or a count.
- **Where does `rails_per_span` live** now that it is knowledge — a parameter table scoped
  to the assembly definition, or a property of the definition itself? Leaning: the
  definition, since it is structural rather than conditional.
- **Tenancy in this repo.** The engine is currently single-tenant throughout. The client
  can carry a tenant without the engine modelling one, but persistence and the UI will
  need it eventually. Decide before step 4, not after.
