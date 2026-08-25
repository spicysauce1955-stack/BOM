# ADR-0005: Rules as typed condition/action ASTs with an owned evaluator; defeasible precedence

Status: accepted · 2026-08-09

## Decision
- No rule-engine dependency (Drools/OPA/Cedar/ZEN rejected — Research B). Knowledge objects
  are data records; conditions are closed ASTs (Pydantic discriminated unions:
  FieldRef|Lit|Cmp|And|Or|Not|In|Between|FnCall over a whitelisted function registry);
  actions are typed (SetParam|RequireComponent|ForbidComponent|AddNote|FlagForReview...).
  Never eval() of authored strings.
- A small tree-walking evaluator we own evaluates rules and natively emits trace events
  (fired / not-applicable / defeated_by / conflict) that become decision-graph edges.
- Precedence: authority tier (hard constraint > approved exception/override > company rule >
  preference > heuristic > learned candidate-never-auto) → scope specificity (structural
  count of bound scope dimensions; explicit `overrides: [id]` links allowed) → recency
  (same-tier tiebreak). Strict structural wins resolve silently but record `defeated_by`;
  ties produce surfaced conflict objects; a violated hard constraint is a generation failure.
  A hard TIE is a generation failure only between two `authored` rules — one involving a
  `published` row is a surfaced conflict, since contract §3.2.4 forbids failing a run over a
  gap. Absence of a rule is never a failure: it is a `Gap` (`core/gaps.py`).
- Knowledge objects carry examples/counterexamples executed as tests on every edit and in CI.

## Rationale
Every off-the-shelf engine hides the firing/conflict trace we must persist, can't carry
authority/scope/provenance metadata, or is unmaintained. DMN hit-policy and defeasible-logic
semantics are borrowed conceptually.
