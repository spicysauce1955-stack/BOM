# Open work

Handoff, updated 2026-08-17. Everything below is unstarted unless it says
otherwise. State it follows from: `plan/current-status.md` (newest entry first)
and `docs/superpowers/specs/2026-08-16-part-specs-and-fence-system-design.md`,
whose §11 carries the wave plan with each wave's findings folded back in.

`main` is green: **1152 pytest · 175 scenario tests · 170/170 smoke · compatibility gate
byte-identical** (plus `vinyl.json`, a new fixture, and the one deliberate proved
regeneration recorded in the spec's §9).

---

## ~~1. Finish W3 — the routed vinyl case~~ — DONE, 2026-08-17

All three pieces landed, plus the preview gap the last of them made closable:
`288a1d7` (panel facts reach post matching; the authoring refusal deleted in the
same commit), `edeb0d0` (M-VINYL and golden scenario S16), `0c3472c` (boundary
posts intersect; the three §8 failure codes), `e033f01` (the panel preview
measures its own model's post). See `plan/current-status.md` for what each
decided and what building them found.

## 2. Assembly and installation instructions per panel (roadmap Admin 3)

*"Each fence panel has assembly rules and instructions (also support installation
rules and instructions)."* The only roadmap item with **no foundation at all** —
nothing on `FenceModel` carries prose, an ordering, or a step. Worth a
brainstorm before code: an instruction that is only text is a doc, while an
instruction that names slots and an order is data the assembly film could already
drive (`js/animate.js` computes a build order today from roles alone).

## 3. Section-scoped decisions, and commenting on one (roadmap step 5)

*"focus on specific sections of the fence and get only the decisions related to
the selected session. change, comment or start a conversation about it!"*

`/api/runs/{id}/explain/{element}` answers per ELEMENT. Scoping to a section and
returning only its decisions does not exist; nor does any comment surface.
Annotations, `Correction` and the AI ports are the machinery to build it on — and
the boundary holds: a comment becomes an interpretation, an interpretation
becomes a PROPOSAL, and only a human confirms. AI never decides.

## 4. BOM grouped by section / panel / decision (roadmap step 7)

`Bom.lines` are flat and sorted by sku; `report/structure.py` already inverts
pegs to put parts on bays and stations, so grouping by section and panel is a
read-model addition rather than new arithmetic. Grouping by DECISION is the new
one — `SupplyDecision` and the graph carry what is needed.

## 5. `DesignRun` / `MaterialRun` (backend audit §1.5)

The audit's sharpest finding and verified in code: `/bom` reads LIVE inventory and
logs an `inventory_hash` that enters no identity, so one `run_id` yields different
BOMs as stock moves; and `objective_preset` — read only by supply resolution —
sits inside the DESIGN digest (`generator.py`). Deserves its own spec: it changes
persisted identity. Dispositions in
`docs/reviews/backend-audit-2026-08-16-response.md`.

---

## Smaller, known, and cheap

- **`elevation.js` layer identity is positional.** `.elev-edges` and `.elev-seats`
  tie shapes to members by ARRAY POSITION; only `.elev-member` carries
  `data-order`. A change to one loop mis-pairs an outline with the wrong slat.
  `assembly.js` defends itself by checking layer lengths agree. Give those rects a
  `data-order`.
- **Post candidate selection is sorted-first, not cost-based** (`_model_post_skus`).
  Defensible for an indivisible each; the line still carries its full eligibility
  into demand, so the choice stays explainable there. Still true after W3, and
  now visible: a routed line with two acceptable posts buys the alphabetically
  first, and the intersection at a boundary is taken over sets, not over prices.
- **A model's cap is matched against the MODEL's post, not the one finally
  written.** `_make_post` puts a forced sku, a masonry mount and a gate
  reinforcement ABOVE the model's post, so a cap whose predicate reads
  `post.face_width_mm` reads the face of a post that situation replaced. Narrow —
  it needs a predicate-matched cap AND a situational post at one station — but it
  is a wrong answer rather than a missing one when it happens.
- **Architecture fitness tests** (audit §5): forbidden imports, table inventory,
  port inventory, route inventory, hash field lists. The right answer to the whole
  class of drift the audit found. Best done once the import graph stops moving.
- **Application layer** (audit §1.3): extract a handler when a use case is next
  touched — `generate`, `/bom`, `quote`, `impact` are the four with real
  duplication risk. Rejected as a big-bang restructure.
- **Knowledge taxonomy orthogonalization** (audit §4.1): deferred with a trigger —
  revisit when a rule genuinely needs two of lifecycle/effect/enforcement/origin
  to vary independently. Note that "the tier decides the consequence" is a shipped
  feature, not an accident of the enum.

## Traps

- **Subagents share one working tree.** One agent's `git checkout -b` moves
  another's branch; one agent's `git add -A` stages another's in-progress files.
  It happened here — see the archaeology note in `current-status.md`. Give each
  agent its own worktree, or let exactly one agent touch git; stage by path.
- **The browser suite is a release gate, not a nicety.** It has now caught six
  defects in this arc that pytest structurally could not — a user-visible parts
  ordering change, two JS readers left on migrated catalog keys, a rail painting
  black, a stale bay preview, and a new built-in model absent from the tool that
  offers them. `TestClient` serialises requests, so no pytest test can see the
  concurrency class at all. It is also FLAKY under load: one run of this arc
  reported 32 unrelated failures from the first generation onward and the next
  clean run passed 170/170. Re-run before believing a broad collapse; believe a
  single localised failure immediately.
- **A new user-visible code needs BOTH locale bundles** and a line in the
  `REFUSAL_CODES`/`WARNING_CODES` list; the guard scans `api/app.py` and both
  `code="..."` spellings.
- **Mutation is the standard.** A new test is expected to be shown failing against
  the pre-fix code. Two vacuous assertions were caught in this arc by doing that —
  one determinism test whose fixture was already sorted, one cap test naming the
  company default.
