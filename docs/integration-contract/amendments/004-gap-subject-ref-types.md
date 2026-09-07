# Amendment 004 — the three ref types `Gap.subject` unions are undefined or undelegated

```text
Obligation   §1.2.1 (Gap.subject) and §1.1 (the stable core type list)
Trigger      D — an obligation depends on something the contract does not define.
             B for the fix Planning asked for in conversation.md T14: it cannot be
             built deterministically, because two of the three target shapes do not
             exist.
Filed by     Planning & BOM, 2026-08-30, after a type sweep of contract.md
Status       FILED. Governs nothing until ratified (AMENDING.md §3 step 2).
```

## The gap

`contract.md:171`, inside the `Gap` block — a type §1.2.1's own heading calls *"the shape
this contract has invoked six times and never defined"*:

```text
  subject      EntityRef | SlotRef | ParamRef     WHAT is missing, addressably
```

**`SlotRef` and `ParamRef` appear exactly once in the contract — here — and are defined
nowhere.** Not in §1.1's type list, not elsewhere in `contract.md`, and not in
`knowledge-datamodel.md` either, which §1.2 names as the place *"full shapes of every
type above"* live. We grepped both; the mention count is one and the definition count is
zero.

`EntityRef` **is** defined (`contract.md:58`) — `{ kind, id, tenant }` — but neither of
its two open fields is pinned:

- **`kind` has no vocabulary and no delegation.** The contract knows how to delegate a
  vocabulary: `contract.md:320` says *"`TaskCode`, `SourceClass` and `RoleCode` are closed
  vocabularies in the registries."* It does this for three types by name and does not do
  it for `EntityRef.kind`. That asymmetry is what makes this a defect rather than an
  omission — a reader cannot tell whether `kind` is open, closed, or registry-governed.
- **`tenant` is typed `TenantId` at `contract.md:119`, and `TenantId` is defined
  nowhere.** Third undefined type, same sweep.

## Evidence — the missing types have already produced two divergent implementations

### E1 · The type sweep

`[measured]` Every `*Ref` / `*Id` / `*Code` / `*Doc` / `*Spec` name in `contract.md`,
against its definition count:

| Named | Defined in §1.1 | Delegated to a registry | Status |
|---|---|---|---|
| `EntityRef`, `VersionRef`, `SourceRef`, `SnapshotRef`, `SourceDoc`, `UnitCode` | yes | — | fine |
| `TaskCode`, `SourceClass`, `RoleCode` | no | **yes**, `contract.md:320` | fine |
| `PanelSpec` | no | — | prose reference to a `knowledge-datamodel.md` type; fine |
| **`SlotRef`, `ParamRef`, `TenantId`** | **no** | **no** | **the defect** |

Two of the three sit inside a BINDING type. `AMENDING.md` §2 lists trigger D as *"an
obligation depends on something it does not define"*, which is this, three times.

### E2 · Both sides flattened the same missing type, differently

`[measured]`, snapshot `3ae88642`, all 81 gaps:

| `kind` | `subject` as published | count |
|---|---|---|
| `illegible_source` | `element-ea87258651-0000` | 54 |
| `unquantified` | `element-…` | 7 |
| `missing_value` | `doc-bcaa40d0536a` | 4 |
| `uncovered_condition` | `param:footing_diameter_mm@fence_model/mfr/certainteed-simtek-molded-composite-not-extruded-pvc#exposure D, fence height 49" to 76", HVHZ` | 16 |

Every one is a **string**, and three different ad-hoc encodings are doing the work the
three missing types would do: an `element-` / `doc-` id prefix carrying what `kind` is
for, and `param:<parameter>@<kind>/<id>#<point>` carrying an entire `ParamRef` in
punctuation.

Planning did the same thing in the other direction. `fenceai/core/gaps.py:49-65` collapses
all three refs into **one** discriminated `GapSubject { kind, id, tenant }`, with the
docstring recording it as a judgment call — *"a discriminated ref rather than three types,
because every consumer wants the same two things."* That was a guess. It is a poorer shape
than the string the other side ships, because a single opaque `id` cannot hold the
parameter, the scope and the condition point that `param:…@…#…` actually carries.

**The sharpest instance:** `parameters.py::_uncovered_gaps` builds
`", ".join(f"{k}={v}" …)` from the condition point; the Knowledge platform builds
`"exposure D, fence height 49\" to 76\", HVHZ"` from *the same dict*. Two teams
independently flattened one structured value into two different strings, in the same
release, because the type that would have held it was never written down. Neither is
wrong against the contract, and that is the whole problem — §1.2.1's *"addressably"* is
the one word the field exists for, and a string nobody agreed on is not addressable.

### E3 · The correction Planning owes on this, stated plainly

`conversation.md` T14 asked the Knowledge team to *"fix `Gap.subject` to the structured
shape"* per §1.2.1. **Two of the three shapes do not exist to be fixed to.** That ask was
not fair as written, and this amendment replaces it: the shapes have to be defined before
either side can be asked to ship them. Full `Snapshot` ingestion is still blocked on the
same field, so nothing about the priority changes — only about who owes what first.

### E4 · No worked example exists for `SlotRef`

`[measured]` Of 81 published gaps, **zero** carry a slot-shaped subject; 65 are
entity-shaped and 16 are param-shaped. Planning emits none either — `core/gaps.py`'s
`"slot"` literal has no producer today.

Recorded because it bears on the proposed text below: `EntityRef` and `ParamRef` can be
derived from data that exists, and `SlotRef` cannot. We propose the minimal shape and say
openly that it is the one part of this we are guessing at.

---

## Proposed text

### 1 · §1.1, add after `SourceRef`

```text
SlotRef      { entity: EntityRef, slot: str }        a named position inside an entity
ParamRef     { parameter: str, scope: EntityRef,
               point: { <dimension>: <value> } | null }
             # a table cell; point null addresses the whole table
TenantId     str | null       null = tenant-agnostic, i.e. Knowledge-global
```

`ParamRef.point` deliberately reuses the shape `ParameterTable.uncovered` entries already
have (`{ exposure_category: "D", hvhz: true }`, `contract.md:253`) rather than inventing a
second way to name a condition point. That is also exactly what the published
`param:…#exposure D, fence height 49" to 76", HVHZ` string is a rendering of, so this
costs the publisher a decomposition rather than new curation.

`TenantId` is `str | null` because the first real snapshot publishes `scope.tenant: null`
on all four `ParameterTable`s, and `contract.md:453` already names *"`mfr/<manufacturer>`
(Knowledge, global, **tenant-agnostic**)"* as a real category. Planning widened its own
model to `str | None` on 2026-08-30 (`82d47f2`) to accept the published shape; this makes
that widening the contract's answer rather than one repo's accommodation.

### 2 · §1.1, add one sentence beside the `EntityRef` line

```text
`EntityRef.kind` is a closed vocabulary in the registries, on the same terms as
`TaskCode`, `SourceClass` and `RoleCode`: adding an entry is never a breaking change
and never an amendment.
```

This is the only part of 004 that is *not* a shape change — it settles which side may add
a `kind` and at what speed. **The values themselves are not proposed here and must not
be**: `fence_model`, `element` and `doc` are all already in use and are registry
additions, which `AMENDING.md` §2 explicitly excludes from ratification. Routing them
through this file would destroy the property that lets the two teams move at different
speeds.

### 3 · §1.2.1, no change

`subject EntityRef | SlotRef | ParamRef` becomes correct the moment the three exist. We
are not proposing Planning's collapsed `GapSubject` as the contract's answer — it is the
weaker of the two shipped shapes, and we would be asking you to adopt our shortcut.

---

## Cost if this lands

**Knowledge.** `Gap.subject` becomes an object on 81 gaps. Every field is already held:
the `element-`/`doc-` prefix becomes `kind`, the `param:…@…#…` string decomposes into
`parameter` / `scope` / `point`. No new curation, no re-reading of any document. This is
the fix T14 asked for, now with something to fix it *to*.

**Planning.** `core/gaps.py`'s three-into-one collapse retires; `GapSubject` becomes the
real union. `parameters.py::_uncovered_gaps` and `_lapsed_gap` emit `ParamRef`s carrying
the point dict they already compute and currently stringify. `js/gaps.js` and the evidence
viewer render a structured subject instead of parsing a string — which they cannot do
today and do not attempt.

**Both.** Full `Snapshot` ingestion unblocks. It has been blocked on this field since the
first real snapshot.

## In-flight

- **`3ae88642` needs a re-cut.** It already does for amendment 002; batching these two
  means one re-cut, not two, which is an argument for dispositioning them together.
- **`docs/integration-contract/fixtures/snapshot-example.json`** (both repos) carries gap
  subjects in Planning's collapsed shape and takes the same edit.
- **`SlotRef` has no consumer on either side**, so if the disposition wants to defer it —
  define `EntityRef`/`ParamRef`/`TenantId` now and leave `SlotRef` for its first real
  example — that costs nothing today and we would not argue. Say so and we will re-file
  it that way rather than have it accepted on a shape neither of us has tested.

---

## Disposition — Knowledge Platform

**ACCEPT-MODIFIED. 2026-08-30. Defer `SlotRef`; ratify `EntityRef.kind`
delegation, `ParamRef`, and `TenantId` now.**

E4's own framing decided this for us: zero of our 81 published gaps carry a
slot-shaped subject, your engine emits none either, and `SlotRef` is the
one part of this proposal you named as a guess rather than a derivation.
Ratifying an unused, untested shape trades a real fix now for a guess we'd
both have to live with. Take your own offer — define `EntityRef`/`ParamRef`/
`TenantId` today, re-file `SlotRef` against its first real worked example
(most likely once `ContainedSlot` or a slot-level `Warning.attaches_to`
actually produces one).

`ParamRef.point` reusing `ParameterTable.uncovered`'s existing entry shape
is the right call — it costs us a decomposition of a string we already
build (`_uncovered_gaps`'s `", ".join(f"{k}={v}"...)`), not new curation,
and E2's sharpest instance (two teams flattening the same dict two
different ways) is exactly what that reuse closes.

The `EntityRef.kind` registry-delegation sentence: accept as written. It
settles who may add a value and at what speed without proposing any values
ourselves, which is the right scope for this file.

Correction acknowledged (§2, "T14's ask... two of the three shapes do not
exist"): agreed, and the amendment is the right replacement for that ask.

Cost on our side as stated: `Gap.subject` becomes an object on all 81
gaps, decomposing fields we already hold. Batches with 002 for the re-cut.

---

## Ratification text under ACCEPT-MODIFIED — Planning, 2026-08-30

Deferral accepted. `SlotRef` comes out and is re-filed against its first real
worked example, exactly as offered in In-flight above.

**But the deferral leaves one hole this amendment exists to close.** §1.2.1's
union still reads `EntityRef | SlotRef | ParamRef`, and with `SlotRef` deferred
**one of the three named types in a BINDING union remains undefined** — the
precise defect this file was filed about, surviving at one-third scale. The
proposed text said *"§1.2.1, no change… becomes correct the moment the three
exist"*, and under accept-modified only two will.

Cutting v1.2 in that state would ratify a known-undefined type in a BINDING
union, one turn after both sides agreed that is a defect. So the modified text
adds **one line, and no shape**:

### 1 · §1.1, add after `SourceRef` (`SlotRef` reserved, not defined)

```text
ParamRef     { parameter: str, scope: EntityRef,
               point: { <dimension>: <value> } | null }
             # a table cell; point null addresses the whole table
TenantId     str | null       null = tenant-agnostic, i.e. Knowledge-global
SlotRef      RESERVED. Named in §1.2.1's union and deliberately left undefined
             — no worked example exists on either side (zero of 81 published
             gaps and zero Planning-emitted gaps are slot-shaped). No producer
             may emit a slot-shaped `Gap.subject` until an amendment defines it.
```

### 2 · §1.1, the `EntityRef.kind` delegation sentence — unchanged from the filed text

```text
`EntityRef.kind` is a closed vocabulary in the registries, on the same terms as
`TaskCode`, `SourceClass` and `RoleCode`: adding an entry is never a breaking
change and never an amendment.
```

### 3 · §1.2.1 — still no change

The union keeps all three names. `RESERVED` is what makes that honest: a reader
can now tell that `SlotRef` is *deliberately* undefined and unemittable, rather
than accidentally missing — which is the distinction the filed evidence said a
reader cannot currently make about `EntityRef.kind`. Narrowing the union to
`EntityRef | ParamRef` was considered and **not** proposed: it is a change to
§1.2.1 neither side has dispositioned, and making it as a side effect of
executing a cut is the exact failure `AMENDING.md` §5 names.

**This needs one line back from Knowledge before step 5 runs.** If `RESERVED`
reads as scope creep on an accept-modified, say so and we will cut with the
union untouched and `SlotRef` simply absent from §1.1 — the hole stays, we will
both know it is there, and it closes with the re-filing. We would rather ask
than decide it inside the commit that freezes it.
