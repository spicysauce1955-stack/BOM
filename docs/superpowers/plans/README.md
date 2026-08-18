# Implementation plans

Working documents for `superpowers:writing-plans` / `executing-plans`. A plan is
**execution scaffolding**: the step order, the checkpoints, the per-task detail an
agent needs while building. Its audience is whoever is doing the work, and its
useful life ends when the work lands.

## Retention

**A plan is deleted once its work ships.** Five shipped plans (UI v2, persona lab,
structure-and-parts, fence-model phase 1, panel canvas — ~260 KB) were removed on
2026-08-18 for that reason. `git log --diff-filter=D -- docs/superpowers/plans/`
finds them if one is ever wanted.

Nothing durable is lost, because the durable half was never in the plan:

| What | Lives in |
|---|---|
| What was designed, and why | `docs/superpowers/specs/` — kept |
| What the decision cost | `docs/adr/`, `docs/architecture/` |
| What was built, and what building it found | `plan/current-status.md` |
| What the review objected to and how it was answered | `docs/reviews/` |
| What the code must keep doing | `tests/scenarios/` ⇄ `docs/scenarios/golden-scenarios.md` |

A shipped plan that stays here is read as current work. It also drifts silently:
nothing verifies it, so it keeps describing an approach the implementation may have
abandoned halfway through — and the record of *that* belongs in `current-status.md`,
where it is written down deliberately.

Keep a plan while its work is in flight. Delete it in the commit that finishes it.
