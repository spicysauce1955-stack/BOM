# Decision model

Plane: **Engine** — see [00-overview.md](00-overview.md#three-planes).

The persisted decision graph is the explanation (foundation doc §8; ADR-0006). Prose is
rendered *from* it, never stored as the only record.

## Structure

Per GenerationRun, one document (`decisions/graph.py: DecisionGraph`), built during
`generate()` by a `GraphBuilder` and stored inside the run:

```
DecisionNode { id, ordinal, kind, action (short machine-readable label), payload{},
               scope_refs: [strategy element id | topology object id],
               confidence: deterministic|inferred|uncertain,
               status: proposed|accepted|edited|rejected|pinned|superseded }
DecisionEdge { from_id, to_id,
               type: governed_by | defeated | corroborated | input_from |
                     derived_from | assumption_of,
               knowledge_ref: "OBJ@vN" | None }   # set on governed_by / defeated / corroborated
```

**Knowledge enters as nodes, cited by edges.** A `governed_by`, `defeated` or
`corroborated` edge runs from an `input_fact` node with action `knowledge_version`,
created the first time a ref is cited and carrying `{knowledge_ref, admitted_by?,
origin?}` — what the source was worth under the source policy, and whether the fact
was authored here or published. `governed_by` means this version decided the value;
`defeated` cites the LOSING version; `corroborated` means the version independently
said the same thing and was never beaten — rendering agreement as defeat once showed
five agreeing sources as "4 defeated". `derived_from` and `assumption_of` are
declared and never emitted.

Node kinds, by what is actually emitted:

| Kind | Emitted as (actions, e.g.) |
|---|---|
| `input_fact` | `topology_node`, `run_geometry`, `gate_event`, `gate_span`; `knowledge_version` (above) |
| `rule_firing` | `resolve_max_span` — the one resolution with a firing node of its own |
| `structural` | `place_post`, `create_span`, `layout_spans`, `place_gate`, `resolve_panel`, `derive_continuity`, `credit_contained` |
| `selection` | `select_model`, `select_variant`, `select_product`, `select_gate_kit`; `select_supply` at read time ([below](#supply-decisions-are-added-at-read-time)) |
| `vertical` | `choose_vertical_mode` |
| `quantity` | `resolve_span_quantities`, `resolve_post_embedment`, `resolve_demand_products` |
| `conflict` | `knowledge_conflict`, `sliver_span`, `span_rounded_over_published_limit`, `exact_span_over_max`, the panel-limit codes, … — several carry `governed_by` the limit they report on rather than `defeated`, because the rule was honoured, not beaten |
| `override_applied` | one per applied override, action = its directive kind (`pin_post`, `lock_bay`, …), payload naming the `override_id` |
| `gap` | `missing_default`, `site_condition_missing`, `uncovered_quantity`, `uncovered_param` — confidence `uncertain`: a question nobody answered, and the value the run proceeded on |
| `choice` | `resolve_choice_set` (a person chose), `resolve_choice_set_default` (the default stood) |

`mounting`, `assumption` and `failure` are declared in `NodeKind` and never emitted.
A `GenerationFailure` raises out of `generate()`; `/generate` answers 422 and stores
nothing, so there is no failure node to read.

**Acyclicity by construction**: `GraphBuilder._edge` refuses any edge that does not
run from a lower ordinal to a higher one, and a knowledge node is materialised before
the node that cites it. Ordinal order is therefore causal order.

**Edges are passed, not captured.** Each `builder.add(kind, action, inputs=,
governed_by=, defeated=, corroborated=, assumptions=)` names its evidence explicitly;
nothing records which inputs the code actually read (the Salsa-style dynamic capture
the design once named, Research B, was not built). Node ids are positional
(`d0001`, …) and renumber when the design changes, so an id names a decision within
one run and is not comparable across runs (`core/ids.py`). That is why a
correction's `decision_ref` is refused without its run (422
`decision_ref_needs_run`).

### Supply decisions are added at read time

Which product fills a multi-candidate slot is chosen in fulfillment, which runs on
every read and has no graph builder. `decisions/supply.py: with_supply_decisions`
therefore returns a **copy** of the stored graph with one `selection/select_supply`
node per `SupplyDecision`:

* id `s<hash>`, the first 10 hex characters of a sha256 over (role, slot_key,
  requirement ids) — named by what the decision is about, never by what it chose, so it holds still when the yard
  restocks; it is still not stable across runs, because `DemandLine.id` is
  positional. `decision_id()` is the one name for it, and the grouped BOM uses the
  same (`report/bom_groups.py`);
* ordinals continue from the stored maximum; the node scopes to the elements the
  group's lines peg to and takes `input_from` the `resolve_panel` node that asked for
  the part.

`/explain` and section decisions apply it. The stored document is never touched, and
supply decisions are not persisted on `SupplyRun`. A post's and a cap's products
are chosen during generation and explained by their `place_post` node instead,
which carries `rejected` / `cap_rejected`.

## Contract with the generator

Every structural/selection/quantity output of `generate()` MUST be created through the
builder with its evidence edges. What the tests actually hold
(`tests/scenarios/test_invariants.py`, over every fixture shape):

* every requirement pegs at least one strategy element, and every pegged element has
  at least one decision node of any kind (`test_full_traceability_chain`);
* every edge references existing nodes;
* every `knowledge_ref` resolves to a version the run pinned — in its knowledge
  snapshot or, for a model policy contribution, through its `model_snapshot`
  (`test_knowledge_refs_resolve_to_snapshot`);
* regenerating from the same inputs yields a byte-identical graph (`test_determinism`).

No test asserts that every element sits in a *structural* node's `scope_refs`, or
that every structural node has a `governed_by` or `input_from` edge; and with no
`assumption` node ever emitted, a rule tying them to unconfirmed interpretations
would have nothing to hold.

`governed_by` means **this rule decided this value** — it is not a "related rule" link.
A value copied from a user payload carries `input_from` the fact it was copied from and
NO `governed_by` (e.g. `select_gate_kit` on a gate event that names its kit: the kit is
the user's, while K-GATE-REINF governs only the flanking POST upgrade). Citing a rule for
a value it did not choose makes the rendered explanation state something untrue.

## Questions the graph answers (and their query shapes)

- *Why is this element here?* — `GET /api/runs/{id}/explain/{element_id}` →
  `explain_element`: every node scoping the element, each followed by its ancestors
  of kind `input_fact`, `rule_firing`, `override_applied` or `conflict` (a `gap` or
  `choice` ancestor is not printed), over the graph with supply nodes added.
- *What was decided about this section?* —
  `GET /api/runs/{id}/sections/{section_id}/decisions` → `report/section_decisions.py`:
  each node once, in ordinal order, in the same template sentences. It refuses a
  moved drawing or site (409 `topology_changed`, `site_conditions_changed`); `/explain`
  is per element and refuses neither.
- *Which decisions depend on rule R?* — `GET /api/runs/{id}/impact/{object_id}` →
  `dependents_of_knowledge`: nodes with a `governed_by` edge citing any version of R,
  then a forward walk. `defeated` and `corroborated` edges are not followed.
- *Which were overridden?* — `override_applied` nodes, and `place_post` nodes whose
  status is `pinned`. No route asks this directly.

Not answered by the graph:

- *What changes if this topology feature changes?* — there is no reverse
  `input_from` query. The impact tools that exist regenerate and diff, for a
  knowledge or fence-model change (`learning/impact.py`).
- *Which decisions rest on an AI interpretation?* — no `assumption` node is emitted,
  and a confirmed interpretation reaches generation as an ordinary topology event or
  override. See [`ai-layer.md`](ai-layer.md).

## Explanations

Tier 1, the only tier: a deterministic template per **action**, per language —
`decisions/explain.py: TEMPLATES[lang][action]` — with optional fragments
(`place_post_alt`, `place_post_cap`, …), a `generic` fallback for an action with no
template, and the provenance suffixes `_governed`, `_defeated`, `_corroborated` and
`_pinned`. The `en` and `he` key sets must stay identical. The route takes `lang`
(`en|he`) and `units` (`mm|cm`); a `*_mm` param renders in the reader's unit and a
`*_milli` param at published precision (`_display_milli`), so a 1422.4 mm limit never
prints as 1422. For `place_post`, in English:

> Post at station {station_mm} {u} ({kind}, {mounting} mount, {sku}) on {surface} base.

followed by ` Governed by {refs}.` when the node has `governed_by` edges.

Tier 2 — an LLM rewrite of Tier-1 fragments with a post-validator (ADR-0009) — is
designed, not built; there is no explanation port. See
[`ai-layer.md`](ai-layer.md#designed-not-built).

## Statuses and user interaction

**No route changes a decision's status.** `DecisionNode.status` declares six values;
generation writes `proposed`, and `pinned` for a post a `PinPost` override placed, and
nothing writes the others. A person shapes a fence through overrides (anchored to
topology, ADR-0004) and comments on it through corrections; neither touches a stored
graph. An override is not a graph node: the next generation applies it as an
`override_applied` node carrying the `override_id`, and the decisions it shaped take
`input_from` that node. Corrections feed the learning loop
([`ai-layer.md`](ai-layer.md)); who may act at all is
[`people-and-work.md`](people-and-work.md).

Runs have no superseded status. A run is stored once, `ON CONFLICT DO NOTHING` on its
content-derived id, and never deleted — so every graph ever generated stays readable
for audit.
