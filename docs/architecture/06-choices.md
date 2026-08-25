# 06 — Choices

Why the system is shaped this way. Each entry states the choice, what it buys, **what
it costs**, and when it would be right to revisit. A choice with no stated cost has
not been thought about.

---

## Determinism over intelligence

**Choice.** `generate()` is a pure function. Same topology, knowledge, catalog,
models and overrides ⇒ same fence, same run id. No AI anywhere in the calculation
(ADR-0004, ADR-0009).

**Buys.** Reproducible quotes. A run-id content hash that means something. The
portfolio impact preview — *"this rule change would affect N of your projects"* —
which is only possible because every project can be regenerated and diffed. 155
golden scenarios as a release gate. A decision graph that is the actual causal
record rather than a plausible reconstruction.

**Costs.** Every piece of judgement must be expressed as data before it can be used.
There is no "the model will figure it out" escape hatch — a new kind of reasoning
means a new rule type, a new action, or a new schema field, all of which are work.

**Revisit when.** Never for selection or placement. The right place to widen AI is
the *input* side: text → typed intents is thin today, and `ObstaclePayload` is
authored by nobody and read by nothing.

---

## Rules as data, in one owned evaluator

**Choice.** Knowledge is typed, versioned objects with a **closed** condition AST and
an evaluator this project owns (ADR-0005). No rule exists only in a prompt. No second
evaluator exists anywhere.

**Buys.** Rules are reviewable, diffable, testable (`RuleExample` is executable), and
explainable — a `defeated` edge can cite the losing version because both were
evaluated by the same machinery. Precedence is one algorithm: authority → specificity
→ recency.

**Costs.** The AST is deliberately not Turing-complete, so genuinely novel logic
needs a new node type rather than a clever expression. Authors work through a
sentence-style builder or an Advanced-JSON escape hatch, neither of which is as
expressive as code.

**Consequence worth naming.** Because there is one evaluator, a model's layout
requirements enter it as *contributions* scoped `series=<model_id>` rather than
through a private channel — which is what keeps a manufacturer maximum a hard
constraint and a nominal width a beatable preference.

---

## Four kinds of "should", never collapsed

**Choice.** Hard constraint ≠ preference ≠ objective ≠ override. Distinct types,
distinct code paths.

**Buys.** The same safety check can *stop* a job under a `hard_constraint` and merely
*warn* under a `company_rule`, so a jurisdiction pack changes behaviour with no code
change. A hard tie between two rules **we** authored is a `GenerationFailure` rather
than a silent coin flip; one touching a **published** row is a `Conflict`, because
contract §3.2.4 forbids failing a run over something only the other team can fix.

**Costs.** Four things to get right whenever a new rule is added, and a real
authoring burden: someone must decide which kind a number is. Getting it wrong
produces either an unbeatable preference or a beatable safety limit.

---

## Integer millimetres and cents at rest

**Choice.** All persisted geometry is integer mm; all money is integer cents. Float
only transient. Exactly **two** named tolerances, both in `core/units.py` (ADR-0002).

**Buys.** Content hashing works. Two call sites cannot differ by a rounding. A cut
list adds up.

**Costs.** Conversion at every boundary — the display-unit layer exists entirely to
pay this cost, and rate pricing needs one declared rounding point
(`purchase_price_cents`) that nothing upstream or downstream may re-round.

---

## The decision graph *is* the explanation

**Choice.** Prose is rendered from the graph via per-language templates. The graph is
built **during** generation, append-only, acyclic by ordinal (ADR-0006).

**Buys.** Explanations cannot drift from behaviour, because they are the same
structure. "Click anything to see why" works for every element, requirement and BOM
line. `en` and `he` templates are key-identical by test.

**Costs.** Generation code must remember to emit nodes at the right moment with the
right scope; a node emitted after the thing it explains can only share a scope tag,
and a shared scope is not a chain anything can walk. Several review rounds have been
spent fixing exactly that.

---

## Read models derived, never stored

**Choice.** `StructureReport` and `PanelElevation` are pure functions of
`(topology, strategy, requirements, bom)`. They obtain parts by **inverting** pegs and
are forbidden from recomputing a quantity.

**Buys.** Σ(parts) ≡ BOM holds by construction. There is no cache to invalidate and no
second source of a number.

**Costs.** They must refuse rather than adapt: a report laid out over an edited
topology is a 409, not a best effort. And a read model that is a function of mutable
inventory needs something recording that fact — hence `inventory_hash`.

---

## Optimise honestly, not maximally

**Choice.** First-fit-decreasing cut planning with kerf and remnant-first bins, plus
a **proved lower bound** (`max(lp_bound, counting_bound)`) and a `certified_optimal`
flag. No CP-SAT (ADR-0007).

**Buys.** Fast, explainable, and truthful: a provably optimal plan is not called
heuristic, and no solver vocabulary reaches a BOM line.

**Costs.** Some plans are optimal and cannot be *proved* so. Arc-flow over multiple
stock lengths and sources remains unbuilt (phase 3).

---

## SQLite, one connection, serialized

**Choice.** SQLite with documents as JSON columns, and every `Store` method wrapped
in a re-entrant lock held for the whole call (ADR-0008).

**Buys.** Zero-configuration, single-file, trivially reproducible for tests and demos.
The lock closed a class of live 500s and, worse, silently interleaved read-then-write
sequences.

**Costs.** Single writer, single process, no multi-tenancy. Route-level
read-then-write is still a TOCTOU window, and the ADR says so rather than implying
the problem is solved. Postgres is the V2 trigger.

---

## No build step on the frontend

**Choice.** Native ES modules, SVG, bundled fonts, no framework, no CDN (ADR-0010).

**Buys.** Nothing between the source and the browser. No toolchain rot on a project
whose lifetime is measured in years. A strict content policy is trivially satisfied.

**Costs.** No component model and no type checking across module boundaries — which
is why the JS vocabularies are pinned against the Python ones by node tests in both
directions, and why the browser smoke suite is a release gate rather than a nicety.

---

## Refuse the half-built feature by name

**Choice.** A schema field the resolver does not honour is **rejected at load**, with
the reason, in `_UNSUPPORTED` (`fencemodel/model.py`).

**Buys.** A deferral cannot read as a working feature. The table has caught real
defects in both directions — a field only demo data wrote became dangerous the moment
an authoring UI put it in front of a person.

**Costs.** Authors meet refusals for things the schema visibly supports, which reads
as arbitrary until you read the message. The messages are therefore long on purpose.

**The rule that makes it work.** Deleting an entry and changing the resolver are the
**same commit**.

---

## Hebrew first, English second

**Choice.** The app opens in Hebrew. Locale bundles must keep identical key sets; CSS
uses logical properties only; drawings are never mirrored.

**Buys.** The market this ships into is served first rather than retrofitted. Bugs
that only appear in RTL surface immediately.

**Costs.** Every user-visible string, warning code, enum value and role word needs
two entries before it can ship, enforced by test. That is friction on every feature —
and it is the cheapest moment to pay it.

---

## Generation stays behind a button

**Choice.** Nothing auto-generates. Typing a dimension re-prices a *preview*; it never
lays out a fence.

**Buys.** The user always knows which numbers are the run's and which are a
hypothesis. The cost strip names both figures rather than switching one figure's
meaning underneath the reader.

**Costs.** An extra click, and a stale-run state the UI has to represent honestly.

**Standing.** This was proposed as an ease-of-use improvement and **rejected by the
user**; the smoke suite counts a project's runs across a dimension change to prove it
never fires.

---

## What V1 deliberately defers

A deferral is a choice too, and it belongs next to the others rather than in a list of
its own. Each of these is absent on purpose; the trigger is what would make it right.

| Deferred | Trigger to revisit |
|---|---|
| Multi-user, auth, concurrent editing | A second simultaneous estimator |
| Postgres | The same trigger — SQLite is one writer, one process (ADR-0008) |
| Embeddings / semantic search | Knowledge bases past the size a person can scan |
| CP-SAT and arc-flow cut planning | Plans FFD leaves provably far from the bound (ADR-0007) |
| 2D sheet cutting | A model whose infill is cut from sheet rather than from bar |
| Arcs in plan geometry | ADR-0003 reserves `segment_kind` for it |
| IFC export | A customer who consumes one |
| Reservation / ATP beyond flags | Inventory that more than one job draws down at once |

**Portfolio impact preview left this list.** It is shipped — `learning/impact.py`,
`preview_impact` / `preview_model_impact`, reporting `projects_checked` and
`projects_affected` — and runs synchronously inside the review endpoint, over one
process and a serialized store. That is a real scaling limit, and it is recorded in
`docs/v1-known-limitations.md` rather than by leaving a deferral list claiming the
feature does not exist. A stale deferral reads as a missing feature, which is the more
expensive of the two mistakes.
