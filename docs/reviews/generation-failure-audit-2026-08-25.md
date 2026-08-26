# Every `GenerationFailure` site, audited

```text
Written:  2026-08-25, building item 1 of plan/next-session.md.
Against:  integration contract v1.1 §3.2.4 — "Never fail a run over a gap.
          Warned, named, unfulfilled lines instead."
Scope:    all thirteen sites that raise or construct a GenerationFailure.
Result:   three converted, ten stay. The audit IS the deliverable; the two
          conversions the plan named were not the only candidates, and the
          reasoning for each site that stays is recorded so the next reader
          does not have to re-derive it.
```

## The line the audit draws

§3.2.4 forbids failing a run over a **gap** — something nobody told us. It does not
forbid failing over the two other things this engine refuses on, and conflating them
would be a worse outcome than the defect it fixes:

| | Refuses | Because |
|---|---|---|
| **A gap** | never | absence is a work item for a curator, and a fence can be planned around it and warned |
| **A violated hard constraint** | always | somebody *did* tell us, and the fence they described must not be built (ADR-0005: the tier decides the consequence) |
| **Input that cannot be carried out** | always | a pin naming a model that does not exist has no correct silent interpretation; building something else is the failure the refusal prevents |

The test for a gap is not "did generation stop" but **"is the missing thing something
a person outside this repo would have to author?"** That question separates all
thirteen cleanly.

## The verdicts

| # | Site | What it is | Verdict |
|---|---|---|---|
| 1 | `knowledge/evaluator.py` `resolve()` | two contenders tie, disagree, both authority ≤ 3 | **converted** — raises only when both are `authored`; a published contender makes it a `Conflict` |
| 2 | `strategy/generator.py` `_generate_run`, `max_span_mm` | no rule covers the parameter | **converted** — `Gap(uncovered_condition)`, laid out to `FALLBACK_MAX_SPAN_MM`, every bay warned |
| 3 | `strategy/generator.py` `_resolve_default_post` | knowledge names no `default_component` for `post_ground` | **converted** — the post stands with no sku, which demand already reports as an `unresolved` line; `Gap(missing_value)` |
| 4 | `_no_post_failure` → `post_spec_conflict` | two product lines meet and no post satisfies both | stays |
| 5 | `_no_post_failure` → `post_routing_mismatch` | the panel wants rails where the post is not routed | stays |
| 6 | `_no_post_failure` → `no_item_covers_part_spec` | the catalog stocks nothing meeting the post spec | stays — see the open question below |
| 7 | `_with_parts` → `fence_model_invalid` | a part the model names has no active version | stays — invalid authored data |
| 8 | `_validate_resolved_model` → `fence_model_unknown_sku` | the model names a SKU the catalog does not stock | stays — invalid authored data, already a coded 422 |
| 9 | `_validate_resolved_model` → `fence_model_invalid` | an unbuilt feature, a non-positive advance, an unsuppliable length | stays — each means the panel built is not the panel authored |
| 10 | `_pick_model` → `fence_model_not_found` (M-LEGACY pin) | a version pin the compatibility model does not have | stays — input that cannot be carried out |
| 11 | `_pick_model` → `fence_model_not_found` | a model id that does not exist or has no active version | stays — same |
| 12 | span width > `sm.max_span` | a bay wider than the hard maximum | stays — violated hard constraint |
| 13 | `_check_panel_limits` under a `hard_constraint` winner | clear gap, rail separation, pattern residual | stays — violated hard constraint, and the tier is exactly what decides it |

Sites 4–13 are the ten. Note what they have in common: **not one of them is about
something knowledge failed to say.** Every one is either a fence that must not be
built or an instruction that cannot be followed. That is the audit's real finding —
after the three conversions, the engine has no refusal left that a curator could
close, which is what §3.2.4 asks for.

## The one open question, recorded rather than settled

**Site 6, `no_item_covers_part_spec`, is the taxonomy's `unsatisfiable_requirement`
almost word for word** — *"nothing can fill a slot"* — and converting site 3 made
"a post standing with no product" a representable state, which removes the technical
objection its docstring raises (*"a post is not a line item — without one there is no
fence to be short of"*).

It stays a refusal on a boundary argument rather than a modelling one: the catalog is
**Planning's own artefact**, not the knowledge boundary. A gap is a work item we send
to a curator, and *"buy a different post"* is not curator work — it is a purchasing
decision for the company whose catalog it is. Filing it as a `Gap` would put an item
in a review queue that the queue's readers cannot action, which is the exact property
obligation §1.2.1 says a queue must have.

What would reopen it: a `closes_by` value that names the tenant rather than either
platform. If that is ever added, sites 4–6 are the first three candidates.

## What the conversions cost, honestly

`FALLBACK_MAX_SPAN_MM = 1800` is a number nobody stated, and inventing one is the
move the contract warns against everywhere else. Three things make it the right
trade here, and they should be re-checked if any stops being true:

1. **It is never quiet.** A run that uses it carries a warning naming it, a gap in
   the report, and a graph node governed by nothing. The number is the loud answer,
   not the silent one.
2. **It errs toward standing up.** A fallback that guessed *wider* could plan a fence
   that falls down; a tighter-than-necessary bay is a fence that stands.
3. **The precedent was already set, less honestly.** `DEFAULT_RAILS_PER_SPAN = 2` and
   `DEFAULT_SCREWS_PER_SPAN = 8` had been silent fallbacks for unstated quantities
   since before this audit. The max-span fallback was the first one that said so.

**Point 3 is closed, 2026-08-26, and closed the way the trade above argues for:** the
two counts keep their VALUES and gain the report. `uncovered_rails_per_span` and
`uncovered_screws_per_span` are gaps, warnings and `gap`/`uncovered_quantity` graph
nodes; 2 and 8 are unchanged, because moving either would silently reprice every job
that ever relied on the default — a different and much larger change than the defect,
which was that the engine answered a question nobody had answered.

The expected cost was "golden numbers on runs that are currently green". Measured, it
was **none**: the demo knowledge states both counts, so no green run produces either
gap, and the scenario gate did not move (268 before, 268 after). A before/after diff
over twenty BOMs — five knowledge bases against four fence lengths, comparing purchase
and engineering quantities, overage, unit prices and totals — moved zero cost and zero
quantity. `test_reporting_the_count_moved_no_quantity_and_no_price` keeps that.

---

## What four reviews changed, after this audit was written

The audit above was written before the slice was reviewed. Four reviewers — an
architecture critic, a test reviewer, a correctness reviewer and a contract-compliance
audit — read it against the code. Recorded here because the corrections are more
instructive than the original.

**Two defects escaped the audit entirely, and both were consequences of the
conversions rather than of the sites left alone.**

1. **The third conversion moved a refusal instead of removing one.** A post standing
   with `sku=""` is not the "deleted product" case `resolve_supply` had a branch for,
   so it reached `_resolved`, `ResolvedSupplyLine.sku` refused it (`min_length=1`),
   and the `ValidationError` surfaced as a **raw 400** on `/bom`, `/structure` and
   `/quote` — untranslated, uncoded, and strictly worse than the coded 422 it
   replaced. Generation stopped refusing and the first read after it refused instead.
   Two reviewers found it independently. The test that should have caught it stopped
   one call short of the bug.

2. **The evaluator conversion let the alphabet decide a safety limit.** Two published
   maxima of 1200 mm and 2400 mm tie; the tie-break ends on `object_id`, so the run
   built 2000 mm bays or 1200 mm bays according to what the rows were *named* — and
   the 2000 mm answer exceeded a maximum one of them stated. **A contradiction is not
   a gap.** §3.2.4 says never fail a run over a gap; the contract says at §1.2.1 that
   a publish-time `disputed` is not a resolution-time `Conflict`. Not blocking is
   right; picking the looser number was not. It now resolves to the most restrictive
   contender — at the site that knows which direction is safe, because the evaluator
   cannot: lower is safer for `max_span_mm`, higher for `min_rail_separation_mm` — and
   files a `Gap(disputed, on="value")`, so the only people who can fix two of their
   own rows contradicting each other actually hear about it.

**The fallback did not stay in its lane**, which was the audit's own weakest claim
above. `FALLBACK_MAX_SPAN_MM` was consumed by every check that *judges* against a
maximum, so an uncovered run with a 2400 mm manufactured panel reported, at **error**
severity, that the panels exceeded "the 1800 mm maximum span" — a limit nobody set, on
a plan that could not be built. A manufactured width is authored data and the fallback
is not, so the fallback now yields to it. The mitigation in "What the conversions cost"
above was necessary and was not sufficient.

**The type was emit-only.** `Gap` claimed to be one type in both directions and could
not parse a published one: `SourceRef` had been redefined as `{doc_id, locator}` against
the contract's `{id, belongs_to}` — reintroducing, under the contract's own type name,
the exact defect its BINDING clause exists to close — and `disputed` had lost its
`on: value | conditions` discriminator, the field standing for the 33.3% of the
platform's human-gated facts where the value is certain and the conditions are not.

**Two mutations proved the tests did not bite.** Setting the fallback to 5000 — planning
five-metre bays, the "guessed WIDER, could fall down" failure this document argues 1800
avoids — left the suite fully green, because every assertion about the number compared
the code against itself. Fabricating `governed_by=["K-INVENTED@v1"]` on a gap node also
left it green, because the "nothing governs it" assertion read out-edges, and
`governed_by` edges point *in*. Both now fail. The leave-one-out property test —
retire each knowledge object in turn, demand a plan every time — is the executable form
of this document's central claim, and is the test that would have found all three
original defects without anyone naming them first.

**The census held.** No fourteenth site, and no "stays" verdict was overturned, including
the contestable one at site 6. The `MissingField` paths reachable from `generate()` were
checked separately and are caught at every call site, so a run does not die on missing
knowledge through that route either.
