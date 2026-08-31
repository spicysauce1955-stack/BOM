# Opening the door: a published snapshot that reaches a real run

**Date:** 2026-08-31 · **Status:** design, awaiting approval
**Contract:** §1.2 (`Snapshot`), §1.5 (Resolution surface), §3.2 obligations 1–3
**Build-order:** the wiring three slices have been built behind

---

## 1 · The problem, and it is not a missing feature

Three slices have added depth to the published-knowledge path. None of them
connected it. Verified:

| Built | Reachable from the app |
|---|---|
| `knowledge/source_policy.py` — the §1.4 policy | via `expand()` only |
| `knowledge/snapshot.py` — `load()` / `ingest()` | **no caller in `src/` at all** |
| the admissibility gate and the provenance chip | **no** — nothing produces the data |

`store/db.py`'s `knowledge_base()` reads `knowledge_versions` and returns
`KnowledgeBase(versions=…)`, so `admitted` and `declined` are empty on every
reload by construction.

So: a complete, tested pipeline with no door. Everything it does is correct
against a fixture and invisible to a person. A fourth layer behind the same
closed door would make that worse, which is why this slice is wiring rather than
capability.

## 2 · Where a snapshot comes from — the decision, and it is reversible

**Default taken: an explicit operator load of a snapshot document, persisted.**

§1.5 defines a Resolution surface (`GET /snapshots/{id}`) and there is no service
to call — the other team has designed it and built nothing. So fetching is not
available, and inventing a client for an absent service would be building against
a guess.

The two real options were a **bundled default that loads itself** and an
**explicit load**. Explicit, because a knowledge base that swaps itself under a
project changes numbers with no action anyone took — the same reason generation
sits behind a button rather than firing on edit.

*(Worth noting: `AMENDING.md` §1 already asserts "a bundled default snapshot ships
inside the Planning repo." It does not. The only snapshot in the repo is the
conforming fixture, which tests assert cannot be mistaken for published data. The
sentence describes an intent, not a file.)*

**Override this if you want the bundled-default behaviour** — it is a smaller
slice, not a bigger one, and the rest of the design is unchanged.

## 3 · The design: store the document, re-derive the verdict

The instinct is to persist `admitted` and `declined` beside the versions. **That
would be wrong**, and the repo already knows why: read models are derived, never
stored.

A source verdict is not a property of the snapshot. It is a function of
`(snapshot, policy, task)` — and the policy is an operator's configurable table.
Freezing the verdict at load time records an answer that the next policy edit
makes false, with nothing to say it changed.

So:

- **Persist the snapshot document**, keyed by its own `snapshot_id`. It is
  immutable by contract (§1.2.1: the same hash resolves to the same bytes until
  `retain_until`), which makes it exactly the kind of thing worth storing.
- **Re-derive** versions, verdicts and declined bounds by re-ingesting on load.
  One code path for a fresh load and a reload, so the two cannot diverge.

The cost is honest and small: ingesting four tables is cheap, and the alternative
is a cache that can lie.

## 4 · Pinning, which is a promise we have not been keeping

§3.2 obligation 1: *"Pin a snapshot hash on every run; re-fetch historical runs
by hash, never re-resolve."*

A `Run` records `knowledge_snapshot` (our `(object_id, version)` pairs) and
`snapshot_hash` — **our own digest of that list, not the publisher's
`snapshot_id`.** So a stored run cannot be re-fetched by hash the way the
obligation requires: nothing persisted says which published snapshot it used.

This slice pins the real one. A run gains the publisher's `snapshot_id`, and our
existing digest stays exactly as it is — it answers a different question (*which
knowledge objects*, authored included) and both are worth having.

## 5 · What changes for a person

An operator loads a snapshot. From then on, on the plan:

- values from published rows carry *"backed by sealed engineering approval ·
  curation level 2"*
- a refused row shows *"we did not use the manufacturer's 36 inches — nobody has
  verified it"*, and the layout is never laxer than the number refused
- the run says which published snapshot it was built against

None of that is new behaviour. It is the behaviour of the last three slices,
becoming visible for the first time.

## 6 · Scope

**In:** a `knowledge_snapshots` table (`snapshot_id` + document) and an active
pointer; a load route that ingests and persists; `knowledge_base()` returning
authored + published with verdicts; `snapshot_id` pinned on the run; the
ingest's gaps and warnings surfaced where gaps already surface.

**Out, with named seams:**

- **Fetching from the Resolution API.** No service exists. The load route takes a
  document; pointing it at `GET /snapshots/{id}` later changes one function.
- **Policy versioning.** The verdict depends on the policy, so a historical run
  re-derived under an edited policy would render differently. Nothing versions the
  policy today and nothing edits it either, so the exposure is zero until an
  operator UI lands — but it must land together with pinning `policy_version`,
  which §1.4 already says is part of the snapshot's identity.
- **Tenant scoping.** One active snapshot, matching the single-tenant store.
  §1.1's `TenantId` is modelled; the store is not multi-tenant and this slice does
  not make it so.

## 7 · How we will know it works

- The conforming fixture loads through the route, persists, and survives a
  reload with verdicts intact — the reload is the assertion, since that is the
  path `knowledge_base()` broke.
- A generated run carries the publisher's `snapshot_id`, and a stored run read
  back reports the same one.
- The provenance chip appears in the browser smoke suite, in Hebrew, on a real
  page rather than in node.
- The real snapshot (`3ae88642`) is still **refused by version** — it predates
  the typed `Date` and wants their re-cut. The route must report that refusal as
  the one clear sentence it already produces, not as a stack trace. That is the
  first thing a person will actually hit.

## 8 · Files

| File | Change |
|---|---|
| `store/db.py` | `knowledge_snapshots` table; store/fetch/activate; `knowledge_base()` re-ingests |
| `api/app.py` | load + inspect routes; refusal reported as a typed 4xx |
| `strategy/model.py` | `Run.snapshot_id` |
| `strategy/generator.py` | stamp it |
| `web/static/js/` + `i18n` | where the active snapshot and a refusal are shown |
| `tests/` | per step, plus the reload, plus a smoke check |
