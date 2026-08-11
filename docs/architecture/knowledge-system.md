# Knowledge system

Typed, scoped, versioned knowledge with explicit precedence and surfaced conflicts.
Decisions: ADR-0005 (rules as data), ADR-0006 (versioning). Research: knowledge-rules-provenance.md.

## Types and authority

| Type | Authority tier | Behavior |
|---|---|---|
| hard_constraint | 1 (non-overridable unless an approved exception exists) | violation ⇒ generation failure or blocking warning |
| override (project) | 2 | generator must preserve; approved exceptions live here |
| company_rule | 3 | normally treated as hard within company scope; may allow authorized exceptions |
| fact | — (not a rule; input data) | exact properties; contribute parameters |
| preference | 4 | affects ranking/choice, never validity |
| heuristic | 5 | weak preference; advisory |
| candidate | 6 — never evaluated while `proposed` | requires human approval to become any other type |

Authority is an explicit field (default derived from type) — the foundation doc requires
modeling authority rather than hard-coding one list.

## Condition AST

Discriminated-union Pydantic models; closed node set:
`FieldRef(path) | Lit(value) | Cmp(op,l,r) | And | Or | Not | In | Between | FnCall(name,args)`.
`FnCall` resolves against a code-registered whitelist (`slope_pct`, `span_width`, `base_surface`,
`borders_gate`, `distance_to(kind)` …). No eval of strings, ever. Actions are typed:

```
SetParam{param, value}            e.g. max_span_mm=1800   (facts/constraints)
RequireMounting{surface, mounting}
RequirePostReinforcement{context} e.g. gate-adjacent
PreferEqualSpans{weight} | PreferMinSpanWidth{min_mm, weight} | PreferVertical{mode, weight}
ForbidComponent{sku} | RequireComponent{sku, context}
AddNote{text} | FlagForReview{reason}
```

The evaluator is a small owned tree-walker: `evaluate(rules, ctx) -> [RuleFiring]`, where each
firing records object_id+version, matched condition bindings, produced actions, and losers as
`defeated_by`. It is pure and emits the trace the decision graph persists.

## Scope and precedence

`scope` is a dict of bound dimensions (project_id, base surface, context tag, …).
Applicability = scope matches ctx AND condition true. Precedence when actions collide:

1. authority tier (lower number wins);
2. scope specificity = count of bound dimensions (structural, not condition complexity);
   explicit `overrides: [object_id]` links beat specificity;
3. newer version — same tier+scope only.

Strict structural wins resolve silently **with `defeated_by` recorded**. Ties (same tier,
incomparable scope, conflicting outputs) emit a `Conflict` node — surfaced in warnings and
the decision graph, generation continues with the flagged pick only if categories permit
(preferences) and fails if hard constraints conflict.

A hard constraint violated by the final strategy (no authorized exception) is a
**generation failure**, distinct from conflicts.

### Which dimensions are bound during generation

A dimension is only a key/value pair in the evaluation context — there is no enum of
allowed dimensions, and none of them is specific to fences or to a catalog.
`strategy/generator.bind_scope()` binds, from facts the run actually has:

| dimension | bound where | source |
|---|---|---|
| `project_id` | every resolution in the run | `generate(..., project_id=)`; the impact preview binds `ImpactCase.project_id` |
| `surface` | post-level slots (mounting, default component, demand roles) | `base_surface_at()` under the post |
| `context` | post-level slots resolved in a structural context | e.g. `"gate"` for gate-post reinforcement |

An absent or empty fact leaves its dimension **unbound**, so a rule scoped to it cannot
match (`evaluator._scope_matches` compares `scope_ctx.get(k) == v`). Adding a dimension is
therefore a matter of putting the fact in the context — no evaluator change. Dimensions the
knowledge UI hints at but the topology model cannot yet supply (product series, soil type)
need a **model** field first; they are not expressible today at any layer.

## Versioning and provenance (ADR-0006)

Immutable `KnowledgeVersion` rows; edits insert. Fields use PROV vocabulary: `attributed_to`
(author/agent), `derived_from` (previous version | correction ids | interpretation id),
`source_text` verbatim when originating from human words. Generation runs stamp the exact
snapshot set + hash. Examples/counterexamples stored on the version and executed as tests
(`tests/knowledge/test_examples.py`) — editing a rule that breaks its own examples fails CI.

## Conflict detection

- Authoring-time (static): pairwise check over same-tier rules with overlapping scopes and
  interval/set-intersectable conditions; result shown in knowledge UI, non-blocking.
- Evaluation-time (dynamic): actual collisions become Conflict decisions (above).

## Learning loop

```
Correction (immutable capture) ─► KnowledgeProposer (AI port, batch)
        ─► KnowledgeVersion{status: proposed, derived_from: corrections}
        ─► review: approve | edit-then-approve | scope-restrict | reject(reason)
        ─► active version (or rejected — kept, suppresses re-proposal)
```
Proposals default to the **narrowest** scope consistent with evidence. Nothing `proposed` is
ever evaluated by the generator. Every approval records who/when. (Research D anti-patterns.)
