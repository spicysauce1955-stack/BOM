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
