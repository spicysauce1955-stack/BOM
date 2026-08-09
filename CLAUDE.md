# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

This repository contains **no code yet**. Its only content is `fence_ai_architecture_foundation_v0.1.docx` — the product and architecture foundation document (v0.1, 9 Aug 2026) for **Fence AI SaaS**: a visual construction-topology tool with explainable strategy generation, BOM optimization, and expert-in-the-loop learning. There are no build, lint, or test commands. All future work should be grounded in that document; extract its text with e.g. `pandoc` or Python's `zipfile` + `word/document.xml` (it is a normal OOXML docx).

The document is explicitly a foundation, not a frozen spec. The intended next artifact is a "Domain Model & Reasoning Design v0.1" built from real fence cases — not implementation tickets.

## The system being designed

Core pipeline (section 2 of the doc):

1. **Construction topology** — user-authored visual description of physical reality (runs, elevation, base conditions such as soil/concrete/wall, obstacles, intent, spatially-scoped annotations). Source of truth; stays stable while strategies come and go.
2. **Strategy reasoning engine** — combines the topology with the product model, inventory, and a **knowledge substrate** (facts, hard rules, soft preferences, heuristics, text knowledge, overrides, examples) to generate an **editable construction strategy** (posts, spans, mounting, product selections, warnings).
3. **Decision graph** — every generated element links back to the facts/rules/annotations that caused it. Persisted structured data, never reconstructed prose; the doc deliberately says "decision trace/graph", not chain-of-thought.
4. **Expert review loop** — user corrections become either project-specific overrides or, after expert review, versioned reusable knowledge candidates. Corrections are never silently promoted to global rules.
5. **Fulfillment/BOM** — construction strategy produces engineering demand first; a separate fulfillment stage maps demand to inventory, remnants, cutting plans (with kerf), package rounding, substitutions, and a purchase BOM.

Candidate service boundaries (section 14): topology, product catalog, knowledge, strategy engine, decision graph/audit, inventory/fulfillment, AI orchestration, project/collaboration.

## Non-negotiable architectural properties (section 15 — enforce these in any design or code)

- No company rule lives only inside an opaque prompt; knowledge is explicit, scoped, versioned objects with authority levels.
- Every BOM item traces to structural demand; every construction decision is explainable from persisted inputs and rules.
- Original human text is preserved alongside any AI-generated structured interpretation.
- User overrides are explicit first-class state, not prompt text.
- Deterministic where possible: geometry, unit conversion, package arithmetic, rule evaluation, inventory accounting, and cut feasibility are exact computations testable without the LLM. The LLM is bounded to interpreting text, reasoning at fuzzy boundaries, proposing knowledge candidates, explaining, and critiquing.
- Hard constraints, soft preferences, optimization objectives, and human overrides are distinct categories — never conflate them.
- One topology supports multiple strategy versions; inventory/purchasing is separated from physical construction requirements.
- The system represents unknowns and ambiguity instead of fabricating certainty.
- Knowledge, products, strategies, and interpretations are versioned with provenance; changes recompute incrementally (changed rule → affected constraints → decisions → structural elements → demand → BOM) and support impact analysis before destructive edits.

## Key domain distinctions

- Fence **run** (topology) ≠ generated fence **section** (strategy) ≠ installation/base **segment** — a 3 m run may be fulfilled by unequal spans, and a base transition may occur inside a span.
- Products carry **consumption semantics**, not just SKUs: indivisible discrete, divisible linear (kerf, reusable remnants), sheet/area, packaged (engineering unit ≠ purchase unit), volume/coverage, assemblies/kits, substitutables, leftover stock.
- Knowledge precedence (provisional, must be modeled explicitly, not hard-coded): safety/hard product constraints > approved project exceptions > company rules > project requirements/annotations > company preferences > heuristics > AI suggestions.

## Open questions

Section 16 lists 10 unresolved design questions (minimum topology primitives, deterministic vs. expert decisions, ranking objectives, uncertainty representation, correction-to-rule authorization, inventory granularity, audit persistence, etc.). Resolve these against real installations before committing to schemas or algorithms.
