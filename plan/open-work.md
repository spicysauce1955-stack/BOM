# Open work

Handoff, updated 2026-08-20. Everything below is unstarted unless it says
otherwise. State it follows from: `plan/current-status.md` (newest entry first)
and `docs/superpowers/specs/2026-08-16-part-specs-and-fence-system-design.md`,
whose §11 carries the wave plan with each wave's findings folded back in.

The branch is green: **1542 pytest · 191 scenario tests · 198/199 smoke ·
compatibility gate byte-identical** — the one smoke failure is another agent's
in-flight check, uncommitted in this tree, not a regression.

**Every numbered item below is now closed or specified.** What is left is the
"smaller, known" list, the deferred triggers, and whatever the two review rounds
recorded as knowingly not done.

---

## ~~1. Finish W3 — the routed vinyl case~~ — DONE, 2026-08-17

All three pieces landed, plus the preview gap the last of them made closable:
`288a1d7` (panel facts reach post matching; the authoring refusal deleted in the
same commit), `edeb0d0` (M-VINYL and golden scenario S16), `0c3472c` (boundary
posts intersect; the three §8 failure codes), `e033f01` (the panel preview
measures its own model's post). See `plan/current-status.md` for what each
decided and what building them found.

## ~~2. Assembly and installation instructions per panel~~ — DONE, 2026-08-19

`AssemblyStep` on `FenceModel`, `report/assembly.py`, M-VINYL's own instructions,
and the Panel tab (`6839e25`, `a94048b`, `5d50357`). The plan's own line settled
the design: a step names slots, so it is data rather than a paragraph, and the
invariant is that every member is placed by exactly one step or reported
`unplaced`.

**Knowingly not done**, both recorded in `report/assembly.py`:
* the assembly FILM still orders itself by its role heuristic. For every demo
  model the authored order and the heuristic agree, so rewiring adds a second
  ordering path to a well-tested feature for no observable difference. A model
  whose order genuinely disagrees is what should motivate it.
* the placeable vocabulary is the PANEL's slots, so no step can name a post, its
  cap or its footing — an installation instruction about posts is prose today.
  Closing it means giving the read model the bay's posts, a different input.
* `text_i18n` is versioned with the engineering document, so fixing a typo mints
  a new product-line version. The split, if it is worth it: keep `key/kind/slots`
  on the model, move the prose to a separately versioned instruction document.

## ~~3. Section-scoped decisions, and commenting on one~~ — DONE, 2026-08-19

`report/section_decisions.py`, two routes, the side-panel surface, S17, and the
propose-a-rule loop (`6db459f`, `47dfcd7`, `28e0e73`, `dda3675`). The boundary
holds and is on screen: a comment is verbatim, changes no fence, and becomes a
candidate only a person can approve.

**Knowingly not done:**
* "CHANGE it" — the third verb of that roadmap line — is still the existing
  override path (pin post, force sku) and is not reachable from this panel.
* a comment cannot follow its decision into a new run, because a decision id is
  positional. The panel counts and names earlier-run comments rather than
  pretending they do not exist; making one MIGRATE needs a semantic anchor
  (section + action + station) stored beside `decision_ref`.
* the proposer still reads a comment as raw text, so a QUESTION ("why is this bay
  1500?") is evidence for a rule in the same way a correction is. A
  `kind: correction | comment | question` discriminator is the cheap fix.

## ~~4. BOM grouped by section / panel / decision~~ — DONE, 2026-08-19

`report/bom_groups.py`, the `grouped` key on `/bom`, and the BOM tab (`dfbb154`,
`5d50357`, `972d767`).

**Knowingly not done: money per section.** A purchase is pooled per sku across
the run — one bar is cut for two bays — so a per-section price is an
apportionment nothing measured. The missing concept is not arithmetic but a
named, versioned **apportionment policy** (by consumed length / by piece count /
by list value), which is an objective in the ADR-0007 sense and belongs in an
ADR rather than in a read model. An estimator quoting a two-phase job genuinely
needs this; it is the most valuable single thing left on this list.

Also open: the grouped BOM and the structure sheet answer "what does section A
need" differently for a SHARED corner post, because one sums and the other does
not. Both are right for their own question and the difference is now named on
screen, but one of them should probably change.

## 5. `DesignRun` / `MaterialRun` — SPECIFIED, not built (backend audit §1.5)

Spec: `docs/superpowers/specs/2026-08-19-design-run-material-run.md`. The defect
is demonstrated there rather than described — one run id, 40 700 then 27 200
agorot after three posts arrive in the yard, with `GET /runs/{id}` byte-identical
between them.

**It stops at a spec on purpose, and needs ONE decision from you** (§5): removing
`objective_preset` from the design digest means a regeneration of an unchanged
project produces a new id where it used to return the old one. One deliberate
discontinuity (recommended) against a permanent conflation. It also strands
comments anchored to a design run, which item 3 just made concrete.

---

## The merge review, 2026-08-20 — found, and NOT fixed

Three reviewers over the branch before it merged (architecture, tests, frontend
contracts). Verdicts: SOUND-WITH-FIXES, GAPS, and 2 blocking defects. Everything
blocking was fixed and is in the branch. What follows was found, judged, and
deliberately left — each with the evidence, so nobody has to rediscover it.

**The biggest one: the model's post and cap are priced choices with no decision
node.** `strategy/generator.py` takes `sorted(set.intersection(...))[0]` for both
— the lexicographically smallest sku — throwing away the authored order that
`_matched()` returns. Then `demand/derive.py` hands `resolve_supply` a
ONE-MEMBER eligibility, so no decision node is emitted at all. Reproduced: give
M-VINYL's cap slot two eligible members and the declared first preference loses
to alphabetical order, `honour_priority` cannot reach the choice, and the cap is
on the BOM while appearing nowhere in the graph. This violates "every BOM line
traces through the decision graph" and it is exactly the gap
`decisions/supply.py`'s own docstring declares CLOSED. Not a regression (the post
path was always like this and the branch only re-authored the cap alongside it),
which is why it did not block. Fix direction: either put `cap_sku` and its
rejected set in the `place_post` payload, or route the model's post/cap through
`resolve_supply` by giving `derive_requirements` the full matched member list
instead of `chosen(...)`. Until then the supply.py docstring should stop
claiming coverage it does not have.

**`unassigned` conflates two different facts.** `report/bom_groups.py` puts
purchase overage (`purchased − asked > 0`) and demand pegged to nothing in one
list, appended separately — so one sku can appear twice meaning two different
things, and the panel renders both under one heading. A reader cannot tell "we
bought more than the fence needs" from "this demand belongs to no section". Split
the buckets or tag the entries.

**The backend reads the frontend's locale bundles.** `api/app.py`'s
`_locale_bundle` / `GET /api/part-types` returns `label_i18n` per type, keyed
`part_type.<type>`, which the client already has. It puts locale rendering on the
server against "every user-visible string goes through `t()`", and the
process-level cache means editing `he.json` needs a restart. Return keys and let
`panel-inspector.js` call `t("part_type." + key)`.

**Two naming schemes in one panel.** `decisions/explain.py` prints raw ids in
user-facing prose ("Section runA is 800 cm long…") beside a grouped BOM that is
scrupulous about routing every row name through the single tag source, precisely
so a money view does not print a third name for one thing. The section panel says
`runA` where the drawing and the schedule say `A`. The backend cannot see tags —
they are a read model — so this needs a decision about where the join happens.

**Clearing the part picker authors an unsaveable slot.** `panel-inspector.js`:
the empty prompt option is always selectable, and choosing it clears `part_id`
without restoring `role`, `eligibility`, or the `width_mm`/`thickness_mm` the
earlier pick zeroed. `validate_model` then refuses the slot. A milder version of
the same "422 the author cannot see" this arc exists to remove, plus real data
loss on a dimension the field redisplays as `0`. Recoverable (the pane says
"Choose a part"), hence not blocking.

**Test gaps left open**, all with a surviving mutation recorded against them:
* `report/section_decisions.py`'s `by_payload` also reads `run_ref`; no decision
  node in `src/` carries that key. Reducing it to `run_id` alone leaves 1570
  green. Dead code, or a real path with no test and a comment overstating it.
* `test_no_group_carries_money` is a field-NAME substring scan — satisfied by a
  group with no lines, and by a cost field spelled `total_agorot`. Keep it as a
  design-intent guard; do not count it as coverage.
* `test_section_decisions.py`'s "a project-wide choice is excluded" passes for
  free: `resolve_demand_products` is excluded incidentally (no `run_id`, no scope
  refs) and nothing implements the rule the docstring claims.
* the grouped-BOM balance invariant — the analogue of `Σ(parts) ≡ BOM` — runs on
  the straight 6000 mm fixture only, not over `test_invariants.py::_fixtures()`
  (raked, slat, L-shape, gates). Parametrize it or move it into the invariants
  module.
* two browser checks over-promise in their names: "its own decisions, localized"
  reads no sentence and asserts no Hebrew, and the smoke project has ONE run at
  that point so section isolation is not observable there even in principle; and
  "a conversation can be turned into a candidate rule" concedes in its own
  comment that it passes either way.

## Smaller, known, and cheap

*(`elevation.js` layer identity, the cap following the stood post, and the
architecture fitness tests all shipped on 2026-08-19 — `051578c`, `979a1a9`,
`336cb6f`. The fitness tests found real drift on their first run: the part-library
arc had added a table and two routes without touching the backend doc.)*

- **Post candidate selection is sorted-first, not cost-based** (`_model_post_skus`).
  Defensible for an indivisible each; the line still carries its full eligibility
  into demand, so the choice stays explainable there. Still true after W3, and
  now visible: a routed line with two acceptable posts buys the alphabetically
  first, and the intersection at a boundary is taken over sets, not over prices.
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
  offers them, and a Models tab that was opened and never used. `TestClient`
  serialises requests, so no pytest test can see the concurrency class at all.
- **It was NOT flaky, and this note used to say it was.** A run reporting ~33
  unrelated failures from the first generation onward, green again on a re-run,
  was diagnosed on 2026-08-17 as load. It was a shared Chrome profile: no
  `--user-data-dir`, so `localStorage` survived the run, and this suite ends by
  toggling to English — the next run opened in English with every Hebrew
  assertion red. Fixed at the source (`987e17b`, which gave the run its own
  profile and its own DB; `6004a29` added the readiness wait a cold profile
  needs). The lesson generalises: an
  identical failure SET across two runs is never flakiness, and "re-run and see"
  is how a real defect gets written off twice.
- **A new user-visible code needs BOTH locale bundles** and a line in the
  `REFUSAL_CODES`/`WARNING_CODES` list; the guard scans `api/app.py` and both
  `code="..."` spellings.
- **Mutation is the standard.** A new test is expected to be shown failing against
  the pre-fix code. Two vacuous assertions were caught in this arc by doing that —
  one determinism test whose fixture was already sorted, one cap test naming the
  company default.
