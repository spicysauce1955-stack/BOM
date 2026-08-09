# Task 02 — Catalog
Goal: Product + consumption semantics union + SubstitutionRule + demo catalog fixture.
Rationale: products are behavior, not SKU rows. Dependencies: 00.
Outputs: fenceai/catalog + tests + demo catalog (golden-scenarios shared catalog).
Acceptance: all 6 semantics representable; kit explosion data; integer price/ratio fields.
Non-goals: 2D sheet cutting semantics (deferred). Validation: uv run pytest tests/catalog -q
