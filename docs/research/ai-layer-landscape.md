# Research D — LLM integration, HITL learning, explanations, editor & stack

*Researcher D report, 2026-08-09. Synthesized into ADR-0009/0010 and docs/architecture/ai-layer.md.*

## Claude API structured output (authoritative per claude-api skill, Aug 2026)

- Models: `claude-opus-5` ($5/$25 per MTok) default for interpretation/critique;
  `claude-sonnet-5` ($3/$15) volume tier; `claude-haiku-4-5` ($1/$5) cheap polish. Exact IDs,
  no date suffixes. API drift notes: adaptive thinking replaces budget_tokens; sampling params
  removed on Opus 5; assistant prefill gone — do not design around prefill.
- Mechanisms, in order of preference: (1) **`client.messages.parse()` with a Pydantic model**
  — validated instance out; SDK strips unsupported schema constraints and validates them
  client-side; (2) `output_config: {format: {type: "json_schema", ...}}`; (3) forced tool
  choice with `strict: true`.
- Schema constraints: no recursion, no server-side numeric ranges/string lengths (Pydantic
  validates), `additionalProperties: false` everywhere. Keep ONE stable discriminated-union
  schema (not per-project) to hit the 24h schema compile cache + prompt cache.
- Retry loop: syntactic failure ~eliminated; semantic failure (Pydantic validators) →
  re-prompt once with error text → second failure degrades to "needs human interpretation".
  Cap 2 attempts, log both. Check `stop_reason` (max_tokens → truncated; refusal possible).
  SDK auto-retries transport errors — don't duplicate.

### Interpreter output shape
```python
class CandidateConstraint(BaseModel):
    constraint_type: Literal[...]        # discriminated union per subtype
    source_text: str                     # verbatim span, never paraphrased
    confidence: Literal["high","medium","low"]  # enums beat uncalibrated floats
    ambiguity_note: str | None
class InterpretationResult(BaseModel):
    candidates: list[CandidateConstraint]
    unparsed_spans: list[str]            # surfaced, never dropped
```

### Provider port with deterministic fake
- Ports speak **domain types, not API types**: `AnnotationInterpreter`, `KnowledgeProposer`,
  `ExplanationWriter`, `StrategyCritic` Protocols. If the port takes a prompt string you've
  built an LLM client, not a domain port.
- `ClaudeInterpreter` (anthropic SDK + parse()); constructed on config flag / working client,
  not merely env-var presence.
- `StubInterpreter`: deterministic rule-table fake (~20 demo phrases → CandidateConstraint;
  unknown → unparsed_spans). Genuinely useful offline demo; byte-stable tests.
- Provenance stamps interpreter id + model on every response; stub output never mistaken for
  model output. Test layers: unit (stub only), contract suite against both impls (invariants,
  not exact text), live tests behind a marker.

## HITL learning (Label Studio / Prodigy / GitHub-suggestion patterns)

Pipeline: **Correction capture** (immutable record: original output, corrected value, full
context snapshot, author, time — automatic and lossless) → **batch candidate proposal** (LLM
proposes CandidateRule in the deterministic rule DSL: proposed rule, generalization scope,
supporting correction links, rationale; schema-validated) → **review queue state machine**
(approve / reject-with-reason / edit-then-approve / **scope-restrict**) → versioned rule store
with provenance (`derived_from: correction_ids`, `approved_by`).

- Killer review feature: **impact preview** — "this rule would have changed 3 of your last 12
  quotes — view them" before approval.
- Anti-patterns: silent auto-learning (destroys trust, feedback loops, monetary consequences);
  overgeneralization by default (propose narrowest scope consistent with evidence; widening is
  a human act); deleting rejected candidates (keep — suppresses re-proposal); conflating
  "AI was wrong" with "customer wanted something unusual" (only the former yields global
  candidates).

## Explanations from structured provenance

- **Tier 1 (default): templated** per node type from the decision graph. Zero hallucination,
  testable, offline. Build first; may suffice for V1.
- **Tier 2 (optional): LLM polish** — model receives only the serialized subgraph + templated
  fragments; contract: every claim must map to a provided node; output as sentences carrying
  `source_node_ids`, deterministically post-checked. Degrade to Tier 1 on failure/no key.
- Never CoT-derived: not returned by current models, not faithful to the deterministic
  engine, not reproducible. Graph is ground truth; LLM is a renderer.

## Landscape

- **Fence software** (JobNimbus, ArcSite, FenceCloud, Visual Fence Pro): market is CRM/sales-
  centric; ArcSite's draw-on-site → auto takeoff is the closest UX analog and proves the
  draw-to-takeoff loop. None have explainable rules, correction learning, or annotation
  interpretation — that's the differentiation. Don't compete on CRM.
- **CPQ** (Tacton, Configit): prove declarative constraints + deterministic solving + guided
  UI, and that "why is this invalid" explanations are valued and hard. Heavyweight; nothing to
  reuse directly.
- **Grasshopper concept**: dataflow provenance graph = our decision-graph idea; no CAD tooling
  needed.

### Canvas/editor libraries
| Option | License | Fit |
|---|---|---|
| **Plain SVG + vanilla JS** | — | **Recommended.** Click-place vertices, polylines, hit-test, overlays = few hundred lines on native SVG events; DOM hit-testing; CSS; serializable; zero deps. Dozens–hundreds of objects ≪ SVG limits (thousands). |
| Konva | MIT | Mature fallback if overlays get very dense. |
| Paper.js | MIT | Wrong shape (Bezier/vector-math). Skip. |
| React Flow | MIT | Node-graph, not geometric polylines. Skip. |
| tldraw SDK | **Proprietary** (license key, watermark, enforcement) | **Avoid.** |

### Stack
**FastAPI + Pydantic + static vanilla-JS/SVG page.** All complexity budget to the domain;
server-authoritative render data (frontend can't drift from engine); no build toolchain; same
Pydantic models validate API and LLM output. Revisit (small React+Vite) only if UI state gets
genuinely complex — review queue is the likely trigger; server-rendered lists + light JS carry V1.

## Open trade-offs
(a) confidence enum vs calibrated bands — enum; (b) batch vs inline rule proposal — batch, avoid
anchoring reviewers mid-job; (c) critic port separate from interpreter port with prose output —
yes, separate; (d) stub sophistication — cap at ~20 demo phrases (it must not become a second
rule engine).
