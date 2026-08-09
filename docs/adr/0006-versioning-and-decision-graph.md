# ADR-0006: Immutable knowledge versions, run snapshot sets, append-only decision graph

Status: accepted · 2026-08-09

## Decision
- `KnowledgeObject` (stable id, current version pointer) + immutable `KnowledgeVersion` rows
  (content, AST, scope, authority, status draft/active/retired, derived_from, author,
  verbatim source text). Edits insert versions; nothing mutates. PROV vocabulary
  (attributed-to, derived-from) as field names; no RDF, no event sourcing, no bitemporal
  beyond optional effective dates (not in V1).
- Every generation run records its (object_id, version_id) snapshot set (content-hashed) and
  each decision node references the version-ids it actually read (dynamic capture).
- Decision graph per run: append-only nodes (type, payload, ordinal) + edges
  (derived_from | governed_by(version) | defeated(version) | input_from), acyclic by
  construction (edges point to earlier ordinals). Stored as one immutable document per run.
  No graph database.

## Rationale
Research B. Answers "generated under which knowledge", "why is this post here", "what depends
on this rule" from persisted structure — the foundation doc's core explainability requirement.
