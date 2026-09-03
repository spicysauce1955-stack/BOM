# A published part's own numbers, judged before they are believed

**Date:** 2026-09-03 · **Status:** BUILT. §9 records what the build found.
**Contract:** §1.2.1 (the closure rule), §1.4 (source policy), §2.1 (the part-type
spine), obligation 6 · delegated: `knowledge-datamodel.md` §2.2 (`SpecField`),
§2.4 (`Provenance`), §3.1 (`Part`)
**Build-order:** item 7 — *`Provenance` on `SpecField`, the `source_docs` join*

---

## 1 · The problem, in one paragraph

A rail is manufactured in fixed lengths, and which length it is decides whether it
runs through a post or stops at it — which decides how many pieces get cut, which
decides the bill of materials. The Knowledge Platform now publishes that number:
`shared/bt-rail-pr-3rail-white` states a nominal length of **4 876 800
thousandths of a millimetre** (16 ft, from *"16 foot lengths"* on a page), and
`…-3rail-color` states **3 657 600** (12 ft, from *"12 foot rails"*). Both cite
two real documents. Until today this engine reported all of it as
`unconsumed: {part_types: 5, parts: 11}` — the honest word, but an honest word
about a hole. It held two manufactured lengths with citations and could not say
whether either was worth believing.

## 2 · What changes for the person holding the plan

**Today:** the snapshot summary says *"11 parts, unconsumed."* Nothing else.

**After:** it says *"2 published spec values, both judged: a manufacturer
installation instruction, admitted at rank 3 for a component dimension"* — and,
against each one, *"no product in this catalog claims to be that part, so the
value reaches no line."*

The second half is the one that matters. It would have been easy to consume these
by guessing: our demo catalog has rails, the published parts are rails, and a
plausible name match would have wired 4 877 mm into a cut plan. That is exactly
the correlation the Knowledge team's own first draft of these parts made and
withdrew — evidence headed *"Breezewood"*, attached to Chesterfield because
Chesterfield was the only rail in the universe at the time (`conversation.md`
T41 §2). A number that reaches a builder is not the place to find out we were
wrong about which rail it described.

## 3 · What "judged" means here, and why it is the same mechanism as before

`knowledge-datamodel.md` §2.4 settles it in one sentence: *"a Chesterfield rail
length is `derived`, marketing-grade OCR, or PE-sealed depending on which of the
eleven documents it came from — exactly the same admissibility problem as a
parameter row."* So this slice adds no new judgement: it points the §1.4
mechanism item 6 built at the second place a number read off a page arrives.

One thing genuinely had to be decided, because the contract deliberately leaves
it to us. §1.4 is BINDING that **Planning** applies the policy, *"because
admissibility depends on the task a value is being used for, and only the planner
knows the task"* — and a `SpecField` carries no task. `task_for()` is that named
seam, and it answers by the value's SHAPE:

| The field carries | Task | Why |
|---|---|---|
| a `Quantity` | `component_dimension` | it is a measurement of a component; the shipped default table has that row for exactly this |
| a `Token` | `product_description` | a colour is not a measurement, and holding a brochure's word for one to the bar for a dimension refuses a fact that was never a dimension |

A lookup table of field KEYS was the alternative and is worse: it would need an
entry per registry addition on their side, so a new spec key would arrive
unjudgeable rather than judged by what it carries.

## 4 · The join, which is the other half of the item's name

§1.4's third tie-break criterion is the document's `issue_date`, and that lives
only on `SourceDoc`. §3.2.2 forbids calling Discovery during a run. So the
citations have to be resolved against the `source_docs` the payload brought with
it — which is precisely what §1.2.1's closure rule guarantees is possible:

```text
SpecField.provenance.cites[j].belongs_to
        │
        └──► Snapshot.source_docs[content_hash]  →  class · status · issue_date
```

`PublishedSpec.sources` carries the resolved documents in cited order, so a
reviewer reads what backs the value rather than an opaque id.

**The real data lands on the last tie-break step.** Both documents behind these
two values are `manufacturer_installation_instruction`, both `version_status:
unknown`, both undated — so rank, curation level and date all tie, and the winner
is decided by `content_hash`, the terminator amendment 005 added. Without it the
winner was whichever citation the payload happened to list first, and two
implementations of this contract would stamp different `admitted_by`.

## 5 · The five moves

1. **Type them.** `knowledge/parts.py` holds `PartTypeRef`, `PartType`,
   `SpecField`, `Part` — the contract's §2.1 and the delegated §2.2/§3.1, field
   for field. `Snapshot.parts`/`part_types` stop being `list[Any]`.
2. **File each part against the spine.** §2.1 is BINDING that every extension's
   parent chain terminates in the shared spine, and the spine is Planning's
   registry (*"Roles | Spine: Planning. Extensions: Knowledge"*), so `SPINE`
   lives here. A chain that ends nowhere, ends in the reserved `site_material`
   id, or cycles is reported.
3. **Join, then judge.** Per spec field: resolve the citations, then compete them
   through `source_policy.resolve()` — scoped strictly INSIDE the field, the way
   `_judge` scopes inside a row. This answers *"which of this value's citations
   admits it"*, never *"which value wins"*. Two mechanisms selecting between
   facts is the failure the whole knowledge design avoids.
4. **Refuse out loud.** A field the policy declines produces no value and one of
   `source_inadmissible` / `source_below_min_curation` — `parameters.py`'s own
   two codes, reused, because the fact is the same fact and a second pair would
   be two sentences to keep in step for a distinction already drawn.
5. **Say what we still cannot do.** Every admitted value emits
   `published_spec_unapplied` — `unmodellable_entity`, `closes_by: planning`,
   `would_close` naming the work: *a catalog product declaring which published
   Part it is*. Same call as `parameter_paired_unsupported`: the publisher is
   correct, the missing mechanism is ours.

## 6 · Decisions taken

**A spec value never becomes a `KnowledgeVersion`.** A parameter row is a rule
about a fence and belongs in front of the evaluator; a spec field is a fact about
an ITEM. Giving it a version would put two kinds of thing on one precedence
ladder where nothing selects between them — and `Ingested.part_specs` is a
separate list for the same reason `warnings` is.

**A payload contradicting its own schema is authoring text, not a gap.** A
`supplies` field carrying a value (§2.2 says it carries none), a valued
agreement with no value, a part filed under a type nobody published: all close by
an edit at the sender, so they join `Ingested.part_defects` in the convention
`warning_defects` and `gap_defects` already follow. A curator's queue must not
show work only the publisher can do.

**Only an `active` part is consumed.** Judging a `draft` would put a value nobody
published behind a verdict that reads exactly like a published one. `retired` and
`draft` parts are named in `inactive_parts`, counted rather than dropped.

**`contributing_sources` accepts a hash OR a document.** The delegated §3.1
writes `[SourceDoc]`; the real payload sends content hashes. Both parse and only
the join key is kept, because `source_docs` is the authority and a second copy of
a document's fields here would be a second authority over the same facts.
Accepting both rather than the one we happened to receive is the direct lesson of
`conversation.md` T42 §5 — three shapes the contract permits have now been
rejected by a narrower type of ours, each time with the symptom pointing at the
sender.

**`part_types` leaves `unconsumed` too**, and it is not a technicality: it is
what `Part.type` resolves against, so a part filed under an extension nobody
published is a reported defect rather than an unread field. The rule for that
list is unchanged — an entry may only leave it when it has somewhere to go, the
standard `warnings` met when the annexe gave them a home.

## 7 · What this deliberately does not do

- **It does not link a published `Part` to a catalog product.** There is no field
  for it and no naming convention worth trusting; the demo rails are 3 000 mm and
  3 600 mm stock and the published ones are 4 877 mm and 3 658 mm. The seam is
  `published_spec_unapplied`'s `would_close`, and the work is real: a product
  declaring which published part it is, after which `strategy/continuity.py`
  already knows what to do with a manufactured length (obligation 14, item 9).
- **It does not answer §2.2's mechanical test for `gate_kit`.** This snapshot
  publishes two `component_type_unmapped` gaps, `closes_by: planning`, asking
  whether a gate hardware kit is one part or several. That is build-order item
  10's territory (the kit-credit rule) and it is a design question, not a parse.
- **It does not consume `models`, `procedures`, `combinations` or `rules`.**
  Still carried, still counted, still honest.
- **It does not render anything.** `GET /api/knowledge/parts` serves the judged
  values with their documents; no JS reads it yet. The frontend design's own
  argument for its step 1 applies — building against the data is what tells us
  whether it is what a reviewer needs.

## 8 · Files

| File | What |
|---|---|
| `src/fenceai/knowledge/parts.py` | new — the types, `SPINE`, `task_for`, `consume` |
| `src/fenceai/knowledge/source_docs.py` | new — `SourceDoc` moved here so `snapshot` and `parts` can both import it without a cycle |
| `src/fenceai/knowledge/snapshot.py` | `parts`/`part_types` typed; the closure rule reaches into them; `Ingested.part_specs`/`part_defects`/`inactive_parts` |
| `src/fenceai/api/app.py` | counts on the snapshot summary; `GET /api/knowledge/parts` |
| `src/fenceai/web/static/i18n/{en,he}.json` | `warning.published_spec_unapplied` |
| `tests/knowledge/test_parts.py` | new — 22 tests over the unit |
| `tests/knowledge/test_snapshot.py` | the door: closure, `unconsumed`, defects-not-gaps |
| `tests/knowledge/test_real_snapshot.py` | `f4d40fb8…` pinned — the first cut carrying spec values |
| `tests/web/test_locale_bundles.py` | `parts.py` added to the scan; the new code listed |
| `docs/architecture/04-backend.md` | the published-knowledge routes, which had never been in the table |

## 9 · What the build found

### 9.1 · The closure rule could not see into parts

§1.2.1 is BINDING for every `SourceRef` cited **anywhere** in a snapshot. While
`parts` arrived as `list[Any]`, `dangling_refs()` walked warnings, gaps and
parameter rows and nothing else — so a published part could have cited a document
the payload never carried and every closure test would still have passed. The
hole was invisible for an honest reason (nobody had published a part) and it is
the same shape as every other one this boundary has produced: a check that was
complete against the data that existed.

Both levels are inside the rule now — `Part.cites` (the definition's own
evidence) and each `SpecField`'s (the individual value's).

### 9.2 · The check the join makes possible, and it found nothing — this time

Once the documents are resolvable, a field claiming one `source_class` while its
cited document states another is checkable. Without it, a payload can upgrade its
own admissibility by claiming a class its document does not have.

In this snapshot the claims agree — provenance and both documents all say
`manufacturer_installation_instruction`. So the mechanism reports nothing today,
and it is reported rather than refused on purpose: §2.5 records the reason a
mismatch may be legitimate rather than false — *one SHA-256 filed four times
under four manufacturers has four `source_class` values, and `belongs_to` names
one of them*. Resolving those groups is on their list (§8, N-obs-1). Ours is to
make the disagreement visible instead of silently picking a side.

### 9.3 · A pinned test had to change, and that is the design working

`test_the_first_snapshot_carrying_parts_loads_and_verifies` asserted
`unconsumed == {"part_types": 5, "parts": 11}` under a docstring that said *"we
do not consume them yet — that is item 7."* Item 7 exists, so the assertion is
now `{}` — changed deliberately, with the old value and the reason kept in the
docstring. `b2f2fe45` stays pinned beside `f4d40fb8` because it is the only cut
carrying the two list-valued `because` params
(`specfield_wire_shape_unresolved`), which is a real defect of ours that a newer
snapshot no longer exercises.

### 9.4 · The scanner blind spot, a fourth time

`published_spec_unapplied` shipped, ran green through the whole suite, and had no
locale entry in either bundle — because `tests/web/test_locale_bundles.py` scans
a hand-maintained list of files and `knowledge/parts.py` was not on it. Exactly
the hole `snapshot.py`, `parameters.py`, `continuity.py`, the routes and the read
models were each added to close. The list is the mechanism, and a new emitting
file is a new entry on it; there is no version of this that is automatic while
the list is written by hand.
