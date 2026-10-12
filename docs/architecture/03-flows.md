# 03 — Flows

The sequences worth knowing, grouped by the plane that owns them (see
[`00-overview.md`](00-overview.md#three-planes)). Where a flow crosses into another
plane the crossing is marked **⇢ plane** at the step where it happens.

| Plane | Flows |
|---|---|
| **Engine** | [E1 Generate](#e1-generate-a-strategy) · [E2 Read a priced run](#e2-read-a-priced-run--and-refuse-a-stale-one) · [E3 A what-if that never generates](#e3-a-what-if-that-never-generates) · [E4 Published knowledge arrives](#e4-published-knowledge-arrives) |
| **People & work** | [P1 A request is identified](#p1-a-request-is-identified) · [P2 A job goes from the sale to a plan](#p2-a-job-goes-from-the-sale-to-a-plan) · [P3 An admin grants a capacity](#p3-an-admin-grants-a-capacity) |
| **AI & learning** | [A1 Free text becomes structure](#a1-free-text-becomes-structure) · [A2 A correction becomes knowledge](#a2-a-correction-becomes-knowledge) · [A3 Advice on an open question](#a3-advice-on-an-open-question) |

Every `/api` request first passes the identity gate (P1); the diagrams below start
after it.

---

## Engine

### E1. Generate a strategy

The only place a fence is decided. Explicit, never automatic.

```mermaid
sequenceDiagram
    autonumber
    actor U as Office (any active account)
    participant W as js/state.js
    participant A as api/app.py
    participant S as Store
    participant G as strategy.generate()
    participant C as StrategyCritic (stub)

    U->>W: press Generate (editor.js wires the button)
    W->>A: POST /projects/{id}/generate
    A->>S: project · catalog · knowledge_base() · fence models · parts
    A->>G: generate(topology, kb, catalog, overrides, policy,<br/>project_id, models, default_model, parts, site, choices)

    activate G
    G->>G: bind_scope · demand products · node posts
    G->>G: per run: fixed stations (corners, bases, gates,<br/>model boundaries, pins) · closed-form layout ·<br/>model per segment · resolve_panel per bay · panel safety
    G->>G: gate spans · post lengths · unfilled posts ·<br/>missing site conditions · conflicts · orphaned overrides
    G->>G: graph · run identity (digest) · probe regenerations<br/>to cost each choice set
    G-->>A: GenerationResult(run, strategy, graph,<br/>orphaned_overrides, choice_sets)
    deactivate G

    A->>S: save_run — ON CONFLICT(id) DO NOTHING
    A->>C: critique(result)   ⇢ AI & learning
    C-->>A: CritiqueNote[] (never stored)
    A-->>W: {result, critique}
    W->>W: emit result-changed → /structure, /bom, /advice are fetched
```

**`generate()` is pure and deterministic** (ADR-0004). Same inputs, same fence,
same run id — which is what makes the run-id digest, immutable quotes, the portfolio
impact preview and the golden scenarios possible. Generation checks no capacity and
no job state: the office road's Generate is a plain engine call.

**A model boundary is a structural boundary.** A `fence_model` interval event adds
its stations to the fixed set, so no bay ever straddles the place where the fence
visibly changes — spans sample their properties at the mid-point, which would
otherwise hand one model's panel to a bay that is half another's.

**Choice sets are costed, not chosen.** Where the data leaves two admissible
layouts, the generator records a `ChoiceSet` and prices each point by regenerating
with `offer_alternatives=False`. A person answers it (`PUT /projects/{id}/choices`)
and the answer becomes an input to the next run; the agent may only rank it (A3).

**A failure is refused, not stored.** `GenerationFailure` is a 422: a coded one
(`fence_model_invalid`, `post_spec_conflict`, a hard panel limit, …) carries
`code + params` and renders in the reader's language; a hard tie between authored
rules currently carries only the constraint refs and answers an English string.
Nothing is written to `generation_runs`.

---

### E2. Read a priced run — and refuse a stale one

Pricing is re-run on every read, against today's catalog and stock, by one pipeline.

```mermaid
sequenceDiagram
    autonumber
    participant W as js/tabs.js · structure-data.js
    participant A as api/app.py
    participant S as Store
    participant P as fulfillment.pipeline<br/>price_strategy()

    W->>A: GET /runs/{id}/bom   (or /structure)
    A->>S: run · project (live objective preset) · catalog · inventory

    opt /structure and section decisions (advice: the topology check only)
        alt drawing moved since the run
            A-->>W: 409 topology_changed
        else site conditions moved
            A-->>W: 409 site_conditions_changed
        end
    end
    alt catalog schema or a SKU this run named moved
        A-->>W: 409 catalog_schema_changed · catalog_changed
    else still valid
        A->>P: derive_demand → resolve_supply → fulfil
        activate P
        P->>P: DemandLines (no sku) → one sku + unit per line
        P->>P: cut plans per divisible sku (kerf, remnants first)
        P->>P: round packages, net inventory, price
        P-->>A: PricedRun(requirements, unresolved, warnings, decisions, bom)
        deactivate P
        A->>S: save SupplyRun (id = sup_ + digest, idempotent)
        A-->>W: BOM + grouped + quoted warnings (code + params)
    end
```

**One pipeline, three call sites.** `api._priced` serves `/bom`, `/structure`,
`/quote`, `/explain`, section decisions, `/readiness` and `/flags`;
`learning/impact.py` uses it for the three impact previews; and
`fencemodel/preview.py` for the three panel previews. The phases are declared
(`fulfillment/phases.py: PIPELINE`) and their order is checked at import. They were
four hand-written copies once, and the copies had already diverged: `create_quote`
loaded the catalog directly, so the one endpoint freezing an immutable commercial
document was the only one exempt from the staleness check.

**The BOM refuses a moved catalog and nothing else.** It describes the run, not the
drawing, so it stays readable after the drawing is edited. The views that lay the run
over the drawing refuse instead, because "the decisions for section A" stops being a
true sentence once A may have moved.

**`catalog_hash` is narrowed to what a run named** — chosen SKUs, every eligibility
rival, kit components transitively. Adding an unrelated product no longer 409s every
prior run; repricing one it bought still does. Safe only because **eligibility is
frozen into the run**.

**A quote is a supply run somebody stood behind.** `POST /runs/{id}/quote` refuses a
moved site or catalog and any unresolved supply (400 `unresolved_supply`), then
freezes requirements, BOM and the three hashes. Accepting it supersedes the
project's previously accepted quote. Neither act moves the job's status — see
[`people-and-work.md`](people-and-work.md).

---

### E3. A what-if that never generates

The Assembly tab prices an imagined panel without touching the stored run.

```mermaid
sequenceDiagram
    autonumber
    actor U as Office
    participant AS as js/assembly.js
    participant A as api/app.py
    participant PV as preview_panel()

    U->>AS: type a height / pick another product
    AS->>AS: debounce 250 ms
    AS->>A: POST /runs/{id}/bays/{element_id}/panel-preview
    A->>A: from the RUN: cut basis, rail and screw counts,<br/>the STAMPED model version, option answers, part snapshot
    A->>A: catalog checked against the run's stamp (409 if moved) ·<br/>objective preset from the project's live policy
    A->>PV: preview_panel(model, bay + only what the user imagined)
    PV-->>A: ResolvedPanel + elevation + priced parts
    A-->>AS: preview
    AS->>AS: show BOTH figures — this run's BOM total<br/>AND this panel's preview total
```

**The route reads what the run decided off the run.** An earlier version priced a
stored bay through the model-scoped preview route, which hardcodes `least_cost`,
hardcodes `length_basis="width"` and reads the live catalog — it marked the wrong
product as chosen and priced a bay at 51% of what it cost, under a tag that said *"as
generated"*. The preset is the one deliberate live read: it is a supply choice, not
part of the design's identity, and it is the same preset `/bom` prices under. The
route's docstring still says "the run's preset"; the code is the authority.

**Two numbers with the same shape and different meanings are named, always.** The
cost strip never silently switches one figure's meaning underneath the reader, and
generation stays behind its own button.

---

### E4. Published knowledge arrives

The boundary door with fence-rag (contract v1.3). Loading is explicit and never
automatic.

```mermaid
sequenceDiagram
    autonumber
    participant K as fence-rag (another team)
    participant A as api/app.py
    participant L as knowledge/snapshot.py
    participant S as Store

    K->>A: POST /knowledge/snapshot (a Snapshot document)
    A->>L: load(body)
    alt contract major/minor, id hash, or shape refused
        L-->>A: 400 contract_major_unsupported · contract_minor_predates_typed_date ·<br/>snapshot_id_mismatch · snapshot_malformed
    else accepted
        A->>S: save_snapshot — knowledge_snapshots + active_snapshot
        A->>L: ingest(snapshot) → counts
        A-->>K: versions · admitted · gaps · defects · part specs
    end
    Note over S: every later knowledge_base() re-ingests the active snapshot,<br/>so verdicts are derived on read, never stored
```

Published rows become `fact` versions beside the authored ones and resolve in
`generate()` like any other knowledge. Nothing flows back: the contract's "report
gaps" obligation has no implementation, and `POST /source-refs:batch` answers from a
vendored fixture rather than a live Discovery API. Details:
[`knowledge-system.md`](knowledge-system.md).

---

## People & work

### P1. A request is identified

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant G as api/auth.py gate
    participant P as IdentityProvider<br/>(iap | dev)
    participant S as Store (users, audit_log)
    participant R as the route

    B->>G: any /api request
    alt exempt: /api/health · /api/session · /api/dev/identity
        G->>R: pass
    else
        G->>P: principal(headers, cookies)
        alt no verified identity
            G-->>B: 401 no_identity
        else Principal(email, subject)
            G->>S: user_by_email · first-admin bootstrap · bind subject
            alt no row · deactivated · subject mismatch
                G-->>B: 403 no_capacity · account_deactivated · subject_mismatch
            else
                G->>R: request.state.user = User
            end
        end
    end
```

The browser asks `GET /api/session` once, last, after every module is listening; the
answer sets the view and emits `signed-in` or `signed-out`. A sales account lands on
its jobs, an office or admin account on the queue. The rules — capacity versus view,
bootstrap, last admin, the actor is the caller — are in
[`people-and-work.md`](people-and-work.md).

---

### P2. A job goes from the sale to a plan

Every move is a command through one door, `POST /projects/{id}/actions`; field edits
(customer, address, the drawing) are ordinary writes.

```mermaid
sequenceDiagram
    autonumber
    actor SA as Salesperson
    actor OF as Office
    participant A as POST /actions<br/>commands.perform
    participant J as Project (status)
    participant E as Engine routes

    SA->>E: create job · draw · state facts · notes (ordinary writes)
    SA->>A: submit_job
    A->>J: drafting → waiting
    OF->>A: claim_job (the queue's Take)
    A->>J: waiting → planning · assignee = caller
    OF->>A: acknowledge_sale
    A->>J: Acknowledgement(sale_read, hash of her notes)
    alt something is missing
        OF->>A: return_to_sales {reason}
        A->>J: → returned · the reason becomes a verbatim note
        SA->>A: submit_job (answers sent)
        A->>J: returned → waiting
    end
    OF->>E: POST /generate   ⇢ Engine
    OF->>A: acknowledge_warnings {run_id}
    OF->>A: commit_plan {run_id}
    A->>E: precondition: run on this job · drawing, site, catalog unmoved   ⇢ Engine
    A->>J: planning → planned · committed_run_id
    OF->>E: POST /runs/{id}/quote   ⇢ Engine (status does not move)
```

`perform` asks capacity → performable → state → payload → precondition, in that
order, and logs `command:<kind>` only on success. `quoted` and `delivered` are
declared states that no command reaches. The state machine and the full command
table are in [`people-and-work.md`](people-and-work.md).

---

### P3. An admin grants a capacity

```mermaid
sequenceDiagram
    autonumber
    actor AD as Admin
    participant A as api/app.py
    participant S as Store

    AD->>A: POST /users {email, name, capacity}
    A->>A: require_admin (403 capacity_insufficient)
    A->>S: create_user_guarded (409 user_exists · reserved_address)
    S->>S: audit save_user + grant_capacity
    Note over AD,S: the person's first request binds Google's subject to the row (audit identity_bound)
    AD->>A: PATCH /users/{id} {capacity | active}
    A->>S: amend_user_guarded — would this strand the admins? (409 last_admin)
```

---

## AI & learning

### A1. Free text becomes structure

Foundation §9's central loop, and the one place AI touches authored reality — always
through a person.

```mermaid
sequenceDiagram
    autonumber
    actor U as Any active account
    participant A as api/app.py
    participant AI as AnnotationInterpreter<br/>(stub, or claude if FENCEAI_AI=claude)
    participant P as project/intents.py

    U->>A: POST /projects/{id}/annotations {target_ref, text}  "הגדר גובה 1.8 מ׳ לאורך הגדר"
    A->>A: store VERBATIM, author = the session
    U->>A: POST /annotations/{aid}/interpret
    A->>AI: interpret(annotation)
    AI-->>A: InterpretationRecord with proposed CandidateIntents
    A->>A: append to annotation.interpretations · save project
    A-->>U: proposals — the drawing has not changed

    Note over U,P: an intent influences NOTHING until confirmed (ADR-0009)

    U->>A: POST /intents/{intent_id}/confirm {annotation_id, run_id}
    A->>P: confirm_intent(...)   ⇢ Engine
    alt height_intent · top_line
        P->>P: IntervalEvent over the whole run,<br/>payload.source = record id · topology revision + 1
    else post_request
        P->>P: Override(PinPost) noted "from interpretation <id>"
    end
    P-->>A: materialized_id
```

`run_id` here is a TOPOLOGY run id, not a generation run. `material_preference` and
`other` cannot be confirmed (400), and nothing writes an intent's `rejected` status.
The stub understands the demo vocabulary in **English and Hebrew** and is
deliberately capped — it must not become a second rule engine.

---

### A2. A correction becomes knowledge

```mermaid
sequenceDiagram
    autonumber
    actor E as Any active account
    participant A as api/app.py
    participant KP as KnowledgeProposer (stub)
    participant I as learning/impact.py
    participant R as learning/review.py

    E->>A: POST /projects/{id}/corrections<br/>{generation_run_id, decision_ref | element_ref, comment}
    A->>A: store — append-only, author = the session
    E->>A: POST /projects/{id}/propose-knowledge
    A->>KP: propose(all the project's corrections)
    KP-->>A: KnowledgeVersion[] type candidate · status proposed
    A->>A: insert (skipping ids that already exist) · actor proposer:stub

    Note over KP,R: a candidate is INERT — not active, and the evaluator skips its type

    E->>A: POST /candidates/{id}/{v}/preview   (optional)
    A->>I: regenerate + re-price every project, before and after   ⇢ Engine
    I-->>E: "this would affect N of your M projects"<br/>+ per-project deltas vs the accepted quote
    E->>A: POST /candidates/{id}/{v}/review {approve | scope_restrict | reject}
    A->>R: apply_review(candidate, reviewer = the session)
    R-->>A: v+1 active heuristic (candidate retired) — or candidate rejected
    A->>A: apply_review_outcome — one transaction   ⇢ Engine knowledge
```

**Impact can be shown before the change** (foundation §11), but the review does not
require it — preview and review are separate requests. A project that was *already*
failing is reported as `baseline_failed` and not counted as affected. The preview
regenerates without the project's answered choice sets.

---

### A3. Advice on an open question

```mermaid
sequenceDiagram
    autonumber
    participant W as js/agent-advice.js
    participant A as api/app.py
    participant D as agent.run_task
    participant T as TaskRunner (StubAgent)

    W->>A: GET /runs/{id}/advice   (on project-loaded / result-changed)
    alt drawing moved since the run
        A-->>W: 409 topology_changed
    else
        A->>D: run_task(RANK_CHOICE_SET, AgentView(project, result))
        D->>T: run(task, view)   — view shows only unanswered choice sets
        T-->>D: proposals + claims
        D->>D: 1 may_emit · 2 every claim grounded in a handed-over ref ·<br/>3 the point is still offered · cap at max_proposals
        D-->>A: TaskResult
        A-->>W: shown — never stored, never applied
    end
```

The one action kind the agent may propose, `select_choice_point`, is registered in
the desk's command table with no capacities, so `POST /actions` refuses it to
everyone ⇢ People & work. Answering the question is still a person's
`PUT /projects/{id}/choices`.
