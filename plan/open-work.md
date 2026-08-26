# Open work

Handoff, updated 2026-08-21. Everything below is unstarted unless it says
otherwise. State it follows from: `plan/current-status.md` (newest entry first)
and `docs/superpowers/specs/2026-08-16-part-specs-and-fence-system-design.md`,
whose §11 carries the wave plan with each wave's findings folded back in.

`main` is green: **1617 pytest · 193 scenario tests · 202/202 smoke ·
compatibility gate byte-identical**, and pushed. The design/supply identity arc
merged 2026-08-20 (`639d1bf`, `49814c0`) and the post/cap preference fix
2026-08-21 (`66685de`); the `part-picker-repair` arc merged 2026-08-20
(`c0f38a4`) after three reviewers over the whole branch.

**Every numbered item below is now closed.** What is left is the merge review's
own findings (next section), the "smaller, known" list, the deferred triggers,
and whatever the earlier review rounds recorded as knowingly not done.

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
* ~~the assembly FILM still orders itself by its role heuristic~~ — still true,
  and now for a sharper reason than "no observable difference": see build-order
  item 11 below.
* ~~the placeable vocabulary is the PANEL's slots, so no step can name a post~~ —
  DONE, build-order item 11. `AssemblyStep.bay_parts` (`post | cap | footing`)
  and `assembly_plan(..., bay=...)`.
* `text_i18n` is versioned with the engineering document, so fixing a typo mints
  a new product-line version. The split, if it is worth it: keep `key/kind/slots`
  on the model, move the prose to a separately versioned instruction document.

## ~~11. Step scopes, and `requires` as a partial order~~ — DONE, 2026-08-25

Contract obligations 11 and 12, plus the post/cap/footing gap item 2 recorded.
`AssemblyStep.scope` (all five: `panel | bay | post | run | site`),
`AssemblyStep.bay_parts`, `AssemblyStep.requires` as typed EDGES,
`fencemodel/step_order.py`, `AssemblyPlan.order` / `.unplaced_bay`, and the panel
sheet's order note. M-VINYL is the document that exercises all of it.

**The decision that needed making: a partial order has no single sequence.** The
read model returns ONE linearisation — deterministic, tie-broken by authored
position — and publishes the SHAPE beside it so nothing has to be assumed:
`order.stages` groups steps that are mutually unordered, `order.unique` says
whether the sequence returned is the only valid one, and `order.basis`
distinguishes an order the document ASSERTED from one it merely PRINTED. The
sheet renders all three cases as three different sentences. Returning a bare
sorted list would have re-flattened the partial order with an engine's authority
behind it, which is the failure obligation 11 exists to name.

**Cycles are refused at authoring** (`validate_model`), not discovered at render:
the author is holding the document and can say which edge was wrong. `not_before`
loops are NOT refused — "neither starts before the other" is concurrency, and
refusing it makes a true statement unauthorable. `report/assembly.py` still
renders a cyclic draft and reports the circle, because a document being typed is
invalid by definition.

**Knowingly not done, and the reasons are new:**
* **the assembly film is still on its role heuristic**, and the case for rewiring
  it got WEAKER rather than stronger. `animate.js` animates a whole RUN — posts
  along the line, then each bay's members — while an assembly plan is per-panel
  and its steps now carry scopes (`run`, `site`) the film has no vocabulary for.
  Feeding one panel's linearisation into a run-wide reveal would need a second
  ordering concept (how do five bays' `stage 1`s interleave?) that nothing has
  asked for. The motivating case is unchanged: a model whose authored order and
  the role heuristic genuinely disagree.
* **`footing` is nameable and not yet countable.** `bay_parts_from_posts` inverts
  `ElevationPost`, which is a drawing rectangle carrying no `mounting`, so a step
  naming `footing` places nothing — honestly, the same way a step naming a slot
  only a variant has does. The seam is one function wide: a caller holding the
  run's own `Post` objects (which DO carry `mounting`) builds the row and every
  reader downstream gets it. That caller does not exist yet because
  `preview_panel` builds a `Strategy` with no posts at all.
* **`unplaced_bay` is opt-in**, populated only once a model names a bay part
  anywhere. Assumption, stated rather than buried: a document that says nothing
  about the bay is not making an INCOMPLETE claim about it. Reporting every
  legacy model's posts as unplaced would put a warning on every sheet in the app
  and bury the case that matters (a model that stands the posts and forgets the
  caps). `unplaced` itself is untouched and is still obligation 9 exactly.
* **containment is item 10 and was not built here.** When it lands, a part
  contained inside another becomes a member like any other and joins `unplaced`
  by the existing rule — this read model needs no new concept for it, only the
  panel to carry them.
* **`exclusive_with` is published, validated and rendered as a note, and nothing
  BRANCHES on it.** A plan containing two alternatives returns both steps; no
  surface asks which one this job is doing. Choosing needs a condition to choose
  by, which is a `Variant`-shaped question and not an ordering one.

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

## ~~5. `DesignRun` / `MaterialRun`~~ — DONE, 2026-08-20, as **`SupplyRun`**

ADR-0011, `fulfillment/supply_run.py`, the `supply_runs` table, `digest-v3`, and
`Quote.supply_id`. The spec's §1 reproduction is now a regression test: same run
id, two yards, two named supply runs, `GET /runs/{id}` byte-identical between
them. The compatibility gate never moved, which is the evidence this was an
identity change and not a costing one.

**Renamed on the way in.** `material` was already a catalog product attribute
(vinyl, steel, cedar) that a part's spec declares as a CONSTRAINT on an item
(`item.material == "vinyl"`), rendered in a UI surface called the material
drawer. `MaterialRun` would have read as a run about vinyl-versus-steel. The
half it names is the half below the demand boundary, which this codebase already
calls supply.

**Two things the spec had wrong, both found by checking it against the code:**
* `objective_preset` was in the digest TWICE — by name, and inside `policy`,
  which `DEFAULT_POLICY` always populates. Removing one occurrence would have
  left the id unmoved and the change inert while looking done.
* §5 claimed the bump invalidates the property
  `test_regenerating_the_same_drawing_keeps_the_conversation` depends on. It does
  not: that test generates twice against ONE digest version, and digest stability
  is a property within a version. The bump strands persisted run ids once, at the
  boundary, and nothing after.

**Knowingly not done:**
* ~~the frontend does not SHOW the supply id~~ — DONE, 2026-08-21. The print
  sheet's title block names it beside `run_id`, the BOM tab carries a provenance
  line, and a viewed quote names what it froze. `/structure` now goes through the
  same `_supply_run_for` as `/bom`, so the sheet and the BOM cannot name
  different yards. The print sheet was the surface that mattered: its part rows
  print `from_bars`, which move with the stock on hand, so two printings of one
  run could carry different cut lists under an identical title block.
* no retention policy — supply runs are append-only and never expire (spec §7.2,
  decided). Idempotency means growth tracks real yard changes, not read volume,
  so nothing forces the question yet.
* the impact preview still compares designs, not supply runs (spec §7.3,
  decided). It is strictly easier now that there is a thing to diff.
* `GenerationRun.objective_preset` is still populated and still stored. It is now
  a record of what a run was generated under and **nothing may read it for a
  decision** — `save_run` is INSERT OR IGNORE, so on an unchanged fence it is
  frozen at the first generation for ever. ADR-0011 exists mostly to say this.
* the quote's staleness refusal can now cite its supply run and does not. Saying
  so needs a new user-visible code in both locale bundles, which is a separate
  slice with its own bundle test.

---

## ~~8. The warning model, `attaches_to`, and the annexe~~ — DONE, 2026-08-26

Contract obligation 10 and §3.3.5. `core/warnings.py` (`DocumentWarning`,
`WarningTarget`, the shared `warning_errors`), `report/annexe.py`
(`place_warnings` / `place_for_plan`, one placement and the `Σ instances +
not_in_plan` invariant), `js/doc-warnings.js`, `FenceModel.warnings`,
`Snapshot.warnings` typed and consumed, S19, and the registry split written into
CLAUDE.md. Details in `plan/current-status.md`.

**Knowingly not done, with the reasons:**
* **A published warning still reaches no surface.** Nothing wires an ingested
  snapshot into a run — the seam item A left — so the authored path
  (`FenceModel.warnings`, the model editor) is what renders today. The placement
  read model is indifferent to which door a warning came in by, which is the
  whole reason it takes a list rather than a run.
* **`procedures` is a parameter with no caller.** §1.2 publishes `Procedure` as a
  step sequence that owns no panel; this engine models none, so a
  procedure-scoped warning naming one is reported `unplaceable`. The seam is one
  argument wide and named.
* **The model EDITOR cannot author a warning yet.** The backend accepts them,
  `validate_model` refuses a broken one, and the raw-JSON editor can write one —
  but there is no form. The frontend design asks for `text_raw` + `lang` +
  `attaches_to` + the publisher's severity word with no translate affordance, and
  the preview surface it needs (the annexe preview on the Panel tab) is the half
  that landed.
* **`instances` is counted per placement, not per plan.** A footnote quoted by two
  models that cite different source docs is two annexe entries with `instances=1`
  each, which is right; if a third document ever quotes it with no citation at
  all, that is a third entry. No corpus evidence says a reader wants those
  merged, and merging them would have to drop the attribution to do it.

## The merge review, 2026-08-20 — found, and NOT fixed

Three reviewers over the branch before it merged (architecture, tests, frontend
contracts). Verdicts: SOUND-WITH-FIXES, GAPS, and 2 blocking defects. Everything
blocking was fixed and is in the branch. What follows was found, judged, and
deliberately left — each with the evidence, so nobody has to rediscover it.

**~~The biggest one: the model's post and cap are priced choices with no decision
node.~~** — FIXED, 2026-08-21. Both halves: `_preferred()` now orders candidates
by the company's stated `priority` instead of `sorted(...)[0]`, and the
`place_post` node carries `rejected` / `cap_rejected` with `explain.py` sentences
in both languages.

**The handoff offered two fix directions and the code ruled one out.** "Route the
model's post/cap through `resolve_supply`" would have moved the choice to read
time — but a post's sku drives GEOMETRY (`preview.py` reads its face width for
the bay's clear width, `report/structure.py` its declared length for the
setting-out sheet), so the drawing would move whenever the yard moved. That is
the opposite of ADR-0011. The choice stays in generation and generation was made
to explain it instead.

Nothing existing moved, and that was measured rather than hoped: `_matched`
returns exactly ONE candidate on every call across every gate fixture
(`{1: 10}`), so preferred-order and alphabetical give the same answer everywhere
today. Both new behaviours were shown failing against mutants.

**Still open, and smaller than it was:** when two lines claim one post and their
stated orders CONFLICT, the tie breaks alphabetically and the node does not say
that it did. A reader sees a preference that was not honoured with no note
explaining why. Deliberate — "first claim wins" would make the answer depend on
the walk order — but a `preference_tied` flag in the payload would let the
sentence admit it.

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
