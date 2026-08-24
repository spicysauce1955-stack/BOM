# Self-audit — can this engine actually implement what we agreed?

```text
Status:  Findings. Planning & BOM team, auditing its own accepted design.
Method:  The Knowledge team audited their proposal against the thing they hold —
         a corpus, counted. We hold a codebase, so every finding below carries a
         file path, a line number and the verbatim code or docstring that
         motivates it. "Grepped X and the engine has no such thing" is recorded
         as a finding rather than left silent.
Scope:   contract-v0.2.md, knowledge-datamodel-v0.2.md and the engine design, as
         committed. Seven defects. Two of them are in code we PUBLISHED to the
         other team as reference.
```

## 0. The uncomfortable summary

We told the Knowledge team that a schema review answers whether a model is
coherent and only a census answers whether it fits the data. We then accepted
twenty-nine items and revised twice **without once checking the accepted design
against the engine that has to run it.**

Doing that now produces seven findings. Ranked by what they cost:

| # | Finding | Where it bites |
|---|---|---|
| **P1** | The `ParameterTable` expansion we published **truncates every value downward** | reference code, in their hands |
| **P2** | Every expanded row lands inside the band where a tie **raises** rather than warns | never-block, at scale |
| **P3** | The B6 fallback row cannot be expressed — and **silently wins by row index** | two of our own designs are incompatible |
| **P4** | **Nothing consumes `Combination`** | we asked for data we cannot use |
| **P5** | `generate()` has no clock and must not have one | N22's lapsed-authority warning as specified is impossible |
| **P6** | Thousandths in `fit.py` collides with ADR-0002's "exactly two tolerances" | B3's fix is deeper than stated |
| **P7** | Containment has **no path to demand** | the one genuinely new concept |

One check passes and is recorded so it is not re-litigated: **post roles are
reachable.** `_ModelPost` resolution already carries `side.kind` and
`sides[0].station` (`strategy/generator.py:702-733`), so `for_post_roles` keyed on
`end | corner | line | gate | junction | transition` is implementable as agreed.

---

## P1 · The expansion we published truncates, downward, silently

`docs/superpowers/specs/2026-08-23-bom-engine-design.md` §6 gives the
`ParameterTable` → rule expansion as reference, and it is in the Knowledge team's
hands as the thing their tables will be consumed by:

```python
actions=[SetParam(param=table.parameter, value=row.value.amount_milli // 1000)],
```

`//` is floor division. `177800 // 1000` is **177**, not 178. Every value loses up
to 0.999 mm, always in the same direction.

Sub-millimetre sounds harmless. It is not, because the value passes through a
ceiling. `strategy/layout.py:27`:

```python
n = math.ceil(length_mm / max_span_mm)
```

The audit's own `97" / Exposure B` row is 2463.8 mm — floor **2463**, round
**2464**. One millimetre:

| Run | posts at 2463 | posts at 2464 |
|---|---|---|
| 9 855 mm | **6** | 5 |
| 12 320 mm | **7** | 6 |
| 14 790 mm | 8 | 8 |

**A truncation of one millimetre buys an extra post** — with its footing, its
concrete and its labour — on two of three sample runs. That is a priced,
customer-visible consequence of a `//` chosen because it type-checks, and it is
systematically in the expensive direction.

It is also the same defect as B3, which we raised *against them*, written into the
code we handed them as the correct way to consume their data.

**Cause worth naming.** `SetParam.value: int` (`knowledge/model.py:35`) carries no
unit and no lexeme — `max_span_mm` means millimetres by field-name convention
only. So the boundary's `Quantity` has nowhere to land, and the conversion is
forced somewhere. `//` was chosen because it type-checks.

**Fix:** `round()`, not `//`, as the single declared rounding point — and it must
be named in the contract, because "the engine rounds once in the adapter" is
currently a claim with no code behind it.

---

## P2 · Every expanded row lands inside the hard-failure band

`knowledge/evaluator.py:107-115`:

```python
if (winner.version.effective_authority() <= HARD_AUTHORITY_MAX
        and other.version.effective_authority() <= HARD_AUTHORITY_MAX):
    raise GenerationFailure(
        f"hard knowledge conflict on '{key}': ... tie with disagreeing outputs")
```

`HARD_AUTHORITY_MAX = 3`. `DEFAULT_AUTHORITY` (`knowledge/model.py:19`) puts
`hard_constraint` at 1 and **`fact` at 3**. Our expansion:

```python
type="hard_constraint" if table.task.is_structural else "fact"
```

**Both branches are inside the band.** So every row of every published parameter
table becomes an object that can hard-fail a run when it ties with a disagreeing
peer.

`hit_policy = unique` catches collisions *within* one table at publish. It says
nothing about two tables — two manufacturers scoped to one product, or a model's
`PolicyContribution` against a manufacturer table. The engine design claims those
"resolve exactly as they do today", which is true and is the problem: today they
raise.

This is the second confirmed never-block violation, and unlike the `max_span_mm`
one it **scales with adoption** — the more knowledge the platform publishes, the
more objects sit in the failure band.

**Fix:** a disagreeing tie between two *published* rows is a conflict to surface,
not a failure to raise. The existing `Conflict` path already does this for
softer authorities; the hard branch needs to distinguish "two hard constraints
authored by us disagree" (a real build error) from "two published tables disagree"
(a warned line and a conflict for review).

---

## P3 · The fallback row cannot be expressed, and silently wins by position

This is the sharpest finding, because **two things we published are incompatible
and the failure is silent.**

We promised the Knowledge team (datamodel §3.8.1, contract obligation 13) that a
`condition_basis: stated` row with empty conditions is a fallback: *excluded from
the `unique` check, consulted only where no conditioned row matches.*

The engine has no fallback tier. `resolve()` orders contenders by
`_beats` (`knowledge/evaluator.py:74-84`) — authority, then `overrides_objects`,
then specificity, then:

```python
if a.object_id == b.object_id and a.version != b.version:
    return a.version > b.version
```

And our expansion mints:

```python
object_id = f"KP-{table.parameter}-{table.scope.id}",
version   = row_index,
```

Every row of one table therefore shares an `object_id` and differs only by
**`version = row_index`**. An unconditioned row compiles to an always-true
condition, so it fires alongside every conditioned row of its own table — same
object_id — and `_beats` hands the win to **whichever has the higher row index**.

So a fallback row placed after the conditioned rows beats all of them, on every
site, because of where it sits in the table. No conflict is raised, nothing is
warned, and the decision graph will attribute the answer to a real source. It is
precisely the failure `fencemodel/model.py:377` warns about in another context:
*"an arbitrary answer that reads as measured."*

**Fix:** the fallback needs to be a distinct authority tier or a distinct
`object_id`, and `version` must stop carrying row position. Row identity and
version identity are different things and we conflated them.

---

## P4 · Nothing consumes `Combination`

```
$ grep -rn "Combination" --include=*.py src/
(no output)
```

Zero occurrences. `Combination` is binding tier 2, it is in the snapshot payload,
and we asked for it on the strength of the AHRI argument — *the rating applies to
the combination, not the members, and swapping one invalidates it rather than
inheriting it.*

A published `Combination` would be inert. Swap a member and nothing checks,
because there is no checker. We asked another team to curate data we cannot read.

**Fix:** either build the consumer or tell them to deprioritise it. Asking for it
and silently ignoring it is the worse of the three.

---

## P5 · `generate()` has no clock, and must not have one

N22 promises Planning *"warns on a line whose backing authority has lapsed
relative to the run date."*

`GenerationRun.created_at` exists (`strategy/model.py:213`) and
`strategy/generator.py:231` constructs the run **without it**, so it is `""` on
every generated run. The date that does exist is stamped by the *store*:

```python
# store/db.py:598
"INSERT OR IGNORE INTO generation_runs (id, project_id, created_at, doc) "
"VALUES (?,?,?,?)", (result.run.id, ..., _now(), ...)
```

`_now()` at save time, outside the pure function.

And that is correct, not an oversight. **`generate()` is pure and deterministic.**
A pure function that reads a clock is not: the same project against the same
pinned snapshot would emit different warnings on different days, and the golden
scenarios would drift.

So the warning as specified cannot live where we said it does. The date must be an
**explicit, pinned input** — `as_of`, alongside `site_revision` — not ambient and
not read.

**Worth recording honestly:** the Knowledge team offered `as_of_date` as a
condition dimension and we rejected it. The rejection was right for its stated
reason (a time domain makes `uncovered` report every unenumerated date as a
coverage hole), but their underlying instinct — *the date has to be an input* —
was correct, and our answer kept the field while leaving the input problem
unsolved. The resolution is a third option neither side proposed: a pinned run
input, not a condition and not a clock.

---

## P6 · Thousandths in `fit.py` collides with ADR-0002

B3's fix says the fitting arithmetic consumes thousandths and rounds only its
outputs. That is right, and it is deeper than one module.

`core/units.py` opens:

> *"Unit discipline (ADR-0002): integer millimeters and cents at rest. **Exactly
> two tolerances exist in the whole system. Do not add ad-hoc epsilons.**"*

`Mm = int` appears in **215 annotations**. `fit_pattern`, `_count_members`,
`_cycle_advance_mm`, `_spread` and `FitResult` (`fencemodel/fit.py:25-109`) are all
`Mm`. Changing them is contained to a module — but `NUMERIC_TOLERANCE_MM = 1` is
an *millimetre-scale* constant, and comparing micron arithmetic against a 1 mm
tolerance either swallows the precision the change exists to preserve or needs a
third tolerance the module explicitly forbids.

**Fix:** this is an ADR-0002 amendment, not a refactor. Either the tolerance gains
a thousandths sibling with a stated reason, or the fit path documents that its
inputs are micron and its comparisons remain at mm scale — which is defensible but
must be written down, because right now B3 promises precision the tolerance will
quietly discard.

---

## P7 · Containment has no path to the bill of materials

`demand/derive.py:111` is the whole of how a panel becomes demand:

```python
for slot in span.panel.slots:
    add(slot.qty, [span.id], cut_length_mm=slot.length_mm, ...)
```

`span.panel.slots` is `ResolvedPanel.slots` — `frame`, `infill`, `fixing`. A
`ContainedSlot` reaches demand only if `resolve_panel` flattens it into that list,
and the design never says it does.

Worse, the crediting rule we specified —

> *if the host's SKU is an assembly kit already listing the contained part, credit
> the contained requirement against it rather than buying it twice*

— has nowhere to live. `add()` takes a quantity and an eligibility; it has **no
notion of one line covering another**. That rule is not an adjustment to demand
derivation, it is a new concept in it.

**Fix:** the design must say how a contained slot is flattened and where crediting
happens, before the Knowledge team authors containment against it. This is the one
genuinely new structural concept in the whole revision, and it is the one whose
consumption path we never traced.

---

## 1. What changes on the other side of the boundary

Four of the seven change what we told them, so they go into
`planning-asks-v0.2.md` and, where binding, into the contract:

- **P1** — the reference expansion in their hands is wrong. Correct it before they
  build against it.
- **P3** — obligation 13 and datamodel §3.8.1 describe a mechanism the engine
  cannot honour. Either the engine grows a fallback tier or the obligation is
  restated. **They are holding an early publish on exactly this** (their §6 item 4,
  blocked on B6), so it is urgent rather than merely wrong.
- **P4** — tell them whether `Combination` is wanted now or deferred.
- **P5** — N22's warning needs a pinned `as_of`, which is a contract change.

P2, P6 and P7 are ours to fix and change nothing they author against.

## 2. The method note, since it is the transferable part

Every finding here came from grepping the code and reading a docstring, not from
re-reading the design. The three that matter most — P1, P3, P5 — were invisible
from the documents, because the documents are *internally* consistent. P3 in
particular required holding two of our own published artefacts side by side and
asking what the engine would do with both, which is the exact move the Knowledge
team made when they took §8's instruction literally and tried to author the
artefact.

We asked them to check the model against the data they hold. We should have been
running the same check against the code we hold, at the same time.
