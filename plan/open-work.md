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
