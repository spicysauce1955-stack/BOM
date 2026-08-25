# Knowledge system

Typed, scoped, versioned knowledge with explicit precedence and surfaced conflicts.
Decisions: ADR-0005 (rules as data), ADR-0006 (versioning). Research: knowledge-rules-provenance.md.

## Types and authority

| Type | Authority tier | Behavior |
|---|---|---|
| hard_constraint | 1 (non-overridable unless an approved exception exists) | violation ⇒ generation failure or blocking warning; an authored–authored tie fails, a tie touching a published row conflicts |
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

**A hard tie fails only between rules WE authored.** `KnowledgeVersion.origin`
separates `authored` from `published`, and the tier rule above is read against it:
two authored rules that tie and disagree cannot both be right and someone here can
go and fix that, so it stays a generation failure. A tie involving a row the
Knowledge Platform **published** is neither our bug nor fixable in this repo — it
resolves to a `Conflict`, a warned line and a review task. Integration contract
§3.2.4 (ratified v1.1) forbids failing a run over a gap, and the exposure scales
with adoption: the snapshot expansion puts published rows at authority 1
(structural) or 3 (everything else), so **both** branches sit inside the tier band
that used to raise.

**Absence is never a failure.** A parameter no row covers, or a default nobody
stated, produces a `Gap` (`core/gaps.py`) — a plan is still generated, every line
it affected is warned, and the gap names what would close it. The audit of all
thirteen refusal sites, with the verdict on each, is
`docs/reviews/generation-failure-audit-2026-08-25.md`.

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

### What `site.*` does NOT reach

Knowledge rules only. A **fence model's variant condition**
(`fencemodel/resolve.py`) and an **eligibility predicate** (`fencemodel/match.py`)
evaluate against a panel/product context carrying no `site` namespace, so a
variant conditioned on `site.hvhz` resolves to *not satisfied* and the model
falls through to its default spec, silently. That is a real gap, not a decision
made and defended — an HVHZ panel build-up is exactly what a variant is for.
Recorded rather than half-closed, because whether a MODEL should see the site is
a design question, and inventing the answer while shipping something else is how
the entity retracted in the engine spec's §6 came to exist. The guard above
covers the knowledge path and does not reach these two.

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
