# System design

Modular monolith (`src/fenceai/`), Python 3.12, FastAPI, Pydantic v2, SQLite. Static SVG/JS
frontend. See ADR-0001, -0008, -0010.

> Diagram-led companions to this document: [`00-overview.md`](00-overview.md),
> [`01-domains.md`](01-domains.md), [`02-entities.md`](02-entities.md),
> [`03-flows.md`](03-flows.md), [`04-backend.md`](04-backend.md),
> [`05-frontend.md`](05-frontend.md), [`06-choices.md`](06-choices.md). Index:
> [`README.md`](README.md). Where they and this document disagree about a mechanism,
> **this document wins**.

## Module map and dependency rule

```
core        units (int mm/cents), ids, errors, tolerances          (depends on: nothing)
topology    nodes, runs, events, stationing, profiles              (core)
catalog     products, consumption semantics, substitution rules    (core)
knowledge   objects/versions, condition AST, evaluator, precedence (core)
decisions   decision graph builder, node/edge types, explanations  (core)
fencemodel  panel schema, pattern fit, resolution, model library   (catalog, knowledge)
strategy    generator pipeline, layout, overrides, warnings        (topology, catalog, knowledge, decisions, fencemodel)
demand      requirement derivation from strategy                   (strategy, catalog, fencemodel)
fulfillment supply resolution, cut planner, packaging, netting, BOM (demand, catalog, fencemodel)
report      structure + elevation read models (derived, never stored) (strategy, demand, fulfillment)
ai          ports + records (dependency-free); stub/claude ADAPTERS may import domain models
project     project aggregate, annotations, intent confirmation    (topology, ai.records, strategy.overrides)
learning    corrections, candidates, review, impact preview       (knowledge, decisions, strategy, demand, fulfillment)
store       SQLite repositories                                    (all models; no domain logic)
api         FastAPI routes + composition root                      (everything)
web         static frontend assets                                 (—)
```

Arrows only point down the list. `topology` never imports `strategy`; `demand`/`fulfillment`
read strategy output only; `decisions` is a passive data structure everyone writes into via
the builder. The AI layer is invoked only by `api`/`learning`/`strategy` through ports and
never sits inside deterministic computation (ADR-0009).

## The spine

```
Topology + Annotations ──┐
Catalog ─────────────────┼─► generate() ─► Strategy + DecisionGraph + Warnings
Knowledge snapshot ──────┤        (pure, deterministic — ADR-0004)
Overrides ───────────────┘
        Strategy ─► derive_requirements() ─► RequirementLines (pegged to elements)
        RequirementLines + Inventory + Policies ─► fulfill() ─► BOM + CutPlan + Allocations
```

Every stage is a pure function over explicit inputs; persistence happens between stages, not
inside them. A `GenerationRun` record captures inputs' identity (topology revision, knowledge
snapshot hash, overrides, policy, the fence model(s) used, catalog content hash, objective
preset) so any strategy is reproducible; the run id is a content hash over that identity, and
a later `/bom`/`/structure` read refuses (409 `catalog_changed`) rather than silently
recomputing against a catalog that no longer matches it.

## API surface (V1)

REST/JSON: projects CRUD; topology editing (nodes/runs/events); annotations + interpretation
(propose/confirm); knowledge CRUD (versioned) + conflict check; strategy generate/list/get;
decision graph + explanation endpoints; overrides; corrections + candidate review;
requirements/BOM/cut-plan; inventory; scenario fixtures loader for the demo.

## Frontend (pragmatic V1)

Single page: SVG plan canvas (draw runs, place gates/events, elevation entry), strategy
overlay (posts/spans/gates with warning badges), inspector panel (click element → decision
trace → explanation), tabs for knowledge, annotations/interpretations, review queue, BOM/cut
plan. Frontend renders server JSON only.

**Four drawings, one fence.** The plan canvas looks DOWN; the profile side view unrolls the
ground and the post tops so they can be edited (at 5x vertical exaggeration — a measuring
instrument, not a picture); the Assembly tab's macro viewport draws the run STANDING UP at
true scale (posts in their footings, panels docked between them, risers, gates); and the
panel elevation draws one bay's members. They must never disagree, so each of them PLACES
numbers it was given rather than deriving its own:

* the panel elevation's rectangles are `report/elevation.py`'s, computed once on the server,
  because the fit behind them is an algorithm with a justification x excess matrix and a JS
  copy would eventually disagree with the cut list the same numbers produced;
* the macro viewport (`js/runview.js`) reads the structure report — itself a read model
  forbidden from recomputing a quantity — so a bay width on the drawing is the same integer
  as the bay width in the schedule and in the BOM;
* the joint section (`js/joint.js`) exists because 15 mm on an 1800 mm panel is illegible:
  it is the same `JointDetail` numbers at their own scale, and it derives none of them.

Where a drawing does not have a number, it says so rather than inventing one: an undeclared
post face width or member thickness draws as a flagged nominal, and a gate opening with no
neighbouring height gets no leaf.

**Live figures name what they are.** A panel preview is not a run: the Assembly tab prices
what-ifs (a typed dimension, a material swap) through the same `preview_panel` pipeline, and
the cost strip shows the run's BOM total and the preview's panel total side by side rather
than switching one figure's meaning underneath the reader. Generation stays behind its
explicit button.

## What V1 deliberately defers

Multi-user/auth, concurrent editing, Postgres, embeddings/semantic search, CP-SAT solvers,
2D sheet cutting, arcs in plan geometry, IFC export, reservation/ATP beyond flags,
impact-preview across historical projects (single-project impact analysis only).
