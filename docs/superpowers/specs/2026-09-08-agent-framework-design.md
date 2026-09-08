# The agent framework

**Status:** DESIGN. Nothing here is built.

Companion to `2026-09-08-advisory-agent-design.md`, which records **what** was
decided and by whom. This document is **how**: the types, the boundaries, and
the five properties that make an advisory agent auditable rather than merely
present.

Approved section by section with the product owner on 2026-09-08.

## Why this document exists

The calibration settled that the agent proposes into input slots and never
reaches inside `generate()`. That is a boundary, not a framework. A boundary
tells you what the agent may not do; it does not tell you how a task is
declared, what the agent is allowed to look at, how a proposal is checked before
a person sees it, or how the system knows the difference between *"I looked and
found nothing"* and *"I never looked."*

Everything below is derived from something this repository or the integration
thread already paid for. Where a design choice is a straight lift, it is cited —
not out of deference, but because a convention that was invented to fix a
specific observed failure is worth more than one reasoned from first principles.

---

## 1. The permission list is the grammar

`ai/claude.py` carries a comment that decides this framework's shape:

> Structured outputs require `additionalProperties:false` — a free-form params
> dict is INEXPRESSIBLE in the constrained schema and silently stays empty.
> Explicit typed fields instead.

An action's payload therefore cannot be a dict. It must be a typed model. Once
that is true, a much stronger property is available for free:

**A task declares which action kinds it may emit, and the framework builds the
model's output schema from exactly that list.**

A task permitted to rank a choice set receives a schema whose only verb is *pick
point `p2`*. It cannot emit *move a post* — not because a validator rejects it
afterwards, but because **the word does not exist in the grammar it was given**.

This is the same instinct as `knowledge/ast.py`, whose `FnCall` resolves against
a code-registered whitelist with "no eval of strings, ever". Narrow run stops
being a policy somebody must enforce and becomes a type.

**Consequence for the tool-calling seam (§11):** the permission list is the
durable artefact. Whether it is compiled into an output schema or into a set of
tool definitions is an execution detail, changeable without touching what a task
is allowed to do.

---

## 2. The action registry

A code-registered table. Each entry:

```
ActionSpec {
  kind            str            closed vocabulary, one per action
  payload         type[BaseModel] explicit typed fields, no dicts (§1)
  rung            Rung           note | selection | directive | rule
  materialize     callable       payload -> the first-class object, on keep
  disposition     Disposition    show | hold_pending | auto  (§7)
  i18n_key        str            he.json + en.json, key-identical
}
```

**What it holds today.** The six members of `Override.Directive` — `pin_post`,
`suppress_post`, `force_post_sku`, `force_mounting`, `force_vertical`,
`lock_bay` — plus one entry per remaining rung: author a note, make a selection,
propose a knowledge version.

**Growth is additive and never invalidates a stored run**, because a run stamps
only the inputs it actually had. This is the seam the calibration's D1 defers
to: *"for now it is ok, it will be extended in the future."*

**`materialize` is the generalisation of an existing function.**
`project/intents.py::confirm_intent` already does exactly this for three intent
kinds — takes a proposal, produces the first-class object, chains provenance
back to the source. The registry makes that a per-kind callable instead of an
`if/elif` chain that must be edited for every new action.

---

## 3. The task

Data, not code:

```
TaskSpec {
  id              str
  goal            str            what this task is for; the prompt's spine
  trigger         Event          what causes it to run
  reads           list[Slice]    which view slices it may query (§4)
  may_emit        list[str]      action kinds -> becomes the output schema (§1)
  max_proposals   int            a cap, not a target (§8)
  stub            callable       deterministic offline answer (§9)
}
```

Registered in a table beside the registry. **Adding a capability is adding a
row**, not building a subsystem — which is the property the product owner asked
for when they said the design must stay modular and extendable.

**Triggering events, as a starting list:** a stretch is opened · a `Gap` appears
· a `ChoiceSet` has more than one live answer · a correction is made · the user
asks *"why this?"*.

Generation itself stays behind its explicit button and never auto-fires. A task
that runs while somebody is still drawing is answering a question about a fence
that does not exist yet.

---

## 4. The view — broad read, narrow run

The product owner's decision was that the agent always has access to the layout,
the map and the relevant knowledge, while invocation is small and goal-scoped.

This is in direct tension with `ai/ports.py`, which was built so that each port
takes exactly what it needs and **no ambient context object** — *"an adapter
that wanted more would be reaching for state the deterministic side owns."*

The resolution keeps both halves, and the split is the point:

* **Breadth is in what it may look at.** `AgentView` is a read-only interface
  the task queries — layout, map, gaps, open choice sets, resolved knowledge. It
  exposes no mutators and holds no engine state.
* **Narrowness is in what it is asked and what it may do.** One goal, one
  output schema, one permission list.

**What a task read is recorded with what it proposed.** Not for tidiness: it is
what makes the retrospective scoring of `advisory-agent-design.md` §6 honest.
Replaying a job against an approximation of what the agent saw measures nothing.

---

## 5. The proposal record

The largest section, because it carries four separate properties that each fix a
failure somebody has already had.

```
Proposal {
  id              str
  task_id         str
  project_id      str
  run_id          str | None
  kind            str            must be in task.may_emit
  payload         BaseModel      the ActionSpec's typed payload
  claims          list[Claim]    the rationale — never prose (§5.1)
  saw             ViewDigest     what was read (§4)
  source_class    "ai_proposal"  fixed (§5.2)
  agent_id        str            "stub" | "claude:<model>", as today
  status          proposed | kept | reversed
  rejection       RejectionType | None   the five of the calibration spec
  created_at      str
}
```

### 5.1 A rationale is a list of tagged claims, never prose

`conversation.md`'s ground rule 2, adopted verbatim in structure:

| Marker | Means | Must carry |
|---|---|---|
| `measured` | I ran something, this is the output | the query |
| `read` | I read a document | file + page or line |
| `inferred` | reasoning, not observation | nothing — but say it |

The rule exists because of a specific failure, and the thread says so plainly:
one side asserted from memory that a table read `NON HVHZ`, and it did not;
later the same string was asserted and this time it was true, and *"the only
difference a reader can see is that the second one arrives with a query
attached. Make that difference visible by construction rather than by trust."*

**That is an advisory agent's failure mode, described precisely, by people who
hit it without one.** *"Make the middle bay 1400 mm so it clears the window"* is
either a measurement or a plausible-sounding guess, and on screen the two
sentences are identical.

```
Claim {
  marker   measured | read | inferred
  text     str
  evidence str | None    required for measured and read; must be None for inferred
}
```

**And it pays for itself twice**, which is why it is a mechanism rather than a
formatting rule: a `measured` claim can be **re-executed and compared before the
proposal is ever shown** (§6). An `inferred` claim cannot be, so it is rendered
to the user as reasoning. The agent cannot hand somebody advice resting on a
number it invented, and cannot pass off an opinion as an observation.

### 5.2 Agent output is `ai_proposal`, and that is already ratified

`SourceClass` is a closed registry vocabulary in the integration contract, and
the **BINDING** source-policy block in §1.4 states:

> `ai_proposal` is proposal-only on every task and is omitted from the table for
> width.

So the framework invents no provenance for agent output. It carries
`ai_proposal`, and `knowledge/source_policy.py` — which already ranks
admissibility per task and explains rejections — refuses it as authority
everywhere, by a rule agreed with the other team.

**This gives the calibration's "nothing proposed is ever evaluated" a second,
independent lock.** Our review gate is one. The source policy is the other, and
it holds even if a disposition (§7) is misconfigured to `auto`: the object is
created, and it still cannot back an accepted value on any task.

Using an existing registry class is not an amendment and needs no ratification —
`AMENDING.md` excludes registry usage explicitly.

### 5.3 A proposal is added beside a record, never instead of it

From `conversation.md` T55 §7, written about a mechanism that was deleting the
other team's own statements:

> emit the dispute **in addition to** the coverage gap, never instead of it, so
> a false dispute costs a curator a question rather than a record. That is the
> wrong direction to be wrong in.

**Framework rule:** no proposal may delete or overwrite a `Gap`, a warning, an
`Annotation`, a `Selection` or an `Override`. It is stored beside the thing it
concerns and rendered beside it.

The case this prevents is concrete. A job carries *"height never confirmed,
assumed 1800"*. The agent reasons that the neighbouring stretch is 1800 and
proposes the same here. If the proposal replaced the warning, the job would read
as confirmed, nobody would ever ask the salesperson, and **the only record
saying nobody checked would be gone.** Beside it, a wrong guess costs a
dismissal.

**The rule governs a proposal while it is a proposal.** A proposal the user
*keeps* materialises under the ordinary rules of its rung (§2 `materialize`),
and those rules already refuse silent loss: knowledge versions are immutable and
edits insert, a quote supersedes rather than mutates, an override is a
first-class row. What is superseded stays readable. The prohibition here is on
the pending proposal reaching past the person and editing the record it is
arguing with.

### 5.4 The result is ledger-shaped

`conversation.md` ground rule 3: every turn ends with a ledger, and **no
decision may live only in prose.**

A `TaskResult` carries the same four categories:

```
TaskResult {
  proposals   list[Proposal]     what it proposes
  declined    list[Declined]     what it considered and did not propose, and why
  measured    list[Claim]        what it established, whether or not it proposed
  needs       list[str]          what it would need from a person to go further
  evaluated   bool               whether it examined anything at all (§8)
}
```

`Declined` is an action kind plus the claims that ruled it out — the same
`Claim` type, so a rejection is evidenced exactly as a proposal is. It is not
padding: a task that considered relaying the whole fence and rejected it because
the cost was 40% is telling the user something, and it is also the record that
stops the same idea being re-proposed next week.

`ViewDigest` records **which slices were queried and the identity of what came
back** — the run id, topology revision and knowledge snapshot hash the view
resolved against. Not the payload: the identity, which is what the pipeline
already stamps on a `GenerationRun` and what makes a replay provably the same
situation rather than a similar one.

---

## 6. Three checks before a person sees anything

1. **Schema** — free, from §1. The output cannot be malformed or name an action
   the task may not emit.
2. **Grounding** — every `measured` and `read` claim is re-executed against the
   view and compared. This generalises the check `ai/claude.py` already makes
   (`if c.source_text in annotation.text` — the span must be verbatim).
3. **Referential** — does the anchor resolve, does the SKU exist, is that
   `DesignPoint` actually in `offered()`? A proposal that fails is **dropped and
   logged as an agent defect, never shown.** A user must never be offered
   something impossible.

Admissibility — *would applying this still generate?* — is a fourth check,
expensive, and run only for the action kinds whose `ActionSpec` asks for it.

The retry discipline is the adapter's existing one and is not re-invented:
two attempts with validation errors appended, then degrade to *needs human*.

---

## 7. Disposition is configuration, not the agent's business

Per action kind: `show` · `hold_pending` · `auto`. Owned by the backend, per the
product owner's D3, and changeable without touching a task.

**The agent is never told which disposition applies to its output.** An agent
that knows which of its proposals get applied automatically will learn to phrase
things to get applied — and the drift would be invisible, because the proposals
would keep passing every check in §6.

---

## 8. Two rules about staying quiet

### A task may be silent, and silence is a designed outcome

> A guard that always fails is a guard everybody learns to ignore.
> — `conversation.md` T55 §8

An agent that comments on everything is the same alarm. `max_proposals` is a
cap, not a target, and a task returning zero proposals with a populated
`measured` list has done its job.

### "I did not look" is never "nothing to report"

`TaskResult.evaluated` is a separate field for a reason this repository has
already paid for twice. The integration thread calls it **vacuous green** —
*"a check with nothing to check must not report success."* This repo's own audit
B01 was a cached `null` painting a clean bill of health across the app. And
`2026-09-07-eight-step-road-design.md` makes it a rule: `unknown` is never
folded into `done`, because a green tick is a claim that something was checked.

A task whose view slice was empty, or whose adapter failed, reports
`evaluated: false`. The UI must render that as *"could not check"* and never as
*"nothing found."*

---

## 9. The stub

Every `TaskSpec` carries a deterministic stub or offline development breaks —
the property ADR-0009 exists to protect, and the reason `build_interpreter()`
falls through to the stub on any failure to construct a client.

**The cap is unchanged and is the whole point:** the stub must not become a
second rule engine. For the choice-ranking task it picks the first non-default
point in `offered()` and emits one `inferred` claim saying exactly that. Honest,
tiny, and it exercises the entire framework without pretending to judgement.

---

## 10. Module layout

New module `fenceai/agent/`:

| File | Holds |
|---|---|
| `registry.py` | `ActionSpec`, the action table |
| `tasks.py` | `TaskSpec`, the task table, the trigger vocabulary |
| `view.py` | `AgentView`, the slices, `ViewDigest` |
| `proposal.py` | `Proposal`, `Claim`, `TaskResult`, the lifecycle |
| `run.py` | dispatch: event → task → adapter → checks → proposals |

`fenceai/ai/` keeps its current job — transport and adapters — and gains a
task-shaped port beside the three that exist.

**Dependency rule: nothing depends on `fenceai/agent/` except the API layer.**
`strategy`, `demand` and `fulfillment` must not import it, and the architecture
fitness tests in `tests/architecture/` should pin that on the first slice. A
framework that the pipeline can import is a framework that will eventually be
imported by the pipeline.

---

## 11. Named seams

Deferred deliberately, each with what it would cost.

* **Tool calling instead of structured output.** Lets a task take several steps
  and interleave reasoning; needs a step budget and a stopping rule. The
  registry entry is identical either way, so this changes how a task is
  *executed*, never what it may *do*. *Trigger: the first task that genuinely
  cannot be answered in one call.*
* **Registry entries beyond the current six directives.** *Trigger: the first
  advice worth giving that cannot be expressed.*
* **Learned per-task confidence weighting.** Permitted only as a versioned,
  snapshot-stamped field — see `advisory-agent-design.md` §10.
* **Multi-task planning.** One task at a time, by decision. A planner that
  chains tasks is a different design and should be argued for on evidence from
  running single ones.

---

## 12. What this design refuses

* **No AI call inside `generate()`, `derive_requirements()` or `fulfill()`.**
  ADR-0009, unchanged.
* **No free-form action payloads.** §1 makes them silently empty in practice
  and unbounded in principle.
* **No prose rationale.** §5.1 — a sentence with no marker is not a reason, it
  is a mood.
* **No proposal that deletes.** §5.3.
* **No green tick the agent did not earn.** §8.
* **No agent-authored knowledge that can act as authority.** §5.2, ratified.

---

## 13. Left to the plan

Sequencing, not design:

1. The first task is **ranking an existing `ChoiceSet`**. `generate()` already
   enumerates the admissible points, `offered()` already drops the dominated
   ones, and the axes and deltas are already measured — so a task that sorts
   three rows and writes tagged claims **cannot produce an inadmissible fence**,
   because it was never handed the vocabulary to describe one. It exercises
   every part of this framework and risks nothing.
2. Whether the back-office workspace lands before or beside it. The agent needs
   a surface and the surface is unbuilt.
3. The session log's shape, which gates all retrospective measurement.
4. Whether the team key rides with this or lands as its own slice.

Every slice ends with the product owner opening the app and doing one named
thing. No concurrent agents inside a slice.
