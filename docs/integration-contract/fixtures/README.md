# Fixtures — what we expect to receive, not what anyone published

**Nothing in this directory is real published data.** The Knowledge Platform is
still designing; it has published nothing, and these files are this repo's
statement of what it expects a snapshot to look like, written from
`../contract.md` §1.2 and §1.3.

They exist for three reasons, and the third is the point:

1. They exercise the `ParameterTable` loader against a whole document rather than
   unit fixtures assembled in a test.
2. They make the loader reachable, so the codes it emits stop being strings
   nothing renders.
3. **They are evidence for the other team while they are still designing.** The
   frontend design makes this argument for its own step 1: *"building against it
   is what tells the Knowledge team whether their endpoint returns what a
   reviewer actually needs — before they implement it."* A design phase is when
   that is worth most, and it is the opposite of inventing behaviour at the
   boundary: it produces a question to ask, not a commitment to defend.

**They are NOT the contract, and they bind nobody.** The contract is frozen and
hash-verified; these are a reading of it. Where a fixture and the contract
disagree, the contract is right and the fixture is a bug.

`tenant`, `snapshot_id` and the source ids are deliberately obvious
(`FIXTURE-*`, `not-a-real-tenant`) so that a file from here can never be mistaken
for something that arrived over the wire. That is how a hypothesis quietly
becomes a fact nobody checked.

## The Knowledge team's first review, and what it moved

`knowledge-asks.md` v0.2 (fence-rag, 2026-08-27) ran this fixture against their
closed vocabularies and publish gate. Eleven findings landed here, all fixed:
`source_class` values now come from the real eight-member vocabulary
(`manufacturer_installation_instruction`, `sealed_approval`, …); `task` uses the
confirmed `TaskCode` spellings (`structural_parameter`, `installation_step`);
`Provenance.version_status` on the lapsing row now agrees with the `SourceDoc` it
cites (both `superseded`); `scope.kind` names a `FenceModel` (`model`), not the
`product_line` neither side's vocabulary actually has; `gaps[].because{code,
params}` replaces flat fields, and `gaps[].subject` carries `id` + `tenant`
alongside `kind`; `warnings[].cites` is a list; the `slope_method` row's value is
a `Token{key, value_raw}` carrying the document's own sentence, not a bare
string; `warnings[].lang_basis` is present; a `severity_lexeme` with no lexeme at
all is `null`, not `""`; and `gaps[0].cites` now resolves to a `source_docs`
entry that exists (closure — §1.2.1 BINDING), rather than a dangling hash.

Two things changed that are not mechanical fixes:

- **`curation_level` dropped from 2 to 1 on the structural rows.** The Knowledge
  team's corpus has zero rows at level 2 and will for the foreseeable future — a
  fixture that is mostly level 2 exercises a path that will never actually run.
- **`(exposure_category=B, hvhz=true)` is no longer in `uncovered` at all.** It
  was previously in neither a row nor `uncovered` — silently missing from a
  domain the table itself declares as six points, which §1.3's BINDING clause
  forbids. **Settled 2026-08-27** (`conversation.md` T1→T4, `CANDIDATES.md` C4,
  struck): no new `Gap` kind was needed — `kind: uncovered_condition` with
  `domain_basis: measured` already means "checked, and this table really does
  not cover it," which is exactly "refused," not "may not know." What was
  missing was only the WHY, and the agreed fix is a platform code,
  `parameter_condition_excluded`, carrying the excluded point the same way
  `uncovered_parameter_point` already carries `point` — now implemented
  (`web/static/i18n/{en,he}.json`, `tests/web/test_locale_bundles.py`'s
  `PUBLISHED_GAP_CODES`) and used by `gaps[]`'s third entry
  (`FIXTURE-gap-excluded-1`), published directly rather than left for this
  loader to synthesise from a bare domain point — only the publisher knows
  *why* a point is excluded.

One gap remains deliberately unfixed: the fixture still models `max_span_mm` as
a `(exposure, hvhz)` → single-value lookup. The Knowledge team's review (and
their own design's adversarial audit) found the real table is pairs of
`(footing depth, max span)` per exposure — a shape `ParameterTable.value_type`
cannot express today (see `knowledge-asks.md` §1.1(a), §2.4). Changing the
fixture to match would mean inventing an answer to an open question rather than
recording one, so it stays wrong in the way the real table is wrong, flagged
here rather than quietly patched.

## `disputed{on: …}` serialises as a sibling key, on both sides

`contract.md` writes `disputed{ on: value | conditions }` and never says how
that nests. This fixture (and `core/gaps.py`) put `on` beside `kind` rather than
inside it — and the Knowledge team's review found their own model does the
same, independently. Confirmed as the shared convention 2026-08-27
(`conversation.md` T1→T2); nothing to change, worth writing down once instead
of both sides re-deriving it from a fixture forever.

## What the `warnings` block is for

It is the one member of this file that exists to be *placed* rather than parsed.
Nine warnings, and each is there for a reason a single well-formed example could
not carry:

- **Three identical freeze-thaw footnotes.** The corpus has 83 instances of one
  such sentence, printed at the foot of fourteen pages. Three is enough to prove
  `report/annexe.py` collapses them into one entry carrying `instances`, and one
  instance would have proved nothing.
- **`CAUTION` beside `WARNING`.** They are terms of art with different legal
  weight, and a fixture whose severities were all one word would look identical
  under an engine that normalised them.
- **A publisher's own `code` + `params`** (`not_pool_rated`), so the fixture
  shows the overlay being carried without being promoted: it gets no locale entry
  on this side and `text_raw` is still what renders.
- **One warning with no `cites` at all.** Legal here, rendered as unattributed,
  and the count of these is the most useful thing this side can send back:
  §1.1 makes `SourceRef.id` opaque and unbuildable, so nobody without the
  Discovery surface can mint one.
- **One attached to a `procedure`** this engine does not model, which comes back
  from placement as `unplaceable` rather than as somebody else's job. A fixture
  containing only what we can already draw would test nothing about what
  arrives.
- **One attached to a `model`.** `attaches_to` has seven kinds; the earlier
  fixture only ever exercised six. The Knowledge team's own corpus is heavily
  skewed toward `document`/`step`/`warranty` — `product`, `model`, `procedure`
  and `maintenance` are all zero there today — which is exactly why a fixture
  has to carry the rare ones deliberately rather than wait for a real document
  to.
