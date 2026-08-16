# Architecture documentation — index

Two kinds of document live here, and they are not interchangeable.

**The map** — numbered, diagram-led, written to be read in order. It shows shape:
which domains exist, what they own, what flows between them, and why the boundaries
fall where they do.

| # | File | Answers |
|---|---|---|
| 00 | [`00-overview.md`](00-overview.md) | What is this system, end to end, on one page? |
| 01 | [`01-domains.md`](01-domains.md) | What are the domains, what does each own, and what may import what? |
| 02 | [`02-entities.md`](02-entities.md) | What are the entities and how do they relate? (UML) |
| 03 | [`03-flows.md`](03-flows.md) | What happens when you press Generate, read a BOM, or correct a decision? |
| 04 | [`04-backend.md`](04-backend.md) | How is the backend put together — routes, store, purity, refusals? |
| 05 | [`05-frontend.md`](05-frontend.md) | How is the frontend put together — modules, state, four drawings, RTL? |
| 06 | [`06-choices.md`](06-choices.md) | Why is it like this? The load-bearing decisions and their costs. |

**The territory** — prose deep-dives that own the detail.

> **When two documents disagree, the CODE wins** and whichever document contradicts
> it is the defect. This rule started life as "the deep-dive wins", which was wrong
> the first time it was tested: `ai-layer.md` documented four AI ports with
> signatures the three real Protocols do not have, and the map was the accurate one.
> A deep-dive is more detailed, not more current.

| File | Owns |
|---|---|
| [`system-design.md`](system-design.md) | Module map, the spine, deferred scope |
| [`domain-model.md`](domain-model.md) | Entity semantics and invariants, in prose |
| [`knowledge-system.md`](knowledge-system.md) | Types, authority, scope, precedence, conflicts |
| [`decision-model.md`](decision-model.md) | Node and edge kinds, query shapes, explanations |
| [`material-optimization.md`](material-optimization.md) | Demand, cut planning, packaging, objectives |
| [`ai-layer.md`](ai-layer.md) | Ports, adapters, hard boundaries |

Decisions with consequences are recorded as ADRs in [`../adr/`](../adr/) and are
cited throughout. The behavioural contract is
[`../scenarios/golden-scenarios.md`](../scenarios/golden-scenarios.md) ⇄
`tests/scenarios/`; the non-negotiable properties are §15 of
[`../product/architecture-foundation-v0.1.md`](../product/architecture-foundation-v0.1.md).

## Reading paths

* **New to the codebase** — 00, then 01, then 03. That is enough to place any file.
* **Adding a domain concept** — 02, then `domain-model.md`, then the relevant ADR.
* **Touching the frontend** — 05, then the frontend section of `CLAUDE.md`, which is
  the enforced contract.
* **Asking "why is it like this"** — 06.

## A standing rule

`CLAUDE.md`: *change code and these docs together, or not at all*. A diagram that has
drifted is worse than no diagram, because it is read as current. Every entity and
field drawn in 02 is copied from a real model class, and each diagram names the file
it was drawn from so the next person can check it in one command.
