# Amendment 005 — §1.4's tie-break is not a total order, and cannot be made one as worded

```text
Obligation   §1.4, the BINDING tie-break paragraph, as amended by 002 and ratified in v1.2.
Trigger      B — unimplementable. The rule cannot be built as written; the mechanism that
             fails is named and executed below. D applies too: the chain is also
             INCOMPLETE, and the first real snapshot contains a pair that exhausts it.
Filed by     Planning & BOM, 2026-08-30, on building the step 002 unblocked
Status       FILED. Governs nothing until ratified (AMENDING.md §3 step 2).
Note         This amends wording WE proposed in 002 and both sides ratified twelve hours
             earlier. That is not a reason to soften it. The defect is only visible from
             inside an implementation, which is exactly what nobody had when 002 was cut.
```

## What v1.2 says

`contract.md:363-366`, BINDING:

> Ranks are unique within a task row. Where an operator's edit creates a tie, resolution
> breaks it by higher `curation_level`, then later `issue_date` where both carry one
> (§1.1 `Date`), then lexicographic `source_class` — deterministically, and never
> silently preferring an older document.

The clause `where both carry one` is 002's, added to respect §1.1's null rule. It does
respect it. It also makes the ordering **intransitive**.

---

## Defect 1 — the rule admits a cycle

Three candidates, tied on `rank` and `curation_level`, compared by the paragraph's own
words, pairwise:

| | `source_class` | `issue_date` |
|---|---|---|
| A | `industry_standard` | `iso: null` |
| B | `sealed_approval` | 2024-01-01 |
| C | `company_authored` | 2020-01-01 |

- **A vs B** — not both carry a date → lexicographic: `industry_standard` < `sealed_approval` → **A**
- **B vs C** — both carry one → later wins: 2024 > 2020 → **B**
- **C vs A** — not both carry a date → lexicographic: `company_authored` < `industry_standard` → **C**

**A beats B, B beats C, C beats A.** Executed rather than argued: a comparator worded
exactly as §1.4 words it, run over all six permutations of {A,B,C}, returns **all three**
as the winner depending on input order — `{sealed_approval, industry_standard, company_authored}`.

That is precisely the outcome the paragraph's own last sentence forbids. *"Two
implementations could both honour the policy, stamp different `admitted_by.rank`, and hash
differently"* — here **one** implementation does it, twice, on the same set.

### Why no implementation can rescue it

The failure is structural, not a coding problem.

*"Where both carry one"* is a **pairwise** predicate: whether the date step fires depends
on which two candidates are being compared. A sort key, by construction, is computed for
each candidate **alone**. A pairwise predicate that is not a total preorder therefore
cannot be expressed as a key — and this one is not, as the cycle shows.

The obvious escape is to give a null date a position in the key. Every position is either
before all dates or after all dates, i.e. **earliest or latest** — and §1.1's BINDING
paragraph forbids both by name:

> A `null` `iso` is never ordered, and **never treated as earliest or latest.**

So the two BINDING paragraphs, both ratified in v1.2, cannot both be satisfied by any
key-based resolution. That is the trigger-B mechanism, stated exactly.

**This is the default path, not a corner.** 72 of the 75 source documents in `3ae88642`
carry no `issue_date`. Mixed dated/undated candidate sets are the normal case; fully-dated
sets are the rarity.

## Defect 2 — the chain is incomplete, and real data reaches the end of it

When all four criteria tie, §1.4 gives no further instruction and no winner.

`3ae88642` contains the pair. Its two competing footing authorities are both
`sealed_approval`, both `curation_level: 2`, both admitted at rank 1 for
`structural_parameter`:

| `content_hash` | `version_status` | `issue_date` |
|---|---|---|
| `f650c3f1…` | unknown | `04/24/2025` |
| `1c487c73…` | superseded | absent |

Same rank, same curation, not both dated (so the date step is skipped under any reading),
same `source_class`. The chain ends. Whatever resolves them is each implementation's
invention — and one of the two orderings **prefers the superseded document**, which is the
outcome the paragraph names as the thing it exists to prevent.

---

## Proposed text

Replace the BINDING paragraph at `contract.md:362-368` with:

> **BINDING.** Ranks are unique within a task row. Where an operator's edit creates a tie,
> resolution breaks it by higher `curation_level`; then, **only where every tied candidate
> carries an `issue_date`**, by the later `issue_date` (§1.1 `Date`); then by lexicographic
> `source_class`; then by lexicographic `SourceDoc.content_hash`. Each step is a total
> order over the set that reaches it, so the result never depends on the order candidates
> were collected in — deterministically, and never silently preferring an older document.
> Where the tied set is not wholly dated the date step does not fire at all: a `null` `iso`
> is never ordered, and skipping the step is the only treatment of it that is neither
> "earliest" nor "latest".

Two changes, and they are separable if the Knowledge team wants only one:

1. **`where both carry one` → `only where every tied candidate carries an issue_date`.**
   All-or-skip is the sole reading that is a total order. It is also the reading that keeps
   the null rule intact rather than trading it away.
2. **A final `content_hash` step.** It terminates the chain on a value every `SourceDoc`
   already has, that both sides can compute, and that is stable across re-cuts of the same
   document. `content_hash` rather than an arbitrary label, so two implementations agree.

## Cost

**Knowledge:** none. No published shape changes; `content_hash` is already on every
`SourceDoc` and already required by §1.2.1's closure rule.

**Planning:** none beyond what is built. `fenceai/knowledge/source_policy.py` implements
exactly the proposed chain today, with the all-or-skip reading recorded in the docstring
as a reading pending this amendment, and a local final key. If this is ratified as
proposed, one comment changes and the local key becomes the contract's. If it is
ratified differently, the change is confined to one function with five tests on it —
including one asserting all six permutations of {A,B,C} produce one winner.

## In-flight

Nothing breaks. `resolve()` has no non-test caller: item 6's wiring into `expand()` is the
first, and it is deliberately not started until this settles — building an admissibility
decision on an ordering known to be non-deterministic would record `admitted_by` on runs
and make it look decided.

## What Planning did in the meantime, so it is on the record

We did **not** implement the paragraph as literally worded, because doing so would have
produced a cycle in live code. We implemented the all-or-skip reading and said so in the
docstring, citing this amendment. If the Knowledge team's disposition prefers the other
reading, we change it. We would rather have the argument here than have two teams each
quietly pick a reading and discover it through a hash mismatch.

---

## Disposition — Knowledge Platform, 2026-08-31

```text
Verdict   ACCEPT, as proposed.
```

**Defect 1 checked by hand, not taken on report.** Re-ran the three pairwise
comparisons against the ratified §1.4 wording: A/B not both dated →
lexicographic, `industry_standard` < `sealed_approval` → A. B/C both dated →
later wins, 2024 > 2020 → B. C/A not both dated → lexicographic,
`company_authored` < `industry_standard` → C. A beats B, B beats C, C beats
A — the cycle reproduces exactly as filed. The general argument is also
right and not specific to this triple: a comparator whose *choice of
criterion* depends on which pair is being compared is a pairwise predicate,
not a per-candidate key, and nothing requires a pairwise predicate to be
transitive. `where both carry one` is exactly such a predicate. Confirmed
independently that no per-candidate key can rescue it while also honouring
§1.1's null rule — every position for a null date is earliest or latest, and
both are forbidden by name.

**All-or-skip is the only reading consistent with both BINDING paragraphs**,
for the reason filed: it is a real total order over the full set (the date
step either applies to everyone being compared or nobody), and it never
assigns a null date a position relative to a real one. Accepting without a
counter-proposal — we don't have a third option that keeps both guarantees.

**The `content_hash` step is accepted with its actual guarantee understood,
not a stronger one.** It terminates the chain deterministically, which is
what §1.4's own stated reason for existing asks for — *"two implementations
... hash differently"* is about reproducibility, not about the exhausted
case always preferring the newer document. Defect 2's pair (both
`sealed_approval`, one `superseded` with no date, one `unknown` with a
date) still reaches `content_hash` once the date step is skipped for not
being wholly dated, and content_hash ordering has no relationship to
recency — so the exhausted case can still rank a superseded document ahead
of its replacement, deterministically, on both sides now, rather than
arbitrarily on each. That is a real gap in what the tie-break can promise,
not one this amendment claims to close, and not one we're asking you to
solve here: `version_status` already exists as the axis meant to prevent
this pairing from tying in the first place (contract.md §1.4's own BINDING
paragraph on it), and if it isn't currently being used to separate
`superseded` from `active`/`unknown` at the `rank` step, that's an operator
configuration question, not a tie-break defect. Named so nobody reads
"content_hash added" as "the superseded-document problem is now solved."

**Verified against our own side.** `fence_evidence` implements no part of
§1.4's resolution chain — `grep` across the package for the tie-break
mechanism returns nothing; `admitted_by`/rank resolution is entirely
Planning's engine. "Cost: none" is accurate, not assumed.
