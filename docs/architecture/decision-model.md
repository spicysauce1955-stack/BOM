# Decision model

The persisted decision graph is the explanation (foundation doc §8; ADR-0006). Prose is
rendered *from* it, never stored as the only record.

## Structure

Per GenerationRun, one append-only document:

```
DecisionNode { id, ordinal, kind, action (short machine-readable label), payload{},
               scope_refs: [element_id | run_id | event_id],
               confidence: deterministic|inferred|uncertain,
               status: proposed|accepted|edited|rejected|pinned|superseded }
DecisionEdge { from_id, to_id, type: derived_from | governed_by{object_id, version} |
               defeated{object_id, version} | input_from | assumption_of }
```

Node kinds: `input_fact` (topology/catalog/inventory facts read), `rule_firing`,
`structural` (post/span/gate placement), `selection` (product choice), `vertical`,
`mounting`, `quantity`, `conflict`, `assumption` (unconfirmed interpretation used),
`override_applied`, `failure`.

Acyclicity by construction: edges reference earlier ordinals only. The graph is written once
by the generator via a `GraphBuilder` (dynamic dependency capture: nodes record exactly the
inputs the code actually read — Salsa lesson, Research B).

## Contract with the generator

Every structural/selection/quantity output of `generate()` MUST be created through the
builder with its evidence edges. Tests enforce: every strategy element id appears in
`scope_refs` of ≥1 structural node; every structural node has ≥1 `governed_by` or
`input_from` edge; `assumption` nodes exist iff unconfirmed interpretations were used.

## Questions the graph answers (and their query shapes)

- *Why is this post here?* — nodes with element in scope_refs → walk `governed_by`/`input_from`
  ancestors → template.
- *Which decisions depend on rule R?* — edges `governed_by(R,*)` → forward walk.
- *What changes if this topology feature changes?* — `input_from` reverse walk → affected
  decisions → affected elements/requirements → regenerate-and-diff (impact analysis).
- *Which decisions rest on AI interpretation?* — `assumption` ancestors.
- *Which were overridden?* — `override_applied` nodes / `pinned` status.

## Explanations

Tier 1 (default): deterministic template per node kind, e.g.

> Post P@run1:4000 (masonry mount): base interval 4000–7000 is masonry_wall
> (topology event ev_12) and rule K-MASONRY v3 requires masonry mounting.
> Alternatives considered: none (hard constraint).

Tier 2 (optional, ADR-0009): LLM rewrites Tier-1 fragments + subgraph only; each output
sentence carries source node ids; a post-validator rejects sentences citing unknown nodes;
fallback is Tier 1. Never generated from model reasoning.

## Statuses and user interaction

User accept/edit/reject/pin acts on decisions (via elements). Edits produce Corrections
(learning loop) and/or Overrides (anchored, ADR-0004); the next run's nodes cite
`override_applied` with `input_from` the override. Superseded runs keep their graphs (audit).
