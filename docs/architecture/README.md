# Architecture documentation — index

**Three planes.** Every package, entity, flow, route, table and frontend module is
read as belonging to one of three planes, and every document here says which:

| Plane | Answers | Territory |
|---|---|---|
| **Engine** | What is this fence, why, and what does it cost? | `knowledge-system.md` · `decision-model.md` · `material-optimization.md` · `published-part-inspection.md` |
| **People & work** | Who is asking, what may they do, and whose desk is the job on? | `people-and-work.md` |
| **AI & learning** | What does a model suggest, and how does a correction become a rule? | `ai-layer.md` |

The one rule between them — **AI output changes no engine computation until a person
confirms it** — with its qualifications, and the imports that cross planes, are in [`00-overview.md`](00-overview.md#three-planes)
and [`01-domains.md`](01-domains.md).

Two kinds of document live here, and they are not interchangeable.

**The map** — numbered, diagram-led, written to be read in order. It shows shape:
which domains exist, what they own, what flows between them, and why the boundaries
fall where they do.

| # | File | Answers |
|---|---|---|
| 00 | [`00-overview.md`](00-overview.md) | What is this system, end to end, on one page — and what are the three planes? |
| 01 | [`01-domains.md`](01-domains.md) | Which packages are in which plane, what does each own, and what may import what? |
| 02 | [`02-entities.md`](02-entities.md) | What are the entities and how do they relate? (UML, one part per plane) |
| 03 | [`03-flows.md`](03-flows.md) | What happens when you generate, price, move a job, sign in, interpret a note, or correct a decision? |
| 04 | [`04-backend.md`](04-backend.md) | How is the backend put together — the gate, routes by plane, store, purity, refusals? |
| 05 | [`05-frontend.md`](05-frontend.md) | How is the frontend put together — modules by plane, the bus, screens, roads, drawings, RTL? |
| 06 | [`06-choices.md`](06-choices.md) | Why is it like this? The load-bearing decisions and their costs. |

**The territory** — prose deep-dives, one per domain, that own detail the map does
not carry. Each answers a question no numbered document answers; none of them
restates one.

| File | Owns |
|---|---|
| [`knowledge-system.md`](knowledge-system.md) | Engine — types, authority, scope, precedence, conflicts, the published snapshot |
| [`decision-model.md`](decision-model.md) | Engine — node and edge kinds, query shapes, explanations |
| [`material-optimization.md`](material-optimization.md) | Engine — demand, supply, cut planning, packaging, objectives, supply runs and quotes |
| [`published-part-inspection.md`](published-part-inspection.md) | Engine — inspecting the parts a published snapshot carries |
| [`people-and-work.md`](people-and-work.md) | People & work — identity, capacity, the job lifecycle, the command door, the roads |
| [`ai-layer.md`](ai-layer.md) | AI & learning — ports, adapters, the agent, the learning loop, the boundaries and what enforces them |

> **When two documents disagree, the CODE wins** and whichever document contradicts it
> is the defect. The rule started life as "the deep-dive wins" and was wrong the first
> time it was tested: `ai-layer.md` documented four AI ports with signatures the three
> real Protocols do not have, and the map was the accurate one. **A deep-dive is more
> detailed, not more current.**

> **One question, one document.** Two documents that answer the same question do not
> stay consistent — they take turns being right, and a precedence rule between them
> only tells you which one to believe, never which one is true. `system-design.md` and
> `domain-model.md` were deleted on 2026-08-18 for this reason: everything they were
> read for is above, and what they carried alone had gone stale where it was not
> outright wrong. `domain-model.md` described a `SetSpanBoundary` override that has
> never existed in any version of the code, and documented gate-kit fit as
> `attrs["opening_width_mm"]` — a bag lookup the catalog moved to a typed
> `Capabilities` field precisely because, in its own words, *a magic string key in
> Python is the defect*. Both had been flagged as doc-vs-doc contradictions in the
> 2026-08-16 backend audit and survived it. Deleting the loser is the fix; a
> precedence rule is not.

Decisions with consequences are recorded as ADRs in [`../adr/`](../adr/) and are
cited throughout. The behavioural contract is
[`../scenarios/golden-scenarios.md`](../scenarios/golden-scenarios.md) ⇄
`tests/scenarios/`; the non-negotiable properties are §15 of
[`../product/architecture-foundation-v0.1.md`](../product/architecture-foundation-v0.1.md).

## Reading paths

* **New to the codebase** — 00, then 01, then 03. That is enough to place any file.
* **Working on the engine** — 02 Part I, 03 §Engine, then the engine deep-dive.
* **Working on accounts, jobs or the roads** — `people-and-work.md`, 02 Part II,
  03 §People & work, then 04's identity and command rows.
* **Working on anything AI** — `ai-layer.md` first (the boundary and what enforces
  it), then 02 Part III and 03 §AI & learning.
* **Adding a domain concept** — 01's "where a new concept goes", 02, the deep-dive
  for its plane, then the ADR.
* **Touching the frontend** — 05, then the frontend section of `CLAUDE.md`, which is
  the enforced contract.
* **Asking "why is it like this"** — 06.

## A standing rule

`CLAUDE.md`: *change code and these docs together, or not at all*. A diagram that has
drifted is worse than no diagram, because it is read as current. Every entity and
field drawn in 02 is copied from a real model class, and each diagram names the file
it was drawn from so the next person can check it in one command.
