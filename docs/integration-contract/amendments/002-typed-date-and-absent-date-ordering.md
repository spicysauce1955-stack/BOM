# Amendment 002 — a typed `Date`, and what an absent date does to a BINDING ordering

```text
Obligation   §1.1 (stable core, type list) and §1.4 (BINDING tie-break).
             Obligation 16 (§3.1) is affected and is NOT edited — see "Why obligation 16
             is not in the proposed text".
Trigger      A — falsification. Measured evidence contradicts a binding item, and both
             sides are building against it now. B applies too: the tie-break's third
             criterion could not be built and the mechanism is named below.
Filed by     Planning & BOM, 2026-08-30, on consuming the first real snapshot
Status       FILED. Governs nothing until ratified (AMENDING.md §3 step 2).
Promotes     CANDIDATES.md C6, raised by Knowledge 2026-08-30
```

## Why this is filed rather than left in the waiting room

C6 set its own condition, and it has expired. Its entry reads:

> **Blocking?** No. Planning consumes no snapshot yet. Batches — **but it stops batching
> the day they do.**

Planning consumed `3ae88642` on 2026-08-30 — `ParameterTable`s loaded through
`fenceai/knowledge/parameters.py` and `expand()`, four tables, sixteen rows. The
day named in C6 is the day this was filed.

`AMENDING.md` §4 forces a cut on a trigger-A falsification of a binding item
someone is currently building against, and on a trigger-B item blocking work.
This is both, so it does not batch. If the Knowledge team reads the trigger as D
rather than A, say so in the disposition and it batches with C1/C5 instead — the
evidence is the same either way, and we would rather argue the trigger than
argue the fact.

---

## The gap

Two BINDING items order dates. **The contract types no date at all.**

**§1.4, the paragraph marked BINDING** (`contract.md:324`):

> Ranks are unique within a task row. Where an operator's edit creates a tie, resolution
> breaks it by higher `curation_level`, **then later `issue_date`**, then lexicographic
> `source_class` — deterministically, and **never silently preferring an older document.**
> Without this, two implementations could both honour the policy, stamp different
> `admitted_by.rank`, and hash differently.

**§3.1 obligation 16:**

> Planning pins `as_of` on the run alongside the topology and snapshot hashes, and warns
> when a line's backing **`valid_until` precedes it**.

**§1.1's type list** (`contract.md:59-70`) types `EntityRef`, `VersionRef`, `SourceRef`,
`SnapshotRef`, `Quantity`, every `UnitCode`, `Provenance` and `PostRole`. It types
`issue_date` and `expiration_date` nowhere — they appear only as bare field names inside
`SourceDoc` (`contract.md:62`). `ParameterTable.rows[].valid_from` / `.valid_until` are
likewise bare (`contract.md:251`).

So the one comparison §1.4 names for `source_class` — lexicographic — is the only reading a
bare string field offers, and it is the reading that falsifies the clause.

---

## Evidence

All five measurements are from snapshot
`3ae88642ec789f30de43766da57b5e201a58964999ffa6cec65ce1bacb430508`, the first
snapshot either side has published, and from Planning's own loader.

### E1 · Every date in the first real snapshot is `MM/DD/YYYY`, never ISO

`[measured]` 75 `source_docs`, 4 `ParameterTable`s, 16 rows:

| Field | Values |
|---|---|
| `issue_date` | `"05/04/2023"`, `"04/04/2013"`, `"04/24/2025"` |
| `expiration_date` | `"03/13/2029"`, `"04/04/2028"` |
| `valid_from` | `"04/24/2025"` × 8 rows |
| `valid_until` | `"04/04/2028"` × 8 rows |

Twenty-one date values, five field kinds, one format, and it is not the format any
consumer would guess from a contract that names lexicographic comparison.

### E2 · Ordered as strings, the 2023 document beats the 2025 one

`[measured]` The three real `issue_date` values sort:

```
"04/04/2013"  <  "04/24/2025"  <  "05/04/2023"
```

*"Later `issue_date`"* under the only comparison a bare string offers selects
**`05/04/2023`** over **`04/24/2025`**. §1.4's own sentence forbids that outcome by
name — *"never silently preferring an older document."* This is the falsification: not
an argument that the clause is unclear, a measurement that the clause as written
produces the result it prohibits, on the only real data that exists.

### E3 · The contract's own named case is in the data, and the tie-break has no input for it

§1.4's second BINDING paragraph explains why `version_status` is a policy axis:

> A superseded approval and its replacement are otherwise the *same* source class, the
> same role and the same task — the policy would rank them identically.

`[measured]` That exact pair is published:

| | `1c487c731b56…` | `f650c3f14efe…` |
|---|---|---|
| `source_class` | `sealed_approval` | `sealed_approval` |
| `version_status` | `superseded` | `unknown` |
| `superseded_by` | **`f650c3f14efe…`** | — |
| `issue_date` | **`null`** | `"04/24/2025"` |

The older document *names its own replacement* and carries **no `issue_date` at all**.
Both back `footing_depth_mm` / `footing_diameter_mm` tables. Same class, same task,
identical rank — precisely the tie §1.4 says the `issue_date` step exists to break — and
one side has nothing to compare.

*(These two do not compete in a run today: their `scope.id`s differ, so a run selects by
scope and never reaches the policy. That is a separate observation and is reported in
`conversation.md` T15 rather than here — the same approval lineage published under two
scope ids is a data question, not a contract defect. The tie-break defect stands without
it.)*

### E4 · Absent is the common case, not the edge

`[measured]` **72 of 75** published `source_docs` carry no `issue_date`; 73 of 75 carry no
`expiration_date`; 8 of 16 rows carry neither `valid_from` nor `valid_until`.

The contract says nothing about what an ordering does with a missing operand. Two
implementations may honour §1.4 exactly as written and disagree — one treating absent as
earliest, one as latest, one skipping the criterion — which is the divergence §1.4's own
BINDING rationale exists to prevent (*"stamp different `admitted_by.rank`, and hash
differently"*). Typing the date without settling this would close half the defect.

### E5 · Planning's engine, where it actually bit

`[file + line]`

- **`src/fenceai/knowledge/parameters.py:287-301`.** Obligation 16's lapse check compared
  `row.valid_until < as_of` as strings — correct only if both are ISO. Against
  `3ae88642`, `"04/04/2028" < "2026-08-30"` is **true**, so a row valid until 2028 was
  reported **LAPSED four years early**. Found by loading the real snapshot, not by
  reading it.
- Fixed in commit `82d47f2` by comparing **only when both sides already look ISO** —
  because parsing `MM/DD/YYYY` here would be this side inventing the comparator §1.4 is
  supposed to define. The consequence is stated plainly: **obligation 16's lapse check
  does not execute on any of the 8 rows in `3ae88642` that carry a `valid_until`.** A
  BINDING obligation is currently unexecutable against the only real data there is. That
  is trigger B, and the guard is the attempt `AMENDING.md` §2 requires before claiming it.
  Obligation 16 therefore executes today in exactly one place — Planning's own
  hand-authored conforming fixture, whose dates are ISO because we wrote them that way.
  A binding rule that passes only against the data its implementer authored is not
  a rule anyone has tested.
- **`src/fenceai/knowledge/source_policy.py:231-258`.** `resolve()` implements rank, then
  `curation_level`, then **skips `issue_date`** and falls through to lexicographic
  `source_class` as a fourth criterion. Documented in-source as deliberate, naming this
  candidate. Two implementations of §1.4 now exist on paper and one of them is knowingly
  three-quarters of the rule.

---

## Proposed text

Two edits. Neither touches an obligation.

### 1 · §1.1, add to the type block after `Quantity`

```text
Date         { iso: str | null, value_raw: [str] }   iso is ISO-8601 YYYY-MM-DD
```

### 2 · §1.1, add a BINDING paragraph after the existing thousandths paragraph

```text
> **BINDING.** Every date-valued field crossing this boundary is a `Date`:
> `SourceDoc.issue_date`, `SourceDoc.expiration_date`, and
> `ParameterTable.rows[].valid_from` / `.valid_until`. `iso` is ISO-8601
> `YYYY-MM-DD`, so ordering is lexicographic and needs no comparator; `value_raw`
> carries the source's own stamp beside it — `"04/24/2025"` next to `2025-04-24` —
> for the reason `Quantity.value_raw` already exists.
>
> `iso` is `null` when the source states no date, or states one that cannot be
> normalised without guessing. `"05/04/2023"` is ambiguous on its face, and a
> publisher resolving it by house convention has manufactured a fact rather than
> read one. **A `null` `iso` is never ordered, and never treated as earliest or
> latest.** A rule reaching for a date and finding `null` moves to its next
> criterion; a consumer that cannot proceed without one reports it rather than
> assuming. Absent is the common case — 72 of the 75 source documents in the first
> published snapshot carry no `issue_date` — so silence here is not an edge case,
> it is the default path.
```

### 3 · §1.4, the BINDING tie-break, replacing seven words

```text
…breaks it by higher `curation_level`, then later `issue_date` where both carry
one (§1.1 `Date`), then lexicographic `source_class` — deterministically, and
never silently preferring an older document.
```

## Why obligation 16 is not in the proposed text

It needs no edit. *"Warns when a line's backing `valid_until` precedes it"* is exactly
right once `valid_until` is a `Date`; the only thing it lacked was a comparable operand.
The `null`-`iso` rule in §1.1 covers its remaining case in one place rather than two —
and a rule about ordering dates that lives in the date's own definition is where a
consumer will actually find it.

`AMENDING.md` §2 warns that wording which changes no meaning is not an amendment. This
one changes meaning in §1.4 and adds a type to §1.1, so it is not that. It is also not a
registry addition: no new part type, warning code, condition dimension or source class —
it is a shape in the stable core and an ordering rule, both of which the freeze covers.

---

## Cost if this lands

**Knowledge.** Normalise five field kinds at publish and re-cut `3ae88642` — 21 values
across 75 `source_docs` and 16 rows. **No new curation work:** every lexeme is already
held, and `iso: null` beside the raw lexeme is a legal, honest answer for the ambiguous
ones. `"05/04/2023"` may stay unresolved forever without blocking anything.

**Planning.** Larger, and ours:

- `ParameterRow.valid_from` / `.valid_until` become `Date`; `parameters.py`'s ISO guard
  (`82d47f2`) is deleted and obligation 16's lapse check runs unconditionally wherever
  `iso` is present.
- A `valid_until` with `iso: null` becomes a reported gap, not a silent pass — an
  authority whose expiry we cannot read is not an authority we may assume current.
- `source_policy.Candidate` gains `issue_date: Date`; `resolve()` gains its real second
  criterion, and the lexicographic-`source_class`-as-fourth workaround retires to its
  contract-stated place as third.

## In-flight

- **`3ae88642` needs a re-cut**, which changes `snapshot_id`. Nothing on the Planning
  side pins it — it has been loaded, never stored against.
- **`docs/integration-contract/fixtures/snapshot-example.json`** (the conforming fixture,
  both repos) carries `valid_from` / `valid_until` as bare strings that already happen to
  be ISO — three rows, one of them deliberately lapsed. The edit is shape-only: no value
  changes, `value_raw` stays empty, and the lapsed row keeps lapsing.
- **Nothing is built on the omission.** `resolve()`'s missing step has one test, which
  asserts the documented fallback and will be replaced by a test of the real rule.
- No third party consumes either shape.

---

## Disposition — Knowledge Platform

**ACCEPT, as proposed. 2026-08-30.**

E2 is the falsification and it needs no argument from us: `"04/24/2025"` is
the later document, lexicographic order picks `"05/04/2023"`, and §1.4
forbids that outcome by name. Trigger A, as filed.

The `null`-`iso` rule is the part we did not originate and would have
gotten wrong if left to guess at alone — "never ordered, never earliest,
never latest" is the only reading consistent with 72 of 75 `source_docs`
carrying no `issue_date` at all being the common case rather than the edge
one. Accepting it as written rather than counter-proposing.

Cost on our side taken as described: normalize 21 values across 75
`source_docs` and 16 rows, re-cut `3ae88642`. No new curation — every
lexeme is already held, and `iso: null` beside an ambiguous lexeme
(`"05/04/2023"`) is exactly the honest non-answer we'd publish anyway.

Batches with 004 for the re-cut, per Planning's own note that both need
one. Not filing a counter-amendment on obligation 16 — the reasoning for
leaving it untouched is correct as written.
