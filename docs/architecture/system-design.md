# System design

Modular monolith (`src/fenceai/`), Python 3.12, FastAPI, Pydantic v2, SQLite. Static SVG/JS
frontend. See ADR-0001, -0008, -0010.

## Module map and dependency rule

```
core        units (int mm/cents), ids, errors, tolerances          (depends on: nothing)
topology    nodes, runs, events, stationing, profiles              (core)
catalog     products, consumption semantics, substitution rules    (core)
knowledge   objects/versions, condition AST, evaluator, precedence (core)
decisions   decision graph builder, node/edge types, explanations  (core)
strategy    generator pipeline, layout, overrides, warnings        (topology, catalog, knowledge, decisions)
demand      requirement derivation from strategy                   (strategy, catalog)
fulfillment cut planner, packaging, inventory netting, BOM         (demand, catalog)
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
snapshot hash, overrides, policy) so any strategy is reproducible.

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

## What V1 deliberately defers

Multi-user/auth, concurrent editing, Postgres, embeddings/semantic search, CP-SAT solvers,
2D sheet cutting, arcs in plan geometry, IFC export, reservation/ATP beyond flags,
impact-preview across historical projects (single-project impact analysis only).
