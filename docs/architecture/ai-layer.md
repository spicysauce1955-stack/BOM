# AI layer

Bounded roles (foundation §12): interpreter, knowledge-acquisition assistant, explainer,
critic. Deterministic code owns geometry, rules, arithmetic, cutting, inventory.
Decision: ADR-0009. Research: ai-layer-landscape.md.

## Ports (domain-typed Protocols — no prompt strings in signatures)

```python
class AnnotationInterpreter(Protocol):
    def interpret(self, annotation: Annotation, ctx: ProjectContext) -> InterpretationRecord: ...
class KnowledgeProposer(Protocol):
    def propose(self, corrections: list[Correction], ctx) -> list[KnowledgeVersion]:  # status=proposed
class ExplanationWriter(Protocol):
    def polish(self, subgraph: DecisionSubgraph, tier1: list[str]) -> PolishedExplanation | None: ...
class StrategyCritic(Protocol):
    def critique(self, strategy: Strategy, graph, topology) -> list[CritiqueNote]: ...
```

## Implementations

- **Stub (default)**: deterministic keyword/regex table (~20 demo phrases) producing
  CandidateIntents with verbatim source_text; unknown text → unparsed_spans. Powers the
  offline demo and all unit tests; capped in sophistication by design (it must not become a
  second rule engine).
- **Claude adapter**: anthropic SDK `messages.parse()` with stable Pydantic schemas;
  model configurable (`claude-opus-5` default, sonnet/haiku tiers); 2-attempt semantic retry
  (append validation errors), then `needs_human_interpretation`; stop_reason checked;
  SDK transport retries not duplicated. Selected at composition root: `FENCEAI_AI=claude`
  + constructible client; otherwise stub. Every record stamps interpreter id + model.
- Contract test suite runs against both (invariants, not exact text); live tests behind a
  pytest marker.

## Hard boundaries

- Interpretations are **proposals**; only human-confirmed intents feed generation, and then
  as `assumption`-free events/knowledge with provenance. Unconfirmed intents used anyway
  (never in V1 defaults) would appear as `assumption` decision nodes.
- The proposer emits `KnowledgeVersion(status=proposed)` in the rule DSL — never active
  rules. Narrowest-scope default. Rejections are kept.
- Explanations: Tier-1 templates are authoritative; Tier-2 polish validated by node-citation
  check; any failure falls back to Tier 1.
- The critic returns prose notes attached to elements — advisory warnings only, never
  mutations.
- No AI call sits inside `generate()`, `derive_requirements()`, or `fulfill()`.
