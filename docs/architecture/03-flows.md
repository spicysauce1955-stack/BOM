# 03 — Flows

Five sequences worth knowing. Everything else in the API is CRUD.

---

## 1. Generate a strategy

The only place a fence is decided. Explicit, never automatic.

```mermaid
sequenceDiagram
    autonumber
    actor U as Estimator
    participant W as js/editor.js
    participant A as api/app.py
    participant S as Store
    participant G as strategy.generate()
    participant B as GraphBuilder

    U->>W: press Generate
    W->>A: POST /projects/{id}/generate
    A->>S: load project, knowledge, catalog, model library
    A->>A: bind_scope() from generation facts
    A->>G: generate(topology, knowledge, catalog, models, overrides, policy)

    activate G
    G->>B: input_fact nodes (geometry, knowledge versions)
    G->>G: fixed posts — corners, base transitions,<br/>gate edges, model boundaries, pins
    G->>G: closed-form span layout per segment<br/>(preferences resolved, alternatives recorded)
    G->>B: structural + selection + quantity nodes
    G->>G: resolve model per segment, resolve_panel per BAY
    G->>G: safety checks — gaps, rail separation,<br/>post lengths, panel residual
    G->>B: conflict / assumption / failure nodes
    G-->>A: GenerationResult(run, strategy, graph, warnings)
    deactivate G

    A->>S: persist GenerationRun (id = content hash of inputs)
    A-->>W: run id + warnings
    W->>A: GET /runs/{id}/structure
```

**`generate()` is pure and deterministic** (ADR-0004). Same inputs, same fence,
same run id. That single property is what makes the run-id digest, immutable
quotes, the portfolio impact preview and 155 golden scenarios possible.

**A model boundary is a structural boundary.** A `fence_model` interval event adds
its stations to the fixed set, so no bay ever straddles the place where the fence
visibly changes — spans sample their properties at the mid-point, which would
otherwise hand one model's panel to a bay that is half another's.

**A hard tie fails.** Two hard constraints that cannot both hold raise
`GenerationFailure` with `code + params`, rendered in the reader's language. The
system represents unknowns rather than fabricating certainty.

---

## 2. Read a priced BOM — and refuse a stale one

```mermaid
sequenceDiagram
    autonumber
    participant W as js/tabs.js
    participant A as api/app.py
    participant S as Store
    participant P as fulfillment/pipeline.py

    W->>A: GET /runs/{run_id}/bom
    A->>S: load run, project, catalog, inventory

    alt topology revision moved
        A-->>W: 409 topology_changed
        W->>W: "the drawing changed" — offer regenerate
    else catalog content moved for a SKU this run named
        A-->>W: 409 catalog_changed
    else still valid
        A->>P: derive_requirements → resolve_supply → fulfill
        activate P
        P->>P: resolve each line's eligibility to ONE sku + unit
        P->>P: plan cuts per divisible sku (kerf, remnants first)
        P->>P: round packages, expand kits, net inventory
        P-->>A: Bom + cut plans + allocations + projected remnants
        deactivate P
        A-->>W: BOM with warnings as code + params
    end
```

**One pipeline, four callers.** `/bom`, `/structure`, `/quote` and the impact
preview all run `fulfillment/pipeline.py`. They were four copies once, and the
copies had already diverged: `create_quote` loaded the catalog directly, so the one
endpoint freezing an immutable commercial document was the only one exempt from the
staleness check.

**`catalog_hash` is narrowed to what a run named** — chosen SKUs, every eligibility
rival, kit components transitively. Adding an unrelated product no longer 409s every
prior run; repricing one it bought still does. Safe only because **eligibility is
frozen into the run**.

---

## 3. Free text becomes structure

Foundation §9's central loop, and the one place AI touches authored reality.

```mermaid
sequenceDiagram
    autonumber
    actor U as Expert
    participant A as api/app.py
    participant AI as AnnotationInterpreter<br/>(stub or claude)
    participant P as project/intents.py

    U->>A: POST /annotations  "הגדר גובה 1.8 מ׳ לאורך הגדר"
    A->>A: store VERBATIM, immutable
    U->>A: POST /annotations/{id}/interpret
    A->>AI: interpret(annotation)
    AI-->>A: InterpretationRecord with candidate intents
    A-->>U: proposals — nothing has changed yet

    Note over U,P: intents influence NOTHING until confirmed (ADR-0009)

    U->>A: POST /intents/{intent_id}/confirm
    A->>P: confirm_intent(project, annotation, intent, run)
    P->>P: materialise IntervalEvent(height_intent,<br/>source = interpretation record id)
    P-->>A: new event id
    A-->>U: first-class topology state, provenance intact
```

The stub understands the demo vocabulary in **English and Hebrew** and is
deliberately capped — it must not become a second rule engine. The Claude adapter is
opt-in and implements the same port.

---

## 4. A correction becomes knowledge

```mermaid
sequenceDiagram
    autonumber
    actor E as Expert
    participant A as api/app.py
    participant KP as KnowledgeProposer
    participant I as learning/impact.py
    participant R as Review queue

    E->>A: POST /corrections  (before, after, verbatim comment)
    A->>A: store — immutable, pegged to run + decision
    E->>A: POST /propose-knowledge
    A->>KP: propose(corrections)
    KP-->>A: KnowledgeVersion[] with status='proposed'

    Note over KP,R: a candidate is INERT — it fires nothing

    R->>A: POST /candidates/{id}/{v}/preview
    A->>I: regenerate every project and diff
    I-->>R: "this would affect N of your M projects"<br/>+ per-project deltas vs the accepted quote
    R->>A: POST /candidates/{id}/{v}/review<br/>approve · edit_approve · scope_restrict · reject
    A->>A: new immutable version — runs stamp their snapshot
```

**Impact is shown before the change, not after** (foundation §11). A project that
was *already* failing before the change is reported as `baseline_failed` and is not
counted as affected — the change did not break it.

---

## 5. A what-if that never generates

The Assembly tab prices an imagined panel without touching the stored run.

```mermaid
sequenceDiagram
    autonumber
    actor U as Estimator
    participant AS as js/assembly.js
    participant A as api/app.py
    participant PV as preview_panel()

    U->>AS: type a height / pick another product
    AS->>AS: debounce 250 ms
    AS->>A: POST /runs/{id}/bays/{element_id}/panel-preview
    A->>A: read from the RUN: preset, cut basis, rail and screw<br/>counts, the STAMPED model version, option answers
    A->>PV: preview_panel(model, bay + only what the user imagined)
    PV-->>A: ResolvedPanel + elevation + priced parts
    A-->>AS: preview
    AS->>AS: show BOTH figures — this run's BOM total<br/>AND this panel's preview total
```

**The route reads everything the run decided off the run.** An earlier version priced
a stored bay through the model-scoped preview route, which hardcodes `least_cost`,
hardcodes `length_basis="width"` and reads the live catalog — it marked the wrong
product as chosen and priced a bay at 51% of what it cost, under a tag that said *"as
generated"*.

**Two numbers with the same shape and different meanings are named, always.** The
cost strip never silently switches one figure's meaning underneath the reader, and
generation stays behind its own button — the smoke suite counts the project's runs
across a dimension change to prove it.
