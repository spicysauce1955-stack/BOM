# 04 — Backend

Python 3.12, FastAPI, Pydantic v2, SQLite. One process, no queue, no cache tier, no
ORM. ADR-0001, -0008.

---

## Layers

```mermaid
flowchart TB
    subgraph L1["api — the only layer that knows about HTTP"]
        R["47 routes"]
        CR["composition root:<br/>picks the AI adapter, opens the Store,<br/>seeds the demo"]
    end
    subgraph L2["orchestration"]
        PI["fulfillment/pipeline.py<br/>derive → resolve_supply → fulfill"]
        LI["fencemodel/library.py · learning/review.py"]
    end
    subgraph L3["pure domain"]
        PD["generate() · resolve_panel() · fit_pattern()<br/>plan_cuts() · build_structure() · panel_elevation()"]
    end
    subgraph L4["persistence"]
        ST["store/db.py — 8 tables, documents as JSON"]
    end

    R --> PI
    R --> LI
    PI --> PD
    LI --> PD
    R --> ST
    PI -.->|"never"| ST

    style L3 fill:#1f2937,color:#fff
```

**The pure layer takes no repository.** Every domain function receives its inputs as
arguments — topology, catalog, knowledge base, inventory — and returns a value.
Persistence happens *between* stages, in the route. That is what makes the whole
domain testable without a database and what keeps `generate()` reproducible.

---

## The API surface

47 routes. Grouped by what they are for rather than by path:

| Group | Routes | Notes |
|---|---|---|
| Projects & topology | `GET/POST /projects`, `GET /projects/{id}`, `PUT /projects/{id}/topology` | Topology PUT bumps `revision` |
| Generation | `POST /projects/{id}/generate`, `GET /projects/{id}/runs`, `GET /runs/{id}` | The only write that decides a fence |
| Explanation | `GET /runs/{id}/explain/{element_id}`, `GET /runs/{id}/impact/{object_id}` | Takes `lang` **and** `units` |
| Read models | `GET /runs/{id}/structure`, `GET /runs/{id}/bom` | 409 on stale topology or catalog |
| Money | `POST /runs/{id}/quote`, `GET/POST /quotes/{id}[/accept]`, `GET /projects/{id}/quotes` | Immutable snapshots with a lifecycle |
| Knowledge | `GET/POST /knowledge`, `POST /knowledge/{id}/{v}/retire`, `POST /knowledge/preview-impact` | Versioned; never edited in place |
| Learning | `POST /projects/{id}/corrections`, `POST /projects/{id}/propose-knowledge`, `GET /candidates`, `POST /candidates/{id}/{v}/review` | Candidates are inert |
| Fence models | `GET/POST /fence-models`, `PUT /fence-models/{id}/draft`, `POST .../publish`, `POST .../status`, `DELETE .../{v}`, `POST /fence-models/preview`, `POST /fence-models/{id}/preview-impact` | Publish is the gate |
| Panel preview | `POST /runs/{id}/bays/{element_id}/panel-preview` | Reads the run, not the live catalog |
| Annotations | `POST /projects/{id}/annotations[/{id}/interpret]`, `POST /projects/{id}/intents/{id}/confirm` | Verbatim in, proposals out |
| Overrides | `POST /projects/{id}/overrides`, `DELETE .../{override_id}` | Anchored to `(run, station, kind)` |
| Catalog & inventory | `GET /catalog`, `PUT /catalog/products`, `GET/PUT /projects/{id}/inventory` | |
| Ops | `GET /api/health`, `GET /api/audit` | |

Two routes exist that look redundant and are not: `POST /fence-models/preview` takes
an **unsaved** document in its body, while `POST /fence-models/{id}/{v}/preview`
prices a stored one. The first exists because an editor that must save to preview
leaves half-typed model ids in the library forever.

---

## Refusals are typed, localized data

Two exception types carry `code + params`; the English `message` is a fallback only.

```python
ReadRefused(code="topology_changed", message="...", **params)   # → 409
GenerationFailure(code="fence_model_unknown_sku", ...)          # → 422
```

A new code needs `warning.<code>` / `critique.<code>` / `error.<code>` entries in
**both** locale bundles, and `tests/web/test_locale_bundles.py` enforces it — it
scans `api/app.py` and both `code="..."` spellings, which immediately caught four
codes shipping untranslated, including two 409s a user meets whenever they edit a
catalog or a drawing.

**Warnings carry structure, not sentences.** `js/warnings.js` owns the single
`code + params` → sentence path, so a bay is named by its structure-report tag rather
than by an id the server happened to interpolate.

| Situation | Shape |
|---|---|
| The drawing moved under a stored run | 409 `topology_changed` |
| A product this run bought was repriced | 409 `catalog_changed` |
| Nothing in the catalog can supply a slot | warning `no_eligible_item` + `unresolved` line |
| Candidates were tried and none fits | warning `no_feasible_item` |
| A part could not be measured at all | **error** `panel_length_unresolved` |
| Two hard constraints conflict | `GenerationFailure` |

The distinction in the last three rows is deliberate: a warning describes a fence
built badly, an error describes a part not bought at all.

---

## Persistence

Eight tables. Documents are stored as JSON `doc` columns; the schema holds only what
is queried or ordered by.

```sql
projects(id, doc)
knowledge_versions(object_id, version, status, doc)   -- PK (object_id, version)
fence_models(model_id, version, status, doc)          -- PK (model_id, version)
generation_runs(id, project_id, created_at, doc)
corrections(id, project_id, doc)
inventories(project_id, doc)
catalogs(id, doc)
quotes(id, project_id, status, created_at, doc)
audit_log(seq, at, actor, action, ref)
```

**Versioned rows are append-only.** A knowledge version and a published fence-model
version are never updated in place; `DELETE` on a fence model is refused **in the
store** for a published version, because an immutable document any route could delete
is not immutable.

**The store is serialized** (ADR-0008). `Store` holds one `sqlite3.Connection` opened
`check_same_thread=False`, and FastAPI serves sync endpoints from a threadpool — so
overlapping requests interleaved statements on one connection. The visible half was a
500 from `GET /inventory` while a draft was saving, reproduced at **48 failures in
~540 overlapping requests**. The silent half is worse: half of `Store`'s methods are
read-then-write sequences, and another thread's `commit()` landing inside one commits
a transaction nobody finished.

Every public method now takes a re-entrant lock, held for the **whole call**. A
per-thread connection was rejected because it would give every `Store(":memory:")`
test its own empty database. What this does **not** cover is recorded in the ADR:
route-level read-then-write is still a TOCTOU window.

**`TestClient` serialises requests**, so no pytest test can see this class of bug.
The browser smoke suite was the only detector — red there, green on main. That is why
the smoke suite is a release gate and not a nicety.

---

## Testing tiers

| Tier | Command | What it is for |
|---|---|---|
| Unit + integration | `uv run pytest -q` | ~1045 tests over pure functions and routes |
| Golden scenarios | `uv run pytest tests/scenarios -q` | 155 scenarios — the behavioural contract, ⇄ `docs/scenarios/golden-scenarios.md` |
| Compatibility gate | committed per-fixture requirement lines + BOM as JSON | Proves a refactor changed no number |
| Browser smoke | `uv run --with websocket-client python tools/ui_smoke.py` | 159 CDP-driven checks; the only tier that sees concurrency and rendering |

**Mutation is the standard, not coverage.** The recurring failure mode in this
codebase is a green suite over a broken feature — a vacuous assertion
(`buttons == len(options) - 1` evaluating `0 == 0`), a test named for a property it
never asserted, five `runview.js` mutants surviving at once. New tests are expected
to be shown failing against the pre-fix code.
