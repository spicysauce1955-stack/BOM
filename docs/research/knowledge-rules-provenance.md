# Research B — Rules-as-data, precedence, provenance, decision graphs

*Researcher B report, 2026-08-09. Synthesized into ADR-0005/0006 and docs/architecture/knowledge-system.md.*

## Engine landscape verdicts

- **Drools/Rete** (Apache-2.0, JVM): poor fit — JVM sidecar, programmer-facing authoring,
  solves incremental re-matching at scales we don't have, and its conflict resolution
  (salience/activation groups) is *implicit* — opposite of our explicit-surfacing requirement.
- **DMN 1.5**: the most relevant *conceptual* import; adopt semantics, not runtime (Python DMN
  tooling weak; production runtimes JVM). Steal: **hit policies** (UNIQUE/ANY/FIRST/PRIORITY/
  COLLECT — conflict semantics as a declared property of a rule set), **DRD** with *knowledge
  sources* (authority/provenance in the dependency diagram), **FEEL**'s non-programmer
  expression design.
- **OPA/Rego, Cedar** (Apache-2.0): answer "is this allowed", not "what follows from these
  rules" — wrong problem shape. Steal Cedar's static policy analysis idea (detect shadowed/
  conflicting rules at authoring time).
- **venmo/business-rules** (MIT): right shape (JSON conditions/actions for non-programmer UIs)
  but abandoned since ~2016 — design reference only. **durable_rules**: dormant, skip.
- **GoRules ZEN** (MIT engine, Rust): the one modern option, but imposes its JDM schema (can't
  carry authority/provenance/examples) and resolves conflicts silently inside the engine.
  Known-about, not adopted.

**Verdict: rules as data records with typed condition ASTs, evaluated by a ~300-line
interpreter we own.** Every off-the-shelf engine either hides the firing/conflict trace we
must persist, imposes a schema that can't carry our metadata, or is unmaintained. Trace
emission is trivial in a hand-rolled tree-walker, painful to retrofit. Performance is a
non-issue at dozens–hundreds of rules per generation event.

## Rule representation

- **Never eval() expert/LLM strings** (simpleeval/asteval have documented escape history).
  Use a **closed AST**: JSON expression tree with enumerated node types (Pydantic
  discriminated unions): `FieldRef | Lit | Cmp | And | Or | Not | In | Between | FnCall`,
  where `FnCall` whitelists registered domain functions. Actions equally typed
  (`SetParam | RequireComponent | ForbidComponent | AddNote | FlagForReview`), never code.
- JSONLogic is the prior art but untyped/fragmented; our own discriminated-union AST gets
  validation + versioning free via Pydantic. CEL (`cel-python`, Apache-2.0) is a maintained
  text-syntax option for power users later.
- Store **examples/counterexamples on the knowledge object and run them in CI and on every
  edit** — the rule-regression suite no engine gives us.
- Version at knowledge-object level and stamp evaluations with the exact version set used —
  DMN's own versioning story is thin; the repository layer must do it.

## Precedence & conflict handling (defeasible logic, kept informal)

Three orderings:
1. **Lex superior** (authority): HARD CONSTRAINT > approved project OVERRIDE/exception >
   COMPANY RULE > PREFERENCE > HEURISTIC > LEARNED CANDIDATE (never auto-applied).
2. **Lex specialis** (scope specificity within a tier): project > segment/customer > global.
   Compute structurally from the scope selector (count of bound dimensions), not from
   condition complexity.
3. **Lex posterior** (recency): same-authority-same-scope tiebreak only; prefer flagging.

Resolution policy:
- Resolve silently **only** when precedence is strict and structural — and record losers as
  `defeated_by` edges ("silent" = no interruption, never unrecorded).
- Surface a **conflict object** when rules tie (same tier, incomparable scopes, contradictory
  outputs). Static detection at authoring time (pairwise scope-overlap + interval/set
  intersection on the closed AST — no SAT solver) plus dynamic detection at evaluation.
- A violated HARD CONSTRAINT with nothing defeating it is a **generation failure**, not a
  conflict — separate path, blocks output.

## Provenance & versioning

- **W3C PROV: borrow vocabulary, skip RDF.** Entity/Activity/Agent → knowledge-object-version
  / generation-run / (expert | AI-interpreter | system); `wasAttributedTo` → verbatim expert
  text + structuring agent (model+prompt version); `wasDerivedFrom`/Revision → version chains
  and candidate-promotion lineage.
- **No event sourcing.** Immutable version records + append-only audit log:
  `knowledge_object` (stable id, current_version ptr) + `knowledge_object_version` (immutable:
  content, AST, scope, authority, derived_from, author, status draft/active/retired). Edits
  insert versions.
- **Generation runs** record the exact `(object_id, version_id)` snapshot set (content-hashed
  for cheap comparison); every decision node references the version-ids it consumed.
- **Bitemporal: 1.5 axes max.** Transaction-time free via immutable versions; optional
  `effective_from/to` only if future-dating is needed; no retroactive-correction semantics —
  corrections are new versions + explicit re-generation of affected projects.

## Decision graph & impact analysis

- Salsa/build-system lesson: we need **dependency tracking for invalidation, not incremental
  recomputation**. Capture dynamically: during generation, log every knowledge-version, input,
  and upstream decision each node *actually read*. Impact analysis = reverse-dependency walk →
  affected decisions/BOM/projects → **re-generate and diff** (full re-run is milliseconds).
- Storage: DAG as edge list — `decision_node` (run_id, type, payload, ordinal) +
  `decision_edge` (from, to, type: derived_from | governed_by(version) | defeated(version) |
  input_from). Append-only, write-once per run; acyclic by construction (edges only to earlier
  ordinals). Recursive CTEs suffice; **no graph database**. Denormalizing a run's graph into
  one immutable JSON document for serving is fine.
- The persisted graph — not LLM text — *is* the explanation. LLM proposals enter as nodes with
  agent provenance; downstream still justified by rule/fact edges.

## Hybrid text + structured; embeddings YAGNI

- Always store verbatim expert text on the version record next to the structured
  interpretation + confirmation flag. Non-negotiable; it is ground truth and future eval corpus.
- **Embeddings: not for V1's core loop.** Rule selection must be exact/structural
  (deterministic, explainable). Plausible later uses: authoring-time duplicate detection,
  correction routing — at V1 scale substring/trigram search covers both. Adding pgvector later
  is a migration, not a redesign. Revisit at ~500+ objects.

## License notes
Everything relevant is permissive (Apache-2.0/MIT); real risks are maintenance (abandoned
libs) and schema lock-in (ZEN JDM), not licensing.

## Open trade-offs
(a) hand-rolled interpreter (~1–2 wk, owned forever) vs ZEN speed with opaque conflicts —
we choose hand-rolled; (b) depth of static conflict detection; (c) scope specificity as total
order vs declared `overrides: [rule_id]` exceptions (lean: allow explicit links);
(d) per-rule-group hit policies vs one global precedence algorithm (global simpler to explain).
