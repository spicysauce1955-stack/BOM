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
        ST["store/db.py — 13 tables, documents as JSON"]
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

## Two kinds of gate, and the invariant between them

A gate can be authored two ways, and they are different physical claims.

* **In a run** — `GatePayload`, a point event at a station. The fence is
  interrupted: part of that run's layout is consumed by the opening. This is the
  original kind, it is what every stored project and every golden scenario uses,
  and it is unchanged.
* **Beside the runs** — `GateSpan` in `Topology.gates`, joining two nodes and
  lying on no run at all:

  ```
  o------------o  [====gate====]  o------------o
      run rA       the GateSpan       run rB
                   n2          n3
  ```

  *"a run and a gate are different things. the gate is placed next to a run, not
  on it"* — so it combines two runs drawn unconnected and **changes the layout of
  neither**.

Three properties hold this together.

* **A `GateSpan` stores no width.** The opening is the distance between its two
  nodes (`topology.station.gate_opening_mm`), exactly as a run's length is the
  distance between its own. A stored width would disagree with the geometry the
  moment somebody drags a node, and from then on the drawing and the price would
  be about different gates. The four swing facts are validated by the same
  function `GatePayload` uses (`check_swing_coherence`) — one implementation, or
  one of the two ways of drawing a gate quietly starts accepting the nonsense the
  other refuses.
* **One `Gate` element, two origins.** `Gate.run_ref is None` **is** the
  standalone gate: it has no station, its ends are `start_node_id`/`end_node_id`,
  and `width_mm` — populated for both kinds — is the field every consumer reads.
  A reader that subtracted the stations itself would get 0 for every standalone
  gate. In the read models a `None` means *belongs to no section*: `bom_groups`
  leaves it out of the section partition and reports its kit under `unassigned`
  (a group kind of its own is the follow-up and needs a `bom.group_*` locale
  entry in both bundles), `section_decisions` gives it an empty section set, and
  `structure.py` lays it out in `StructureReport.gates` at the top level, between
  the tags of the two posts it hangs from.
* **`_generate_gate_spans` runs after every run is generated, and that placement
  is the design.** Nothing about a run can observe a gate span — every post, bay,
  warning and decision node a run produces is already built and its ordinals are
  already fixed. `tests/strategy/test_gate_span_generation.py` asserts this by
  generating the same topology twice, with and without its gate spans: remove the
  gate's own decision nodes from the first and the two graphs, posts, bays,
  warnings and BOM lines are identical. What the pass *does* add is its own — the
  gate, its kit (through the same `_resolve_gate_kit` / `_check_gate_kit_width`
  path an in-run gate uses) and a post at each of its two nodes, because a gate
  with a post on one side only is unbuildable. A node a run already stands at
  keeps the post the runs decided: the gate-adjacency reinforcement rule in
  `_generate_node_posts` is deliberately **not** extended to a gate span's shared
  nodes, because it would change that post's sku and therefore the BOM of a fence
  the gate was supposed to leave alone.

Both gaps this section used to name are now closed, and both by sharing rather
than by copying.

**`gate_on_slope` reaches a standalone gate.** The limit comes from
`_resolve_gate_max_slope` and the verdict from `_check_gate_slope` — one
resolution and one emission, called by both kinds of gate, so the graph cites the
same winning version and the warning carries the same `code + params` whichever
way the gate was drawn. Only the MEASUREMENT differs, because only the caller
knows where its ground is: an in-run gate reads the run's ground profile at the
opening's two stations, a gate span reads the elevations of its own two nodes.
The span's context is the run path's minus the `run` facts it genuinely has none
of — omitted, so a rule conditioned on one is *not applicable* rather than
false. An unstated elevation is not a slope: `Node.z_mm` defaults to 0 and the
run path reads that same defaulted field through `ground_samples`, so a gate
whose nodes were never given a height warns about nothing, exactly like the run
beside it.

**A force override reaches a gate's own post.** The post `_generate_gate_spans`
emits at a node no run stands at is bought and drawn, and nothing could address
it: the pass never consulted overrides, so a forced sku did nothing and was then
reported back as `orphaned_override`. It now consults `_matched_force_overrides`
— the run path's own matcher — for the posts it CREATES, and records what it
honours in the same `applied` set. No new addressing scheme was needed: such a
post's `run_ref` is `node:<id>` at station 0, which is what the matcher already
compares. The consultation sits after the *"a run already stands here"*
`continue`, so an override cannot become a way around the invariance above —
`tests/strategy/test_gate_span_generation.py` asserts that the same directive
aimed at a shared node leaves that post byte-identical and is reported orphaned.
Suppression stays out: a gate with a post on one side only is unbuildable.

---

## The API surface

74 routes. Grouped by what they are for rather than by path:

| Group | Routes | Notes |
|---|---|---|
| Projects & topology | `GET/POST /projects`, `GET /projects/{id}`, `PUT /projects/{id}/topology`, `PUT /projects/{id}/site`, `PUT /projects/{id}/job`, `PUT /projects/{id}/context`, `PUT /projects/{id}/stated` | The two revisioned PUTs bump their own `revision` server-side — a client that forgot to would make a stale document look current. `/job` is deliberately NOT revisioned: who bought the fence, where, who sold it and when changes no quantity and invalidates no derived view. It is a separate route from creation because a salesperson enters this after the visit from paper — they start with a customer name, draw for twenty minutes, and only then find the address on the sketch, which must not cost them the drawing. `GET /projects` carries `label` beside `name` for the same person: the picker said *"project 7"*. `/context` carries the house, the street and the boundary — everything on the property that is NOT the fence. It is on the PROJECT and never in `Topology`, because a landmark changes no quantity: in the topology it would bump the revision and 409 the structure sheet because somebody nudged a driveway. `/stated` is unrevisioned for `/job`'s reason and carries what the salesperson says this job does NOT have — `no_gates`, `no_promises`. Named facts rather than step keys, so a screen's structure stays out of the project record and `handover_gaps` can contradict a claim the drawing disagrees with without knowing that a road or a step exists. The claim is stored as GIVEN and never validated here: refusing it would mean a salesperson could not record what they believe, which is the one thing the field exists to capture |
| Generation | `POST /projects/{id}/generate`, `GET /projects/{id}/runs`, `GET /runs/{id}` | The only write that decides a fence. WHICH run is the one people build from is `commit_plan` (`Project.committed_run_id`), performed through `/actions`. Its guards are STRICTER than any working view's and stricter than `create_quote`'s — the quote checks the site, the catalog and unresolved supply but not the topology revision — because a working view that renders something stale is re-read while a committed plan is built from. They are asked by `commands.perform` as a `precondition`, AFTER capacity and state: answered earlier, the door would tell a salesperson which run ids exist and how far a job had got. `revise_plan` takes it back (`planned`/`quoted` → `planning`), and `reopen_job` / `return_to_sales` clear it, so a job never comes back naming a plan from a previous life |
| Explanation | `GET /runs/{id}/explain/{element_id}`, `GET /runs/{id}/sections/{section_id}/decisions`, `GET /runs/{id}/impact/{object_id}` | Takes `lang` **and** `units`. The section view 409s on a moved topology and the element view does not — see below |
| Read models | `GET /runs/{id}/structure`, `GET /runs/{id}/bom`, `GET /projects/{id}/handover` | 409 on stale topology or catalog. `/bom` also carries `grouped` — the same demand by section, panel and decision, and it does NOT 409 on topology. Both are read models that WRITE: `/bom` returns the `supply` run it stored and `/structure` stamps its `supply_id`, through one construction so the sheet and the BOM can never name different yards. Idempotent by digest (ADR-0011). `/handover` is the salesperson MVP's read model and the odd one out: it is derived from the PROJECT rather than from a run, deliberately, because by the time a `Strategy` exists the silent defaults (1800 mm height, `soil` base) have been applied and look decided — catching them before that is its whole point. Both run-scoped ones also carry `quoted_warnings` — every warning the fence models QUOTE from their documents, each placed where §3.3.5 says it renders (`report/annexe.py`): the setting-out sheet draws the annexe, `/bom` draws the product notices on the line group, and each carries the buckets it does not draw so nothing is lost at the edge of a surface |
| Run advice | `GET /runs/{id}/advice` | The one `fenceai/api/` door onto `fenceai.agent` — no other layer imports it. Runs `agent.tasks.RANK_CHOICE_SET` against an `AgentView` of the run through `agent.run.run_task`, and returns the checked `TaskResult` as-is: nothing is stored, nothing is generated. 409 `topology_changed` on the same stale-topology guard as `/structure`, since advice about a layout laid over an edited drawing is advice about a fence nobody drew (ADR-0009: no AI inside `generate()` — this reads a generation the user already asked for) |
| Money | `POST /runs/{id}/quote`, `GET/POST /quotes/{id}[/accept]`, `GET /projects/{id}/quotes` | Immutable snapshots with a lifecycle |
| Knowledge | `GET/POST /knowledge`, `POST /knowledge/{id}/{v}/retire`, `POST /knowledge/preview-impact` | Versioned; never edited in place |
| Published knowledge | `GET/POST /knowledge/snapshot`, `GET /knowledge/parts` | The boundary door (contract §1.2). Loading is explicit and never automatic — a knowledge base that swapped itself under a project would change numbers with no action anyone took. The POST's interesting path is the REFUSAL: an unknown contract major, a payload predating §1.1's typed `Date`, or a document whose members do not hash to the id it declares, each a typed 400 with one sentence. `/knowledge/parts` is item 7's surface: every published `SpecField` value with its §1.4 verdict and the `SourceDoc`s its citations resolve to — per value, not per part, because admissibility is decided per value |
| Learning | `GET/POST /projects/{id}/corrections`, `POST /projects/{id}/propose-knowledge`, `GET /candidates`, `POST /candidates/{id}/{v}/review` | Candidates are inert. The GET is filterable by `decision_ref`/`element_ref`/`generation_run_id` |
| Parts | `GET /parts`, `GET /part-types` | The shared library a model's slot names; read-only, versioned like knowledge |
| Vocabularies | `GET /vocabularies` | The length rules, fixing bases and objective presets the schema accepts, so the editor offers exactly them rather than keeping a copy. Names only — the words live in the locale bundles the browser already loads. The seam for the handler registries of `specs/2026-08-25-engine-architecture.md` §4: when a fixing basis becomes a registration rather than a `Literal` arm, only `fencemodel/vocabulary.py` changes |
| Fence models | `GET/POST /fence-models`, `PUT /fence-models/{id}/draft`, `POST .../publish`, `POST .../status`, `DELETE .../{v}`, `POST /fence-models/preview`, `POST /fence-models/{id}/preview-impact` | Publish is the gate |
| Panel preview | `POST /runs/{id}/bays/{element_id}/panel-preview` | Reads the run, not the live catalog |
| Annotations | `POST /projects/{id}/annotations[/{id}/interpret]`, `POST /projects/{id}/intents/{id}/confirm` | Verbatim in, proposals out |
| Overrides | `POST /projects/{id}/overrides`, `DELETE .../{override_id}` | Anchored to `(run, station, kind)` |
| Choices | `PUT /projects/{id}/choices`, `DELETE .../choices/{choice_set}?scope=...` | A row of its own, not part of Overrides, because a choice is **not** an override: nothing was wrong, the data simply left two admissible answers (specs/2026-09-03-design-choices-and-placement-design.md §3). So a selection anchors to a **scope** — `gap:run1:0`, `model:M-VINYL` — instead of a station, and survives a redraw that would kill an override; and it is an *input* to `generate()`, not a patch on its output. PUT upserts on `(choice_set, scope)`: choosing again replaces, or a project would hold two current answers to one question. `asked: false` on the same route is a **pin** (*"we always dig 610, stop asking"*) — the same record with one flag, because pinning and choosing differ in what happens next, not in what was decided. The DELETE takes the scope as a **query** parameter because a real scope is `model:mfr/certainteed/rail` and a path segment cannot carry the slashes |
| Catalog & inventory | `GET /catalog`, `PUT /catalog/products`, `GET/PUT /projects/{id}/inventory` | |
| Evidence | `POST /source-refs:batch` | Fixture-backed (`knowledge/discovery_stub.py`): resolves a `SourceRef.id` (core/gaps.py) against a vendored copy of fence-rag's design fixture, not a live Discovery API — see specs/2026-08-23-frontend-design.md §3. Batched from the first commit so a queue resolving many citations issues one call, not N |
| Identity | `POST /api/session`, `DELETE /api/session`, `GET /api/me`, `GET /api/users` | Accounts, and the first thing in this app that is a PERMISSION rather than a preference. A `capacity` (`sales \| backoffice \| admin`) is what an account may DO and is read on the server; a `view` is what is SHOWN and is a browser preference — `identity/model.py` carries the paragraph keeping the two apart. `/me` answers which view to open on, which is the safe way to flip the default the salesperson MVP left at `all`: nobody edits a global setting, Dana lands on her own screen because of who she is, and the smoke signs in as an `admin` and keeps seeing today's app. Sign-out is server-side because the token IS the row — a self-describing token would stay valid in a pocket and make both "sign me out" and "deactivate this account" promises we could not keep. **Nothing is gated yet**: a request with no session is the ordinary case and still writes `system`, which is what keeps 3000-odd tests and the whole browser smoke working. What DID change is that a session now outranks `?author=` at eleven write sites — an actor a client can name was never an audit trail |
| Commands | `POST /projects/{id}/actions` | **One door.** Every change that MOVES a job — whose desk it is on, or what it commits to — is a named, typed, permission-checked row in `fenceai/commands/` rather than a route of its own (backoffice design §10). Field edits are deliberately NOT commands: typing an address is not one, and forcing it to be turns the design into ceremony. The row answers three questions before anything happens — may this capacity perform this kind · is the job in a status that allows it · does the payload type-check — and in that ORDER, so a refusal never leaks whether the job was in a state that would have allowed it. `command_wrong_state` is a 409 because it is a conflict with the job as it stands (somebody moved the folder while the screen was open); everything else is a 403 or a 404. This is the **first and only gated route** in the app: it 401s an anonymous caller, because a command names who did it and `system` is not somebody who may take a job. Retrofitting capacity onto the other sixty-eight in the slice that introduces the mechanism is how a feature ran away here before. The table is shared with the agent, which keeps the SUBSET it may propose (`agent/registry.py::KINDS`) — a human pressing a button and an agent proposing one reach the same row, or the second implementation drifts and the drift is where an untraceable change comes from |
| The office road | `GET /api/projects/{id}/readiness` (resolves supply for step 5, and reports `supply_unknown` rather than refusing when the run cannot be priced) | What the OFFICE still has to do — the run-scoped sibling of `/handover`, and deliberately not folded into it. `/handover` is a pure function of the PROJECT and must stay one: that is what lets it catch the silent 1800 mm height before a strategy exists to make it look decided. These questions are about a run, so folding them in would drag a run into a function whose whole value is not needing one. The road reads both and GROUPS them; it never recounts, because three surfaces answering "what is left" and disagreeing is a defect this repo has already paid for. It reads the STORED run and loads no knowledge base — `readiness()` takes none, so there is nothing in scope to re-evaluate: re-running the evaluator would re-resolve to "current" (contract 3.2.1) and recompute a quantity in a read model (foundation §15). Nothing it returns is `blocking`, because contract 3.2.4 forbids failing a run over a gap and a step that stopped somebody generating would be the first thing worked around |
| The office job screen | `GET /api/projects/{id}/sections`, `GET /api/projects/{id}/flags` | What each stretch of fence IS — length, what it stands on, the ground along it, whether anybody stated a height — as a pure function of the TOPOLOGY. The office opens a job it did not draw, and half of what it needs to understand exists the moment the salesperson stops drawing and long before `generate()` runs; `/structure` cannot answer any of it. It is the only per-stretch view here that **cannot go stale**: `/structure` and `/runs/{id}/sections/{id}/decisions` refuse with 409 `topology_changed` because they describe a stored run generated from a drawing that has since moved, while this describes the drawing — a moved drawing is a new answer, not a refusal, and a guard would lie about what the reader is looking at. A job with nothing drawn answers an empty list rather than a 404, because a job nobody has drawn is a real state the screen renders. It reports the SILENT DEFAULTS rather than blanking them: a run with no base event stands on `soil` and this says `soil`, because a blank reads as "nobody has looked" — the failure `/handover` exists to prevent, one surface further on. It carries no STEPS, and that omission is a decision: both step functions in `topology/station.py` take a `min_step_mm` whose value is knowledge rather than code (K-STEP-POST), so a read model picking one would hard-code a rule the knowledge base owns. The shape is a section fact; the judgement that a step is too big arrives after generation as `excessive_step` · `/flags` places what three other models already FOUND — the handover sheet, the office's readiness list, and the stored run's own warnings — so a mark can be drawn at the thing each one is about. It finds nothing itself. Until a finding can be drawn it is a line somebody scrolls past, which is how a review surface dies: the industry's cautionary tale is a dialog of a thousand unlinked warnings. Nothing is ever dropped — a scope this cannot place (`model:mfr/certainteed/rail` is a real one) lands on the job rather than vanishing, because a finding must not disappear over a formatting change nobody noticed. A `DocumentWarning` cannot reach it: `job_flags` takes no parameter one could arrive through, which makes contract §3.3.5 a signature rather than a filter somebody can delete. Severity comes from the SOURCE, never from a code table here — the rule that emitted it is the one with the reasoning behind it. Like `/sections` it never 409s: this is the screen that TELLS somebody the drawing moved (`plan_stale` is one of the items it carries), so refusing would hide the answer behind the problem it reports. A `run_id` naming another job's run is 422 `run_not_on_this_job`, the command door's refusal — not that the run does not exist, but that it is not this job's |
| A salesperson's jobs | `GET /api/my-jobs` | Her home screen: the jobs HER account created (`Project.created_by`, written by `POST /projects` from the session and never from the body), each with a sales word for where it is — `draft · pending · needs_info · accepted · rejected`, folded from the eight job states by `lifecycle.sales_status` — and what the office has said about it: a count of notes written through another account, and the latest one verbatim. Pure over loaded projects (`queue.my_jobs`) and unpaged, because its per-row cost is a pass over one job's notes, not a handover sheet. A 401 without a session rather than an empty list, which would read as "you have no jobs". `POST /projects/{id}/annotations` now stamps `created_at` and lets the session outrank `author`, which is what lets this list tell the office's notes from hers |
| The queue | `GET /api/queue` | What should I work on next, or — in the finished bucket — what did we do. A SECOND route rather than a rebuild of `GET /api/projects`, which stays the picker's bare list of three fields: they answer different questions and want different rows, and folding them together meant changing the picker's envelope from a list to an object under five existing callers. Paged from the first commit, because the open-question count is DERIVED per row — free for twenty-five, unaffordable for an unbounded list, which is what would make "read models are derived, never stored" a rule nobody could keep. `assignee=me` is resolved HERE from the session: the pure half REFUSES the literal string, because matched as an id it returns an empty page reading as "you have nothing to do". A bad cursor is a 400 rather than a silent restart (a paging loop would otherwise run for ever) and an over-large `limit` is a 422 rather than a clamp |
| Ops | `GET /api/health`, `GET /api/audit` | |

Two routes exist that look redundant and are not: `POST /fence-models/preview` takes
an **unsaved** document in its body, while `POST /fence-models/{id}/{v}/preview`
prices a stored one. The first exists because an editor that must save to preview
leaves half-typed model ids in the library forever.

**One asymmetry that is deliberate.** `GET /runs/{id}/sections/{section_id}/decisions`
refuses a topology the run was not generated from (409 `topology_changed`), and
`GET /runs/{id}/explain/{element_id}` does not. A SECTION is a topology object,
so "the decisions for section A" stops being a true sentence once A may no longer
be the stretch the reader is looking at — the same refusal `/structure` makes. An
element id is self-identifying (`post@run1:1500`), so the element view answers
whatever the drawing has since become. The difference is between the two
questions, not between two standards.

**And one anchoring rule a caller must not read past.** A `Correction` may carry a
`decision_ref` (a decision-graph node id) or an `element_ref`, and both are
GENERATED ids — `core/ids.py` states that nothing may reference them across runs.
That is why every correction also carries `generation_run_id`, and why the list
route lets you filter by it: a ref means what it means only inside its own run.

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
| The SITE moved under a stored run | 409 `site_conditions_changed` |
| A product this run bought was repriced | 409 `catalog_changed` |
| Nothing in the catalog can supply a slot | warning `no_eligible_item` + `unresolved` line |
| Candidates were tried and none fits | warning `no_feasible_item` |
| A part could not be measured at all | **error** `panel_length_unresolved` |
| Two **authored** hard constraints conflict | `GenerationFailure` |
| A tie touching a **published** row, inside the hard band | **error** `knowledge_conflict` + `Gap(disputed)`, resolved to the most restrictive contender |
| No rule covers a parameter | warning + `Gap`, laid out to a named basis |
| Knowledge names no default product | **error** + `Gap` + `unresolved` line |

The distinction between a warning and an error is deliberate: a warning describes a
fence built badly, an error describes a part not bought at all. That is also why the
last row is an error rather than a note — every post in the job is unbought, and
supply already says so once per post.

A published tie is the one row where never-blocking is not the whole answer. The
tie-break that picks a winner ends on `object_id`, so letting it decide a safety
limit means the alphabet decides it: two published maxima of 1200 and 2400 built
2400 mm bays or 1200 mm bays depending on what the rows were NAMED. The run still
does not fail — §3.2.4 — but it resolves to the tightest figure every contender
could live with, at the site that knows which direction is safe for its own
parameter. The evaluator cannot know: lower is safer for `max_span_mm` and higher
is safer for `min_rail_separation_mm`.

---

## Persistence

Fifteen tables — fourteen document stores plus the append-only `audit_log`. Documents are
stored as JSON `doc` columns; the schema holds only what is queried or ordered by.

```sql
projects(id, doc)
knowledge_versions(object_id, version, status, doc)   -- PK (object_id, version)
fence_models(model_id, version, status, doc)          -- PK (model_id, version)
parts(part_id, version, status, doc)                  -- PK (part_id, version)
generation_runs(id, project_id, created_at, doc)
supply_runs(id, design_id, created_at, doc)
corrections(id, project_id, doc)
inventories(project_id, doc)
catalogs(id, doc)
quotes(id, project_id, status, created_at, doc)
knowledge_snapshots(snapshot_id, loaded_at, doc)      -- the published document
active_snapshot(only_row, snapshot_id)                -- CHECK (only_row = 1)
audit_log(seq, at, actor, action, ref)
users(id, email, doc)                                 -- email UNIQUE
sessions(token, user_id, doc)                         -- the token IS the key
```

**`email` is UNIQUE and `User.email` normalises.** It is what somebody signs in with, so
two rows answering one address is a lookup with no right answer. Normalisation lives on
the model rather than at the call sites, because the first version of this lower-cased on
write and stripped on read: an account created with a trailing space was unreachable from
the machine that created it.

**An account is deactivated, never deleted.** `audit_log.actor` names people who have left
the company and every one of those rows must keep resolving to a name. `active=False` is
the company's move, `verify_password` refuses it, and `delete_sessions_for` is the other
half — without it, deactivating is a label somebody is still signed in behind.

**The session token IS the row.** Opaque and looked up server-side rather than
self-describing and merely validated, so signing out actually signs out: the row is
deleted and the token stops working everywhere at once. A token carrying its own claims
would stay valid in a pocket until it expired, which makes both "sign me out" and
"deactivate this account" promises the server cannot keep.

**The published snapshot is stored as the DOCUMENT, and what we make of it is not.**
`knowledge_snapshots` keeps the bytes the Knowledge Platform sent, keyed by its own
`snapshot_id` — the contract promises a hash resolves to the same bytes until
`retain_until`, which is exactly what makes a document worth persisting. The
versions, the source verdicts (§1.4 `admitted_by`) and the declined bounds are
**re-derived by `knowledge_base()` on every read**, because a verdict is a function
of `(snapshot, policy, task)` and the policy is an operator's editable table:
freezing it would record an answer the next policy edit makes false. Read models are
derived, never stored, and a verdict is a read model. It also leaves one code path
for a fresh load and a reload, so a stored run cannot render different provenance
from a fresh one.

`active_snapshot` is a one-row table because "which snapshot runs resolve against"
is a fact about the installation rather than about any project. The `CHECK` is what
keeps it one row instead of a convention somebody has to remember.

**A run id answers one question; a supply run answers the other.** `generation_runs`
holds the DESIGN — what fence this is, pure and deterministic and reproducible for
ever. `supply_runs` holds what it costs to build from a particular yard, at
particular prices, under a particular objective; that is a statement about a moment
and is legitimately different tomorrow. One design has many supply runs, and a
`Quote` is a supply run somebody decided to stand behind. Both tables are append-only
and idempotent by digest — the id IS the content, so `INSERT OR IGNORE` means a
repeated read of an unchanged yard writes nothing.

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
