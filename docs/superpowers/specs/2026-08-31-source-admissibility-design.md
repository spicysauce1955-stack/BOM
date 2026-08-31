# Judging a published fact before using it, and showing what backed it

**Date:** 2026-08-31 · **Status:** BUILT. §10 records where the build corrected
the design.
**Contract:** §1.4 (source policy), obligations §3.1.6 and §3.3.2
**Build-order:** item 6

---

## 1 · The problem, in one paragraph

The Knowledge Platform sends us facts — *"post holes must be 30 inches deep"* —
each with a note saying which document it came from and whether a **person** has
checked it against that document, or whether software merely scraped it. Today we
use every fact we are handed, no questions asked. That is wrong in a specific and
expensive way: a footing depth nobody has verified should not quietly decide how
deep somebody digs, and a plan that used one should say so on its face.

## 2 · What changes for the person holding the plan

That is the whole point of this slice, so it goes first.

**Today:** a plan says *"posts at 2235 mm."* Nothing says who decided that.

**After:** the same line can say *"posts at 2235 mm — sealed engineering
approval, checked by a person."* And where the source was not good enough, the
plan says that instead: *"posts at 1800 mm — we did not use the manufacturer's
2235 mm because nobody has verified it against the page."*

The second sentence is the one that matters. A number the system declined to use,
with the reason attached, is the difference between a tool that hides its doubts
and one an expert can correct.

## 3 · What "good enough" means, and who decides

Not us. The contract carries a table (§1.4) saying, for each **job**, which kinds
of document may back a value and how well checked they must be. It is data an
operator configures, not logic. We already hold it, tested, in
`knowledge/source_policy.py`; it has simply never been connected to anything.

The rule that bites here: **anything structural** — how deep to dig, how far
apart posts may go — must have been checked by a person against the source page.
Software extraction alone is not enough. A product description has no such bar,
because getting a colour wrong is not dangerous.

## 4 · The four steps

**Step 1 — judge each row as it becomes knowledge.** `expand()` already turns a
published row into a rule. It now first asks the policy whether the row's source
is admissible for the table's declared job. `expand()` gains an optional policy
argument; passing nothing keeps today's behaviour, so every existing caller is
untouched.

**Step 2 — a rejected row becomes a gap, never a silence.** No rule is produced,
and one of two notes is recorded, because they send a person to different work:

- *this kind of document may never back this job* → find a better document
- *this document is fine, nobody has checked it* → have a reviewer check it

**No new fallback machinery is needed.** A rejected row simply does not exist,
and the generator's existing *"nothing covered `max_span_mm`"* path already
handles that honestly — a conservative fallback, a gap, and a warning on every
bay built to it. That path was built for exactly this shape of hole.

**Step 3 — carry the verdict with the facts.** `KnowledgeBase` already travels
into `generate()`. It gains `admitted`, a verdict per fact. **No function
signature changes**, and `generate()` stays pure — the verdict is computed at
ingest and threaded read-only, like every other input.

**Step 4 — show it.** The decision graph already puts a `knowledge_version` node
on every fact that governed a decision, and every edge already carries that
fact's ref. The verdict joins onto that existing ref and renders there. Nothing
new is invented in the graph; an existing node gains a field.

## 5 · The one genuinely new question

A fact can cite **more than one document.** Measured: 8 of the 16 rows in the
first real snapshot cite two.

So there are two different questions, and conflating them would be the mistake:

| Question | Answered by |
|---|---|
| **Within one fact** — which of its citations makes it usable, at what rank? | the source policy (new here) |
| **Between facts** — which fact wins for this site? | the evaluator (unchanged) |

Using the policy to choose *between* facts would build a second selection engine
beside the evaluator. That is the one thing this repo's knowledge design exists to
prevent: two mechanisms answering the same question eventually disagree, and
neither can explain the other. **The policy scopes strictly down, into a single
fact's own sources.** How facts compete does not change.

## 6 · Two decisions taken

**An unrecognised job: use the fact and flag it.** Jobs arrive as free text; our
list is closed. If a table names a job we do not know, rejecting its rows would
punish their data for a gap in *our* list. So the rows are used and a gap records
that we could not judge them — `closes_by: planning`, because the fix is a
registry entry here. The value is used; the hole is visible.

**Show it on the plan now, not later.** Step 4 is in scope.

## 7 · What this deliberately does not do

- **No operator UI for the policy table.** `SHIPPED_DEFAULT` is used, and the
  policy is already a parameter, so configuring it later needs no redesign.
- **No re-ranking of the shipped table.** Settled separately on 2026-08-31.
- **No `paired` value support.** Nobody publishes one; a named seam, not a stub.

## 8 · How we will know it works

The conforming fixture splits two ways on purpose, which makes one change
exercise both paths:

| fact | job | checked? | expected |
|---|---|---|---|
| `max_span_mm`, 3 rows | structural | **no** | **rejected** → fallback + warning |
| `slope_method` | installation step | no | **admitted** — no bar for that job |

**A golden scenario number moves**, intentionally: `max_span` falls to the
fallback. That goes through the `golden-scenarios` skill, not an edited expected
value.

**Against the real snapshot, nothing changes.** All 16 rows are stamped
engineering approvals checked by a person, so all 16 are admitted at the top
rank. A gate whose first act was to reject real data would be a gate with the
wrong bar; this one agrees with the data that exists.

## 9 · Files

| File | Change |
|---|---|
| `knowledge/parameters.py` | judge rows; two gap builders |
| `knowledge/snapshot.py` | pass the policy and the document index |
| `knowledge/model.py` | `KnowledgeBase.admitted` |
| `decisions/graph.py` | the verdict on the existing knowledge node |
| `web/static/js/` + both `i18n` bundles | render it; two new codes in en **and** he |
| `tests/` + `tests/scenarios/` | per step, plus the golden number |

---

## 10 · What the build corrected

Recorded because a design that is quietly wrong in two places and shipped
anyway teaches the next reader nothing.

### 10.1 · Validity had to be judged BEFORE admissibility, not after

§4 put the policy gate first and returned early. That masked a real fact: the
fixture's `max_span_mm` row 2 is **both** unchecked **and** backed by an NOA that
expired in 2025. Rejecting on the source and stopping reported only *"a reviewer
should check this against the source image"* — which sends a reviewer to open a
crop for a document that lapsed two years ago.

That is exactly the wasted bounded work the review queue exists to avoid, so the
two checks are now independent: *"is this authority in force?"* and *"is this
source good enough?"* are different questions about the same row, and a row can
fail both. Both are reported.

### 10.2 · The golden number did not move

§8 predicted a golden scenario would change. **None did**, and the reason is
worth keeping: the scenarios build knowledge with `demo_knowledge()`, which is
authored. Authored knowledge has no provenance, so there is nothing to judge and
nothing changes. The prediction was wrong in the safe direction, and the
`golden-scenarios` skill was not needed.

The behaviour is instead pinned directly, over the fixture, by
`test_the_fixtures_own_rows_fall_back_when_unchecked`.

### 10.3 · Two smaller things

**The verdict key had to be `KnowledgeVersion.ref`**, not a rebuilt string. It
was first written as `OBJ@N` where the graph's `governed_by` edges use `OBJ@vN`,
and the symptom was a verdict that silently reached no graph node at all —
suite green, feature absent. Both sides now go through the one property.

**Two of the three new warning codes were invisible to the locale guard.** It
finds codes by scanning for `code="..."` at the emitting site, and these arrived
as a variable returned from `explain_rejection`. They are now written as literals
at the gap site. A code the guard cannot read is a code that reaches a screen as
its own key in both languages.

## 11 · What is still deferred, and where the seam is

- **`paired` values** — `SUPPORTED_HIT_POLICIES` and `value_type` parsing are the
  seam; nobody publishes one yet, and the open question is where a choice set
  lives (an optimiser objective, not a fact).
- **Operator-configured policy** — `ingest(snapshot, policy=...)` and
  `expand(..., policy=...)` are already parameterised; only storage and a UI are
  missing.
- **`Interval` consumption (amendment 007)** — ratified, unbuilt on both sides.
  Until it lands, the real snapshot's 16 rows still condition on a bracket
  nothing binds, so they are inert regardless of admissibility.

---

## 12 · What an adversarial review found after it shipped

Two of these were safety-relevant and both were mine. Recorded in full, because
a design doc that only lists what went right is a design doc nobody consults.

### 12.1 · The fallback was not conservative — the gate made plans LESS safe

§4 step 2 said the generator's existing "nothing covered `max_span_mm`" path
"was built for exactly this shape of hole." **It was not.** That fallback is
conservative relative to **silence**. "A source we have not verified told us
858 mm and we declined to believe it" is not silence, and treating it as silence
took the number the wrong way:

| site | source said | before the fix | after |
|---|---|---|---|
| exposure C | 1219 mm | **1500 mm bays** | 858 mm bays |
| exposure C, HVHZ | 914 mm | **1500 mm bays** | 858 mm bays |

**The defect is general, and the first row is the one that matters.** In the
ordinary case the slice laid out bays 25% wider than the document it had just
refused; the HVHZ row is the same defect louder, not a different one. An earlier
draft of this section led with the hurricane figure, which overstated the
scope — the bug had nothing to do with which conditions were in play.

Worth recording alongside it: the 914 mm HVHZ row is in **our fixture**, which we
wrote. All four tables in the first real snapshot declare `hvhz` in their domain
and **no row conditions on it**, so nothing published exercises that case. Citing
it as evidence was citing our own test data.

`FALLBACK_MAX_SPAN_MM`'s own note already forbade the widening: *"a fallback
that guessed WIDER would be a fallback that could fall down."*

**Fix.** A refusal now carries the declined value (`declined_mm`) and the
source's own lexeme, `ingest()` gathers them per parameter onto
`KnowledgeBase.declined`, and the span resolver takes
`min(FALLBACK_MAX_SPAN_MM, declined)`. **Declining to trust a number is not the
same as believing the opposite**: an unverified claim that something is unsafe is
still evidence about risk, so the most restrictive thing anybody said stands as a
ceiling while backing no line and winning no tie. It gets its own basis
(`declined_bound`) and its own code (`declined_max_span`), because filed under
`uncovered_max_span` it would read "no rule states this" — false, and false in
the direction that hides a refusal.

**Known cost, accepted:** the bound is the minimum across all refused rows, so a
run is held to the strictest limit any refused row stated, whatever conditions it
was scoped to. Matching conditions first would mean
selectively trusting data we refused. A fence built tighter than it needs to be
stands up; this repo already prefers that trade.

**Direction is not general** — lower is safer for a span limit, higher for a rail
separation — so nothing interprets `declined`; it sits beside the hard-tie
handling, at the site that knows its own parameter.

### 12.2 · A registry addition took down the whole snapshot

§2 of the contract guarantees new source classes need no ratification. But
judging a row builds a policy `Candidate` whose `source_class` is a closed
`Literal`, so a snapshot naming an unregistered class loaded fine at the door and
then raised a raw `ValidationError` inside `ingest()` — losing 4 tables, 289
warnings and 81 gaps because the other team registered a word. §1.4 records that
two classes were added in its own last revision, so this was the expected case.

The asymmetry is the embarrassing part: the design agonised over the unknown
**task** registry and then made the unknown **class** an unhandled exception.
Now both decline to judge and report it.

### 12.3 · The rest

- **A verdict could be misattributed.** `_object_id` is unique within a table,
  not across tables, so two unscoped tables for one parameter let the second's
  verdict describe the first's number — "backed by a spec sheet" printed about a
  sealed approval's value. A collision now drops **both** verdicts and reports
  it: claiming neither is the only honest option when we cannot tell which is
  which.
- **Obligation 3 was unenforced.** A row with no citation at all was admitted
  silently, so the chip claimed "checked by a person" with nothing to click
  through to. Still judged — the axes are all on the row, and refusing to judge
  would make an uncited row *more* admissible — but now reported.
- **`dependents_of_knowledge` was broken by our own id change.** It split on the
  first `@`, and a published object_id now contains one, so impact analysis
  returned nothing for the real id and everything for the bare parameter name.
- **The per-model knowledge view dropped every verdict**, because it rebuilt
  `KnowledgeBase(versions=...)` instead of copying. `model_copy(update=...)` now.
  The same trap then bit the new test that was supposed to catch 12.1.
- **A test whose assertion could not fail.** `all(width <= FALLBACK_MAX_SPAN_MM)`
  is true for 1500 by construction, and it was the assertion standing where
  12.1 should have been caught. It now asserts against the declined bound.

## 13 · Still open, deliberately

- **The verdict is not persisted.** `store/db.py` returns a base with `admitted`
  empty, and `KnowledgeVersion` keeps no provenance, so a reloaded run can
  neither read the verdict back nor re-derive it. The seam is
  `(snapshot_id, ref) → AdmittedBy` stored beside the versions.
- **`ingest()` has no production caller.** The published path is test-only, so
  the chip cannot appear in the app yet. That is the next wiring, not this slice.
- **A published row used unjudged is indistinguishable from an authored one** on
  the plan: the graph payload carries no `origin`. Three states, two renderings.
- **`policy_version` is never stamped on a run.** Once the operator-policy seam
  lands, two runs with identical knowledge and different policies would be
  indistinguishable.
- **A refusal reaches no `defeated` edge.** Removing a row before the evaluator
  changes which facts compete, and the graph cannot say the policy did it.
