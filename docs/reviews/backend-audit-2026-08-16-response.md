# Backend architectural audit — dispositions

Audit: `backend-audit-2026-08-16.md`, kept verbatim. It states up front that it read
the documentation and not the implementation, so every checkable claim below was
verified against code before being accepted or rejected.

**Score:** of the six documentation defects it lists, **four hold** (two of them
introduced by the diagram-led doc set the day before), **one is inverted**, and **one
is a false positive**. Of the structural findings, the sharpest — no first-class
materialization identity — is **verified and accepted**.

---

## Fixed immediately (commit `d8872ef`)

| Finding | Verdict | What was done |
|---|---|---|
| AI has three ports vs four | **Holds, and worse** | `ai-layer.md` documented four ports; `ai/ports.py` has three Protocols — and all three documented *signatures* were wrong too (an ambient `ctx` on `interpret`/`propose`; `critique` taking strategy+graph+topology rather than one `GenerationResult`). `ExplanationWriter` appears nowhere in `src/` or `tests/`, and `v1-known-limitations.md:235` records Tier-2 polish as unimplemented while the doc described it as a live boundary. Signatures corrected from source; the phantom port moved to a "Designed, not built" section |
| "Eight tables" but nine listed | **Holds — ours** | `04-backend.md` said eight over a nine-row block including `audit_log` |
| `project` → `strategy.overrides` missing from the domain graph | **Holds — ours** | The import is real (`project/model.py:9`). Edge drawn, and annotated together with `project` → `ai.records` as inverted ownership that is not a correctness defect today: both types are inert data, no behaviour is imported, the graph stays acyclic |
| Portfolio impact contradicts V1 | **Inverted** | The feature shipped (`learning/impact.py`, `preview_impact` / `preview_model_impact`, `projects_checked` / `projects_affected`). `system-design.md`'s deferral list was stale. Fixed there, including the scaling limit it runs under |
| `RequirementLine` represents two states | **Holds** | Imprecisely stated — the fields are `= ""` defaults, not required — but the modelling point is right and is the best of the six. Documented in `02-entities.md`; the type split is scheduled (below) |

The audit also exposed a defect in the doc set's own **precedence rule**. `README.md`
said *"where the map and a deep-dive disagree, the deep-dive wins"*, which resolves
the AI-ports drift the wrong way round — the map was the accurate document. The rule
is now: **the code wins**, and whichever document contradicts it is the defect.

## Rejected

| Finding | Why |
|---|---|
| `code + params` contradicts a `message` field | **False positive.** `StrategyWarning` carries `code`, `severity`, `params` **and** `message`, with `message` documented as the English fallback. Both documents were right |
| §4.6 — bound impact analysis back to single-project | A recommendation to remove a **shipped feature**, reached from the stale deferral line above. The underlying concern — regenerating a portfolio synchronously in one process over a serialized store — is accepted and recorded as a scaling limit; the answer is a job boundary, not a retreat |
| §2 — restructure into `shared/domain/application/infrastructure/transport` | Rejected **as a big bang**: ~16 module renames across 1045 tests for largely nominal gain. The one piece of real content in it — an application layer — is accepted below in incremental form |
| §1.4 — route-level TOCTOU presented as a critical discovery | True, and already stated explicitly by ADR-0008, which declines to solve it and says so. Accepted as a known limitation, not counted as a new finding |
| §4.5 — trim the V1 AI ports | Largely moot: only three exist. Resolved by documenting reality |

## Accepted and scheduled

| Finding | Verified | Where it lands |
|---|---|---|
| §1.5 — no first-class materialization identity | **Yes.** `/api/runs/{id}/bom` reads live inventory and computes an `inventory_hash` that goes to the **audit log**, not into any identity, so one `run_id` yields different BOMs as stock moves. And `objective_preset` — read only by `supply.py`, the panel preview and impact — is inside the *design* run digest at `generator.py:197` | **Its own spec.** It changes persisted identity, so it gets the same brainstorm → spec → review → plan treatment as the part-spec design. Not blocking the vinyl arc |
| §1.7 — split `DemandLine` / `ResolvedSupplyLine` / `UnresolvedSupplyLine` | Yes — `fulfill()` refuses a blank sku at runtime because the type system cannot | **Part-spec arc, W2.** `resolve_supply` writes sku and unit in one statement and the matcher produces the eligibility it consumes; splitting while already at that seam is far cheaper than twice |
| §4.2 — type what deterministic code reads | Yes — `_can_supply_length` does `attrs.get("length_mm")`; `face_width_mm` and `opening_width_mm` are the same shape | **Part-spec arc, W2, narrowed.** *Code* stops reading magic keys (typed capabilities); *predicates* keep reading the open bag, because a predicate is data and needs no release. This is what reconciles the audit's rule with the arc's premise |
| §1.6 — engine behaviour versions in the content identity | Yes — the digest holds data versions only, so a legitimate algorithm change can reuse a run id | **Part-spec arc, W2.** Three constants; the cheapest Phase-0 item in the audit |
| §1.3 — no application layer | Yes — `api/app.py` is 1007 lines and orchestrates; `fulfillment/pipeline.py` was a reactive fix after four copies diverged | **Opportunistic.** Extract a handler when a use case is next touched. `generate`, `/bom`, `quote` and `impact` are the four with real duplication risk |
| §1.10 — `generate()` is pure but not SRP | Yes — `strategy/generator.py` is **2002 lines** | Accepted. The `DecisionRecorder` protocol is the cheap half and can land alone |
| §4.4 — three meanings of "run" | Yes — topology `Run`, `GenerationRun`, and `run_id` inside override anchors | Accepted: typed ids. Unscheduled, low cost |
| §4.3 — quote lifecycle out of fulfillment | — | Accepted, low priority. Nothing forces it until quotes gain terms, tax or approval state |

## Deferred with a trigger

| Finding | Trigger |
|---|---|
| §4.1 — orthogonalize the knowledge taxonomy into lifecycle / effect / enforcement / origin / authority / scope | Intellectually right and expensive: a persisted-data migration for a modelling improvement, against seven types whose distinct handling is encoded in 155 golden scenarios. Note that "the tier decides the consequence" — the same check blocking under a `hard_constraint` and warning under a `company_rule` — is a deliberate shipped feature, not an accident of the enum. Revisit when a rule genuinely needs two of those axes to vary independently |
| §5 — architecture fitness tests (forbidden imports, table inventory, port inventory, route inventory, hash field lists) | Accepted in principle and the right answer to this whole class of drift. Worth doing right after W2, when the import graph stops moving |

## What a documentation audit could not see

Recorded so the method is weighted correctly next time. While this audit was being
read, the doc set and the code together showed two defects it had no way to find:

* `clear_width_mm` has **never been computed** (`generator.py:1332`, `# face widths
  arrive in phase 2`), so `resolve.py:466` fits every vertical infill across the
  centre-to-centre width — each panel laid out over an opening that includes half a
  post at each end. This is the subject of the part-spec arc's W1.
* `ObstaclePayload` is authored in the topology model and read by nothing —
  one grep hit, its own class definition.

A documentation audit finds structural smells. It does not find wrong numbers.
