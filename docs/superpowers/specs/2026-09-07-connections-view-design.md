# Connections — seeing what references what, and what nothing does

**Status:** SPEC. Nothing here is built. The interactive mockup at
`https://claude.ai/code/artifact/a0380b52-2778-4668-b6ab-5e3b0532327a` is a
design preview only — static sample data, no backend behind it.

Supersedes nothing. Independent of the Knowledge-tab reorganization discussed
in the same conversation (sub-navigation, candidate-count fix, sentence-style
action rendering) — that work is scoped to `#tab-knowledge` alone and can ship
on its own schedule; this document is the escalation that came out of the same
conversation once the ask outgrew that tab.

## Why this document exists

A request to declutter the Knowledge tab surfaced a sharper complaint: this
app's data models are genuinely interconnected — rules name products, models
require parts, parts cite documents — and **nothing anywhere lets a person see
those connections, or find the two failure shapes that matter: an orphan**
(nothing points at this) **and a dangling reference** (this points at
something that doesn't exist).

Two real, live, previously-invisible findings justified building this rather
than filing it as a nice-to-have:

1. **A published Part has no link to a catalog Product, anywhere.**
   `knowledge/parts.py:26-29` says so outright: *"nothing in this engine can
   say which catalog product a published Part is."* It is a named, permanent
   gap (`published_spec_unapplied`), not a bug — but today it is invisible
   unless you already know to grep for that comment. 212 published parts are
   affected in the live snapshot.
2. **Nothing checks the reverse direction of a reference, anywhere, for
   anything.** `Snapshot.dangling_refs()` (`knowledge/snapshot.py:213`) checks
   whether a citation resolves to a real document — the forward direction —
   and is real, tested, and currently clean (0 dangling on the live snapshot).
   Nothing checks whether a `SourceDoc` is cited by anything at all, or
   whether a catalog Product is reachable by any rule or any model's
   eligibility. Both are real, buildable gaps that simply don't exist today at
   any layer of this codebase.

## Non-goals

- **Not a global, all-entities-at-once graph.** Researched explicitly: every
  tool that draws one (dbt, Airflow, Terraform, Bazel) relies on an external
  layout engine, and this frontend is contractually not allowed one — "No
  framework, no build step, no CDN" (`CLAUDE.md`). No surveyed precedent even
  argues a global graph is the right tool for an audit task; the tools built
  for exactly this task (Notion, Obsidian, GitHub's dependency graph,
  DataGrip) all use a focused per-record view instead.
- **Not a replacement for any existing tab.** Models, Knowledge, BOM, Inventory
  keep doing what they do; this is a new lens across them, not a rebuild of
  any of them.
- **Not live/streaming.** Computed on request, for one entity at a time (plus
  one batch computation for the orphans list). No caching layer in v1 — see
  "Performance," below, for why that's an acceptable starting point.

## The entity kinds, and what "references" means for each

Mapped directly against the current codebase (all citations current as of
this session; re-verify line numbers before implementing, code moves).

| Kind | Shape | Identity | Outbound references | Inbound (who points at it) |
|---|---|---|---|---|
| **Rule** (`KnowledgeVersion`) | hexagon | `object_id@version` | `derived_from` → another Rule (lineage); named SKUs inside `actions` (`default_component`, `require_mounting`) → Product | scope is a dimension match, not a stored edge — not walked in v1 (see "Deferred") |
| **Published Part** | circle | its opaque id from the snapshot | `citations[].belongs_to` → SourceDoc (`knowledge/parts.py`) | none today — nothing links INTO a Part |
| **SourceDoc** | page | `content_hash` | none (a document doesn't reference anything) | Rule, Part, Gap, Warning — anything with a `cites`/`belongs_to` field naming it |
| **Model** (a `PanelSpec` version) | diamond | `model_id@version` | each frame/infill slot's `requirement.part_id` → Part; each slot's `eligibility.members`/`predicate` → Product(s) | none today |
| **Product** (catalog SKU) | square | `sku` | none (a catalog row doesn't reference anything) | Rule (named directly), Model (via eligibility — see below) |
| **Warning** (`DocumentWarning`) | triangle | its own id | `cites: list[SourceRef]` → SourceDoc (`core/warnings.py:161`) — the identical shape Part/Rule/Gap already use | none — nothing points into a Warning |

**Gap, Project/Override, and generated read-model data** (structure sheet,
BOM, elevation) are named but **out of v1 scope** — see "Deferred," below.
**AssemblyStep was investigated, not deferred by default: it is not a
graphable entity at all** — see the same section for why.

### The one non-trivial edge: Model → Product via eligibility

A slot's eligibility is either a list of named `members` (a direct edge, cheap
to enumerate) or a `predicate` over item attributes — which does not name a
SKU at all, so "what does this reference" is not a static field read for that
case. It does not require running a generation, though: `predicate_skus()`
(`fencemodel/model.py:1220`) is exactly this question, already built and
already used by `validate_model` to refuse a predicate that admits nothing —
*"asking the MATCHER rather than walking the catalog here is the whole
point... the same reason a second copy of the covering rule is how the two
would eventually disagree."* The Connections backend reuses this function
rather than writing a second implementation of eligibility matching.

## The design

### Architecture

```
src/fenceai/connections/
  resolve.py     — per-kind resolver: given (kind, id), return outbound refs
                   and (via a reverse index built from every OTHER entity's
                   outbound refs) inbound refs. Pure, reads the store's already-
                   loaded data — no new persistence.
  audit.py       — the standing checks: dangling SKU references, unreferenced
                   SourceDocs, unreachable Products (via predicate_skus), and
                   the Part→Product structural-gap count. Returns a flat list
                   of findings, not a graph.

src/fenceai/api/app.py
  GET /api/connections/{kind}/{id}   -> {entity, references, referenced_by}
  GET /api/connections/orphans       -> [{severity, category, entity, detail}]

  `kind` is one of the six closed values: `rule`, `part`, `sourcedoc`,
  `model`, `product`, `warning`. `id` is that kind's identity per the table below,
  URL-encoded as one path segment — a Rule's `K-MAXSPAN@v3` and a Model's
  `M-SLAT@v2` both carry their version joined with `@`, so the frontend must
  `encodeURIComponent` it and the route must NOT try to split it into two
  path params (that would treat every kind's identity as the same shape, and
  they aren't: a Product's id is a bare SKU, a SourceDoc's is a content hash).

src/fenceai/web/static/js/connections.js
  Owns #tab-connections entirely (module-boundary rule: talks to state.js only).
  Entity search/switcher, the radial SVG (shape=kind, color=relation, pure
  trig placement per ring — no layout library), the two reference lists, the
  orphans table with severity filters.
```

`Connections` is added to the tab strip and to `role.js`'s hide-list exactly
like `Knowledge`/`Review` — visible only in the `all` (super-user) role. The
audience for "why is this SKU unreachable" is whoever tunes rules and models,
not a salesperson or the office.

### Data flow

1. User picks or searches for an entity (kind + id).
2. Frontend calls `GET /api/connections/{kind}/{id}`.
3. Backend's `resolve.py` reads that entity, walks its own fields for outbound
   refs per the table above, and separately walks the reverse index (built
   once per request from every loaded Rule/Model/Part — see "Performance") for
   inbound refs.
4. Response is `{entity: {kind, id, label}, references: [{kind, id, label,
   relation}], referenced_by: [...]}` — the exact shape the mockup's `ENTITIES`
   fixture already models, so the frontend work is turning that fixture into a
   real fetch.
5. Frontend places outbound refs on the inner ring, inbound on the outer ring,
   by angle (`2π·i/n`, one ring at a time) — no force simulation, no
   iteration, deterministic per the mockup's `ring()`/`shapeEl()` functions.
6. The orphans table calls `GET /api/connections/orphans` once, independently,
   and is never rendered from the per-entity response — the two surfaces stay
   decoupled, matching every real precedent researched (orphans are always
   their own list, never embedded in a graph).

### The orphan/dangling checks, enumerated

| Check | Cost | Mechanism |
|---|---|---|
| Dangling SKU reference (Rule names a SKU not in the catalog) | cheap | scan every Rule's `actions` for a `sku`/`role` field, set-difference against the catalog |
| Unreferenced SourceDoc | cheap | reverse-index scan across Rule, Part, Warning, **and Gap** — Gap is not itself a lookup-able entity in v1 (see "Deferred"), but its `cites` still counts toward whether a SourceDoc is referenced, or the check would report false orphans for a doc only a Gap cites |
| Unreachable Product | cheap, reuses existing code | union `predicate_skus()`/`members` across every slot of every **active** Model version, union every SKU named by an **active** Rule; any catalog SKU absent from both unions is unreachable. Draft/proposed model versions are excluded — an unpublished draft naming no products yet is not a defect. |
| Missing Part→Product link | not a check, a standing fact | report the count of published Parts (212 today) as one **informational** row, not per-part — this is a structural gap, not N separate defects |

### Performance

The reverse index and the three cheap checks are O(rules + models + catalog),
all small (hundreds, not millions) — computed fresh per request is fine for
v1. `predicate_skus()` runs once per slot per active model version, which is
the same cost `validate_model` already pays at load time. No caching, no
background job, no new persistence. If this later needs the audit to run on
every load, revisit — not a v1 concern.

### Error handling

- Unknown `(kind, id)` → 404 with the two values echoed back, matching this
  API's existing not-found style (check `_project`'s 404 shape and mirror it).
- An entity with zero outbound or zero inbound refs is not an error — the
  mockup's empty-ring dashed-circle treatment is the correct rendering, not a
  fallback.
- The orphans route always returns 200 with whatever it found, including an
  empty list — an empty audit result is a real, good state, not a loading
  failure.

### Testing

- `tests/connections/test_resolve.py` — one test per entity kind's outbound
  resolution, one test proving the reverse index correctly attributes an
  inbound ref back to its source (a Rule naming a SKU shows up under that
  SKU's `referenced_by`).
- `tests/connections/test_audit.py` — each of the three checks gets a clean
  case (0 found, mirroring the real `dangling_refs()` invariant) and a dirty
  case (constructed fixture with a genuine dangling ref / unreferenced doc /
  unreachable product), plus one test that `predicate_skus()` is called
  through its real signature rather than re-implemented.
- `tests/web/test_connections_module.py` — following `test_step_surfaces.py`'s
  own pattern: parse `connections.js` for the shape/color mapping tables,
  assert every `SHAPE_OF` kind has a corresponding legend entry (the two must
  never drift, the same discipline `step-surfaces.js`'s CSS-mirror check
  already enforces elsewhere in this codebase).
- `tests/web/test_locale_bundles.py` — new i18n keys added for the tab label,
  panel headings, severity labels; key-identical across `en`/`he`.
- One new browser-smoke case in `tools/ui_smoke.py`: open Connections, switch
  entities, confirm the radial SVG and both lists render, confirm the orphans
  table filters by severity.

## Deferred, and why

- **Gap as a graphable entity.** A `Gap.subject` is a discriminated envelope
  (`EntityRef | ParamRef`) that names what it's ABOUT, not a stable node with
  its own inbound edges — including it would mean designing a second kind of
  edge (aboutness vs. reference) this spec doesn't need yet. Revisit if a real
  use for "what points at this gap" shows up.
- **AssemblyStep — investigated, and it turns out not to be a new node at
  all.** `report/assembly.py` and `model.py:634`: an authored `AssemblyStep`
  names `slots` (this same Model's OWN frame/infill slot keys) and
  `bay_parts` (post/cap/footing roles belonging to the RUN, not a specific
  Product or Part). Every reference it carries is internal to the Model that
  owns it — the same relationship a Rule's `actions` have to that Rule. It
  folds into the Model node; no separate shape, no separate lookup.
- **Project, and the Override layer it carries.** Real references exist —
  `Project.fence_model` → Model, `ForcePostSku.sku` → Product
  (`strategy/overrides.py:40`) — and "which live jobs actually use this
  model" is a genuinely useful question. Deferred anyway: it's a different
  LAYER (operational job data — a specific customer's fence) from the
  knowledge/catalog layer this view audits, with a different audience (the
  person tuning rules and models vs. someone asking about a specific job).
  Folding it in would double the entity count and blur two questions that
  deserve to stay separate. Worth its own pass if "which jobs does changing
  this model affect" becomes a real ask.
- **Generated read-model data** (the structure sheet, BOM, elevation).
  Excluded on a harder principle than scope: these are pure functions of
  `(topology, strategy, requirements, bom)`, recomputed on every read, with
  no persisted identity of their own. "Orphan" and "dangling reference" are
  questions about STORED things — a regenerated view has nothing to be
  orphaned, and graphing it would mean inventing an identity for something
  the rest of the codebase deliberately keeps from having one.
- **Rule `scope` as a graph edge.** `scope` is a dimension match (a rule
  applies to Model X, Exposure C), not a foreign key to one Model instance —
  representing it as an edge would misrepresent a filter as a reference.
  Worth a second design pass on its own if scope-based "what rules could ever
  apply to this model" turns out to matter.
- **Caching / precomputed audit.** See "Performance" — not needed until the
  cheap computation stops being cheap.
