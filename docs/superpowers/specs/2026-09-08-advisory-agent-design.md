# The advisory agent

**Status:** DESIGN. Nothing here is built. Calibrated with the product owner on
2026-09-08; every decision below was answered by them, not inferred.

Supersedes nothing. It is the first document to say what the *agent* half of
`docs/product/architecture-foundation-v0.1.md` actually is, and it changes no
existing behaviour — the pipeline, the contract and the golden scenarios are
untouched by everything proposed here.

## Why this document exists

The foundation names four AI roles and the repository implements three narrow
ports (~390 lines). The product goal is considerably larger than those ports: an
agent that advises on placement, assembly and structure, whose corrections and
whose company's own data become a further layer of knowledge, learning quietly
until the knowledge is precise enough to plan an installation on its own.

The gap between those two sentences is not a backlog. It is a set of decisions
that each foreclose different futures, and the point of this document is to
record which ones were made, which were deliberately deferred, and — the part
that matters most for a product nobody has battle-tested — **which are cheap to
change later and which are not.**

## The constraint everything else obeys

> The user decides everything. The agent only advises and suggests actions, or
> makes an action and the user chooses whether to keep or reverse it.

Stated by the product owner, and it is stronger than it first reads. It is not a
UI preference. It is what keeps every existing non-negotiable in
foundation §15 intact while adding an agent, and §1 below is the mechanism.

---

## 1. The agent writes into inputs, never into the computation

`generate()`, `derive_requirements()` and `fulfill()` are pure functions over
explicit inputs, and a `GenerationRun` is identified by a hash over the identity
of those inputs. That is what makes the same drawing produce the same fence, and
what lets a read against a moved catalogue **refuse** rather than quietly
recompute.

An agent is compatible with all of it on exactly one condition: **it proposes
into the input slots and never reaches inside.** No AI call sits inside any of
the three functions — ADR-0009, unchanged and not up for revision here.

This is also why "the agent advises on a rule" and "the agent moves this post"
are not two designs. Both write an input. They differ only in how far the write
reaches and whether it survives the drawing being redrawn.

### The four rungs

Four input slots already exist, and the codebase already holds them apart from
one another for reasons that predate this document.

| Rung | Type | Anchored to | Asserts | Survives a redraw |
|---|---|---|---|---|
| Note | `Annotation` | any ref | a sentence a person must read and decide about | yes; reaches no computation |
| Selection | `Selection` / `ChoiceSet` | a scope | two right answers; only a person or a stated default resolves it | yes |
| Directive | `Override` | `(run_id, station, kind)` | the engine got this wrong *here*; authority tier 2 | no — it orphans, and says so |
| Rule | `KnowledgeVersion` | scope + condition | this is how we do it; immutable, snapshot-stamped | yes, on every job |

`strategy/choices.py` already states the distinction this table depends on: an
override says the engine was wrong, a choice set says nothing was wrong and
neither point is nicer. An agent that conflates them turns a legitimate
preference into a recorded engine defect, and the learning loop then trains on
a fault that never happened.

**The ladder is the product owner's "supersedes or adds".** A correction that
stays on the Directive rung is this job only; the same correction promoted to
the Rule rung is company knowledge. `learning/review.py` already implements the
promotion, and `scope_restrict` can only *narrow* — nothing in the system
widens a proposal automatically, and nothing here changes that.

---

## 2. The published action registry

**Decision (D1, D2, D3), as stated by the product owner:** the backend publishes
the set of actions that exist; the agent may only emit from that set; the
backend decides what happens to a proposal — shown as pending, applied, or
queued for review. A proposal may be text, an action, or both.

This is stronger than a validation-after-the-fact design. The agent cannot name
an action the backend has not published, so the ceiling enforces itself rather
than being enforced by a checker somebody can forget to run.

### What the registry contains today

`Override.Directive` is a closed discriminated union of six members:
`pin_post`, `suppress_post`, `force_post_sku`, `force_mounting`,
`force_vertical`, `lock_bay`. Plus the other three rungs: author a note, make a
selection, propose a knowledge version.

**This is accepted as the starting vocabulary and is explicitly expected to
grow.** An agent today can move a post, remove one, force a product, force a
mounting, force a vertical mode, and lock a bay to a width. It cannot say "use a
different panel build-up in this bay" or "splice the rail here", because no
directive exists to say it in.

### Adding to the registry

Each new entry is a new thing `generate()` must honour and the decision graph
must explain, so an addition is real work — but it is *additive* work, and it
never invalidates a stored run, because a run only stamps the inputs it actually
had. Registry growth is the intended path for widening the agent's reach.

### Disposition is the backend's

Whether a given proposal is auto-applied or held as pending is a **policy**, set
per action kind and changeable later. The agent has no opinion about it and must
not acquire one; an agent that knows which of its proposals get applied
automatically will learn to phrase things to get applied.

---

## 3. Rejection has five types, and only two touch knowledge

**Decision (D4).** A `Correction` today records a before, an after and a
free-text comment. It does not record *why*, and the difference between "the
rule is wrong" and "the agent did not know something" is the difference between
knowledge that improves with use and knowledge that rots.

| Type | Means | What happens |
|---|---|---|
| **wrong** | the rule is bad | counts against the rule; suppresses re-proposal |
| **unknown_fact** | a fact was missing, not a bad rule | opens a `Gap` naming the fact to fill; the rule is untouched |
| **not_here** | right in general, wrong for this job | narrows scope — existing `scope_restrict` |
| **not_now** | fine, don't bother me | silences on this project; learns nothing |
| **my_call** | no right answer, customer's taste | records a preference; never a correction |

`core/gaps.py` already exists and already means *"nobody stated this, and here
is what would close it"*. `unknown_fact` routes a rejection there instead of at
the rule, which is the whole mechanism by which the loop converges.

**The type is captured at the moment of the correction, never reconstructed
later.** A reconstruction is a guess about the user's intent made by the system
that most wants a particular answer.

---

## 4. Knowledge is a shared backbone plus a per-team view

**Decision (D5), as stated by the product owner.** Not three origins in one
ladder. Two tiers:

* **The backbone** — the sources this product supplies, shared by everyone.
* **A team's view over it** — which of those sources that team treats as
  relevant, drifting over time, plus that team's own corrections and products.

Teams are rarely a shareable source of information. **Cross-team sharing is out
of scope**, and if it is ever wanted, *how* it works is its own design.

### What exists and what does not

`knowledge/source_policy.py` is already the mechanism for "which sources are
relevant": a policy table of admissibility and rank per task and source class,
with `explain_rejection` for why a candidate lost. **It has no team dimension**,
and neither does anything else — no `KnowledgeVersion`, `Project`, `Correction`
or catalogue row is keyed by team.

The `tenant` field that appears in `core/gaps.py`, `knowledge/snapshot.py` and
`knowledge/parameters.py` is **the publisher's**, carried verbatim across the
integration contract (§1.1 `TenantId`). It is not our multi-team concept and
must not be repurposed as one — a `null` there means *Knowledge-global*, which
is a different fact from *belongs to no team of ours*.

### Decision (O1): one company now, keyed from the start

Only one company needs to be supported. **But the team key goes on the data
now**, because retrofitting one means touching knowledge, corrections, source
policy, catalogue and every project at once. Carrying an unused key costs
almost nothing; adding one later costs a migration across every table that
matters.

---

## 5. Broad read, narrow run

**Decision (O4), as stated by the product owner:** the agent always has access
to the layout, the map and the relevant knowledge. Invocation is **event and
goal driven — small tasks, one at a time.**

This creates a tension worth naming rather than discovering. `ai/ports.py` was
built so that each port takes exactly what it needs and *no ambient context
object* — "an adapter that wanted more would be reaching for state the
deterministic side owns." Broad read access is that object.

The resolution keeps both halves:

* **Breadth is in what it may look at.** The agent gets a *read interface* it
  queries — layout, map, gaps, open choice sets, resolved knowledge — rather
  than a fat argument assembled by the caller.
* **Narrowness is in what it is asked and what it may do.** Each **task**
  declares one goal and one output shape, and may only emit actions from the
  registry in §2.

### Triggering events, as a starting list

A stretch is opened · a `Gap` appears · a `ChoiceSet` has more than one live
answer · a correction is made · the user asks *"why this?"*.

Generation itself stays behind its explicit button and never auto-fires. A task
that runs while somebody is still drawing is a task answering a question about a
fence that does not exist yet.

---

## 6. Log everything; sample later; run the agent retrospectively

**Decision (O5), as stated by the product owner.** This is a hosted product with
a web client. AI features are **toggleable**, and the toggle hides the agent
from the user — it does not stop the system recording. Actions, jobs and layouts
are always recorded.

The product owner's refinement replaces an earlier and worse idea (running the
agent invisibly on every job): **log the session, then sample, then run the
agent retrospectively on the jobs worth scoring.** Cheaper, and strictly more
informative.

This is a second invocation mode, not a contradiction of §5. §5's event-driven
tasks run **live, for a person who can see the answer**. Retrospective scoring
runs **later, over a sampled session log, for nobody** — same tasks, same
registry, no reader. Keeping them one code path and two triggers is what makes
the scores comparable to what the live agent would have said.

Three consequences:

1. **"AI off" is the only mode that yields uncontaminated data.** If the user
   saw the suggestion, agreement cannot be distinguished from suggestion. The
   hidden mode is the one that measures whether the agent is actually right —
   which is what earns the trust to turn it on.
2. **Session logging is a real build item and a prerequisite for the entire
   learning story.** It must capture enough to replay: state, what the user did,
   in what order, and what they were shown at the time.
3. **Replay is unusually well-supported here already.** Runs stamp the identity
   of their inputs and knowledge snapshots are immutable, so the agent can be
   put against the exact situation a person faced rather than an approximation
   of it. Retrospective scoring is honest by construction.

The deterministic stub keeps its existing job — offline tests and local
development — and its existing cap. It is not a product mode and must not grow
into a second rule engine.

---

## 7. A recommendation is a decision-graph node

**Decision (O6).** *"The decision graph is the explanation"* is only true of
things that are in it. A recommendation that lives in a toast and vanishes when
clicked breaks that property for every element the agent touched.

Cost: one node kind, its payload, and `warning`/`explain` template entries in
**both** locale bundles — `he.json` and `en.json` must stay key-identical, and
`tests/web/test_locale_bundles.py` enforces it. The node carries which task
proposed it, what it proposed, the rejection type if it was refused, and the
model identity that produced it, exactly as `InterpretationRecord` already
stamps `interpreter` today.

Built as part of the first slice, not after. A graph node added retroactively is
a graph node that was missing from every run in between.

---

## 8. A company's own products and documents

**Decision (O3), as stated by the product owner:** source materials are kept
separate from everything else.

* **Source materials** — manuals, price lists, spec sheets, drawings. Stored
  verbatim, versioned, never edited, only cited.
* **Operational data** — the company's products, jobs, layouts, corrections.
  Live and editable.

**The boundary rule:** a document is source material; anything read out of it is
operational data that **cites** it. A supplier's price list is a source; the
products created from it are catalogue rows carrying a citation back to the page
they came from. This is the pattern the knowledge side already uses —
`SourceDoc` in `knowledge/source_docs.py` is exactly "the provenance definition
every `SourceRef.belongs_to` joins to".

### What exists today

* **Products** — a full typed model with six consumption semantics, and one raw
  `PUT /api/catalog/products` that overwrites the whole catalogue. No import, no
  file, no column mapping, no UI.
* **Documents** — a provenance record type, and **no ingestion of any kind.**

### Who stores a customer's documents — DECIDED 2026-09-08

**The knowledge base does.** Product owner's decision, taken against
`conversation.md` T57 §1 and recorded in `roles-and-boundaries.md`.

The paragraph above — *stored verbatim, versioned, never edited, only cited* —
was written here as a specification for something we would build, and the
Knowledge team read it as a description of what they already are.
`[measured]`, their T57: **146 source documents stored byte-exact and
content-addressed, read-only enforced in code; 82,282 canonical elements;
25,961 published citations resolving with 0 dangling.**

So the split is the boundary rule of this section, applied to the two teams
rather than to two tables:

| | Where it lives |
|---|---|
| The document | The Knowledge platform. Ingested, versioned, immutable, cited. |
| Anything read out of it | Here. Catalogue rows, prices, jobs — operational data that cites the document. |

**What is still ours, and it is not small:** catalogue rows, the import
experience, column mapping, the price-list lifecycle, and the citation from a
product version back to the document version it was read from. The Knowledge
team explicitly does not want any of it.

**Two dependencies this creates, stated rather than discovered.** Both are
theirs, both are measured in T57, and neither is a reason to reverse the
decision:

* **Tenancy is built and exercised by nothing.** All 146 documents are
  `owner_tenant = NULL`, which means *shared*. A customer's own price list must
  not be shared, so **`owner_tenant` has to work before one customer document is
  stored** — the first real row it would ever carry.
* **Their ingestion is tuned for engineering PDFs**, not for arbitrary customer
  uploads. `extract_html` was added five days before this decision, for exactly
  two retained web pages. A price-list spreadsheet is a different animal.

**And one property gets weaker, which is worth saying plainly.** This repo's
offline story is that a run is a pure function over a pinned snapshot, so a plan
from last March renders the same numbers with the Knowledge platform
unreachable. That is unchanged for *published* facts. It does not extend to a
customer **uploading** a document, which now needs them reachable. The
degradation is confined to ingestion and does not touch generation.

The **price-list decision below is unaffected and gets stronger**: a product
version citing an immutable, content-addressed document version is a firmer
anchor than one citing a file we stored ourselves.

### The price-list decision

**Decision, as stated by the product owner:** both prices are kept. A quote made
in March prices at January's numbers; new jobs use June's.

Half of this is already true. A `Quote` is a frozen document — `requirements`
and `bom` persisted in full, `draft → accepted → superseded` — so the signed
March number is already immutable and nothing done to the catalogue can move it.

What is missing is everything around it. Re-opening that job's working views
after a price moves **refuses** today (409 `catalog_changed`, hashed over
`GenerationRun.catalog_skus`). That refusal is correct and is a safe
placeholder: nothing is silently wrong. But it is a refusal, not a
reproduction.

So the build item narrows to: **catalogue products become append-only versions
citing the document version they came from, and a run resolves prices as of its
own stamp instead of refusing.**

---

## 9. What is expensive to change, and what is not

The product has not met a real company yet. The product owner's constraint —
stay flexible, modular, extendable — is the correct one, and this section is
what it means concretely, so that "flexible" does not decay into "undecided".

**The irreversible decisions are about what is recorded. Policy decisions are
reversible.** Be strict about record shape and loose about policy.

The price-list case is the worked example. If June's catalogue only knows
*"the post costs 51₪"*, January's price is gone and no future policy can bring
it back. If both rows are kept, each citing its document version, then all three
candidate policies — update everywhere, surface a diff, or keep both — remain
implementable next year, after real companies have said which they want.

| Seam | Fixed now | Free to change later |
|---|---|---|
| Action registry | proposals may only come from it | what is in it |
| Rejection types | captured at the moment of correction | what each one does |
| Source → product citation | always recorded | what a new document version triggers |
| Team key | present on the data | whether teams ever share |
| Knowledge versions | immutable, snapshot-stamped | authority, weighting, precedence |
| Session log | captured always, AI on or off | what is sampled and when |

Left column: get it wrong now and it is expensive forever. Right column: change
it whenever the world teaches you something.

Two existing behaviours already satisfy the worry that prompted this section and
should be pointed at rather than rebuilt. **Adding a product breaks nothing** —
a run stamps only the SKUs it named, so a new SKU an old job never bought does
not disturb it. **Adding a company rule breaks nothing** — versions are
immutable, edits insert, and `learning/impact.py` reports *"this would change N
of your projects"* before anyone approves it.

---

## 10. Two properties this design presses on

Recorded because both are foundation §15 non-negotiables, and a design that
presses on one without saying so is how a non-negotiable quietly stops being
one.

### "Nothing proposed is ever evaluated"

Held against *"learning behind the scenes, and not too strict."* Both cannot be
unconditional.

**Resolution, agreed:** a correction applies **immediately at project scope** —
an `Override`, authority tier 2, which the generator must preserve and which is
already a first-class supported state. Only **generalising past this one job**
requires a human. Invisible to the user in the moment, still gated where the
consequence is company-wide.

The gate keeps its existing teeth: nothing `proposed` is evaluated, approval is
a recorded act, and the impact preview runs before it.

### Reproducibility, against learned relevance weighting

*"Understand which data is more relevant and which is not"* is a learned weight.
It may exist **only as a versioned, snapshot-stamped field**. A weight that
drifts silently between two runs of the same job ends reproducibility, and with
it every refusal that protects a stored quote.

---

## 11. Explicitly not in this design

Named rather than omitted, each with the trigger that should revisit it.

* **The agent on the salesperson's screen.** The agent is for the back-office
  person first. The salesperson's role already hides the overrides list, the
  choice panel, the inspector and the gaps list — every surface agent advice
  lands on. *Trigger: the back-office workspace exists and the agent is trusted
  in it.*
* **The back-office workspace itself.** Identified in
  `docs/visualizations/salesperson-mvp/` as item D, and explicitly warned
  against being derived from the salesperson storyboard. It is a prerequisite
  for this design and is not specified here.
* **Company data import.** §8's own track, and §8's decision narrows it: the
  document half is the Knowledge platform's, so what is deferred here is
  catalogue import, column mapping, the import experience and the price-list
  lifecycle. *Trigger: a real company's real price list.*
* **Suggesting a rule from repeated corrections — and it must never merge on
  similarity.** The product owner asked that corrections be tracked so trends
  can eventually propose rules. The obvious implementation is the one to refuse.
  `conversation.md` T46 §11 and T49 §7 argue it at length, on real data: a
  published row conditioned `{exposure_category: B}` sat beside four siblings
  conditioned `{exposure_category: B, hvhz: false}`, and merging them *"would
  not have produced a slightly worse explanation; it would have produced a
  confident span on a site the other four documents refuse to answer for."*
  **The near-miss is the finding, not noise.** And grouping must use the whole
  key: *"Agreement across scopes is not corroboration; it is five products whose
  approvals happen to state the same number."* So the capability, when built,
  surfaces the **group and its asymmetries** and proposes nothing merged.
  *Trigger: enough corrections that a person cannot see the group by eye.*
* **Cross-team knowledge sharing.** Out of scope by decision. *Trigger: a
  customer with two teams who want to share, at which point HOW is a design.*
* **Registry entries beyond the current six directives.** *Trigger: the first
  advice worth giving that cannot be expressed.*
* **`ExplanationWriter`** — the Tier-2 LLM polish over template prose. Still
  designed and not built, as `docs/architecture/ai-layer.md` records. This
  design does not need it.

---

## 12. What a plan must still decide

Not open questions about *what* to build — those are answered above — but
sequencing and shape, which belong to `superpowers:writing-plans`:

1. Whether the back-office workspace or the agent's first task comes first, given
   that the agent needs a surface and the surface is unbuilt.
2. Which single task is the first slice. The strongest candidate is **ranking an
   existing `ChoiceSet`**: the engine already enumerates the admissible points,
   `offered()` already drops the dominated ones, and the axes and deltas are
   already measured — so an agent that sorts three rows and writes one sentence
   of reasoning **cannot produce an inadmissible fence**, because it was never
   handed the vocabulary to describe one. Judgement without surrendering
   soundness, and the cheapest large capability available.
3. The shape of the session log, which gates §6 and therefore all measurement.
4. Whether the team key lands as its own migration slice or rides with the first
   feature that needs it.

Every slice ends with the product owner opening the app and doing one named
thing. No concurrent agents inside a slice — the mechanism that let the
choice-set feature run away on 2026-09-03, recorded in
`2026-09-04-sales-mvp-design.md`.
