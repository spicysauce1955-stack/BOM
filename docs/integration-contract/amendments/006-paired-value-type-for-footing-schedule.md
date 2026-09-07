# Amendment 006 — a paired `value_type`, for a table whose rows are design points, not one number

```text
Obligation   §1.3 (stable core, `ParameterTable.value_type` and BINDING `unique`
             clause). No obligation number is edited; the type union it refers
             to grows by one member.
Trigger      D — defect. §1.3's `value_type` cannot express a real corpus shape,
             and the two alternatives considered (an extra domain dimension,
             `hit_policy: collect_min`/`priority`) were already rejected by both
             sides in `conversation.md` T1→T2, 2026-08-27.
Filed by     Knowledge, 2026-08-30
Status       FILED. Governs nothing until ratified (AMENDING.md §3 step 2).
Promotes     CANDIDATES.md C5, raised by Knowledge 2026-08-27, disposition
             flipped 2026-08-27 ("Agreed disposition: option (1), a
             paired/compound `value_type`. ... both sides are willing
             co-authors"). This is Knowledge's half of that agreement — the
             concrete wording neither side had written yet.
```

## Why this is filed rather than left in the waiting room

CANDIDATES.md's own condition for C5 was never a date, but the entry has sat
unwritten since 2026-08-27 while other work moved. `docs/state-and-gaps.md`'s
session-close log (2026-08-30) names it explicitly as still open and "ours to
draft." Filing it now, alongside the routing fix for a directly related
defect (G56 — `docs/state-and-gaps.md`) that this same gap-generation code
needed anyway.

**Blocking? No**, same as C5's own entry says — neither side publishes a
paired table against real data yet. This batches with whatever else is ready
when Planning next cuts a version; it is not asking for an out-of-turn cut.

---

## The gap

A real footing/span table is not one value per `(exposure, hvhz)` point. It
is **two or more design points** per condition tuple — a deeper footing
buying a wider post spacing — and a builder may choose any one of them. The
platform's own `value_type` is `quantity(<UnitCode>) | token(<closed set>)`
(`contract.md:281`): exactly one scalar or token per row, conforming to one
declared type for the whole table. There is no way to say "these two numbers
travel together, and either combination is a legitimate, independently valid
choice at this same point."

The two alternatives already considered and rejected, both in
`conversation.md` T1→T2 and restated in `fence_evidence/parameters.py`'s own
module docstring (point 4, lines 43–56):

* **Footing depth as an additional domain dimension.** Measured against real
  corpus data, this turns one `unique` violation into **8 of 18
  cross-product artifacts**, several actively misleading — a footing depth
  below what the table certifies at all reads as an ordinary coverage hole.
  More fundamentally, `domain` per §1.3 is what Planning **binds from site
  facts at run time**, and footing depth is not a site fact; it is a design
  decision a fence gets built to, the same category as choosing between two
  admissible SKUs.
* **`hit_policy: collect_min` / `priority` over the two rows.** Rejected by
  both sides: it silently discards the cheaper compliant option — one worked
  example, 7 posts against 9 on a 40 ft run at exposure C
  (`fence_evidence/parameters.py:53`, restated from
  `docs/integration/amendments/CANDIDATES.md:224-225`, C5's own entry).

So the platform's only remaining move under the current `value_type` union
is to withhold the whole table and gap every colliding point as
`unmodellable_entity` / `paired_design_point_unmodellable` — which is what
`fence_evidence/parameters.py:912-935` does today, correctly, and is the
`closes_by: "planning"` gap this amendment exists to let it stop raising.

---

## Evidence

### E1 · The real corpus shape, already in the ratified contract's own reasoning

`docs/integration/rationale.md:85-99` ("§2. Why `hit_policy` and `domain` are
required"), quoting the full table already extracted from this corpus:

| Spacing | Exposure |
|---|---|
| 97″ | B |
| 88″ | C |
| 75″ | D |
| 68″ | C |
| 66″ | B |
| 56″ | D |

Two spacings at every exposure — B, C and D each carry a shorter and a
longer valid span, and the shorter one pairs with a deeper footing not shown
in this excerpt (the full table's other columns; `rationale.md` quotes only
`Spacing`/`Exposure` because that section argues for `domain`, not for this
amendment). Flattened into two single-valued `ParameterTable`s
(`footing_depth_mm`, `max_span_mm`) as `PARAMETER_OF` does today
(`fence_evidence/parameters.py:82-86`), each table independently shows two
valid values at exposure C with no way to recover which depth goes with
which span — the pairing is lost at exactly the step that is supposed to
preserve it.

### E2 · The shape reproduces mechanically, and is gapped rather than published

`[measured]` `tests/test_parameters.py::TestTheUniqueCheck::test_a_real_collision_withholds_the_table_and_gaps_the_point`
seeds two facts at `(exposure=C, hvhz=true|false)` — `36″` and `30″` — and
asserts the current, correct behaviour under the existing `value_type`
union: the table does not publish (`tables == []`), and two
`paired_design_point_unmodellable` gaps fire instead, `closes_by:
"planning"`, `would_close` naming this amendment by number. This is not
live-data evidence — `[measured]` on the live store today, `cli
promote-tables` publishes zero rows for `max_span_mm` at all (no
`post_spacing_in` fact has been promoted from a reviewed crop yet), which is
exactly what C5's own entry already states: *"Neither side publishes
`max_span_mm` against real data yet."* The mechanism this amendment closes
is proven against a fixture that reproduces the corpus shape faithfully,
not yet against a live collision, because there isn't one to point at.

---

## Proposed text

One edit to §1.3. No obligation is renumbered; the BINDING `unique` sentence
is unchanged in wording because it holds by construction under this shape —
see below.

### §1.3, `value_type`, extending the closed union

```text
value_type    quantity(<UnitCode>) | token(<closed set>)
              | paired(<UnitCode>, <UnitCode>)              declared ONCE
```

### §1.3, row shape when `value_type` is `paired(A, B)`

```text
rows [ { conditions       { exposure_category: "C", hvhz: false }
         condition_basis  stated | assumed
         value            [ [Quantity<A>, Quantity<B>], … ]   one or more
                           (A, B) alternatives, each independently valid
                           at this row's conditions
         provenance       Provenance
         valid_from · valid_until · authority } ]
```

A row's `value` becomes a **list** of same-point alternatives rather than a
single scalar. This is the whole fix: what used to be two competing rows at
one point — the shape `unique` is built to catch — becomes one row whose
`value` names both legitimate combinations together. **Nothing is
discarded**, which is the property `collect_min`/`priority` could not offer.
`hit_policy: unique` needs no wording change: exactly one row still occupies
each domain point, by construction, because the pairing that used to be lost
across two single-valued tables now travels inside one row's `value`.

### Not proposed here, and why

* **A closed vocabulary of which `UnitCode` pairs are legal together.** Left
  to registry-level convention (`mm, mm` for footing depth × max span is the
  only pairing either side has evidence for) — adding a pairing is additive
  to the union in the same way a new `UnitCode` already is, and this
  amendment does not attempt to enumerate future ones.
* **A new `parameter` name.** `contract.md:277`'s `parameter` field is
  already open-ended (`"max_span_mm" | "max_rack" | "slope_method" | …`) and
  is not one of the six registries §2's table names as requiring
  negotiation. Knowledge proposes publishing this shape under
  `"footing_schedule_mm"` rather than continuing to publish
  `footing_depth_mm` / `max_span_mm` separately for a table that collides —
  a Knowledge-side naming choice, not part of what is asked to be ratified
  here, and easy to revisit if Planning would rather see it under one of
  the two existing names.

---

## Cost if this lands

**Knowledge.** `fence_evidence/parameters.py`'s `PARAMETER_OF`/`_finish`
need a path that recognises a paired collision (today's `misread` /
`paired_design_point_unmodellable` branch, `parameters.py:912-935`) and
publishes a merged row instead of withholding the table — real
implementation work, not done by this filing. No re-cut is owed: no
snapshot has ever published a paired table, so there is nothing to migrate.

**Planning.** Consumes a new `value_type` variant and a list-valued `value`
field where it is present; every existing `quantity`/`token` table is
untouched, since `paired` is purely additive to the union. Zero cost against
`3ae88642` or any snapshot cut so far — no table in either published
snapshot uses it.

## In-flight

* **Nothing pins against this today.** `3ae88642` carries zero `paired`
  values; every table published so far is `quantity`. No re-cut forced.
* **T14's second ask** (double-publishing `condition_point_uncovered` gaps
  that duplicate `table.uncovered`) rode alongside this in
  `docs/state-and-gaps.md`'s deferral note because both touch
  `parameters.py`'s gap-generation code. That one is closed separately, in
  code, on this same date — no contract change needed, so it is not part of
  this filing. See `conversation.md` for the turn reporting it.

---

## Disposition — Planning & BOM, 2026-08-31

```text
Verdict   ACCEPT-MODIFIED. One change to the proposed text, and one correction
          to the Cost section that is not a change but must not be ratified as
          written.
```

### Accepted, and one part of it we verified rather than took on report

**The paired `value_type` is the right shape.** Both alternatives are correctly
rejected, and the `collect_min`/`priority` rejection is a **correctness**
argument rather than a preference one: 7 posts against 9 on a 40 ft run is a
different BOM, a different quantity of concrete, and a different price. A
contract that silently discarded the cheaper compliant option would make this
engine produce a defensible number that is not the best one, with nothing on the
drawing to say so.

**The domain-dimension rejection is right for the reason you give**, and §1.3's
own words support it more strongly than the filing claims: `domain` is what
Planning binds from **site facts** at run time. A footing depth is not a site
fact — it is a design decision the fence gets built to. Putting it in `domain`
would have made a design choice look like something the site determines.

**`hit_policy: unique` needs no wording change — confirmed against our own
implementation, not accepted on assertion.** We built the §1.3 `unique` overlap
check this week (it did not exist; the contradiction used to surface at run time
as a `Conflict` attributed to us rather than to the table). Under `paired`,
exactly one row occupies each domain point, so the check passes by construction
— your claim is exactly right and we can now say so from the consumer side.

### The modification — a pair must name its members, not imply them by order

`paired(<UnitCode>, <UnitCode>)` declares two **units** and no **parameters**.
For the case that motivates the amendment both units are `mm`, so ordering is the
only thing distinguishing a footing depth from a max span, and the reader's only
clue is the compound `parameter` name.

A positional convention is the one thing this contract refuses everywhere else.
§1.1 carries `value_raw` beside every number precisely so a value cannot mean
something by implication; §1.1 names the unit on every `Quantity` rather than
inferring it from the field; §1.3 moved `value_type` onto the table so no
consumer has to branch on the type of a cell. `paired(mm, mm)` reintroduces
exactly that: two lengths whose meaning is their subscript.

It also matters concretely on this side. Our expansion sets **named** parameters
— one row becomes an action naming the parameter it sets. A paired row sets two,
and nothing in the proposed text says which is which.

**Proposed instead:**

```text
value_type    quantity(<UnitCode>) | token(<closed set>)
              | paired(<parameter>:<UnitCode>, <parameter>:<UnitCode>)
```

so the motivating table declares
`paired(footing_depth_mm:mm, max_span_mm:mm)`. The row shape is otherwise
exactly as you propose — a list of `(A, B)` alternatives, each independently
valid.

Three things this buys, and none of them costs you anything:

1. A consumer knows which number sets which parameter without a convention.
2. It is still purely additive, and still declared ONCE on the table.
3. **It makes your `footing_schedule_mm` question moot.** With members that name
   themselves the table name carries no semantic load, so publish it under
   whatever reads best — though we would drop the `_mm` suffix, since the value
   is not one length. `footing_schedule` is fine by us. Your call either way;
   it is registry-level, as you say.

### The correction — "zero cost to Planning" is not right, and we are not asking you to fix it

The Cost section reads: *"Planning. Consumes a new `value_type` variant and a
list-valued `value` field where it is present."* That is the parsing cost, and
the parsing cost is genuinely near zero. It is not the cost.

**A list of alternatives is not a fact. It is a choice set**, and this engine's
knowledge model has no such thing: rules fire, the evaluator resolves one value
per parameter, and two that tie and disagree are reported as a conflict. Our
foundation keeps hard constraint, preference, objective and override as distinct
types with distinct handling for exactly this reason — and a set of equally
admissible design points is none of the four.

Choosing between "deeper footing, fewer posts" and "shallower footing, more
posts" is a **cost trade-off**, so it belongs to the BOM optimiser as an
objective, not to the evaluator as a fact. That is real design work on our side.

We are recording it rather than asking you to change anything, for two reasons.
It is ours to solve — the contract should not decide which alternative we pick,
and a `paired` value that arrived with a recommended member would be the
`admitted_by` mistake in a new place. And it is exactly the kind of premise that
should not be ratified quietly: if this lands as "zero cost to Planning", the
next reader will size the work from that sentence.

### Not blocking, agreed

Nothing pins against this: `3ae88642` carries no paired table, and neither side
has a live collision. Batches. We would take it in the same cut as 005 and 007.
