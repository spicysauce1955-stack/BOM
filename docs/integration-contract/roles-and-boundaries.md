# Roles and boundaries — who does which job

```text
Status:     PROPOSED, 2026-09-08, by the Knowledge team. Both dispositions PENDING.
            REVISED the same day, before any reply, against Planning's two agent
            specs of 2026-09-08 (`advisory-agent-design.md`, `agent-framework-design.md`),
            which were written independently and which this document had not seen.
            Four things it got wrong are corrected in place and marked REVISED.
            NOT AN AMENDMENT. It changes no BINDING item and needs no ratification.
Binds:      Nothing, until both sides record acceptance below.
Authority:  NONE at the boundary. `contract.md` is FROZEN at v1.3 and governs what
            crosses. Where this document and the contract touch the same thing, the
            contract wins and this document is the defect. Say so rather than
            working around it.
Purpose:    The contract says what crosses. It deliberately says nothing about who
            does which job. That gap was harmless while there was one consumer and
            one shape; it stopped being harmless on 2026-09-08, when the Knowledge
            side settled a direction that changes what the other side is expected
            to carry.
Reads with: `docs/knowledge-loop.md` (the Knowledge team's purpose and direction)
            and `conversation.md` T46-T55.
```

---

## 0 · Why this exists, and what it must not become

`AMENDING.md` names three things that are **not** amendments; the second is *"anything
internal — pipeline shape, extraction strategy, storage, read models, curation workflow. If it
does not change what crosses, it is not the contract's business."*

This document is the mirror of that clause. It records **which side does which job**, which is
also not the contract's business — and which both sides have nonetheless been assuming, in
writing, differently, for three weeks. Two examples measured this week:

- Planning's `generator.py` falls through to `FALLBACK_MAX_SPAN_MM` because no published table
  has ever matched a run — `[measured]` zero of 6,563 (T51 §2). Neither side owned the join.
- Knowledge published 18 more `Part`s into an unreachable namespace in one session and noticed
  only while writing a commit message (T53 §4). Neither side owned noticing.

Both are role gaps, not contract gaps. The contract was correct throughout.

**The failure mode to avoid:** this document becoming a second authority over the frozen
contract. It has none. If it ever appears to grant, remove or reinterpret a BINDING obligation,
that is a defect in this file, and the fix is here — not an amendment.

---

## 1 · The line, in one sentence

> **Knowledge owns definitions. Planning owns instances.**

That sentence is from `system-overview.md` §2 and predates everything below. It has survived
every reframe and is still the sentence that settles arguments. Everything that follows is an
application of it, not a replacement.

Its corollary, from `docs/superpowers/specs/2026-08-27-unblocking-planning-design.md` §4 and
equally unchanged:

> **No user ever reaches the Knowledge platform directly.** Screens are Planning's; the CLI and
> the API behind them are Knowledge's. Knowledge builds no UI.

---

## 2 · Who owns what

| | Knowledge (fence-rag) | Planning (BOM) |
|---|---|---|
| **Sources** | The document corpus, its extraction and its citations | Its own product catalogue and pricing |
| **Products** | Nothing. **Knowledge is not a parts catalogue** | The products a job is actually built from |
| **What is true** | Values, procedures, conditions, conflicts — all cited | — |
| **What is happening** | — | The map, the job, actions, choices, run state |
| **Method** | The actions the *sources* describe (`Procedure`, `AssemblyStep`) | The commands the *engine* accepts |
| **Geometry** | Published dimensions in thousandths | Placement, fitting, cutting, assembly |
| **The agent** | — | Hosts it. **REVISED:** it *proposes into input slots* and never reaches inside `generate()` — not "commands the engine" as first drafted |
| **A customer's documents** | Ingested, stored verbatim, versioned, never edited, only cited | — |
| **A customer's products** | Nothing | Operational data, keyed by their team key |
| **The person** | Never sees one. A curator reviews Knowledge's own readings | Owns every screen, and decides what any person is shown |
| **Identity of a job** | — | Owns it entirely |
| **Learning** | Relevance, from its own query log | — |

### REVISED — the source/operational split, and where a customer's own material goes

Planning's `advisory-agent-design.md` §8 (decision O3) settles a question this document had
left open and got half-wrong. A company's material divides in two:

- **Source materials** — manuals, price lists, spec sheets, drawings. *"Stored verbatim,
  versioned, never edited, only cited."*
- **Operational data** — the company's products, jobs, layouts, corrections. Live and editable.

That is the answer, and it falls out cleanly: **a customer's documents come to Knowledge**,
because the first bullet is a description of what this platform already is. **A customer's
products stay with Planning**, because they are operational data.

Planning's §4 warning is correct and does not conflict: `TenantId` on the wire is the
*publisher's* axis and **must not be repurposed** as Planning's multi-team key. Those are two
different concepts — `null` there means *Knowledge-global*, not *belongs to no team of yours* —
and both can exist without touching each other.

> **This has a clock on it.** Planning's §8 records *"**Documents** — a provenance record type,
> and **no ingestion of any kind.** This is the largest unbuilt piece of the product goal. **It
> is its own track**."* Knowledge already ingests 146 documents verbatim, versioned, never
> edited, with every published value resolving to a document, page and region. **Before that
> track is scheduled, both sides should decide whether it is a second copy of this one.**

**The most consequential line is the second.** Knowledge holds `mfr/*` identities derived from
manufacturer documents. Planning will carry different products. Neither side can author the
join alone: Knowledge cannot assert what a product *is* in Planning's catalogue without
inventing a product identity, and Planning cannot assert what a manufacturer document *means*.
Both sides agreed at T52 §2 / T55 §3 that **the join is per-job configuration and belongs to
neither of us.**

---

## 3 · The surfaces between us

Three, and only three. Two are new and proposed; one exists and is unchanged.

### 3.1 The snapshot — unchanged, and it stays

A pinned, hashed, content-addressed object, fetched before a run. Planning's own statement of
why is still right and is not being revised: *a planning run is a pure function, so this
platform can be unreachable and a plan from last March still renders the same numbers.*

**Nothing below weakens this.** It is the engine's surface and it stays exactly as it is.

### 3.2 The query — proposed, outward

*"Here is the situation. What applies, how strongly, and on what evidence?"* Returns values
**and procedures**, cited, with conflicts surfaced rather than resolved.

This is a **second** surface for a **second** consumer, not a replacement for §3.1. The engine
wants reproducibility; an agent wants applicability. A query answer names the snapshot it was
computed from, so an agent's advice stays as reproducible as an engine's plan.

**Why it is Knowledge's to serve rather than Planning's to compute:** retrieval here is not
fetch-by-id. It means knowing which condition dimensions apply, that currency comes from the
supersession graph rather than the `version_status` label, that five tables agreeing is
corroboration rather than redundancy. Those rules have been implemented on the Planning side
four times and got subtly wrong each time — T46 §2, T49 §6, T50 §3, T55 §7 — and in every case
Planning found and fixed it themselves. That is not a competence claim; it is a claim about
where a subtle rule should live.

### 3.3 The override — proposed, inward

The only thing that comes back. Four required fields; refused if any is empty.

| Field | Meaning | Who can supply it |
|---|---|---|
| `WHAT` | The value contradicted, **by its citation** — or a whole document (`distrust`) | Planning, from the citation Knowledge issued |
| `WHY` | The reason, verbatim | Only Planning has it |
| `HOW FAR` | Scope: this job / this product / this jurisdiction / always | Only Planning has it |
| `WHO` | The person and their role | Only Planning has it |

`WHY` and `HOW FAR` **cannot be backfilled**. `WHO` and the role can only ever be *asserted* —
Knowledge never observes a person and cannot verify either — which is exactly why they must be
required rather than inferred.

#### REVISED — adopt Planning's five rejection types; this document's `HOW FAR` was not enough

`advisory-agent-design.md` §3 (decision D4) types a rejection five ways, and **only two of them
touch knowledge at all**:

| Type | Means | What happens | Crosses to Knowledge? |
|---|---|---|---|
| `wrong` | the rule is bad | counts against the rule | **yes** |
| `unknown_fact` | a fact was missing, not a bad rule | opens a `Gap` naming the fact; **the rule is untouched** | **yes** |
| `not_here` | right in general, wrong for this job | narrows scope | no — Planning's `scope_restrict` |
| `not_now` | fine, don't bother me | silences on this project; learns nothing | no |
| `my_call` | no right answer, customer's taste | records a preference, never a correction | no |

**This is better than what this document originally proposed, and the difference matters.** The
first draft argued that a single honest `HOW FAR` field encoded the whole taxonomy — *global
scope means "this is wrong", narrow scope means "not here"* — and that categories should be
derived later from the scopes people actually pick.

Scope cannot express `unknown_fact`, and that is the one that counts. A correction made because
**the agent lacked a fact** is not evidence against the rule; routing it to a `Gap` leaves the
rule intact and names what would close it. Under the scope-only design it would have been
recorded as a narrow-scope disagreement and quietly counted against a rule that was never
wrong — the self-poisoning failure this loop was designed to avoid, reintroduced by the design
meant to avoid it.

`not_now` and `my_call` are likewise real and inexpressible as scope, and both correctly stay on
Planning's side.

**So §3.3 narrows: only `wrong` and `unknown_fact` cross.** Three of five rejections never reach
Knowledge at all, which is a cleaner boundary than this document first drew. `HOW FAR` remains
required on the two that do cross, because *"this rule is wrong, everywhere"* and *"this rule is
wrong, for this soil"* are still different claims.

---

## 4 · What each side takes on

### Knowledge undertakes to

1. Publish **values and procedures**, every one resolving to a document, page and region.
2. Serve §3.2, and keep serving §3.1 unchanged.
3. **Surface conflicts, never resolve them.** No silent winner, ever.
4. Report a **blast radius** before accepting a document-level `distrust` — *"this withdraws 30
   values across 9 rules, confirm"* — rather than silently withdrawing evidence.
5. **Never delete.** A distrust is a link pointing at what it withdraws, so a person who was
   mistaken can be un-mistaken.
6. Never write anything into Planning, and never require Planning to model a Knowledge
   internal.
7. Keep `ref_id`s stable, or version them. **This is newly load-bearing:** an override names a
   value by its citation, so an unstable id orphans a person's correction rather than merely
   breaking a citation.
8. Publish the actions the *sources* describe, and never model Planning's command vocabulary.

### Planning undertakes to

1. **Carry Knowledge's citation ids through to a proposal's rationale.** **REVISED — this was
   filed as "the only real new obligation on Planning" and it appears to be free.**
   `agent-framework-design.md` §5.1 already requires every proposal's rationale to be a list of
   tagged `Claim`s, where a `read` or `measured` claim **must** carry `evidence` — a file and
   page or line. A Knowledge `ref_id` is exactly that evidence. So the hook the correction loop
   hangs from already exists in Planning's design, arrived at independently and for a different
   reason. What is left is confirming the two mean the same thing, not building anything.
2. Send overrides with all four fields of §3.3, or not at all.
3. **Assert `WHO` and the role.** Knowledge cannot obtain them by any other route.
4. Decide what any person is shown, and whether a person is asked anything at all.
5. Answer a quarantined batch **as a batch** — Knowledge holds an override's questions until
   the batch is resolved, and releases all of it or none.
6. Own the map, the job, the actions, the commands, and the products.
7. Host the agent, and keep the agent's writes inside Planning.

---

## 5 · What is explicitly NOT owed, so it is not re-proposed

| Not owed | By whom | Why |
|---|---|---|
| Whole job blobs sent to Knowledge | Planning | A private structure that changes on every refactor is not a corpus, it is a liability. Knowledge would hold many incompatible shapes with a specification for none. If Knowledge needs a field, it asks for that field. |
| A response to every command | Planning | It is an override with everything useful stripped off — no reason, no scope, no author. The override already carries all of it, explained. |
| A model of Planning's commands | Knowledge | Knowledge publishes the actions the sources describe; the agent maps them. Coupling to a vocabulary still being designed is the one move worth avoiding. |
| A usage/feedback channel | Planning | Knowledge serves the queries, so it can count them itself. Relevance is measurable on Knowledge's side alone. |
| A UI, of any kind | Knowledge | §1's corollary. Unchanged since 2026-08-27. |
| A product mapping | Either side alone | Neither holds both endpoints (§2). |

---

## 6 · What would reopen this

Named now so that neither side has to re-derive them.

- **The agent moving out of Planning.** §2 and §3.2 both assume it is hosted there. If it moves,
  the query's authentication, tenancy and rate story all change.
- **A second Knowledge consumer.** Everything here assumes one counterpart. A second one makes
  "Planning decides what is shown" insufficient as a rule.
- **Knowledge acquiring products of its own**, or Planning wanting Knowledge's `mfr/*`
  identities to *be* its catalogue. Either collapses §2's second row and this document with it.
- **A person reaching Knowledge directly** — a curator console exposed to a customer, say. §1's
  corollary would no longer hold.
- **Overrides needing to write into evidence.** The current rule is that they never do; they are
  read at query time and win on contradiction. If that ever has to change, it is a change to
  what an override *is*, not a tuning.

---

## 7 · Dispositions

Neither side has accepted this. It binds nothing until both entries below are filled in, in
writing, in this file — the same standard `AMENDING.md` §5 sets for an amendment, applied here
by choice rather than by requirement.

- **Knowledge team:** PROPOSED, 2026-09-08. Filing is not acceptance.
- **Planning team:** **ACCEPTED, 2026-09-08**, with two notes, neither of which
  is a modification. Reasoning in `conversation.md` T58 §5.

  **Accepted as written:** §1 and its corollary. §2's ownership table, including
  the REVISED source/operational row — settled by our product owner the same day:
  **a customer's documents go to Knowledge; the products and prices read out of
  them stay with Planning**, along with catalogue rows, the import experience,
  column mapping and the price-list lifecycle. §3.1 unchanged. §3.2, a served
  query for an agent, on the Knowledge side's own condition that the answer names
  the snapshot it was computed from — the agent sits outside the pure-function
  cordon by construction, so `build-plan.md` §1 is untouched. §3.3's four required
  fields and the narrowing to `wrong` and `unknown_fact` only. §4's Knowledge
  column. §5's not-owed list. §6's reopening triggers.

  **Note (a) — §4 Planning item 3, `WHO` and the role.** Accepted as an
  obligation; **unmet today, and an override from Planning must be treated as
  unattributed until Planning says otherwise.** This document is right that `WHO`
  can only ever be asserted, which is why the gap matters: the assertion is the
  whole guarantee. `[measured]` `author` is a plain defaulted string on
  `Correction`, `Override` and `Annotation` and on eleven API routes as a
  caller-supplied request parameter; no authentication exists in `api/app.py`;
  `js/role.js` is a 137-line presentation preference that models nobody.

  **Note (b) — §4 Planning item 5, the quarantined batch.** Accepted in
  principle, **unspecified and unbuilt on Planning's side.** `[read]`
  `learning/review.py` reviews one candidate at a time and there is no batch
  concept in the correction path. Recorded so the acceptance is not read as a
  capability; if holding a batch has a required wire shape, Knowledge should
  propose it.

  **§2's clock is answered and replaced by a dependency.** The document-ingestion
  track will not be a second copy of the Knowledge store. In exchange, Knowledge's
  `owner_tenant` carrying a real row is a **precondition for the first customer
  document** — all 146 documents are `owner_tenant = NULL`, i.e. shared, and a
  customer's price list must not be. Planning asks to be told when that changes,
  and is not asking for a date.

**REVISED — what the Knowledge side would like shot at, after reading Planning's two specs.**
The first draft's headline ask has withdrawn itself; these replace it.

1. **The document-ingestion track (§2's clock).** The most urgent item here, because it is the
   only one where waiting costs work rather than clarity. Planning's §8 schedules a
   source-material store that is verbatim, versioned, never edited and cite-only. Knowledge is
   that store, with 146 documents in it. Decide whether the track is a second copy **before it
   is scheduled**, not after.
2. **§3.2** — whether a served query is acceptable at all, given that `build-plan.md` §1 argues
   for a pre-fetched immutable object *"rather than queried"*. The Knowledge reading is that
   both are right for different consumers: the engine gets the snapshot, an agent gets a query
   whose answer names the snapshot it was computed from. If Planning reads the pure-function
   property as excluding a live query even for an agent, that disagreement should surface here
   rather than in an implementation.
3. **Whether a Knowledge `ref_id` is admissible as a `Claim.evidence` value** (§4 Planning
   item 1). If yes, the correction loop's hook is already built on both sides and nobody owes
   anybody anything. If Planning's grounding check in `agent-framework-design.md` §6 must
   *re-execute* a `read` claim against its own view, then a `ref_id` pointing into Knowledge is
   not re-executable on Planning's side, and that needs a mechanism rather than an assumption.

**Withdrawn from the first draft, recorded so the change is visible:** the claim that carrying
citation ids was a new cost on Planning, and the argument that a single `HOW FAR` field made a
rejection taxonomy unnecessary. Both were wrong, and Planning's independently-written specs are
what showed it.
