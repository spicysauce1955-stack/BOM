# Amendment 007 — a condition dimension whose values are quantities has no way to cross

```text
Obligation   §1.3 (`ParameterTable.domain`, `rows[].conditions`, `uncovered`).
             Obligations 2 and 4 (§3.1) both depend on this and neither can be
             satisfied for such a dimension today. No obligation text is edited.
Trigger      D — defect. Two BINDING obligations depend on a shape §1.3 does not
             define. B applies too: the condition compiles to a comparison that
             can never be true, and the mechanism is named below.
Filed by     Planning & BOM, 2026-08-31, on wiring the first real tables
Status       FILED. Governs nothing until ratified (AMENDING.md §3 step 2).
Blocking     YES, and it is the only thing now blocking item 6. Batches with
             005 and 006 if a cut is close; otherwise this is the one that
             wants the next re-cut.
```

## The gap

§1.3 gives a condition dimension a list of values and says nothing about what a
value **is**. In practice they have all been closed tokens — `exposure_category:
[B, C, D]`, `hvhz: [true, false]` — and for those the design is exactly right.

`3ae88642` publishes a third kind, on all four of its tables:

```text
domain           { exposure_category: [B, C, D],
                   fence_height: ["Up to 48\"", "49\" to 76\""],
                   hvhz: [true, false] }
condition_scope  { exposure_category: "site", fence_height: "bay", hvhz: "site" }
```

`fence_height` is not a token. It is a **length**, published as an English phrase
because §1.3 offers nowhere else to put it. This is not a lapse by the publisher —
there is no type to use.

---

## Evidence

### E1 · Obligation 4 cannot be satisfied for it

> **4.** Every dimension is a `Quantity` — integers in thousandths of the named
> unit, with **every** verbatim source lexeme alongside. … No bare `_mm` field
> crosses; nothing in this corpus is a whole number of millimetres.

A fence height bracket is a dimension. It crosses as `"49\" to 76\""` — a bare
string, no thousandths, no unit, the lexeme doing double duty as the value. Every
other dimension in the payload obeys obligation 4; this one cannot, because
`conditions` has no `Quantity` shape available to it.

### E2 · Obligation 2's `uncovered` cannot answer the question it exists for

> **2.** Every `ParameterTable` declares its hit policy and its domain, has no
> overlapping rows under `unique`, and **lists every uncovered point**.

And §1.3's own argument for why `domain` is required at all:

> Declaring the domain is what makes the question *"which sites does this
> knowledge not cover?"* answerable at all; a set of independent assertions
> cannot answer it.

`[measured]` — the two published brackets, converted:

| Label | min | max |
|---|---|---|
| `"Up to 48\""` | unbounded | 1 219 200 |
| `"49\" to 76\""` | 1 244 600 | 1 930 400 |

**There is a 25 400-thousandth band between them that is in no bracket at all.** A
1 225 mm fence — 48.2″, an ordinary height — matches neither value. It is *not*
reported as uncovered, and cannot be: `uncovered` enumerates **domain points**,
and this height is not a domain point. It is outside the declared domain while
looking, to any consumer, like a value the domain simply does not list.

So for this dimension the mechanism §1.3 says exists to make coverage answerable
returns a confident, complete-looking answer that omits a real hole. That is
worse than the coverage gap it was built to surface.

Whether that band is a genuine hole in the source or an artefact of brackets
stated in whole inches is a fact **only the publisher can state**. It cannot be
inferred from the labels, which is the point.

### E3 · The condition can never fire, so the rows are inert

`[measured]` — `fenceai/knowledge/parameters.py`, all 16 published rows compile
to:

```text
bay.fence_height == '49" to 76"'
```

A bay's height in this engine is an integer in millimetres, as ADR-0002 requires
at rest. There is no value it can hold that equals that string, so the comparison
is false for every project that will ever run. All 16 rows expand into rules that
are structurally incapable of firing — and because they simply never match, they
report as *not applicable* rather than as broken.

The only way to make them fire is to read the bounds out of the label. That is
the move §1.1 already forbids by name, one type over:

> `"05/04/2023"` is ambiguous on its face, and a publisher resolving it by house
> convention has **manufactured a fact rather than read one**.

Reading `49` and `76` out of `"49\" to 76\""` is the same act on a length, and it
is worse on this side than on the publisher's: we hold no document and no crop,
so we would be inferring bounds from a string with nothing to check them against.
And any bound we invented would then select which footing depth a fence is built
to.

---

## Proposed text

Two edits to §1.3, both additive. Token dimensions are untouched.

### 1 · `domain` may declare a dimension as quantity-valued

```text
domain        { exposure_category: [B, C, D], hvhz: [true, false],
                fence_height: range(<UnitCode>) }
              # a listed dimension enumerates its values, as now;
              # `range(<UnitCode>)` declares a CONTINUOUS dimension instead
```

### 2 · A row's condition on such a dimension is a bounded interval

```text
conditions { exposure_category: "C",
             fence_height: { min: Quantity | null, max: Quantity | null,
                             min_inclusive: bool, max_inclusive: bool,
                             value_raw: [str] } }
```

- `null` on either bound is **unbounded on that side**, so `"Up to 48\""` is
  `{min: null, max: 48″ as Quantity, max_inclusive: true}`. It is not a missing
  value and is not the null of §1.1's `Date` — an open interval is a statement,
  not an absence.
- `value_raw` carries the publisher's own phrase verbatim, for the reason it
  exists everywhere else: a curator matches `"49\" to 76\""` against the page,
  and a disagreement between the label and the bounds is a bug someone can see.
- **`min_inclusive` / `max_inclusive` are explicit and are the load-bearing
  part.** The real brackets leave a 25.4 mm band between them (E2). Whether the
  source means that band to be excluded, or means its brackets to tile with
  whole-inch rounding, is a fact only the publisher holds — and defaulting the
  flags either way in the contract would decide it silently for every table.

### 3 · `uncovered` for a continuous dimension lists intervals

```text
uncovered [ { fence_height: { min: 48″, max: 49″,
                              min_inclusive: false, max_inclusive: false } } ]
```

This is what makes the E2 hole reportable instead of invisible, and it is the
half that turns this amendment from a typing convenience into the thing
obligation 2 already promises.

### Not proposed here

- **A closed vocabulary of which dimensions are continuous.** Condition
  dimensions are a registry (§2), so `fence_height` needs no ratification and
  neither will the next one. Only the *value shape* is the contract's business,
  which is all this asks for.
- **Any rule about which interval wins when two overlap.** That is `hit_policy`'s
  job and it already has one. Note that our §1.3 `unique` overlap check —
  built this week — becomes genuinely meaningful for the first time here:
  overlapping intervals are checkable, where overlapping opaque labels were not.

---

## Cost if this lands

**Knowledge.** Publish brackets as intervals with the lexeme beside them, and
state the inclusivity. The bounds are already inside the label, and yours is the
side that may legitimately read them: you hold the document, the crop and the
reviewer. Real work, and it is the whole of the work.

**Planning.** Match an integer-millimetre site fact against an interval. Our
evaluator already compares numbers natively (`<`, `<=`, `>`, `>=` are in the rule
AST today); it is the *equality against a token* that was the wrong tool. Small
and confined to one function.

## In-flight

**This one does want a re-cut, and it is the only one that does.** `3ae88642`
publishes 16 rows conditioned on `fence_height`. Under the contract as it stands
they cannot fire; under this they can. Nothing regresses in the meantime — we
refuse that snapshot by version already, for 002 — but until this lands, item 6's
wiring would land 16 rules that resolve to nothing and warn on every line, which
is why we have not started it.

Nothing else pins against it: no other dimension in either published snapshot is
quantity-valued.

## One thing we considered and rejected, so it is not re-proposed later

**Leaving it to us, by having Planning bucket its own heights.** We would declare
brackets on our side and match a site height into one. It fails on the same
argument as every other version of this: the bracket boundaries are the source's,
and a boundary we chose would silently decide which footing depth a fence is
built to — with our number, their citation, and no way for a reader to see the
seam. Where a fact belongs to the document, it has to cross as one.

---

## Disposition — Knowledge Platform, 2026-08-31

```text
Verdict   ACCEPT, as proposed. Schema only -- see "What this disposition does
          NOT do" below for what is still open.
```

**E1-E3 checked directly, not taken on report.** `[measured]`, live store,
2026-08-31: `build_parameter_tables()` publishes exactly what E1/E3 describe
— `conditions: {..., "fence_height": '49" to 76"'}`, a bare string, on all
16 rows across the 4 published tables. The 25 400-thousandth gap in E2
recomputes exactly: 48″ = 1 219 200, 49″ = 1 244 600, 76″ = 1 930 400
thousandths-of-mm, hand-checked against `MILLI_PER_UNIT`.

**Whether the gap is real or a whole-inch-rounding artefact — checked, and
it's genuinely open, not something either side should resolve by guessing.**
The two labels come from `doc-88dcd8a73079` / `doc-2b81f4c2925e`, pp.6/8 —
scanned Miami-Dade NOA tables, OCR text too degraded to carry inclusivity
language ("up to and including" or similar) either way. Read literally,
`"Up to 48\""` means max=48″ inclusive and `"49\" to 76\""` means both
bounds inclusive — which reproduces the 1″ gap exactly as measured. That
could be the source's real convention (a genuine dead band between
brackets) or an artefact of describing a continuous quantity in whole
inches. Filing's own position — *"only the publisher can state which, and
it cannot be inferred from the labels"* — is exactly right and is this
platform's own standing rule (G53, G56: don't resolve from silence, report
the gap and let a person settle it). Not resolving it here either.

**Scope actually checked before committing to it.** `[measured]`, corpus-wide:
`table_read_candidates` carries exactly two non-empty `Fence Height` values
anywhere — `"Up to 48\""` and `"49\" to 76\""` (plus one empty string, an
unread cell, already excluded from published conditions). This is not an
open-ended NLP problem; it is two labels. The proposed shape (`min`, `max`,
explicit `min_inclusive`/`max_inclusive`, `value_raw` kept verbatim) is
consistent with how this platform already treats every other ambiguous or
partial value — `Quantity.value_raw`, `Date`'s `null`-never-ordered rule —
so it needs no new pattern, only an application of ones already accepted.

**What this disposition does NOT do.** Accepting the contract shape is not
the same as having built it. `fence_evidence/parameters.py` does not yet
translate a `fence_height` label into `{min, max, min_inclusive,
max_inclusive, value_raw}` — that is real, separate implementation work
(a new `_translate_fence_height`-shaped function, `CONDITION_SCOPE`/
`DECLARED_DOMAIN` updates, a `_points`/`_matches`/`_windows_overlap`-style
interval-overlap check for `uncovered`, and tests), not something to build
inside a contract disposition. Recorded as the next build-plan item rather
than promised done here. `3ae88642` is already refused by version for 002;
nothing regresses by this staying unbuilt a while longer.
