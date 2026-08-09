# Implementation roadmap

Vertical slices; the app must run after every slice. Order follows the mission's suggested
progression, merged where dependencies make one slice natural.

| # | Slice | Contents | Scenarios unlocked |
|---|---|---|---|
| 0 | Spike | minimal spine: topology → rule eval → strategy → decisions → requirements → BOM on S01+S07+S08 fixtures; critic + test review | S01 (partial) |
| 1 | Core + topology | units, ids, node/run/event model, stationing, ground profile, corner classification, anchors | — |
| 2 | Catalog | products, consumption semantics, substitution rules, demo catalog | — |
| 3 | Knowledge | AST, evaluator, precedence, conflicts, versions/snapshots, demo KB, example-tests | S13 (core) |
| 4 | Strategy + decisions | generator pipeline (fixed posts, span layout, vertical, mounting, selection), decision graph builder, warnings, Tier-1 explanations | S01–S06, S13 |
| 5 | Demand + fulfillment | requirements w/ pegging, cut planner, packages, coverage, kits, inventory/remnants, BOM | S07–S10 |
| 6 | Overrides | anchored overrides, pin/suppress/force, orphan detection, regeneration | S11 |
| 7 | Annotations + AI | annotation records, interpreter ports, stub, confirmation flow, claude adapter (optional live) | S14 |
| 8 | Learning | corrections, proposer, candidate review workflow | S12 |
| 9 | Store + API | SQLite repos, FastAPI routes, GenerationRun persistence, demo seeding | all via API |
| 10 | UI | SVG canvas editor, strategy overlay, inspector/explanations, knowledge/BOM/review tabs | e2e |
| 11 | Hardening | invariant suite, determinism tests, critic + test-reviewer passes, docs (`v1-*`), runbook | release gate |

Milestone reviews (mission §17) after slices 0, 4, 5, 9, 11: tests → verify → code review →
architecture critic → scenario validation → fix → document → checkpoint commit.
