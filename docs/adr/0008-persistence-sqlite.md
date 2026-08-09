# ADR-0008: SQLite (stdlib) document-style persistence behind repositories

Status: accepted · 2026-08-09

## Decision
Single SQLite database via stdlib `sqlite3`. Aggregates (project, topology, strategy+decision
graph document, catalog items) stored as JSON documents in typed tables; knowledge versions,
corrections, candidates, and audit records in append-only tables. Thin repository layer;
domain code never touches SQL. WAL mode; one DB file per deployment (path configurable,
`:memory:` in tests).

## Rationale
Research B assumed Postgres; mission §18 forbids infrastructure without a concrete use case.
All required query shapes are per-project/per-tenant-small; SQLite supports JSON and recursive
CTEs if needed. The repository layer keeps a Postgres swap contained when multi-tenant scale
or concurrent-writer needs appear (that is the trigger).

## Consequences
No cross-process write concurrency beyond WAL's single-writer — fine for V1 single-instance
deployment. Documented as a known limitation.
