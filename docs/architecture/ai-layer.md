# AI layer

Bounded roles (foundation §12): interpreter, knowledge-acquisition assistant, explainer,
critic. Deterministic code owns geometry, rules, arithmetic, cutting, inventory.
Decision: ADR-0009. Research: ai-layer-landscape.md.

Three of those four roles are implemented as ports; the explainer is not (below).

## Ports (domain-typed Protocols — no prompt strings in signatures)

Three, and these are the real signatures — copied from `src/fenceai/ai/ports.py`:

```python
class AnnotationInterpreter(Protocol):
    interpreter_id: str
    def interpret(self, annotation: Annotation) -> InterpretationRecord: ...

class KnowledgeProposer(Protocol):
    interpreter_id: str
    def propose(self, corrections: list[Correction]) -> list[KnowledgeVersion]:
        """Returns versions with status='proposed' only — never active."""

class StrategyCritic(Protocol):
    interpreter_id: str
    def critique(self, result: GenerationResult) -> list[CritiqueNote]: ...
```

Each port takes exactly what it needs and no ambient context object: an
interpreter is handed one annotation, a critic one `GenerationResult`. An adapter
that wanted more would be reaching for state the deterministic side owns.

### Designed, not built

**`ExplanationWriter`** — the Tier-2 LLM polish over Tier-1 template prose. It is in
foundation §12's role list and in no code: `grep -rn ExplanationWriter src/ tests/`
returns nothing, and `docs/v1-known-limitations.md` records the tier as
unimplemented. Named here rather than drawn as a fourth port, because a documented
port with no implementation is the same defect as a schema field the resolver
ignores — it reads as working.

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
- Explanations: Tier-1 templates are authoritative and are **the only tier that
  exists**. The design for Tier-2 polish stands (validated by a node-citation check,
  any failure falling back to Tier 1) and is unbuilt — see "Designed, not built".
- The critic returns prose notes attached to elements — advisory warnings only, never
  mutations.
- No AI call sits inside `generate()`, `derive_requirements()`, or `fulfill()`.
