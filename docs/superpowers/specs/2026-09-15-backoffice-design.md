# The backoffice desk

**Status:** DESIGN. Slices 1–2 built (`4fabd4d`, `927e6bd`, `a777804`, `3707be4`);
everything from §4 onward is unbuilt.

Approved section by section with the product owner on 2026-09-14/15. Several
sections exist because a first draft was **wrong** and was corrected by them; those
corrections are marked, because the wrong version is the one a reader would
otherwise reinvent.

## Why this document exists

`2026-09-04-sales-mvp-design.md` ends: *"The office person's MVP and the super
user's are not written."* `2026-09-08-advisory-agent-design.md` §11 names the
back-office workspace as a **prerequisite** for the agent and explicitly declines
to specify it, warning against deriving it from the salesperson storyboard. Its
§12 asks *"whether the back-office workspace or the agent's first task comes
first, given that the agent needs a surface and the surface is unbuilt."*

This answers that: **the workspace first.** Agent slice 1 is built and has no home.

---

## 1. The two desks

| | Who | What they hold |
|---|---|---|
| 1 | **Salesperson** | Non-technical. Records the layout as sold — the property, the fence, heights, bases, gates, the model, and what was promised. |
| 2 | **Backoffice** | Receives it. Knows the inventory and the items; more technical; holds installation knowledge. |
| 3 | **Super user** | Alters and customises. The knowledge bench, the fence models. |

**The salesperson draws.** This was the first draft's central error, and it is worth
stating positively because the error is natural: the office person does *not*
re-draw the fence. The sales MVP's own sentence governs — *"a sold job, captured
completely enough that the office person never has to phone the salesperson"* —
and its success condition is **completeness, not accuracy**.

So the division is:

> She records **what was sold**. He decides **how it gets built**.

She owns the drawing because she stood in the garden. He owns the products, the
placement, the cutting and the price because he knows the yard.

### The surfaces already say so

`js/view.js`'s sales hide-list is, almost exactly, the backoffice person's job:
`#choices` (two right answers, neither of them a sale), `#override-list` and
`#tool-pin` (placing a post is not a thing that is sold), `#inspector` and
`#section-decisions` (the explanation, not the agreement), `#gaps`, and the
bom / inventory / structure / assembly / panel tabs.

The backoffice desk is therefore **not a new application**. It is the existing
application with a queue in front of it and a road through it, plus four things
nobody has built: identity, a job state, a committed plan, and a filtered list.

---

## 2. One record, two halves

A sale and a job are the same row. Nothing is copied, nothing is synced, and there
is never a question of which version is current.

| Half | Fields | State |
|---|---|---|
| What was sold | `job`, `context`, `stated`, `annotations`, `topology` | built |
| How it gets built | `site`, `choices`, `overrides`, `fence_model` | built |
| Whose desk, and what is real | `status`, `assignee`, `submitted_at`, `created_by`, `committed_run_id` | **new — five fields** |

Those five are **project state, not topology**. They must not bump
`topology.revision`: the `/job`, `/context` and `/stated` routes already establish
that a fact changing no quantity must not 409 every derived view.

---

## 3. Identity — the first permission

Three words that were one word until slice 1, and the separation is load-bearing:

    view      what is SHOWN            sales | backoffice | all       a browser preference
    capacity  what an account may DO   sales | backoffice | admin     read on the server
    role      what a part is FOR       rail | screw | post | …        the contract's registry

`view.js` insists twice that a view is *"a PRESENTATION preference, emphatically
not a permission"*. `identity/model.py` carries the other half. They touch in
exactly one direction: `default_view(capacity)` and `may_choose_view(capacity)`.

**Only an admin is offered the view selector**, and can "play" each role to see
what it looks like. Two consequences that are not optional:

* **The admin-only selector is not a permission.** Hiding is CSS and
  `localStorage` is editable, so a backoffice account that forces itself into the
  sales view has changed what it SEES and none of what it may DO. Every action is
  checked against `capacity` on the server regardless of what is drawn.
* **Playing a role does not change who you are.** An admin previewing the sales
  view and pressing something is still the admin in the activity log. The view
  changes what is drawn; the actor is always the signed-in account. This is a
  test, not a comment — it is the first thing that would quietly break the whole
  "who did what" premise.

### Open: is `admin` one job or two?

The specs describe a **super user** who alters and customises; "admin" usually also
means *manages accounts*. If one person does both here, three capacities is right.
If not it is four — and noticing before `admin` acquires two jobs is the whole
lesson of slice 1.

---

## 4. The lifecycle

Eight states in three lanes. **Open** is the first two lanes; **Finished** is the
third. Status is a filter chip inside a view, never a third tab.

| status | Means | Who moves it | View |
|---|---|---|---|
| `drafting` | Sales is still filling it in; backoffice cannot see it | sales | Open |
| `waiting` | On the queue, nobody has taken it | sales | Open |
| `planning` | A named backoffice account has it | backoffice | Open |
| `planned` | A run is committed as *the* plan | backoffice | Open |
| `quoted` | A price has gone out | backoffice | Open |
| `returned` | Back with sales, with a reason | backoffice | Open · flagged |
| `delivered` | The plan is priced and handed on | backoffice | Finished |
| `cancelled` | It is not happening | backoffice | Finished |

**Corrected: there is no `won` / `lost`.** The first draft had them. The fence is
sold at the customer's kitchen table *before* the job exists — the sales MVP says
the app's number *"is never what wins the deal — it is written confirmation, and
what the office starts from"* — and `Quote.status` is `draft | accepted |
superseded` with no "rejected" in it. Deals that never became jobs are lost before
a job exists, which is the salesperson's screen and not this one.

**Submitting is never gated on completeness.** `HandoverGap.blocking` withholds the
ESTIMATE, not the handover, and exactly two codes carry it. A sheet that refused an
incomplete handover *"would be worked around within a week"*. The office's answer
to an incomplete job is to see how incomplete it is, not to reject it.

**`returned` is a status, not a flag.** If only the salesperson can answer
something, the job has to leave the backoffice queue or the queue stops meaning
"work I can do". The reason travels as a verbatim note, never as a code.

### Open: what happens after pricing?

Whoever receives the priced plan — a materials order, an installation crew, a
document to the customer — is what `delivered` should actually be called, and may
deserve a state of its own. Until told, `delivered` is the name.

---

## 5. Assignee — a name, not a lock

`assignee` is the name on the folder: whose desk the job is on. Three states, and
the empty one is a real state rather than a blank cell:

* **nobody** — the whole reason a queue exists. `Take it` is offered.
* **you** — with since-when. Hand back, or pass to a named person.
* **somebody else** — visible, not forbidden. You can still open it and look;
  opening is not taking.

**Taking a job does two things in one act**: it becomes yours AND moves `waiting →
planning`, because in the office those are the same gesture.

It is deliberately **not a lock**. Two people opening one job is rare; if it stops
being rare the honest fix is optimistic concurrency on the project revision, not a
lock somebody forgets to release before going on holiday.

---

## 6. The queue

The backoffice home screen, and the one route that is rebuilt rather than extended:
`GET /api/projects` today returns `id`, `name` and `label` for **every** project
with no filter and no page.

**Columns (Open):** customer · town · sold by · submitted · waiting · status ·
with · open questions.
**Columns (Finished):** customer · town · sold by · closed · outcome · the plan ·
quote · planned by. Different columns because it answers a different question:
Open asks *what should I work on next*, Finished asks *what did we do and what did
it come to*.

**Filters:** `bucket` (open|finished) · `status` · `assignee` (me|<user>|none) ·
`sold_by` · `submitted_from`/`_to` · `sold_on_from`/`_to` · `has_open` · `q` ·
`sort` · `cursor`.

### Open questions is the column that earns its place

It is the count of **`handover_gaps(project)`** — the twelve checks the salesperson
sheet already computes, already localised, already tested. A job with three of them
is not worth opening yet.

**It counts the SALE's questions only.** The office's own work — a bay width to
choose, a warning to read, a plan to commit — is open on every fresh job by
definition, so counting it would make every row read the same and tell the reader
nothing. The office's list lives on its road, inside the job.

**Paging is a correctness requirement, not a nicety.** The count is derived, and
read models here are derived and never stored. Deriving it for a page of 25 keeps
that rule and costs nothing; deriving it for an unbounded list does not. So the
queue is paged from the first commit, and sorting is over stored columns only.

---

## 7. Committing a plan

Generating is cheap and repeated; **committing is the decision**, and nothing
records it — a project accumulates runs and none is marked as the one people build
from.

`commit_plan(run_id)` writes `committed_run_id` and moves the job to `planned`.
`GET /api/projects/{id}/plan` is then the one place anyone goes to see it.

* **It commits the DESIGN, not the price.** `committed_run_id` names a
  `GenerationRun` — pure, deterministic, reproducible for ever (ADR-0011). What it
  costs is a `SupplyRun`, and a `Quote` is a supply run somebody stood behind. One
  design, many supply runs, one committed design.
* **It must never enter the run digest.** `RUN_DIGEST_VERSION` is `digest-v4` and
  `committed_run_id` is not an input to generation.
* **Committing takes the STRICT staleness guards.** `create_quote` already refuses
  a moved site while `/bom` and `/structure` stay permissive, because *"a quote is
  the one endpoint that freezes an immutable commercial document"*. Committing is
  the same kind of act: somebody else reads it later and builds from it. A stale
  topology, catalog or site refuses the commit rather than committing something
  that 409s on its first read.
* **It does NOT inherit the quote's refusal on unresolved supply.** A design can be
  complete while the yard cannot fill it. That stays a readiness item; the quote
  stays the hard stop.
* **Committing does not freeze the drawing**, and does not need to: the
  `topology_changed` / `catalog_changed` / `site_conditions_changed` refusals are
  built and tested and have never had a screen that needed them.

---

## 8. The office road

Seven steps, one task at a time, on the machinery `js/roads.js` and
`js/road-model.js` already provide. `ROADS` holds one road and `roadFor()` returns
`null` for a role with no road — *"showing an office person a salesperson's map
would be worse than showing them none."* Adding `OFFICE_ROAD` touches no engine
code.

**The agent spec's warning is about the STEPS, not the pattern.** The office person's
work is not a salesperson's work in a different order, so the office gets the same
road machinery and **none of the same steps** — not one is a rename.

| | Step | Responsibility | Surface | `requires` |
|---|---|---|---|---|
| 1 | The sale | Read what she sold and promised | canvas + notes | `sale_unread`, `promises_contradicted`, `gates_contradicted` |
| 2 | The blanks | Fill what the sale left silent | canvas, side-view tools | `height_assumed`, `base_assumed`, `no_model_chosen`, `gate_swing_unstated` |
| 3 | The questions | Answer what the engine is asking | `#choices` | `choices_unanswered` |
| 4 | Generate | Produce it and read what came back | canvas + `#inspector` | `no_run`, `warnings_unreviewed` |
| 5 | The materials | Cut plan, packages, stock | bom + inventory | `supply_unresolved` |
| 6 | The plan | Say which run is the real one | structure | `no_plan_committed`, `plan_stale` |
| 7 | The price | Quote it | bom, quote panel | `not_priced`, `quote_stale` |

`anchor` is `no_fence_drawn`; `wants` are the four job fields. Steps 1, 4, 6 and 7
carry `commits: true` — they already have their own control, and the road suppresses
its Done button rather than putting two buttons on one act.

### The office loops, and the road already allows it

A salesperson fills blanks in one direction; the office generates, reads a warning,
pins a post, generates again. The road is *"a map, never a wizard"* and every step
stays enterable, so the loop is legal. What makes it readable is that state is
**derived**: a new run makes step 4's warnings unread and step 6's plan stale, and
the map says so without anybody navigating. A step going amber because the work
moved underneath it is the road working.

### Two sources of checks, and neither is called a gap

`handover_gaps(project)` answers *did the sale get captured?* and is a pure
function of the project — which is what lets it catch the silent 1800 mm height
before a strategy makes it look decided. Steps 1–2 read it **unchanged**.

Steps 3–7 are run-scoped, so they come from a second read model,
`readiness(project, run)`, emitting `ReadinessItem{code, params, blocking}` — the
same shape as `HandoverGap`, under its own `readiness.*` locale namespace.

**Deliberately not called a gap.** `Gap` is a BINDING contract type (§1.2.1) with
eight closed kinds and two binding fields, implemented unrenamed in `core/gaps.py`,
rendered under `gaps.*`, and reported through `POST /gaps`. `HandoverGap` already
shares the English word. A third would be the B03 defect again.
`agent/registry.py` records the precedent: the Knowledge team wanted a ninth `Gap`
kind, found none of the eight fitted, and declined to add one *"for something we
can measure on our own side."*

### The one new domain concept: an acknowledgement

Two steps ask for something no code can check — *did you read her promise?* and
*did you read the warning?* Counting open warnings instead is worse: a 6 % slope at
a gate is a fact, not a fault, so the step would never go green and the map would
train its reader to ignore it.

An acknowledgement is a stored fact, **anchored to what it acknowledges**, that
dies when the anchor moves — `Stated` in spirit, `Override` in mechanism:

| kind | Anchored to | Stops being true when |
|---|---|---|
| `sale_read` | the set of annotation ids at the time of reading | the salesperson adds a note |
| `warnings_reviewed` | `run_id` | a new run is generated |

Named facts, never step keys — `Stated`'s own docstring: *"a step key would put a
screen's structure into the project record."*

### Three landmines the implementation must clear

* **`step-surfaces.js` is not road-scoped and must become so.** `STEP_TOOLS`,
  `STEP_PANELS` and `STEP_DRAWING` are global maps keyed by step key, with
  `STEP_KEYS = Object.keys(STEP_TOOLS)` deriving each step's hidden list by
  subtraction. `road-model.js`'s `panelFor` is *already* road-scoped for exactly
  this reason. The stylesheet's mirrored copy and the equality test move together.
* **A step-key collision is waiting.** The obvious name for office step 4 is
  `layout`, and sales step 3 IS `layout`. It is called `generate` above on purpose.
* **`road.js` opens on `let current = "job"`** — sales' first step, hard-coded. It
  becomes `def.steps[0].key`.

### Site conditions are NOT a step — postponed

**Corrected.** An earlier draft gave exposure category, HVHZ and frost depth a step.
They are the dimensions published rules key on, so they matter the day a real
snapshot arrives — and on a job today they are a field nobody fills in. A step
amber on every job for a reason nobody can act on is the completeness lie inverted.

So `#site-conditions` is a **collapsed disclosure on the Generate step, shut by
default**, staying exactly where it lives. And **no new check**: the generator
already emits `site_condition_missing`, naming every dimension this snapshot's
rules asked about, carrying `asked_by`, in both bundles. If it fires it arrives
under step 4's `warnings_unreviewed` like any other warning.

*Trigger to revisit: a real published snapshot whose `ParameterTable`s are
conditioned on a dimension.*

---

## 9. Doing it by hand

> *"The backoffice should be able to do anything manually in case it finds the
> engine to be more hassle than help."*

A tool you cannot overrule gets abandoned the first afternoon it is wrong. But the
takeovers are not all the same act, and the system should say which one was used
rather than quietly losing the thread.

| Depth | You… | Costs | Survives a regenerate |
|---|---|---|---|
| 1 · answer | change an input — a height, a choice, a base | nothing; it IS an input | yes |
| 2 · direct | pin a post, force a sku, force a mounting | nothing; the graph cites you | yes, anchored |
| 3 · adjust | add a BOM line, change a quantity, pin a cut | that line stops tracing to a requirement; prints **by hand** | while its anchor exists; orphaned honestly otherwise |
| 4 · replace | "ignore the engine, here is the BOM" | no pegs, no proof; the printout says so | no — it asks first |

Depths 1–2 exist. **3–4 are the new work.**

### Cutting, specifically

Today `CutPlan` is read-only: a table of bars with an `optimal` badge. Four takeovers:
**pin a piece to a bar**, **add a bar by hand**, **buy full lengths — cut on site**
(switches the sku off cut planning entirely), **trim allowance** (+N mm per piece).

* **`certified_optimal` is withdrawn the moment a person touches the plan.** It is a
  proof that the plan attains a computed bound; edit the plan and the bound no
  longer describes it. The badge becomes `hand_adjusted`, with the name and the
  sentence. Keeping it would make the one honest claim in the panel a lie.
* **Where a supported path exists, prefer it.** *"We have a 4 m offcut in the yard"*
  is not a cut-plan edit — it is a line in inventory. Put it there and the planner
  spends it, the order drops a bar, and every number stays true.

### The one question, asked once

Depths 3 and 4 ask **not "why"** — why invites a shrug — but the thing only the
person doing it can answer, and only then:

* **"The engine got this wrong"** → a `Correction`, immutable, in their words,
  joining the review queue. Contract obligation 3.2.7 already governs this shape.
* **"This job is special"** → recorded and attributed, and deliberately **not**
  counted as evidence about anything.

A bent bar end is not evidence; a post the engine should have upgraded is. Nobody
can separate them afterwards from a log of clicks, and that difference is the whole
value of the record.

### Open: depth 4 versus regenerate

Does pressing Generate discard a replaced BOM (asking first), or does replacing
**lock** the job against regeneration until explicitly unlocked? A question about
people, not data.

---

## 10. One door

**Every change that moves a job — whose desk it is on, or what it commits to — goes
through one named, typed, permission-checked command.** Field edits do not: typing
an address is not a command, and forcing it to be one turns the design into ceremony.

The registry exists. `agent/registry.py` is already a closed table with exactly these
columns — `kind`, typed payload, rung, materialize, disposition, i18n key — holding
**one** row, `select_choice_point`. This grows it; it does not invent it. Its header
already states the growth rule (*"a run stamps only the inputs it actually had, so
adding an entry never invalidates a stored run"*) and the restraint that goes with it
(*a finding that fits no entry becomes a counter before it becomes a row*).

| Group | Kinds |
|---|---|
| Sales hands over | `submit_job` |
| The queue | `claim_job` · `assign_job` · `return_to_sales` · `cancel_job` · `reopen_job` |
| Planning | `set_fence_model` · `answer_choice` · `apply_override` · `generate_plan` · `commit_plan` · `discard_plan` |
| Cutting | `pin_cut` · `add_bar` · `skip_cut_planning` · `set_trim_allowance` |
| By hand | `edit_bom_line` · `add_bom_line` · `replace_bom` |
| Money | `create_quote` · `accept_quote` |
| Closing | `close_job` |

Each row answers three questions before anything happens: **may this capacity
perform this kind · is the job in a status that allows it · does the payload
type-check.**

**What one door buys:** "who did what" free and uniform; permissions in one table
rather than scattered across handlers half of which will be added later by somebody
who did not know; a suggestion is a command that has not been run, so accepting is
one call; and an agent operator is a different actor calling the same door, with no
second implementation to keep in step.

---

## 11. The agent's seat

The advisory spec already decided most of this: *"the agent is for the back-office
person first"*, and the salesperson's view already hides every surface agent advice
lands on.

Three stages, one door. The move between them is **a dial per command kind**, which
the registry already calls `disposition`:

| | The agent | The person | |
|---|---|---|---|
| Reads | ranks an existing choice set, writes checkable claims | reads it | built |
| Proposes | returns **unperformed commands** | one click performs it | next |
| Acts | performs low-stakes kinds under its own actor id | sees it in the log; can undo | later |

`answer_choice` may reach `auto`. `commit_plan` and `create_quote` are pinned at
`ask` permanently — those are signed.

**Two names in the log, not one.** `actor` is who performed; `origin` is who
proposed. Without the second there is no way to answer *how often is the agent
right?* and no evidence behind turning any dial up. Same `origin` / `origin_ref`
pattern `Override` already uses for corrections.

**The highest-value thing it does is not on any single job**: reading a hundred
corrections and noticing the group that repeats. Two rules it does not get to break
— surface **the group and how its members disagree**, never a merged average
(*near-misses are the finding*; T46 §11 and T49 §7 argue it on real data), and
whatever it finds is a **proposal**, priced against every job it would change and
inert until approved.

**Nothing here is built FOR the agent.** One command list, typed payloads, a
capacity check, two names in the log — every property earns its keep for the humans
alone. Building it the other way round means a second implementation that drifts,
and the drift is where the untraceable BOM comes from.

---

## 12. Checked against the frozen contract

`sha256sum -c contract.sha256` → `contract.md: OK`, `AMENDING.md: OK`. v1.3.

**Nothing here touches a BINDING item and no amendment is needed.** The contract
governs what crosses the Knowledge Platform boundary; a queue, a status, an
assignee and an activity log cross none of it. Six obligations nevertheless land on
this design:

| Obligation | What it requires here |
|---|---|
| §1.2.1 `Gap` | Readiness items are `ReadinessItem`, never `Gap`, never routed to `POST /gaps` (§8) |
| 3.2.1 re-fetch by hash | `warnings_unreviewed` reads warnings **off the stored run**; it must never re-evaluate rules against the active snapshot, which would re-resolve to "current" *and* recompute a quantity |
| 3.2.4 never fail over a gap | No road step may gate `POST /generate`. Pinned by a test |
| 3.3.5 warning placement | `warnings_unreviewed` counts `StrategyWarning` only, never `DocumentWarning` — quoted document warnings go once into the annexe and never onto a line |
| 3.3.4 both bundles | Every new status, command kind and readiness code needs entries in both, with a `*_CODES` list guarded the way `HANDOVER_CODES` is |
| 3.1.7 tenant | Accounts are the first identity that could carry an org — which is exactly why this slice must **not** invent a tenant model |

---

## 13. Out of scope, with triggers

* **A tenant model** — *trigger: obligation 7 landing on this side.*
* **Locking / optimistic concurrency on a job** — *trigger: collisions turning out
  not to be rare.*
* **Multi-currency** — a `Money(amount, currency)` through the whole cost tier plus
  a rate source with an as-of date. *Trigger: a second currency.*
* **Deals that never became jobs** — lost before a job exists. *Trigger: the
  salesperson's own MVP round two.*
* **SSO** — *trigger: you naming a provider. A different afternoon, not a different
  design.*
* **Photos on the sales side** — cheap, off the critical path, folds into any slice.
* **The super user's bench** — a third MVP, still unwritten.
