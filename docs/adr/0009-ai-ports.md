# ADR-0009: AI behind capability Protocols; Claude adapter + deterministic stub; graph-grounded explanations

Status: accepted · 2026-08-09

## Decision
- Ports speak domain types: `AnnotationInterpreter`, `KnowledgeProposer`, `ExplanationWriter`,
  `StrategyCritic` (critic separate, prose output). No prompt strings in port signatures.
- `ClaudeInterpreter`: anthropic SDK `client.messages.parse()` with stable Pydantic
  discriminated-union schemas; default model `claude-opus-5` (config: sonnet/haiku tiers);
  2-attempt semantic-retry (re-prompt with validation errors), then degrade to
  needs-human-interpretation; stop_reason checked; provenance stamps interpreter+model id.
- `StubInterpreter`: deterministic keyword/regex table (~20 demo phrases) — the default when
  no API key/config; offline demo and tests are byte-stable. Selection at composition root
  (`FENCEAI_AI=claude|stub`, auto-detect).
- Interpretations carry verbatim `source_text`, enum confidence (high/medium/low),
  `unparsed_spans` surfaced; structured intents are `proposed` until human confirmation.
- Explanations: Tier 1 templated from the decision graph (default, offline); Tier 2 optional
  LLM polish receiving only the serialized subgraph, output sentences citing node ids,
  deterministically post-validated; degrade to Tier 1 on any failure. Never chain-of-thought.

## Rationale
Research D; foundation doc §12 boundary (deterministic core must not depend on free-form
model output) and §15 (original text preserved; deterministic core testable without LLM).
