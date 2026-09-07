# Candidate amendments — noticed, not filed

```text
Status:   A running log. Nothing here is filed, and nothing here governs anything.
Purpose:  AMENDING.md §4 says a version is cut "when a batch is ready", and only a
          trigger-A falsification or a trigger-B blocker forces a cut on its own.
          Everything else waits. This is where "everything else" waits, so that
          waiting does not mean forgetting.
Promote:  when a batch is ready and neither side is mid-review, an item here becomes
          `NNN-short-slug.md` beside this file and follows AMENDING.md §3.
Discard:  an item that turns out to be a misreading is struck through with the
          reason, not deleted. Knowing what was considered and rejected is the
          point of keeping a log at all.
```

## How to add one

Name the trigger, quote the text, say what it costs to leave it. If you cannot
name a trigger it is not a candidate — it is a question, and
`docs/integration/planning-asks.md` is where questions go.

Check first whether it forces a cut rather than batching:

- **Trigger A** — measured evidence contradicts a binding item, and someone is
  building against it now. **Cut immediately, do not log it here.**
- **Trigger B** — a binding item cannot be built as written and it is blocking
  work. **Cut immediately.**
- **Trigger C** (scope) and **trigger D** (defect) — batch, unless something is
  blocked.

---

## ~~C1 — `curation_level` 0 versus 1 is never defined~~ — ANSWERED, no amendment

**Answered 2026-08-30 (`conversation.md` T17 §3), the cheapest disposition this
entry itself named: Planning answered directly, and it's settled on their
side.** They adopt this entry's provisional reading as written — `0` =
extracted by machine, uncited or unchecked; `1` = extracted by machine with a
resolvable `SourceRef`; `2` = a person compared it to the source image — and
go further: §1.2.1's closure rule (*"every `SourceRef.belongs_to` cited
anywhere inside a snapshot resolves to a `SourceDoc`"*) is already BINDING,
so a snapshot publishing `curation_level: 1` on a value with a dangling
`belongs_to` is refusable **by machine**, on a rule that already exists —
turning the 0/1 boundary from something two teams remember into an
invariant one of them enforces. Their own `min_curation` never uses 1 today,
but does use 0 for `component_dimension`, `installation_step`, and
`product_description`, so the boundary already decides real ties.

**Not filed.** Planning offered to co-sign a one-sentence disposition in
§1.1 if we'd rather have it in the document; we don't think it's needed —
their answer plus the existing closure rule closes this more strongly than
a defining sentence would. Revisit only if a future reader finds the
0/1 boundary ambiguous in practice.

<details><summary>Original entry, for the record</summary>

| | |
|---|---|
| **Trigger** | **D** — an obligation depends on something the contract does not define |
| **Raised** | 2026-08-25, while designing the snapshot builder |
| **Blocking?** | **No.** Nothing publishes yet, so nothing is relying on the wrong reading. Batches. |

**The gap.** `curation_level` is declared as `0 \| 1 \| 2` in `knowledge-datamodel.md`
§2.4 and rides on `Provenance` for every published value. The contract pins the
**top** of the scale and only the top — obligation 6: *"Nothing reaches level 2
without a person having compared it to the source image."*

**What separates 0 from 1 is stated nowhere**, in either document.

**Why it is not merely internal.** Three binding mechanisms read the value:

1. `SourcePolicy.min_curation` — *"how checked it must be to count here"*. Planning
   writes rows requiring level ≥ N for a task.
2. The tie-break rule (§1.4, BINDING) resolves ties by **higher `curation_level`**
   before `issue_date`.
3. Obligation 6 requires the value be **honest**, which presupposes a shared meaning.

So if this platform publishes `1` for a regex-extracted, cited, unreviewed value
while Planning's policy rows were written assuming `0` covered that case, values
become admissible for structural tasks that both sides would have refused —
silently, at run time, with no error anywhere.

**Cost of leaving it.** Zero today; nothing publishes. It becomes expensive the
moment the first snapshot ships with a level on every value, because policy rows
will have been written against whatever we happened to choose.

**Possible dispositions**, in rough order of cheapness:

- Planning answers the question directly and it turns out to be settled on their
  side — no amendment needed, and `planning-asks.md` was the right venue.
- One clarifying sentence in §1.1 defining the scale. Trigger D, tiny.
- It was deliberately left to the publisher, in which case the fix is a note
  saying so, not a definition — and this platform declares its own mapping.

**Our current provisional reading**, so it is at least written down: `0` = extracted
by machine, uncited or unchecked; `1` = extracted by machine and carrying a
resolvable `SourceRef`; `2` = a person compared it to the source image. That
mapping is an assumption, not an agreement.

</details>

---

## C16 — `Rule` is a BINDING payload member with no shape anywhere

| | |
|---|---|
| **Trigger** | **D** — an omission, but a structural one: the type cannot be produced |
| **Raised** | 2026-09-03, decomposing the four empty snapshot members before building `Procedure` |
| **Blocking?** | **No** for anything currently planned. **Yes** for `rules` ever being non-empty. |

`contract.md` §1.2 lists `rules [Rule]` in the snapshot payload, alongside nine members
that all have a defined shape. `Rule` does not have one. Searched and not found:

- no `Rule { … }` block in `contract.md`;
- no `Rule { … }` block in `knowledge-datamodel.md` — §3 defines `Part`, `FenceModel`,
  `PanelSpec`, `ContainedSlot`, `PartRequirement`, `AssemblyStep`, `Procedure`, `Warning`,
  `ParameterTable` and `Combination`, and stops;
- nothing in `docs/` at all. `FixingRule` (§3.3) is a different type — a `PanelSpec`
  component, not a payload member.

The word appears exactly three times in a load-bearing position: the payload list; §4's
tier-3 mapping, `derived rule → a Rule`; and traceability row B1, *"§4 — seven crossings,
`Gap` and `Rule` published"*. All three assume a shape none of them gives.

One false positive, recorded so it is not re-litigated: `knowledge-datamodel.md` §3.7 has a
table whose second column is headed `Rule` (N12, the registry split). That is a column
header meaning "the rule for this registry", not the type.

**What it costs to leave it.** Nothing today — this platform publishes `rules: []` and no
obligation names the member, so there is no violation to declare. The cost is that the
member is unbuildable by either side, indefinitely and silently. Neither team can be wrong
about `Rule`, because there is nothing to be wrong about; it will simply stay empty while
looking like work someone forgot.

**What we are NOT asking for.** Not a design. §4's mapping suggests Planning has one in
mind (`derived rule → a Rule`), and this platform has no evidence class it is currently
withholding for want of the type. The question is only whether the member is live.

**Likely disposition:** one of three, and any is fine —
(a) a shape, in which case it batches like any other addition;
(b) a note recording that `Rule` is reserved and deliberately unshaped, which makes the
empty member honest rather than outstanding; or
(c) removal from the payload, which is an amendment to a BINDING list and the only
disposition needing a round.

Raised now rather than later because the alternative is discovering it while building the
member, which is when a missing shape is most expensive.

---

## C2 — `Warning.attaches_to.ref` is declared but never typed

| | |
|---|---|
| **Trigger** | **D**, weakly — possibly just an omission a note could close |
| **Raised** | 2026-08-25, building the first `Warning` |
| **Blocking?** | **No.** Batches. |

`knowledge-datamodel.md` §3.7 declares `attaches_to REQUIRED · { kind: step |
procedure | document | product | model | warranty | maintenance, ref }` and gives
`ref` no type. For `kind: document` the obvious value is the `SourceDoc.content_hash`;
for `kind: product` or `model` it would be an `EntityRef`. Both are guesses.

68% of warnings in this corpus are document-scoped, so this is the common case, not
an edge one. **Lower stakes than C1** — a wrong guess here produces a warning that
renders in the wrong place, not a structural value that is wrongly admissible.

Likely disposition: a note rather than an amendment. Worth carrying in the batch so
it gets an answer either way.

---

## ~~C3 — is a `PanelSpec` member edge a "value"?~~ — RESOLVED, no amendment

**Resolved 2026-08-31 (`conversation.md` T39), the disposition this entry itself
named as likely.** Both sides had already leaned the same way independently —
this platform's own reading and Planning's §9.2 (`planning-asks.md`) both said
**no**, a membership edge is not a "value" under invariant 8, matching
Planning's own `ContainedSlot`/kit-credit design (membership cited to the sealed
BOM, slot count authored rather than extracted). No BINDING text is touched —
`knowledge-datamodel.md` is this platform's own Tier-2/3 document, not
`contract.md` — so this closes as a clarifying sentence, not an amendment.

**The sentence**, added to invariant 8: *"A membership or containment edge...
is not itself a value: it is authored structure (invariant 10), and carries no
`SourceRef` of its own. What this invariant binds is a quantity asserted about
that structure — a count, a length, a spacing."* Invariant 10 cross-references
it. Full text in `knowledge-datamodel.md` §6.

**What this unblocks:** `docs/layering.md` §5's carve-out — the hand-researched
dataset's composition graph (32 lines, 59 assemblies, 225 components) is
authored structure, not something a `SourceRef` could ever point at — is now
settled rather than merely assumed. It clears *design*, not *implementation*:
`Part` remains at zero, still blocked on the part-type spine (registry
`§2.1`), which nobody has built yet. C3 was never the only blocker; it was
the cheaper one to close first.

<details><summary>Original entry, for the record</summary>

| | |
|---|---|
| **Trigger** | **D** — possibly; it may be settled and merely unwritten |
| **Raised** | 2026-08-25, deciding how the hand-researched dataset is treated |
| **Blocking?** | **No**, but it blocks *design* sooner than the others. Batches for now. |

Invariant 8 (`knowledge-datamodel.md`): *"Every published **value** carries a
resolvable `SourceRef`."* Invariant 10, same document: *"**Structure is authored,
not extracted.** No table reader produces a `PanelSpec`."*

Those two are not obviously compatible. If the *membership* edge — this component
belongs to this panel — counts as a "value", then structure needs a `SourceRef`,
and invariant 10 says no such reference can exist because nothing extracts it.
If it does not count, `Authorship` on structure is already legal and there is
nothing to amend.

**Why it matters now.** `docs/layering.md` §5 decides that the dataset's *values*
are curated as an ordinary source while its *composition graph* — 32 lines, 59
assemblies, 225 components — is retained as authored structure. That carve-out is
the only route to a `Part` at all, since no amount of curation over 2,147 pages
establishes that three particular components compose one Chesterfield panel. If
membership is a "value", the carve-out needs an amendment before it can be built.

**Likely disposition:** a clarifying sentence distinguishing an asserted quantity
from an authored relation. Cheap if it is only wording; expensive to discover
after Phase D is built either way.

</details>

---

## ~~C4 — no `GapKind` for "the authority explicitly does not extend here"~~ — STRUCK

**Struck 2026-08-27 (`conversation.md` T1→T2).** The premise held — a real footing
table does affirmatively exclude `(exposure_category=B, hvhz=true)`, confirmed
against source by Knowledge — but the fact does not need a new stable-core
`GapKind` to say so. `kind: uncovered_condition` + `domain_basis: measured`
already means "this table really does not cover that point," which IS "checked,
not a guess"; what was missing was only the WHY, and `because{code, params}` —
already a free registry addition per §2 — is exactly the field for that. Agreed
disposition: a new platform code, `parameter_condition_excluded`, carrying the
excluded point the same way `uncovered_parameter_point` already carries `point`.
Needs no amendment. **Implemented on Planning's side 2026-08-27** — the code is
in both locale bundles, guarded by `tests/web/test_locale_bundles.py`'s
`PUBLISHED_GAP_CODES` (codes rendered but never emitted by this engine's own
backend), and the corrected fixture's `(exposure_category=B, hvhz=true)` case
is now `FIXTURE-gap-excluded-1`, published directly rather than left in
`uncovered`. `parameter_condition_excluded` confirmed as the spelling in
`conversation.md` T4 (a).

<details><summary>Original entry, for the record</summary>

`uncovered_condition` means "no row covers this point" or "we may not know the
table's extent." Neither is the fact at `(exposure_category=B, hvhz=true)` in a
real footing table: both non-HVHZ rows are bracketed, and the approval simply
does not extend to HVHZ at exposure B. A planner reading `uncovered` there would
be told "may not know" when the true fact is "checked, and refused" — and would
be free to proceed as though a value might still turn up, which it structurally
cannot.

`GapKind`'s eight values are enumerated inline in the contract's stable-core text
(§1.2.1), not in the free registries (§2), so a ninth value reads as a trigger-D
defect amendment rather than a registry addition.

</details>

---

## ~~C5 — `ParameterTable.value_type` cannot express a paired design point~~ — PROMOTED

> **PROMOTED 2026-08-30 to
> [`006-paired-value-type-for-footing-schedule.md`](006-paired-value-type-for-footing-schedule.md),
> filed by Knowledge.** The disposition below was agreed 2026-08-27; this is
> the concrete wording neither side had written yet. Kept here in full,
> unedited, because the reasoning is the point of the log.

## C5 — `ParameterTable.value_type` cannot express a paired design point

| | |
|---|---|
| **Trigger** | **D** — real corpus data does not fit the closed `value_type` shape |
| **Raised** | 2026-08-27, same review as C4 |
| **Blocking?** | **No.** Neither side publishes `max_span_mm` against real data yet. Batches. |

A real footing/span table is not one value per `(exposure, hvhz)` point — it is
**two** design points per exposure, `(footing depth, max span)`, where a deeper
footing buys a wider span. `value_type: quantity(<UnitCode>) | token(<closed
set>)` — declared once, on the table — cannot express a pair, and `hit_policy:
unique` is violated by the real data as a result (two valid rows at one domain
point, no dimension to split them).

**Disposition flipped 2026-08-27 (`conversation.md` T1→T2).** Planning's original
preference — footing depth as an additional domain dimension — is withdrawn.
Measured against real corpus data, that shape turns one `unique` violation into
**8 of 18 cross-product artifacts**, several actively misleading (a footing
depth below what the table certifies at all reading as an ordinary coverage
hole). More fundamentally, `domain` per §2 is what Planning **binds from site
facts at run time** — footing depth is not a site fact, it is a design decision
a fence gets built to, the same category as choosing between two admissible
SKUs. **Agreed disposition: option (1), a paired/compound `value_type`.** Still
trigger-D — extends the closed `quantity(<UnitCode>) | token(<closed set>)`
union in the stable core — and still needs the amendment process; both sides
are willing co-authors. Worth batching with C1 if both are ready around the same
time, since both touch `Provenance`/`ParameterTable`.

Rejected by both sides: `hit_policy: collect_min`/`priority` over the two rows,
which silently discards the cheaper compliant option — one worked example, 7
posts vs. 9 on a 40 ft run at exposure C.

---

## ~~C6 — no date format is declared, and a BINDING tie-break has to order dates~~ — PROMOTED

> **PROMOTED 2026-08-30 to [`002-typed-date-and-absent-date-ordering.md`](002-typed-date-and-absent-date-ordering.md), filed by Planning.**
> The condition this entry set for itself expired the same day it was written:
> *"it stops batching the day they do."* Planning consumed `3ae88642` through
> `parameters.py`/`expand()` on 2026-08-30, and the lexicographic compare this entry
> predicted reported a row valid until 2028 as lapsed in 2026. Re-triggered **A**
> (falsification, someone building against it now) with **B** alongside, either of
> which forces a cut rather than a batch — see the filed amendment for the argument
> and for the second half of the defect this entry did not reach: **72 of 75**
> published `source_docs` carry no `issue_date` at all, and the contract says nothing
> about what an ordering does with a missing operand.
> Kept here in full, unedited below, because the reasoning is the point of the log.

| | |
|---|---|
| **Trigger** | **D** — a binding rule depends on an ordering the contract never defines *(re-triggered A/B on filing)* |
| **Raised** | 2026-08-30, on cutting the first real `ParameterTable` |
| **Blocking?** | **No.** Planning consumes no snapshot yet. Batches — but it stops batching the day they do. |

**The gap.** §1.4 is BINDING that a policy tie resolves *"by higher `curation_level`,
then later `issue_date`, then lexicographic `source_class`"*. Ordering by `issue_date`
requires knowing what an `issue_date` **is**. The contract types `source_class`,
`curation_level` and every `UnitCode`, and types no date at all — not `issue_date`,
not `expiration_date`, not `ParameterTable.rows[].valid_from` / `valid_until`.

**What this platform actually publishes** `[measured]`, snapshot
`3ae88642`: US-format slash strings, straight from the source document's own
stamp — `"04/24/2025"`, `"05/04/2023"`, `"03/13/2029"`. Three `issue_date` and
two `expiration_date` values in `source_docs`, and now `valid_from` /
`valid_until` on four `ParameterTable` rows, which is the field §1.4's tie-break
reaches through.

**What it costs to leave.** Lexicographic comparison — the obvious reading of a
bare string field, and the one §1.4 already names for `source_class` — orders
`"04/24/2025"` **before** `"05/04/2023"`. The 2025 document loses the tie to the
2023 one. §1.4's own sentence forbids exactly that outcome: *"never silently
preferring an older document."* And `"05/04/2023"` is ambiguous on its face; only
`"04/24/2025"` is self-disambiguating, and only by accident of the day number.

**Not merely this platform's bug to fix.** Publishing ISO-8601 unilaterally would
be the right internal change and would still leave the contract silent, so the
next producer of a date is free to differ. The fix is a typed `Date` in §1.1 —
ISO-8601 `YYYY-MM-DD`, with the source's own lexeme kept beside it where it
differs, the same shape `Quantity` already uses for `value_raw`.

---

## C7 — `Joint` cannot express two simultaneous connection mechanisms at one `FrameSlot`

| | |
|---|---|
| **Trigger** | **D** — real product construction does not fit the proposed shape |
| **Raised** | 2026-08-30, drafting a worked `FrameSlot`/`Joint` example against a real product |
| **Blocking?** | **No.** `Joint` as an object is itself still proposed, not built anywhere (§3.3.1). Nothing is authored against it yet. Batches. |

**The gap.** A SimTek molded panel connects to its post two ways at once, both
load-bearing, neither optional: the panel's edge is received laterally by a
routed channel in the post (*"insert panel into channel on first post... flex
the next post until the channel will receive panel"*), and it also bears
vertically on a panel support bracket screwed to the post at a stated height
(*"ease panel down onto panel brackets... panel support brackets must be used
under both sides of every panel"* — zinc-plated 1½" #10 hex screws, per the
post's own spec sheet). `Joint { kind: butt | channel | groove | bracket |
overlap, ... }` (§3.3) has one `kind` per `FrameSlot`. There is no field for
the second mechanism.

**Sources.** `manuals/barrette-outdoor-living/structural/noa-24-0117.06-simtek-fence.pdf`
p.7 (post/bracket spec sheet) and pp.6/8 (panel drawings);
`manuals/barrette-outdoor-living/bufftech-simtek-fence-install-guide.pdf`
pp.20-21 (install steps and the bracket-position-by-panel-size table). Full
worked example in `docs/superpowers/specs/2026-08-30-llm-assisted-extraction-design.md`
§4, Spike 4.

**Cost of leaving it.** Whichever mechanism is picked as the slot's one `kind`,
the other has no field to live in at all — not reduced fidelity, an outright
absent fact. This is not a hypothetical: SimTek is a real product line in the
vertical slice currently being worked.

**Possible dispositions**, in rough order of cheapness:

- `joint` becomes a list, `[Joint]`, rather than one object — cheapest to add,
  costs a migration for anything already authored against a single `Joint`
  (nothing is, yet).
- A `secondary_joint: Joint | null` field, mirroring how `Member` already
  carries multiple engagement fields rather than one.
- `Joint.kind` becomes a set rather than an enum member — cheapest to state,
  most disruptive to every consumer that pattern-matches on `kind`.

**Second, independent worked example, 2026-08-30 — this is not a SimTek
quirk.** A Chesterfield picket-end channel shows the identical shape on a
different product, different manufacturer-family sheet, different mechanism:
*"Attach channel to post in four locations"* (a screw-fastened face mount)
and, separately, *"Center channel on post between routed holes"* (the same
channel receiving a picket end) — one intermediate part, two `Joint`
relationships, confirmed against the rendered page image
(`bufftech-simtek-fence-install-guide.pdf` p.31: `"ATTACH END CHANNEL TO POST
WITH 4 SCREWS"`). Raises the cost of leaving this unfixed: it is not one
product's edge case.

**Confirmed independently on Planning's own engine, 2026-08-30
(`conversation.md` T17 §0).** `model.py:78`, `JointKind = Literal["butt",
"channel", "groove", "bracket", "overlap"]` — the same five values, arrived
at independently — and it is single-valued on **both** `FrameSlot` (`:375`)
and `Member` (`:422`). Two teams hit the identical hole from opposite
directions, read correctly as evidence the gap is real, not as a
workaround: *"we are confirming your findings, not solving them."*

---

## ~~C8 — no declared rule for choosing `FrameSlot` vs. `Member` for a non-repeating infill unit~~ — RESOLVED, no schema change

**Resolved 2026-08-30 (`conversation.md` T17 §0).** Our proposed rule was
right, and Planning sharpened it with something we couldn't see from our
side: `fenceai/fencemodel/fit.py::_count_members` returns
`floor(usable / (width + gap))`, so a one-`Member` pattern resolves to one
piece **only by coincidence** when the panel happens to be exactly as wide
as its bay — and would silently return 2 the day someone authored a wider
bay or a narrower panel. Resolving by coincidence is worse than failing.

**Agreed rule, better than the one we proposed:** the count is a symptom,
not the test. `InfillSpec` carries `justification`, `excess`, `gap_after`
and `edge_margin` — every one a *distribution* concept meaningless for one
solid piece, while a `FrameSlot` is a named position that runs no fitter at
all. **Anything positioned rather than distributed is a `FrameSlot`,
whatever its count.** No schema change; this is an authoring rule, and it
generalizes past the pattern-count-1 special case we'd guessed at.

<details><summary>Original entry, for the record</summary>

## C8 — no declared rule for choosing `FrameSlot` vs. `Member` for a non-repeating infill unit

| | |
|---|---|
| **Trigger** | **D** — a real product doesn't cleanly fit either authoring shape |
| **Raised** | 2026-08-30, same worked example as C7 |
| **Blocking?** | **No.** Batches. |

**The gap.** `FrameSlot` is a named position in the frame (a rail, keyed);
`Member` is one repeat of a pattern inside `InfillSpec` (one picket among
many). A SimTek panel is one solid molded piece per bay — not a repeating
count of small identical parts like pickets, but also not obviously "framing"
the way a rail is. §3.3.1's own five-authoring-shapes table (`FrameSlot`,
`Member`, `FixingRule`, `PostSlot`, `ContainedSlot`) gives no rule for which
shape a monolithic, non-repeating infill unit should use.

**Why it recurs rather than being a one-off.** SimTek is not the only product
in this corpus built from one solid infill piece per bay rather than a
repeating count of small parts; whatever rule resolves this for SimTek is
needed again for every similar product, not just this one.

**Disposition tried in the worked example, not a fix:** `FrameSlot` was chosen
as the pragmatic answer, with the choice stated explicitly as a modeling
judgment rather than something the schema decided. That is a workaround, not
a closed question.

**Likely disposition:** a clarifying rule analogous to how N10 (§3.6) resolved
`AssemblyStep.scope` ambiguity — something like *"an infill unit with pattern
count 1 and no repeat dimension is authored as a `FrameSlot`."* Cheap if that
is the right rule; needs a second worked example on a different single-piece
product to confirm it generalizes before being written down as one.

</details>

---

## C9 — `Joint.kind` has no value for a spring-retained snap connection

| | |
|---|---|
| **Trigger** | **D** — a real, common mechanism has no enum value |
| **Raised** | 2026-08-30, second `PanelSpec` worked example (Chesterfield) |
| **Blocking?** | **No.** `Joint` is proposed, not built. Batches. |

**The gap.** Chesterfield's top and bottom rails are not screwed, channeled,
grooved, or bracketed onto the post — they are inserted into a routed post
opening and retained by a separate lock ring whose tabs recoil once seated:
*"Insert lock ring in both ends of bottom rail... Depress lock ring tabs,
insert bottom rail in post... Tabs will recoil to hold rail in post"*
(`bufftech-simtek-fence-install-guide.pdf` p.30), confirmed as a diagram
callout on p.31 (`"HOLD TOP RAILS IN POST WITH LOCK RING"`). None of `butt |
channel | groove | bracket | overlap` names a spring-retained insertion —
picking the nearest (`channel`) silently discards the retention mechanism,
which is exactly the failure mode `Joint` exists to avoid for the SimTek
bracket case (C7).

**A second, related gap in the same example.** The lock ring is itself a
distinct physical part (inserted into each rail end before the rail is
inserted into the post), and `PartRequirement` names one part per slot — there
is nowhere to also require the retainer.

**Possible dispositions:** add `spring_retained_socket` (or similarly named)
to `Joint.kind`; separately, allow a slot to carry an additional retainer
`PartRequirement` or a part-contains-part relationship (this second piece
converges with C8's `ContainedSlot` territory).

**Confirmed, not solved, on Planning's engine, 2026-08-30 (`conversation.md`
T17 §0):** same `JointKind` hole as C7 — no help from their side, and their
own words: *"no schema change"* is not on offer here, this one stays open
on both sides.

---

## C10 — no way to express alternative fastening methods independent of joint geometry

| | |
|---|---|
| **Trigger** | **D** — real corpus data states equally-valid alternatives `Joint` cannot hold |
| **Raised** | 2026-08-30, second `PanelSpec` worked example (Chesterfield post cap) |
| **Blocking?** | **No.** Batches. |

**The gap.** *"Caps may be secured with glue, silicone adhesive or #8 x ¾"
screws, caps and washers"* (`bufftech-simtek-fence-install-guide.pdf` p.30).
Three fastening methods, explicitly interchangeable, none more authoritative
than another. `Joint` has fields for interface geometry (`channel_depth`,
`insertion_margin`) but nothing for "how it's held together," and nothing
that can hold three alternatives at all — every other field in this schema
is one value or a null, not a set of equally-valid choices.

**Compounding ambiguity found in the same example.** The product-family
component sheet (`NOA-12-1106.11-extruded-pvc-vinyl-fencing.pdf` p.10) depicts
*two different cap profiles* — an external cap with an overlapping skirt and
an internal cap that enters the post opening — and nothing in the
installation instruction says which one a Chesterfield build actually uses.
That is closer to C1/C3's shape (an undefined axis a binding rule already
depends on) than to a missing enum value, and is filed here rather than
split out because both symptoms trace to the same underlying cause: `Joint`
assumes one fixed geometry and one fixed fastening, and this component has
neither.

**Possible dispositions:** a fastening-method field independent of `kind`,
able to hold alternatives; separately, resolving the cap-profile ambiguity is
a data question (which cap Chesterfield actually ships), not a schema one.

**Confirmed, not solved, on Planning's engine, 2026-08-30 (`conversation.md`
T17 §0):** same single-valued `JointKind` on both `FrameSlot` and `Member` —
no fastening-method field on their side either. Stays open on both sides;
the cap-profile half stays a data question, agreed.

---

## C11 — `AssemblyStep` has no per-step applicability condition

| | |
|---|---|
| **Trigger** | **D** — a real step is explicitly conditional, and nothing carries the condition |
| **Raised** | 2026-08-30, first `Procedure` worked example (Chesterfield installation) |
| **Blocking?** | **No.** `Procedure`/`AssemblyStep` are both unbuilt (§3). Batches. |

**The gap.** *"When installing Arbor Blend, Arctic Blend, Brazilian Blend,
Frontier Blend, Natural Clay, Sierra Blend, Timber Blend or Weathered Blend,
picket end channels are required (2 per section)"*
(`bufftech-simtek-fence-install-guide.pdf` p.30, step 7). `AssemblyStep` (§3.6)
has no condition or applicability field — the finish-dependency can be kept
in `text_i18n`, but that makes it prose a person reads, not something
Planning's engine can act on to decide whether the step applies to a given
build.

**Possible disposition:** a structured `applies_when` condition on
`AssemblyStep`, expressed against the same condition-dimension vocabulary
`ParameterTable` already uses (§2.7), rather than a step-specific one-off.

**Confirmed on both sides, 2026-08-30 (`conversation.md` T17 §0), and the
blocker is narrower than a schema change.** Planning has no applicability
field on `AssemblyStep` either — real gap, confirmed. But they already
evaluate variant conditions against a live fact context
(`fencemodel/resolve.py:64`, `PanelContext.condition_ctx()` →
`panel.*`/`site.*`), so an `applies_when` would plug into an evaluator that
already exists rather than needing a new one. **The actual catch:** our
example's axis — Arbor Blend, Arctic Blend, etc. — is a finish/colour
dimension, and their fact context carries none today (`panel.width_mm`,
`panel.height_mm`, `panel.vertical`, `site.hvhz`, `site.exposure_category`
only). Adding one is a **registry addition** — `AMENDING.md` §2 excludes
registry additions from ratification, so it doesn't wait for this batch or
need their sign-off. Their instinct matches ours: reuse the same condition
vocabulary `ParameterTable` already has, not a step-specific one. The
`applies_when` field itself is still the real, open schema gap.

---

## ~~C12 — one `AssemblyStep` cannot hold two genuinely alternative methods~~ — RESOLVED, no schema change

**Resolved 2026-08-30 (`conversation.md` T17 §0). We had both tools in hand
and didn't recognize the shape.**

**First half — the two alternative methods.** `Edge{kind: after |
not_before | before | exclusive_with}` (`knowledge-datamodel.md` §3.6) —
`exclusive_with` was already in the vocabulary we quoted in our own
extraction contract, and it is exactly *"these two steps are alternatives:
a build does one or the other, never both"*
(`fenceai/fencemodel/model.py:601-632`, live since their obligation 11).
Author *"Solidify Gate Posts"* as **two** `AssemblyStep`s — stiffener, and
rebar-and-concrete — each with its own `slots`/`requires`, joined by one
`exclusive_with` edge. Different parts and different prerequisites are what
two steps express; one branching step isn't needed at all.

**Second half — the cure time's dependency target.** `AssemblyStep.kind:
installation` already covers a step that places no parts (the worked
example on Planning's side is literally *"let the footings cure
overnight"*). Author the 72-hour wait as its own `installation` step; the
step that must wait carries `not_before: <that step>`. No `Elapsed` target
on an edge is needed — the wait becomes a thing in the order, not a
property hanging off one.

**What's still open, separately:** the *duration itself* (72 hours,
machine-readable rather than prose in `text_i18n`) is a real, narrower gap
neither half above closes — worth its own entry if it ever matters enough
to act on.

<details><summary>Original entry, for the record</summary>

## C12 — one `AssemblyStep` cannot hold two genuinely alternative methods

| | |
|---|---|
| **Trigger** | **D** — real instructions branch into two methods with different parts |
| **Raised** | 2026-08-30, same worked example as C11 |
| **Blocking?** | **No.** Batches. |

**The gap.** Step 10, *"Solidify Gate Posts,"* states two methods explicitly
as alternatives — (a) an aluminum gate-post stiffener, screwed in place, or
(b) rebar and concrete fill, cured 72 hours — with different parts, different
`slots`, and different prerequisites (method (b) has a cure time; method (a)
does not). One `AssemblyStep` object can name one set of `slots`; conflating
both methods into it either drops one entirely or falsely implies both
happen together.

**Compounding gap in the same step.** Method (b)'s cure time has nothing to
attach an `after`/`not_before` edge *to* — the source states the gate must
stay blocked for 72 hours, but names no later numbered step as "when
blocking ends." `Elapsed(Quantity)` can represent the duration as a slot
target, but `requires` edges point at step keys, not at elapsed events.

**Possible dispositions:** allow an `AssemblyStep` to branch into named
alternative methods, each with its own `slots`/`requires`; separately, allow
`requires` to target a `SlotTarget` (including `Elapsed`) rather than only a
step key.

</details>

---

## C13 — no relation for "either order is fine," across repeated instances of a step

| | |
|---|---|
| **Trigger** | **D** — the source states an explicit non-dependency `Edge` cannot hold |
| **Raised** | 2026-08-30, same worked example as C11/C12 |
| **Blocking?** | **No.** Batches. |

**The gap.** *"Assembly may be continued by installing all bottom rails
first or one section at a time"* (`bufftech-simtek-fence-install-guide.pdf`
p.30, step 5) is the corpus's own example already named in
`knowledge-datamodel.md` §3.6 as the reason `requires` needs edge kinds at
all — and it still isn't fully representable. `Edge{kind: after |
not_before | before | exclusive_with}` orders two *named steps*; this
statement is about the order **bay instances of the same step** may run in
across a whole fence run, which is a different axis (step keys don't carry a
bay-instance qualifier) that no edge kind addresses.

**Possible disposition:** a branch or alternative-order relation that can
address per-bay-instance step ordering, distinct from the step-to-step
`Edge` that already exists.

**Confirmed, and honestly not yet answerable, on Planning's engine,
2026-08-30 (`conversation.md` T17 §0).** `Prerequisite.step` names another
step's `key`, which carries no bay-instance qualifier either — same gap,
independently. They decline to guess at a shape: their own step-per-bay
instantiation (`report/assembly.py`) isn't built yet, so whether this
*should* be an edge at all is a question honestly deferred rather than
answered speculatively. Stays open on both sides, with no schema proposed
by either.

---

## C14 — `Warning.attaches_to` has no scope between "one step" and "the whole document"

| | |
|---|---|
| **Trigger** | **D**, weakly — may already be settled and simply not carried into a compact reference |
| **Raised** | 2026-08-30, `Warning` worked examples |
| **Blocking?** | **No.** Batches. |

**Not a new gap in the schema — a near-miss worth recording anyway.** Given
only `Warning`'s field list (not the worked reasoning in
`knowledge-datamodel.md` §3.7 N11), a test run filed the page-30 freeze-thaw
caution (printed against method 10(b) specifically, not step 10 as a whole)
as unresolvable, on the reasoning that neither `step` nor `document` honestly
names its scope. §3.7 N11 already settles this exact example —
*"attaching the freeze-thaw footnote to step 10 would be a curator's
inference"* — and its disposition is `document`-scope, one annexe entry,
precisely because a reader judges applicability from the warning's own text
rather than needing a machine-actionable pointer to the one substep. Struck
as a schema gap; kept as a process note: a compact reference that gives a
type's *shape* without its *settled reasoning* will cause this exact
rediscovery again. Fixed in the extraction contract this batch used
(`chatgpt-project-bundle/01-EXTRACTION-CONTRACT.md`, not itself a repo
artifact); worth a one-line addition to `knowledge-datamodel.md` §3.7 itself
if this keeps recurring once real curation work begins.

---

## ~~C15 — `SpecField.value`'s wire shape contradicts obligation 4~~ — RESOLVED, no amendment

**Resolved 2026-09-03 (`conversation.md` T42), no ratification round needed —
two independent reasons, either sufficient on its own.** `SpecField` is not in
`contract.md` at all (grep confirms 0 hits); it lives only in
`knowledge-datamodel.md`, which `contract.md` §1.2 explicitly delegates to this
platform to correct. And obligation 4 had already decided the substance: a
bare `{value: 38, unit: "mm"}` on a key like `nominal_length_mm` **is** the
bare `_mm` field obligation 4 names and forbids, and always was — there was no
ambiguity to ratify away, only a stale sketch in a document this platform owns.

**The fix landed one case narrower than proposed here.** `value: Quantity` was
the reading recommended below; Planning caught that it forbids `colour`, which
this same section's own `key` list names, and pointed at the contract's own
precedent one section over — `ParameterTable.rows[].value: Quantity | Token`
(§1.3), discriminable by shape (`amount_milli` vs. `key`), no separate
`value_type` declaration needed at `SpecField` granularity. Shipped as
`value: Quantity | Token` in `knowledge-datamodel.md` §2.2. The two stock-length
values this candidate names below now publish as real `Quantity`s — see
`state-and-gaps.md` G63.

<details><summary>Original entry, for the record</summary>

| | |
|---|---|
| **Trigger** | **D** — an obligation depends on something the contract does not define consistently |
| **Raised** | 2026-08-31, building the first `Part`s (obligation 5's spine) |
| **Blocking?** | **Yes, for obligation 14 specifically.** Two real stated stock-length values are held back as gaps rather than published, solely on this. Does not block obligation 5, which needs no `SpecField` at all. |

`knowledge-datamodel.md` §2.2 (Tier 2, the shapes `contract.md` §1.2
explicitly delegates to): `SpecField { key, agree, value: 38 | null, unit:
"mm" | null }` — a bare, already-collapsed number, with `unit` a SEPARATE
sibling field. Annotated "Unchanged."

`contract.md` §1.1, obligation 4 (BINDING, stable core): *"Every dimension is
a `Quantity`* — integers in thousandths of the named unit, with **every**
verbatim source lexeme alongside... **No bare `_mm` field crosses**."*
`Quantity` is `{amount_milli, unit, value_raw}` — a nested object, not a bare
number plus a sibling unit, and specifically carries `value_raw`, which a bare
number cannot.

**These are not the same shape, and `SpecField` is not itself in `contract.md`'s
own type list** — grepped, not assumed: `contract.md` never defines `SpecField`
directly, only in the delegated `knowledge-datamodel.md` text. A bare
`38, unit: "mm"` is precisely the "bare `_mm` field" pattern obligation 4
names and forbids — no verbatim lexeme travels with it, so a value like `'16
foot lengths'` (this platform's own real, stated evidence for
`BT-RAIL-PR-3RAIL-WHITE`) could not be published under §2.2's shape without
either discarding the lexeme (violating obligation 4) or overloading `value`
with something other than a bare number (contradicting §2.2 as written).

**Why this platform is not resolving it unilaterally.** Guessing which shape
wins — patch §2.2 to nest a `Quantity`, or read obligation 4 as not reaching
`SpecField` — is exactly the kind of BINDING-adjacent decision `AMENDING.md`
exists to gate. Two stated values are ready to publish the day this is
settled (`state-and-gaps.md` G62; `fence_evidence/parts.py`'s module
docstring has the exact evidence). Recommended reading, given the rest of
this contract's own convention: `SpecField.value: Quantity`, matching how
every other dimension crossing this boundary is shaped — but that is a
recommendation, not something shipped without your agreement.

</details>

---

## Not candidates — recorded so they are not re-raised

- **`retain_until` has no specified value.** The contract requires a snapshot
  *declare* one and deliberately does not fix it. That is a product decision for the
  operator, not a defect. Belongs in `planning-asks.md`.
- **Adding a curation level 3** (machine-consensus between agent-only and
  human-checked). Considered 2026-08-25 and **rejected**: renumbering an ordinal
  scale that policy rows already reference would silently weaken every existing
  row requiring level 2, with no diff anywhere to show it. Shipped instead as the
  registry addition `CURATION_MACHINE_CONSENSUS` — see `planning-asks.md` §3.3.
  Registry additions are explicitly not amendments.
- **Transport, framework, auth, pagination.** Explicitly unspecified by design.
  Never a candidate.
