# Knowledge system

Plane: **Engine** — see [00-overview.md](00-overview.md#three-planes).

Typed, scoped, versioned knowledge with explicit precedence and surfaced conflicts.
Decisions: ADR-0005 (rules as data), ADR-0006 (versioning). Research: knowledge-rules-provenance.md.

Three sources feed **one** evaluator, and none has a private channel into the
generator:

* **authored** knowledge — rows in `knowledge_versions`, written through
  `POST /api/knowledge` or seeded by `demo_knowledge()`;
* **published** knowledge — the Knowledge Platform's parameter tables, re-derived
  from the active snapshot on every read ([below](#published-knowledge--the-snapshot));
* a fence model's **`layout_policy`**, joined per segment and never stored.

## Types and authority

| Type | Default authority | Where it comes from today | Behavior |
|---|---|---|---|
| hard_constraint | 1 | authored | hard band (below). The two checks that read the TYPE rather than the authority single it out: a panel limit whose winner is a `hard_constraint` fails the run (any other type only warns), and a missing site dimension a `hard_constraint` asked about is reported as an `error` |
| override | 2 | nothing | declared and never created. Project overrides are a different type altogether — `PinPost`, `SuppressPost`, `ForcePostSku`, `ForceMounting`, `ForceVertical`, `LockBay` (`strategy/overrides.py`), patches anchored to topology (ADR-0004), not knowledge |
| company_rule | 3 | authored | hard band: an authored–authored disagreeing tie fails exactly as it does for `hard_constraint`. There is no exception mechanism; a `company_rule` panel limit warns rather than fails |
| fact | 3 | **every published row**; product facts in the demo base (rails and screws per span, embedment, the default post) | hard band too — once a snapshot is loaded, facts are most of what the evaluator sees |
| preference | 4 | authored | below the hard band: a disagreeing tie is a surfaced `Conflict`, never a failure |
| heuristic | 5 | authored; an approved candidate | weak preference |
| candidate | 99 | the proposer | never evaluated — see [The learning loop](#the-learning-loop) |

A model's `layout_policy` contribution carries its own type and authority, per
contribution ([below](#a-models-layout-policy-is-knowledge-too)).

Authority is an explicit field (`KnowledgeVersion.authority`, defaulting from
`DEFAULT_AUTHORITY` by type) — the foundation doc requires modeling authority rather
than hard-coding one list. `POST /api/knowledge` does not accept it, so an authored
rule always takes its type's default; only code (the demo base, a model's
`layout_policy`) sets one.

**Type and action are independent.** Nothing pairs a type with the actions it may
carry: a `preference` holding a `SetParam` resolves in `resolve_param` at authority
4 like any other. The type decides authority and the two type-keyed checks above;
the action decides which resolver reads it.

## Condition AST

Discriminated-union Pydantic models on `op`; closed node set (`knowledge/ast.py`):
`FieldRef(path) | Lit(value) | Cmp(cmp, left, right) | And(items) | Or(items) |
Not(item) | In(item, options) | Between(item, low, high) | FnCall(name, args)`.
`FnCall` resolves against a code-registered whitelist (`ast.FUNCTIONS`). The only
function registered today is `covers` (`fencemodel/match.py`), registered for
eligibility predicates; the functions the original design named (`slope_pct`,
`span_width`, `base_surface`, `borders_gate`, `distance_to`) were never built. An
unregistered name raises `MissingField`, so a rule calling one is silently *not
applicable* — the same treatment as an unanswered field. No eval of strings, ever.

Actions are typed (`knowledge/model.py: Action`):

```
SetParam{param, value, value_milli?}     e.g. max_span_mm=1800; value_milli = published thousandths
SetToken{param, value}                   a word from a closed set (published token tables)
RequireMounting{surface, mounting: ground|masonry, sku?}
RequirePostReinforcement{context: "gate", sku?}
PreferEqualSpans{weight} | PreferMinSpanWidth{min_mm, weight} | PreferSpanWidth{width_mm, weight}
PreferVertical{mode: level|stepped|raked, weight}
DefaultComponent{role, sku}              product selection is knowledge, never a code literal
AddNote{text} | FlagForReview{reason}
```

What the generator actually reads: `SetParam` through `resolve_param`;
`RequireMounting`, `RequirePostReinforcement` and `DefaultComponent` through
`resolve_actions`, each narrowed to its slot; the four preferences through
`preference_firings`. Three are carried and decide nothing:

* **`SetToken`** — produced by published token tables, but `resolve_token` has no
  caller, so a published token table changes no fence;
* **`AddNote`** and **`FlagForReview`** — no resolver asks for either. The one
  producer of `AddNote` is the stub proposer, so an approved stub candidate decides
  nothing.

`weight` on the preference actions is declared and read by nothing.

## Scope and precedence

`scope` is a dict of bound dimensions (`project_id`, `series`, `surface`,
`context`; [which are bound](#which-dimensions-are-bound-during-generation)).
Applicability = scope matches ctx (every scoped key equals the context's) AND the
condition is true or absent.

The evaluator is a small owned tree-walker (`knowledge/evaluator.py`), pure:

| Function | Returns | Used for |
|---|---|---|
| `applicable_firings(kb, ctx)` | every applicable `Firing`, sorted by authority, specificity desc, version desc, object id | the base of the four below |
| `resolve_param(kb, ctx, param)` | a `Resolution` over the `SetParam`s for `param` | every numeric parameter — span limits, counts, depths |
| `resolve_token(kb, ctx, param)` | a `Resolution` over the `SetToken`s for `param` | nothing yet |
| `resolve_actions(kb, ctx, kind, match)` | a `Resolution` over one action kind, narrowed by `match` so rules for other slots never compete | mounting, gate reinforcement, default components |
| `preference_firings(kb, ctx, kinds)` | every applicable firing of those kinds, unresolved | span-layout and vertical preferences; the caller resolves per slot |

`Resolution{winner, firings, conflicts}`, and a `Firing` is `{version, actions,
defeated_by, corroborated_by}`. A firing records no condition bindings — what a rule
read is recovered from its condition (`ast.field_paths`), not traced. The decision
graph is built from these results by the generator.

Precedence when two firings target one slot is `_beats(a, b)`, in this order:

1. **authority tier** — lower number wins;
2. **an explicit `overrides_objects` link** — `a` beats `b` when `b.object_id` is in
   `a.overrides_objects`, whatever their specificity. No shipped rule sets one and
   the API cannot, so today only tests exercise it;
3. **specificity** — `len(scope)` plus the number of distinct context field paths
   the condition tests ([below](#a-conditioned-rule-outranks-an-unconditioned-one));
4. **newer version, within the same `object_id` only.** In practice it decides
   nothing: `POST /api/knowledge` retires the previous active version as it inserts
   the next, and every published row is version 1.

Strict structural wins resolve silently **with `defeated_by` recorded**. When
neither beats the other, the pair either **agrees** — the slot's stated value is
equal, compared per pair against the current winner, in thousandths
(`SetParam.effective_milli()`) for a parameter and as words for a token — and the
second is `corroborated_by` the first, which is neither a defeat nor a conflict; or
it **disagrees**, and:

* both versions `authored` and both at authority ≤ 3 (`HARD_AUTHORITY_MAX`) →
  `GenerationFailure`;
* otherwise → a `Conflict` (`hard=True` when both are ≤ 3), the flagged pick stands,
  and the loser is `defeated_by` it.

One site overrides the flagged pick: on a `hard` tie over `max_span_mm` the generator
lays out to the most restrictive contender, because the tie-break that names a winner
ends at `object_id` and the alphabet must not decide a safety limit. Which direction
is safe is not general (lower for a span, higher for a rail separation), so that
choice lives at the site that knows its parameter, not in the evaluator. **Known
defect:** the `resolve_max_span` node still cites the evaluator's winner as
`governed_by`, while the bays are laid out to another row's number.

**The hard band is authority ≤ 3**, so it holds `hard_constraint`, the never-created
`override`, `company_rule` and `fact`. Slots resolved through `resolve_actions` have
no comparable value, so nothing there corroborates and every tie counts as
disagreeing — two authored hard-band rules stating the same `require_mounting` for
one surface fail the run.

A reconciliation pass then re-asks each agreement against the settled winner: an
`overrides_objects` link can unseat a winner after peers were already measured
against it, and an agreement left pointing at the deposed winner would assert a
consensus that does not exist.

A hard limit the final strategy breaks is a **generation failure**, distinct from a
conflict. Two things admit a bay over the maximum, and neither is knowledge: a
person's `LockBay` override (warned `span_placed_over_maximum`, with a `defeated`
edge citing the limit) and the sub-millimetre residue of a published limit that
falls between whole millimetres
([`material-optimization.md`](material-optimization.md)).

**A hard tie fails only between rules WE authored.** `KnowledgeVersion.origin`
separates `authored` from `published`, and the tier rule above is read against it:
two authored rules that tie and disagree cannot both be right and someone here can
go and fix that, so it stays a generation failure. A tie involving a row the
Knowledge Platform **published** is neither our bug nor fixable in this repo — it
resolves to a `Conflict`, a warned line and a review task. Integration contract
§3.2.4 (ratified v1.1) forbids failing a run over a gap, and the exposure scales
with adoption: the snapshot expansion makes every published row a `fact` at
authority 3, so **every** published row sits inside the band that used to raise.

**Absence is never a failure.** A parameter no row covers, or a default nobody
stated, produces a `Gap` (`core/gaps.py`) — a plan is still generated, every line
it affected is warned, and the gap names what would close it. The audit of the
refusal sites, with the verdict on each, is
`docs/reviews/generation-failure-audit-2026-08-25.md`.

### Where a conflict goes

Every resolution site puts its `res.conflicts` into one `ConflictSink` threaded
through the run, and `generate()` drains it once (`_surface_conflicts`),
deduplicated per (slot, contenders): the same slot is resolved per segment, per run
and per post, and one disagreement is one finding. Each becomes:

* a `conflict` decision node, action `knowledge_conflict`, payload `{slot, contenders}`;
* a `knowledge_conflict` warning — `error` when `hard`, otherwise `warning`;
* when `hard` — a tie inside the band that survived only because a contender was
  published — a `Gap(kind="disputed", on="value", closes_by="knowledge")` on
  `Strategy.gaps`. The rows agree on when they apply and disagree on the number, and
  only the publisher can fix that.

### The `site.*` namespace

Whole-site facts — exposure category, HVHZ, frost depth, jurisdiction, code
edition — reach rules through the **evaluation context**, not `scope`, and are
bound in every context a run builds. `FieldRef.path` is a dotted lookup into a
plain dict, so this is additive: no AST change and no evaluator change.

An **unset** dimension is omitted from the namespace rather than sent as `None`,
which makes a rule conditioned on it *not applicable* rather than false — the
evaluator's existing `MissingField` behaviour, used as the hook rather than as an
error path. The run then warns `site_condition_missing`, naming every dimension
this snapshot's rules asked about and the project did not answer, because the
failure mode here is silence: the rule does not fire, the fence is built to
whatever unconditioned rule was left, and nothing says the deciding fact was
never entered.

Anything that varies **along** a run is not a site condition — it is an interval
payload on the topology, the pattern `ElevationSamplePayload` and
`PostTiltPayload` already establish. Soil class is the likely first case.

**A rule is not the only thing that asks.** A fence model's `Variant.condition`
and a slot's `Eligibility.predicate` are AST evaluations outside the knowledge
evaluator — product structure, not defeasible rules — and they read the same
`site` namespace, bound into `PanelContext.condition_ctx()`, `match.panel_facts`
and `match.post_panel_facts`. That was a hole rather than a decision: `site.*`
was bound into every knowledge context and into no fence-model one, so a variant
conditioned on `site.hvhz` came back `MissingField`, read as *not applicable*,
and the bay was built to the **default spec** with nothing said. Of the three
available behaviours that is the worst — worse than refusing the condition at
authoring, because the model looks authored and the fence is quietly something
else. Site conditions exist precisely so that a fence can be conditioned on the
site, so the answer is to bind it and let the existing silence-breaker speak.

These consequences follow, and each is load-bearing:

* **The post reads the same site as its bay.** A post is resolved at its own
  station, where the bay's *width* does not exist — which is why a
  width-conditioned variant is refused beside a post matched on
  `panel.rail_positions_mm`. A whole-site fact does not vary between the two bays
  a post stands between, so there **is** a right answer to give it, and
  `_PostFacts.at` gives the same one the bay gets. A site-conditioned variant is
  therefore admissible there, and the two agree by construction.
* **A condition that can never be true is an authoring error, and there are
  three ways to write one.** `site.hvzh` names a dimension nothing supplies;
  `site.hvhz.enabled` reaches inside a scalar; `site.exposure_category == "Z"`
  names a value a closed domain cannot hold. All three are dead on arrival and
  all three fail the way that hides — not applicable, so the variant falls
  through to the default spec and the slot to the company default, with the
  model still looking authored. `validate_model` refuses all three, in the same
  class as a slot naming an option axis the model does not declare. The
  vocabulary and the domains are read off `SiteConditions` itself
  (`project/site.py`, a leaf module holding nothing else) rather than listed
  twice — a second list goes stale in the direction that never fires.

* **An UNBOUND namespace is not an unanswered dimension.** `choose_variant_by`
  raises (`resolve._assert_site_bound`) when a variant reads `site.*` and the
  caller bound no `site` key at all, which is the check `_assert_namespaces_bound`
  already makes on the knowledge evaluator, in the same words.
  `SiteConditions.facts()` returns `{}` and never absence, so the two separate
  cleanly. Without it this defect is re-openable at every future call site and
  re-opens silently; `match.post_panel_facts` takes `site` as a REQUIRED keyword
  for the same reason — a caller with no site passes `{}` and says so.

`site_condition_missing` covers both askers, and deliberately as ONE warning: the
estimator's work item is a list of fields to go and fill, not one item per thing
that wanted each. A dimension a hard constraint wanted keeps that severity — a
hard constraint that could not be evaluated is not the same event as a variant
that did not fire, and a model's want never dilutes it. (The severity reads the
TYPE: a dimension only published rows asked about is a `warning`, because every
published row is a `fact`.)

The node and the params carry `asked_by` (`rule` | `model` | `both`), because one
sentence for two events is not the same thing as one work item for two askers: a
rule that never fired and a bay built to the default spec have the same repair
and different diagnoses, and a reader cannot recover which from a list of
dimensions. The rendered sentence used to end *"rules needing them did not
apply"*, which was simply false for a model-only want — and false in both locale
bundles, where the en/he parity check cannot see it.

### A conditioned rule outranks an unconditioned one

`specificity()` counts bound scope dimensions **plus the context field paths a
rule's condition tests**. Conditions used to count for nothing, which made the
most natural authoring act in the system a build error: *"we already say the
maximum is 1500; in Exposure C say 1200"* produces two rules of one type at one
authority, one conditioned and one not. Neither beat the other, and inside the
hard band a disagreeing tie is a `GenerationFailure` — so adding an ordinary
conditioned rule bricked every project until somebody reverse-engineered the
authority ladder and hand-tuned `authority=`. A rule that applies *sometimes* is
more specific than one that always applies: scope narrows by dimension, a
condition narrows by value.

### A context that cannot answer is a bug, not a "no"

`MissingField` means *the user did not tell us*, and "not applicable" is the
right answer to that. It cannot, on its own, distinguish that from *the caller
never bound the namespace* — and those need opposite treatments. Since
`SiteConditions.facts()` returns `{}` and never absence, `"site" in ctx`
separates them, and `evaluator._assert_namespaces_bound` raises on the second.
Without it, a resolution path that never received `site` evaluates every
site-conditioned rule as not-applicable and produces a plausible fence built to
rules that never fired — which is how the impact preview came to report that a
rule relaying the whole fence would cost nothing.

### Which dimensions are bound during generation

A dimension is only a key/value pair in the evaluation context — there is no enum of
allowed dimensions, and none of them is specific to fences or to a catalog.
`strategy/generator.bind_scope()` binds, from facts the run actually has:

| dimension | bound where | source |
|---|---|---|
| `project_id` | every resolution in the run | `generate(..., project_id=)`; the impact preview binds `ImpactCase.project_id` |
| `series` | everything resolved under one fence model: the segment view (span limits, `exact_span_mm`, rail and screw counts) and the panel-limit checks; it is also the scope of that model's own `layout_policy` versions and of every scoped published table | `model.id` (`_segment_view`, `_check_panel_safety`) |
| `surface` | post-level slots: mounting, default post | `base_surface_at()` under the post |
| `context` | post-level slots resolved in a structural context | `"gate"` for gate-post reinforcement |

The demand-role defaults (`rail`, `screw`, `concrete`, `cap`) resolve with an empty
surface, which `bind_scope` drops, so they match project scope only.

An absent or empty fact leaves its dimension **unbound**, so a rule scoped to it cannot
match (`evaluator._scope_matches` compares `scope_ctx.get(k) == v`). Adding a dimension is
therefore a matter of putting the fact in the context — no evaluator change. A
dimension nothing in the project or the topology supplies needs a **model** field
first.

Beside `scope`, a context carries the namespaces a condition reads: `site`
everywhere; `run` (`length_mm`, `slope_permille`) where the resolution belongs to a
run; `post` (`surface`, `context`) in post-level ones. No knowledge context binds
`bay`, `panel` or `param`.

## Versioning and provenance (ADR-0006)

Authored `KnowledgeVersion`s are immutable rows; an edit inserts the next version
and retires the previous active one in one transaction
(`Store.replace_active_version`). Status is `draft | active | retired | proposed |
rejected`, and only `active` reaches the evaluator. Published versions are never
rows: they are re-derived from the active snapshot on every read
([below](#re-ingested-on-every-read)).

Fields use PROV vocabulary: `attributed_to` (the caller for an API write, the
reviewer for an approval, `knowledge_platform` for a published row, `fence_model`
for a layout policy), `derived_from` (the previous version for an API write, the
candidate for an approval, correction ids and `run#decision` refs for a proposal,
the model ref for a layout policy — the field also allows an interpretation id, and
nothing writes one), `source_text` verbatim when originating from human words.

Generation runs stamp the exact snapshot set (`knowledge_snapshot`: the sorted
`(object_id, version)` of every active version), its hash (`snapshot_hash`:
`sha256` of that list's JSON, first 16 hex characters), and the publisher's own
`snapshot_id`. The hash is ours and answers "which knowledge objects", authored ones
included; only `snapshot_id` can be handed back to the publisher (§3.2 obligation
1). A model's `layout_policy` versions are not in the set — the run's
`model_snapshot` pins them.

Examples/counterexamples stored on a version are executed as tests
(`tests/knowledge/test_examples.py`) — **for the versions in `demo_knowledge()`
only.** An API-authored version cannot carry examples (`KnowledgeCreate` has no such
field), so a rule written through `POST /api/knowledge` is checked by nothing.

## Conflict detection

- **Authoring-time (static): not built.** No pairwise check runs over authored
  rules, and the knowledge UI shows none. The one static overlap check is
  `parameters._overlap_gaps`, which tests a *published* table's own rows under
  `hit_policy = unique` at ingest and reports an overlap as a
  `disputed{on: conditions}` gap.
- **Evaluation-time (dynamic):** actual collisions become `knowledge_conflict`
  nodes, warnings and, for a hard tie, `disputed` gaps
  ([above](#where-a-conflict-goes)).

## Published knowledge — the snapshot

The Knowledge Platform (fence-rag) publishes a `Snapshot` document under the frozen
boundary contract (§1.2). One is active per installation; its parameter tables
become knowledge versions beside the authored ones, through the same evaluator.

### Loading one

`POST /api/knowledge/snapshot` takes the document as its JSON body — explicitly,
never automatically, for the reason generation sits behind a button: a knowledge
base that swapped itself under a project would change numbers with no action anyone
took. `knowledge/snapshot.py: load()` refuses at the door rather than at generate
(§3.2 obligation 3), each refusal a 400 with a code:

| Code | When |
|---|---|
| `contract_major_unsupported` | the declared `contract_version` major is not 1 |
| `contract_minor_predates_typed_date` | the minor is below 2 — the payload predates §1.1's typed `Date` and needs a re-cut |
| `snapshot_id_mismatch` | the declared id is 64 hex characters and is not the sha256 over the fifteen `CANONICAL_MEMBERS` — the document is not the one its id names |
| `snapshot_malformed` | the payload does not parse as a `Snapshot` at all (the first field errors ride in `errors`) |

A payload declaring no `contract_version` skips the version gate, and an id that is
not hash-shaped (a fixture's `FIXTURE-…`) is not checked. One malformed gap does not
cost the snapshot: gaps are validated one at a time and failures come back as
`gap_defects`, authoring text for the sender. The response counts versions,
admitted verdicts, gaps, defects, part specs and the unconsumed members.

The loader consumes `parameters`, `gaps`, `warnings`, `source_docs`, `part_types`
and `parts`. `models`, `procedures`, `combinations` and `rules` are accepted,
counted as `unconsumed` and not parsed — a private shape for them would be a shape
nobody agreed to.

### Where it lives

`Store.save_snapshot` writes the snapshot to `knowledge_snapshots(snapshot_id PK,
loaded_at, doc)`, upserting on the id; points the one-row `active_snapshot(only_row,
snapshot_id)` table at it (a `CHECK (only_row = 1)` keeps it one row); and audits
`save_snapshot` — with the actor recorded as `"user"`, not the caller. `doc` is the
typed `Snapshot` re-serialised
(`model_dump_json()`), not the bytes that arrived: a field our types do not model
does not survive, whatever the schema comment in `store/db.py` says about keeping
"the DOCUMENT the other team sent". Earlier snapshots stay in the table and appear
only in `history`; nothing reads an inactive one back. `GET /api/knowledge/snapshot`
reports the active one's counts and that history; `loaded: false` is an ordinary
state, not an error.

### Re-ingested on every read

**The published half is never stored as knowledge.** `Store.knowledge_base()`
returns the authored rows plus `ingest(active_snapshot)` — its versions, `admitted`,
`declined` and `snapshot_id` — on every call, so `/generate`, `GET /api/knowledge`
and the impact preview each re-expand it. A source verdict is a function of
(snapshot, policy, task), and one frozen at load would go stale with nothing to say
it changed; one code path also means a fresh load and a reload cannot disagree. A
stored snapshot that no longer parses is skipped and authored knowledge is returned
alone — one bad document must not lock anyone out of their own rules.

Three consequences of the live path, each a fact about the code rather than a
design:

* **Only parameters reach `generate()`.** `KnowledgeBase` carries versions,
  verdicts, declined values and the id. The snapshot's published `gaps`, its
  `DocumentWarning`s and its judged `part_specs` stop at `ingest`: the snapshot
  route counts them and the inspection route shows the specs, and no run sees them.
* **No run date is pinned.** `ingest` is called without `as_of`, so the
  lapsed-authority and not-yet-in-force gaps `expand()` can compute are never
  computed on the live path.
* **The policy is always `SHIPPED_DEFAULT`.** No route reads or edits a source
  policy, though `knowledge_base()`'s docstring calls it "an operator's editable
  table".

### How a table becomes knowledge

`parameters.expand()` turns each `ParameterTable` row into an ordinary
`KnowledgeVersion` through `KnowledgeVersion.from_published` — the one constructor
that sets `origin = "published"` and refuses to be told otherwise:

* `type = "fact"` with no explicit authority (so 3), `version = 1`,
  `attributed_to = "knowledge_platform"`; the `object_id` is parameter, scope and
  row index (`max_span_mm@model/M-VINYL#0`, `footing_schedule#0`).
* The table's scope becomes the `series` dimension (entity kinds `fence_model`,
  `model`, `product_line`). Any other kind is unmappable and the **whole table is
  refused** with a gap — a rule scoped to something we cannot read must not become a
  rule scoped to nothing. So is a table whose `hit_policy` is not `unique`, the only
  one supported.
* Row conditions become an AST over the namespace each key's declared scope names
  (`site | param | run | post | bay | panel`). Generation binds only `site`, `run`
  and `post` into knowledge contexts ([above](#which-dimensions-are-bound-during-generation)),
  so a row conditioned on `bay`, `panel` or `param` is not applicable.
* A quantity lands as `SetParam`, and only in `mm`: a row in any other unit, or one
  that contradicts the table's own `value_type`, becomes a gap instead.
  `SetParam.value_milli` carries the published thousandths beside the rounded
  `value`. A token table lands as `SetToken` — inert, since nothing calls
  `resolve_token`.
* A `paired(...)` table lands its default point — the shortest span — as several
  `SetParam`s on **one** version, so the evaluator can never take the depth from one
  row and the span from another.

### Source policy (contract §1.4)

`knowledge/source_policy.py` is Planning's: the `TaskCode` and `SourceClass`
vocabularies, the shipped default table, and the admission test. Each row is judged
for its table's task against its own citations, and nothing else — choosing BETWEEN
rows stays the evaluator's job. Three outcomes:

* **admitted** — the verdict is recorded on the run, not on the row:
  `KnowledgeBase.admitted["OBJ@vN"]`, copied onto the graph's
  `input_fact/knowledge_version` node as `admitted_by`, beside `origin`;
* **rejected** — the row is not expanded at all and becomes a gap, so the
  generator's "nothing covered this" path takes over. A rejected `mm` value still
  lands in `KnowledgeBase.declined`, and where `max_span_mm` would fall back, the
  smallest declined value caps it (basis `declined_bound`): a refused source that
  said 858 mm is not silence, and laying out wider than the document we refused
  said was safe would be the wrong fallback;
* **not judged** — a task or source class outside our registry is not a rejection.
  The row is used with no verdict and a gap says we could not judge it, which is why
  the graph carries `origin`: published-and-unjudged must not read like authored.

### Gaps

`core/gaps.py: Gap` is one type for the holes the platform published and the holes
expansion discovered — a `kind`, a subject, `because{code, params}`, `would_close`,
and `closes_by` (`knowledge`: a curator adds a row; `planning`: a schema change
here). `Ingested` keeps them in one list and counts `discovered` and `deduped` (a
discovered hole the publisher already declared) separately. Contract §3.2
obligation 6 — report gaps back through `POST /gaps` — has no implementation; a gap
reaches the snapshot route's counts and nothing upstream.

### A model's layout policy is knowledge too

A fence model's `layout_policy` joins the base per segment
(`generator._policy_knowledge`, `_segment_view`, which builds a per-model VIEW of the
base and never mutates it). Each contribution becomes a version with its **own**
`knowledge_type` and `authority`, scoped `{"series": model.id}`, ref
`M-SLAT#max_span_mm@v1`, `attributed_to = "fence_model"` — never stored; the run's
`model_snapshot` is what makes it reproducible. The model gets no private channel
into the generator: what it asks of the layout resolves by the same tiers as a
company rule, and loses out loud when it loses.

### Evidence a person can open

`POST /api/source-refs:batch` resolves `SourceRef` ids to page crops and quoted text —
against `knowledge/discovery_stub.py`, a vendored fixture of seven records, because
fence-rag's Discovery API is design-only. An unknown id comes back in `not_found`
rather than failing the batch.

Published **parts** are judged against the same policy and never evaluated — see
[`published-part-inspection.md`](published-part-inspection.md).

## The learning loop

Corrections, the proposer, candidate review and the impact preview belong to the AI
& learning plane: [`ai-layer.md`](ai-layer.md#the-learning-loop). What this plane
guarantees is that a candidate is **never evaluated**, by two independent guards —
`KnowledgeBase.active()` passes only `status == "active"`, and
`applicable_firings` skips `type == "candidate"` even if one were active. Both
guards read fields the proposer set: `propose-knowledge` stores what the proposer
returns without checking either, so a proposer that wrote `status="active"` on a
non-candidate type would pass both. The stub never does, and no route lets a client
choose those fields. Approval writes a new
`active` version, and from then on it is ordinary knowledge.
