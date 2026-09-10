# Amendment 008 — per-value provenance on authored geometry

```text
Status:     FILED PROPOSAL ONLY — no ratification, no changed obligation.
Against:    FROZEN contract v1.3, 2026-08-31.
Filed:      2026-09-06, Knowledge-side implementation proposal.
Posted:     2026-09-08, conversation.md T50 §1 — formally handed to Planning in the
            thread. Until that date this file had reached Planning only because they
            copied a directory (T49 §9b), which they correctly declined to treat as a
            filing. The disposition clock starts at T50, not at Filed.
Obligation: 6; §1.1 Provenance; delegated geometry definitions in knowledge-datamodel.md §3.
Trigger:    D — an obligation depends on an undefined numeric-owner association.
```

The frozen contract continues to govern. Neither this filing nor its synthetic example authorizes publication. **Both teams have now recorded a verdict — Planning ACCEPT-MODIFIED and Knowledge accepting the three modifications, both 2026-09-08 — so `AMENDING.md` §3 step 3 is satisfied and step 5 waits for a batch.** Read "Both teams' dispositions are pending" until that date. No frozen file or checksum was edited.

## Evidence

1. Frozen contract §1.1 (lines 102–104) defines Provenance with cites, source_class, curation_level and version_status. It explicitly excludes admitted_by, which is run output. Obligation 6 (lines 605–613) extends classification to every published value, not just parameter rows.
2. The delegated datamodel §2.4 says Provenance attaches to Member dimensions and other numeric values; its Joint, Member, Placement and PartRequirement definitions do not define a serialized association for multiple values with different sources. SpecField and ParameterTable rows already have an explicit provenance owner and remain unchanged.
3. The authored-model preflight previously returned only deepcopy(model) after receiving a private field_evidence map. That map held citations only, omitted the required classifications and did not cross with the returned model. This failure is reproduced and recorded in `workspace/reports/emblem-schema-review.md`. The unsafe success path is now refused as `consumer_numeric_provenance_mapping_unresolved`.
4. Actual consumer private parsers do not preserve unknown owner fields; the independently reproduced PostSlot example in `workspace/reports/emblem-public-adapter-boundary.md` demonstrates why a permissive parse or producer-side sidecar is no proof of preserved executable meaning.

## Exact proposed addition

Add the following binding paragraph to the delegated definition of supported numeric owners, referenced by obligation 6 without changing Quantity or Provenance:

> **Per-field provenance on authored geometry.** A Joint, Member, Placement, InfillSpec, PartRequirement, FixingRule or HeightSupport that carries an explicitly authored numeric semantic value carries `field_provenance: {<relative JSON pointer>: Provenance}`. Each pointer starts at that owner and targets the complete declared semantic value, including a complete Quantity where applicable. It never targets only amount_milli, raw lexemes, a schema identifier or provenance metadata. The consumer's supported schema declares the legal target paths and target value kinds. Every present supported numeric value must have exactly one association; dangling, duplicate, wrong-kind and undeclared targets are refused. No provenance record supplies a missing value or authorizes a consumer default.
>
> The map is part of the published, hashed model and must survive consumer ingestion. It carries the frozen Provenance fields only; admitted_by is computed on the run. A producer must not synthesize classifications from a human-review flag or choose a winning source-policy row at publication. Existing SpecField and ParameterTable row provenance remain unchanged and are not duplicated into this map.
>
> An unknown/null value retains its existing owning-field meaning and required Gap behavior. It is never converted to zero. Map absence is not permission to invoke a private default. Unsupported owner fields and variants remain explicit refusals until implemented; this rule alone does not authorize their semantics.

The exact target registry and round-trip behavior must be dispositioned and tested on both sides before acceptance. This filing proposes a representation; it does not claim that a literal JSON pointer vocabulary is already a registry addition authorized by the current contract.

## Quantified initial scope

For the bounded two-rail, one-board-pattern panel with one post requirement, one cap and two separately addressed U-channel fixing requirements:

| Owner | Proposed numeric targets | Potential target count |
| --- | --- | ---: |
| Four Joint owners: two rails, one Member, one post | channel_depth, insertion_margin, shared_host_gap | 12 |
| One Member | base_engagement, top_engagement, gap_after, face_offset | 4 |
| Two FromBottom/FromTop placements | offset | 2 |
| Seven PartRequirements: two rails, board, post, cap, two channels | qty, overlap | 14 |
| Two FixingRules | qty_per_basis | 2 |
| One InfillSpec | edge_margin | 1 |
| One single-height Discrete HeightSupport | heights/0 | 1 |
| **Total potential addresses for this bounded shape** | | **36** |

This counts typed association locations, **not 36 missing dimensions or manufacturer claims**. Null optional values are not numeric readings; unsupported post-host/shared-host behavior remains separately blocked. Quantity defaults such as one board per fitted repeat are authored values and need explicit association; a kit's board inventory must not become per-repeat qty. Continuous/distributed placement, multiple heights and variants require explicit target-registry extensions and coverage tests before supported use. Joint.kind, fitting policy tokens and length-rule names remain separately authored semantic choices; numeric provenance does not establish those choices by itself.

## Concrete review object

`workspace/reports/authored-geometry-provenance-example.json` contains a complete hypothetical Joint with separate provenance for a synthetic 25 mm depth and synthetic 1 mm margin, plus matching synthetic source_refs/source_docs. Its wrapper explicitly says not agreed, not publishable, not manufacturer evidence. Both fields are honestly ai_proposal, curation level 0, version_status unknown. No human review, manufacturer datum, source-policy admission or physical fit is claimed.

The proposed map lives on the Joint, not inside Quantity. Different owners may use the same representation without forcing all fields to share one classification. A JSON-pointer index can distinguish differently sourced discrete heights without inventing a wrapper around each Quantity.

## Cost and implementation obligations

Knowledge: resolve reviewed value records into complete classified owner maps; validate typed target coverage/source closure; hash those maps with the model and referenced Parts; preserve the unchanged original source readings.

Planning: preserve the maps through a lossless public adapter and stored run/model representation; apply source policy per addressed value at run time; refuse unsupported targets, missing coverage and lossy unknown-field parsing; expose resulting admitted_by on run output only.

Both: test positive round trips using synthetic evidence, and refusal controls for dropped maps, absent targets, duplicate associations, malformed pointers, incorrect value kinds, missing classifications, unsupported defaults, null-to-zero conversion and unresolvable SourceRefs. Real Emblem publication additionally needs manufacturer evidence and implemented post-host/board-fit semantics; this amendment does not waive those requirements.

## In-flight impact

No current Part or ParameterTable serialization changes. Published models remain empty under the current implementation. Existing private Emblem candidates stay private. No application may interpret this pending proposal as an accepted alternative wire format.

## What must be on the table when this is judged

Recorded 2026-09-08 with the posting, at Planning's request in T49 §9b — *"Neither of
us should disposition 008 without §1 on the table beside it."* Agreed, and named here
so the condition survives in the file rather than only in the thread. Three items, and
the third is new since this amendment was filed:

1. **T49 §1 — the consumer floors what this map would certify.** `Mm = int` on the
   Planning side, and `contract.md:112-117` requires a multiplied published value to be
   consumed in thousandths and rounded only at its output. A `field_provenance` entry
   that classifies a 88.9 mm centreline is a promise about a number the reader currently
   stores as 89. That does not make the map wrong, but it decides what the map is
   *for*: certifying a value the consumer then re-rounds is a weaker guarantee than
   either side has been describing, and both should say which they mean before
   accepting the representation.

2. **The map is per-value, and the rounding is per-value too.** Every one of the 36
   proposed target addresses in the scope table above is a place where a classification
   and a conversion meet. If a target's value survives ingestion but its precision does
   not, the association is intact and the guarantee is not. Whatever this amendment says
   about "must survive consumer ingestion" has to mean the value as well as the record.

3. **C17, and the measurement in T50 §3.** `max_span_mm` is published today inside
   `footing_schedule`'s `paired` value and is converted to whole millimetres at
   `parameters.py:327`. That is the same class of loss as item 1, already live in
   published data, and it is evidence about how a "must survive ingestion" clause
   actually behaves in this pair of systems. It should inform the wording here rather
   than be settled separately.

## Dispositions

- Knowledge team acceptance: **ACCEPT the three modifications, 2026-09-08** — M1, M2 and M3 taken as written, recorded below (`conversation.md` T52 §3). Filing was not acceptance and posting it into the thread (T50) was not acceptance; this is.
- Planning team disposition: **ACCEPT-MODIFIED**, 2026-09-08 — three changes to the proposed text, recorded in full below (`conversation.md` T51 §4). Formally handed over 2026-09-08 (T50 §1); before that date there was nothing for this side to disposition.
- Ratification/version cut: **NOT PERFORMED**. Follow AMENDING.md steps 3–5 if accepted; do not update frozen files or hashes as a side effect of implementation.

## Disposition — Planning & BOM, 2026-09-08

```text
Verdict   ACCEPT-MODIFIED. Three changes to the proposed text, and one of them
          is a row in §2 that this amendment has to add or the rest of it
          re-ratifies itself every time a field is supported.
          1 · The target registry does not exist yet, so this amendment creates
              it — once, in §2 — and its CONTENTS then sit beneath every future
              amendment.
          2 · "Must survive consumer ingestion" is made to mean the value as
              well as the record, and the registry carries each path's retained
              precision so a floor is declared rather than silent.
          3 · The pointer namespace is named: the delegated published shapes,
              never the consumer's field names.
          Paragraph 3 of the proposed text is accepted verbatim.
```

### The defect is real, trigger D is right, and we checked it rather than taking it on report

`[read]` obligation 6, `contract.md:605-613`, extends classification to every
published value and not only to a parameter row. `[read]`
`knowledge-datamodel.md:283`: `Provenance` *"attaches to a `SpecField` inside a
published `Part`, to a `ParameterTable` row, **to a `Member`'s dimensions**, and
to anything else that carries a number read off a page."* The second sentence
names the owner and the first binds it, and neither document gives that owner a
serialized field. `SpecField` and `ParameterRow` have one; `Joint`, `Member`,
`Placement`, `InfillSpec`, `PartRequirement`, `FixingRule` and `HeightSupport`
do not.

`[measured]` the obligation is live and the gap is total: across all **31**
snapshots in your `workspace/snapshots/`, **not one publishes a single model** —
`models == []` in 25 of them and the key is absent in the other 6, non-empty in
none. So obligation 6 currently binds a payload that cannot be published
conformantly at all, which is trigger D as filed (`AMENDING.md`, *"an obligation
depends on something the contract does not define"*) and not trigger A. Nothing
measured contradicts the frozen text; the frozen text does not reach.

**Evidence 4 reproduced independently, in our tree.** `[measured]`
`PostSlot.model_fields == ["key", "requirement", "cap"]`
(`fencemodel/model.py:465`) — a published `Joint` on a post parses clean and is
discarded whole. `[measured]` none of `FrameSlot`, `Member`, `InfillSpec`,
`FixingRule`, `PartRequirement`, `Discrete`, `FromBottom`, `Provenance`, `Part`
or `SpecField` sets `model_config`, so all ten run Pydantic's default
`extra="ignore"`: a `field_provenance` key added to a `SpecField` parses without
error and is **absent** from `Snapshot.model_dump_json()`. `store/db.py:278-299`
stores that dump rather than the received bytes, so on the typed half of the
payload the map would not merely be unused — it would be gone before it reached
disk. Your report is right, and so is your framing of it: a permissive parse is
not preserved executable meaning.

**Two things we found that are better news than evidence 4, and both are yours
to use.** `[measured]` `models: list[Any]` (`knowledge/snapshot.py:204`) means
the map and its thousandths round-trip **verbatim** on the owner this amendment
actually concerns. And `[measured]` deleting the map from an otherwise identical
payload changes the value of `canonical_snapshot_id`
(`knowledge/snapshot.py:125`), and `load()` refuses a document whose members do
not hash to its declared id. So *"the map is part of the published, hashed
model"* is already enforceable at our door for free: **a dropped map is a hash
mismatch**, and one of the refusal controls your Cost section asks both sides to
build already exists.

---

### 1 · The registry question — answered against our own §6b, which does not hand us the answer we wanted

You said our T49 §6b reasoning is what you would expect to decide this, and that
it might decide it against you. It decides it against **both** framings.

`[read]` §6b's test has two limbs: a vocabulary written out literally in the
frozen text is not delegated, and a vocabulary named in §2's registry table or in
`AMENDING.md`'s exclusions is. `version_status` failed both, and §6b's conclusion
was the honest non-answer — *"we cannot tell you it is free, and we are not going
to tell you it is blocked either."*

Applied to the target paths:

- **Enumerated in the frozen text? No.** `[measured]` `grep` over `contract.md`
  for `Joint|FrameSlot|InfillSpec|FixingRule|HeightSupport|PanelSpec|
  PartRequirement|channel_depth|Placement|Member\b` returns **two** hits —
  `Member.continuity` and `PanelSpec` — neither of them a field list. The shapes
  are delegated by citation, twice: `contract.md:51` and `:203-204`.
- **In §2's table or `AMENDING.md`'s list? No.** §2 names roles, platform codes,
  source warnings, condition dimensions, interfaces, consumption models, tasks,
  source classes. There is no registry of geometry addresses.

So the target paths sit in exactly the position `version_status` sat in, and our
own precedent refuses to call that position free. **The convenient reading is not
available to us and we are not taking it.** Your filing's own caution — that it
does not claim a literal JSON-pointer vocabulary is already authorized — is
correct, and §6b is why.

**Which is why the answer is neither of the two you offered.** The registry is
not part of the binding text and it is not already beneath it. **It does not
exist, so this amendment creates it — once — and its contents are beneath every
amendment after that.** One ratified row, and then every new supported owner
field moves at registry speed forever. Leaving *"the consumer's supported schema
declares the legal target paths"* in the text without that row is the worse of
your two outcomes rather than the better one: a declaration with no registry
behind it is a declaration whose additions have no named mechanism, and by §6b's
own test that makes each one a round. It is `SlotRef` from 004 in a new place — a
named mechanism with no definition.

**Why this is not `version_status`, and not special pleading.** `version_status`
is a **value vocabulary on a frozen type**: a fourth value changes what a
conforming payload may contain, and `[measured]` breaks a consumer `Literal`
declared identically in four files (`source_policy.py`, `parameters.py`,
`source_docs.py`, `discovery_stub.py`) with no way to see it coming. A target
path is an **address in a definition the frozen text delegates**, and the
declaring party is the **consumer** — so an addition is only ever us widening
what we will accept. Additions in that direction cannot break the producer, and
that asymmetry is what §2's *"adding an entry is never a breaking change"* is
about. The existing row with exactly this direction is the one to copy:
*"Condition dimensions — … Planning declares what it can bind."*

---

### 2 · The integer-millimetre problem, which is ours

Your judging item 1 is correct and understated; items 2 and 3 are the same fact.
Grounded rather than asserted:

`[read]` `core/units.py:15`, `Mm = int`, under ADR-0002. `[read]`
`knowledge/parameters.py:249`, `to_mm` — the one named conversion point
`contract.md:112-117` requires, rounding half-away-from-zero. `[read]`
`core/units.py:11-13`, the two named tolerances, of which
`NUMERIC_TOLERANCE_MM = 1` is what this engine compares derived geometry at.

`[measured]` in `5b25c3b6`, walking every `Quantity` node: **110** with
`unit: mm`, **88** not a whole millimetre — your T48 §2 number reproduced
exactly — and the fractional parts are **only** 0.2, 0.4, 0.6 and 0.8 mm. Every
one is strictly below `NUMERIC_TOLERANCE_MM`. So the precision a
`field_provenance` entry would certify is finer than the resolution at which this
engine is permitted to compare geometry at all, and the map's value survives
ingestion only if something changes on our side.

`[measured]` on the values this amendment addresses:

```text
published milli   exact mm    to_mm    lexeme    lossless
     25400          25.400      25       1"        no
     22225          22.225      22       7/8"      no
     88900          88.900      89       3.5"      no
     63500          63.500      64       2.5"      no
      9525           9.525      10       3/8"      no
     25000          25.000      25    (synthetic)  yes
```

Your example `Joint`'s two synthetic values are whole millimetres and survive;
the real corpus's do not. A map saying *"`/channel_depth` is level 2, off a
manufacturer drawing, 25.400 mm"* against a run that cuts to 25 is not a broken
association — it is an intact association attached to a number the run does not
carry, which is your item 2 stated precisely.

**And this is what decides what the map is FOR.** `contract.md:112-117` does not
rescue 008: it governs values that are **MULTIPLIED** — *"a count, a pitch, a
span limit"* — and of the 36 addresses in your scope table, the multiplied ones
are `gap_after`, `overlap` and the widths beside them. `channel_depth`,
`insertion_margin`, `shared_host_gap`, `base_engagement`, `top_engagement`,
`face_offset`, `edge_margin` and `offset` are **summed, subtracted and cut to** —
they land on a cut list and never on a multiplication, and the BINDING clause
says nothing about them. That is not an argument against the amendment; it is the
reason the amendment has to say what surviving means, because the contract
elsewhere does not.

**Where our conformance work stands, so this is not a promise.** `[read]`
`fencemodel/fit.py:177`, `fit_pattern_milli` is conformant-shaped. `[read]`
`fencemodel/resolve.py:702-715` calls it, and its own comment states the thing
this disposition turns on: *"Today's `Member.width_mm` etc. are already whole mm
(authored, not yet sourced from a published thousandths quantity), so scaling by
1000 here is an exact no-op."* **The conformant seam is built and empty** — the
precision it was written to consume cannot reach it, because the field feeding it
is typed `Mm`. That is the integer-millimetre problem in one sentence, measured
in our tree rather than argued.

**What the 36 addresses do today.** `[measured]` against `fencemodel/model.py`:

| Scope row | Addresses | Have a destination | Retained precision |
|---|---:|---:|---|
| 4 `Joint`s × `channel_depth`, `insertion_margin`, `shared_host_gap` | 12 | **4** — both rails only | 1 mm |
| 1 `Member` × `base_engagement`, `top_engagement`, `gap_after`, `face_offset` | 4 | 4 | 1 mm |
| 2 `Placement`s × `offset` | 2 | 2 | 1 mm |
| 7 `PartRequirement`s × `qty` | 7 | 7 | **exact — a count** |
| 7 `PartRequirement`s × `overlap` | 7 | 7 | 1 mm |
| 2 `FixingRule`s × `qty_per_basis` | 2 | 2 | **exact — a count** |
| 1 `InfillSpec` × `edge_margin` | 1 | 1 | 1 mm |
| 1 Discrete `HeightSupport` × `heights/0` | 1 | 1 | 1 mm |
| **Total** | **36** | **28** | **9 exact · 19 at 1 mm · 8 no destination** |

The 8 with no destination are `Member`'s and the post's whole `Joint` (6) and both
rails' `shared_host_gap` (2) — `[measured]` `grep -rn shared_host src/` returns
nothing. That is your adapter report's finding, independently reproduced, and it
is exactly the work a registry declaration exists to make visible rather than
silent.

---

### The modified text

Three changes. Everything not quoted is accepted as filed, and **paragraph 3 of
your proposed addition is accepted verbatim** — *"An unknown/null value retains
its existing owning-field meaning and required Gap behavior… never converted to
zero… map absence is not permission to invoke a private default"* is right, and
it is right about us: `[read]` `insertion_margin_mm: Mm = 0`, `overlap_mm: Mm = 0`
and `edge_margin_mm: Mm = 0` (`fencemodel/model.py`). Your `insertion_margin`
argument at `knowledge-datamodel.md:640-644` — *"a `0` silently asserts 'no
clearance required', which no manufacturer said"* — applies to all three, and we
default all three.

#### M1 · §2, the registry table — add one row

```text
| Authored-geometry provenance targets | Which owner paths may carry a
  `field_provenance` association, and for each one its target value kind, the
  precision the consumer retains, and whether absence is a `Gap` or a default. |
  Planning declares what it can bind. |
```

This is the only new binding surface, it is ratified once, and every addition to
its contents afterwards is a registry addition under `AMENDING.md` §2.

#### M2 · Paragraph 1 — replace the registry sentence, and anchor the pointers

> **Per-field provenance on authored geometry.** A `Joint`, `Member`,
> `Placement`, `InfillSpec`, `PartRequirement`, `FixingRule` or `HeightSupport`
> that carries an explicitly authored numeric semantic value carries
> `field_provenance: {<relative JSON pointer>: Provenance}`. Each pointer is
> relative to that owner **as the delegated definitions serialize it**
> (`knowledge-datamodel.md` §3, cited by §1.2), never as any consumer's internal
> model names it, and targets the complete declared semantic value, including a
> complete `Quantity` where applicable. It never targets only `amount_milli`, a
> raw lexeme, a schema identifier or provenance metadata.
>
> **The legal target paths are a registry and Planning declares it**, on the
> terms §2 already sets for condition dimensions: Planning declares what it can
> bind, adding an entry is never a breaking change, and an addition is never an
> amendment. The declaration is a published, versioned artefact naming each legal
> path, its target value kind, the precision the consumer retains for it, and
> whether an absent value at that path is a `Gap` or a defaulted authored value.
> A snapshot's `contract_version` does not pin it, so a producer resolves
> coverage against the declared registry version it built against. Every present
> value at a declared path carries exactly one association; dangling, duplicate,
> wrong-kind and undeclared targets are refused. No provenance record supplies a
> missing value or authorizes a consumer default.

#### M3 · Paragraph 2 — replace the survival sentence

> The map is part of the published, hashed model and must survive consumer
> ingestion — **the association and the value it addresses, both.** A target's
> `Quantity` crosses in thousandths under obligation 4; a consumer's conversion
> to a coarser unit is a **derivation** of the certified value and never the
> certified value itself, and §1.1's conversion clause governs where that
> conversion may happen. Where a declared path's retained precision is coarser
> than the published value, the consumer publishes that on the run output beside
> the derived number rather than presenting the derived number as the certified
> one; it never publishes an association as though the run carried the value the
> association classifies. The map carries the frozen `Provenance` fields only;
> `admitted_by` is computed on the run. A producer must not synthesize
> classifications from a human-review flag or choose a winning source-policy row
> at publication. Existing `SpecField` and `ParameterTable` row provenance remain
> unchanged and are not duplicated into this map.

**What we considered and did not propose, so it is not re-filed later.** The
stronger rule — *a consumer that cannot retain thousandths for a path does not
declare that path* — would make our initial declaration the **9** count-valued
addresses and nothing else, and would leave 19 real associations refused rather
than qualified. Declared-precision is better on this pair of systems for the
reason you gave us in T49 §2 about `amount_milli` and repeated in T50 §3 about
pre-rounded limits: a loss that is recorded can be measured and fixed; a loss
refused into invisibility cannot. In the same session as this disposition we
factored the rounding rule out of `to_mm` into `core/units.py:32`
(`round_milli_to_mm`) as part of the `max_span_mm` fix T51 §1 reports, so the
rule is now one function its call sites share — which is what makes a per-path
retained precision an honest declaration rather than an aspiration.

---

### Planning's initial declaration under M1 — not part of the ratified text

Recorded so the amendment is not ratified against an imagined consumer. On
ratification day: **28** declared paths, of which 9 are exact counts and 19 are
retained at 1 mm; **8** undeclared — `Member.joint` and `PostSlot.joint` entire,
and `shared_host_gap` on both rails. `Continuous.min_mm`/`max_mm`/`step_mm` is a
fourth `HeightSupport` shape your scope table does not count, and `[read]` it is
our **default**, so the registry covers it or `HeightSupport` is half-addressed;
it goes in undeclared until it has a target kind.

---

### What this disposition does NOT do

- **It does not ratify anything.** 008 is the first amendment against a ratified
  v1.3 with in-flight work on both sides, so `AMENDING.md` §3a does not apply and
  there is no forcing trigger: the defect is real but nothing is being built
  wrong today (`[measured]` no snapshot publishes a model). It waits for a batch,
  and 009 is already owed.
- **It does not make the retained precision better.** Raising the 19 from 1 mm is
  our work, it is the same work `fit_pattern` and `max_span_mm` conformance name,
  and this disposition does not promise it done. What it promises is that the
  number will be declared rather than assumed.
- **It does not implement the refusal controls** in your Cost section beyond the
  one that already exists by hash.
- **It does not settle where `admitted_by` per addressed value is exposed on run
  output.** Your Cost section says *"apply source policy per addressed value at
  run time"*; `[read]` `knowledge/parameters.py:557-562` calls
  `source_policy.resolve()` and returns `resolution.winner` alone —
  `resolution.admitted`, the full admissible set that `source_policy.py:117`'s
  own docstring exists to carry, never leaves the function. That is the T49 item
  we declined as speculative, it is ours and still open, and fixing it is a
  precondition for the Planning half of your cost rather than part of the
  wording.

### One claim we could not verify

Evidence item 3 — the preflight that returned `deepcopy(model)` after a private
`field_evidence` map, the classifications it omitted, and the refusal now raised
as `consumer_numeric_provenance_mapping_unresolved`. `[read]`
`workspace/reports/emblem-schema-review.md` and `docs/state-and-gaps.md` carry
it; nothing in our tree can corroborate any of it and we are not treating it as
measured. It does not bear on the verdict: obligation 6 against the missing owner
in `knowledge-datamodel.md` §3 is sufficient for trigger D on its own, and
evidence 4 we reproduced.

---

## Disposition — Knowledge Platform, 2026-09-08

```text
Verdict   ACCEPT the three modifications, as written. M1, M2 and M3 all improve
          the filing, and two of them fix defects in it that we should have
          caught:
          M1 · we wrote "the consumer's supported schema declares the legal
               target paths" and did not notice we had named a mechanism with
               no definition -- 004's `SlotRef` in a new place, in our own text.
          M2 · "relative JSON pointer" without naming the namespace was
               ambiguous in the one way that matters, and the disambiguation
               went against the reader's convenience rather than ours.
          M3 · accepted on the argument we gave in T49 §2 and repeated in
               T50 §3, which we cannot now decline when it is turned around.
          One concession about our own Evidence, below.
```

**M1 — accept, and the reasoning is better than the one we could have made.** We
filed refusing to claim the target vocabulary was already a registry addition;
we did not go on to say what it therefore *was*, which left the amendment
proposing a declaration with no mechanism behind it. The distinguishing
principle in Planning's disposition is the part we did not have: a value
vocabulary on a frozen type is enumerated and a fourth value breaks a consumer
`Literal` with no warning, whereas a target path is an address in a delegated
definition **declared by the consumer**, so an addition only ever widens what the
consumer accepts and cannot break the producer. That asymmetry is what §2's
*"adding an entry is never a breaking change"* rests on, and it is why the
condition-dimensions row — *"Planning declares what it can bind"* — is the right
one to copy. One ratified row, then registry speed. Accepted as written.

**M2 — accept, including the cost it puts on us.** Anchoring each pointer to the
owner *as `knowledge-datamodel.md` §3 serializes it, never as a consumer's
internal model names it*, is a correction to our text rather than a change to our
proposal: a pointer namespace that was not named would have been resolved
differently on each side, which is the same failure as two teams flattening one
condition dict two ways (004's E2). Two obligations we are taking on with it, so
they are not discovered later:

- **A snapshot's `contract_version` does not pin the registry**, so we must
  record the declared registry version we resolved coverage against, per
  snapshot. That is ours to build and it is not built.
- Because the registry publishes each path's **retained precision**, we can read
  it. That gives us the option, later, of refusing to publish a certified value
  to a path whose retained precision would destroy it. **We are not taking that
  option now** and M3 is why — see below — but it should be on the record that
  the modified text makes it available rather than foreclosed.

**M3 — accept, and it is the one we looked at hardest.** It declares 19 of 28
paths retained at 1 mm: knowingly lossy, and the loss published on the run output
rather than hidden. We cannot decline it without contradicting ourselves twice in
one week. T49 §2 told us to keep `amount_milli` because *"round on your side and
the divergence becomes undetectable from either side of the boundary — the error
would still occur, and nothing in either system could see it"*, and T50 §3
declined to publish limits pre-rounded on that same ground. Planning's *"a loss
that is recorded can be measured and fixed; a loss refused into invisibility
cannot"* is that argument, applied to us. Accepted.

Two things we want stated with the acceptance, neither of them a modification:

- **The declared-precision disclosure has to be machine-readable.** M3 says the
  consumer *"publishes that on the run output beside the derived number"*. If it
  lands as prose we cannot measure the gap between what we certified and what a
  run carried, and the whole argument for preferring declaration over refusal
  rests on that gap being measurable. We are not proposing wording; we are saying
  what we will look for.
- **Retained precision is per path and can improve without an amendment**, which
  is M1 working as intended. The 19 at 1 mm are a starting state, not a
  settlement, and Planning's own disposition says so.

**The rejected stronger rule was rightly rejected.** *A consumer that cannot
retain thousandths for a path does not declare that path* would leave 9 of 28
addresses supported and 19 refused into silence. We would have argued for it a
week ago. The measurement that decides it is Planning's, not ours: the fractional
parts in this corpus are only 0.2, 0.4, 0.6 and 0.8 mm, every one strictly below
the tolerance at which that engine is permitted to compare geometry. A rule that
refuses 19 real associations to protect a difference below the comparison
threshold buys nothing and hides the 19.

**A concession about our own Evidence item 3.** Planning could not corroborate
it and declined to treat it as measured. They are right, and the fault is in the
filing rather than in their reading: item 3 describes our own preflight returning
`deepcopy(model)` and the refusal we now raise as
`consumer_numeric_provenance_mapping_unresolved`. That is a fact about this
platform's internals, it lives only in `workspace/reports/` and
`docs/state-and-gaps.md`, and **a boundary filing should not rest on evidence the
other side cannot open.** It is not load-bearing — obligation 6 against the
missing owner in `knowledge-datamodel.md` §3 carries trigger D on its own, and
evidence 4 was independently reproduced in Planning's tree. We would file it
today as motivation rather than as evidence.

**What this acceptance does not do.** It does not ratify. Both sides now record
a verdict, which satisfies `AMENDING.md` §3 step 3; step 5 waits for a batch, and
`AMENDING.md` §4 forces a cut only on a trigger-A falsification or a trigger-B
blocker. This is neither: `[measured]` no snapshot publishes a model, so nothing
is being built wrong against the gap today. It batches with 009
(`contributing_sources` on `ParameterRow`), which is owed and not yet filed.
