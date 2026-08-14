# V1 known limitations

Deliberate deferrals and honest weaknesses, with the trigger that should revisit each.

## Domain

- **Interior run vertices are supported by the model but not the UI** — the editor
  creates straight runs between nodes; corners are shared nodes (which covers S03).
  Multi-segment runs with mid-run corners work through the API only.
- **Raked vs stepped is per-run resolved, per-span overridable** — no automatic mixed
  mode along one run based on local grade.
- **Gate anchored at its start station**; gates crossing run boundaries unsupported.
- **2D sheet/area cutting** (panel ripping) not implemented — only linear cutting.
  Trigger: first product with sheet semantics.
- **Substitution rules are data but not applied** during netting (suggest-only records
  exist; no automatic substitution pass). Trigger: first real substitution policy.
- **Assembly kits purchase whole**; component explosion is informational (BOM note).
- **Remnant policy lives on the catalog item**, not as a knowledge object (see
  docs/reviews/spike-review-response.md finding 14).
- **Allocation pegging is per-SKU**, not per-connection (critic finding 17) —
  every allocation lists all requirement ids of its SKU.
- **Cut-plan optimality**: FFD + LP bound; when the bound is not met the plan is
  flagged, not escalated. Trigger: real jobs where FFD misses (then CP-SAT extra,
  ADR-0007).
- **Layout is blind to the cut plan.** The two never speak, so nobody is told when a
  small layout change would buy far less material. S07 is the standing example: two
  1500 mm bays need four 3 m bars (1500+3+1500 > 3000, so one rail per bar and a
  1497 mm offcut each — 12 m of stock for 6 m of rail), while 1498 mm bays fit two per
  bar, and three 1000 mm bays need six rails but only **three** bars. More rails, less
  aluminium, one more post. The planner already computes the waste and `layout_segment`
  already emits a rejected alternative; nothing joins them up. This is an *advisory*,
  never an automatic relayout — span width is the user's design decision, and material
  cost is one input to it. Trigger: the first job where a customer is quoted materially
  more than a neighbouring layout would have cost.
- **No workshop model.** The system knows what a fence is made of but not what the shop
  can *do* to make it — the operations available (cut, drill, splice, weld, bend,
  coat), their rules (max handled length, minimum offcut, which joins are permitted
  where), their costs (setup plus per-unit) and their consequences. Today the one piece
  of process knowledge in the system, `DivisibleLinear.kerf_mm`, sits on the *product*,
  when a kerf is a property of the **saw**. Until this exists, "fabricate it" can never
  be an alternative to "buy it", labour is invisible in every comparison, and a rule
  like "we never splice a rail under 2 m" has nowhere to live. Trigger: the first
  decision that turns on shop capability rather than on catalogue contents — most
  likely a made-to-measure panel the shop could either buy or build. See the extension
  seam in `docs/superpowers/specs/2026-08-12-fence-model-design.md`, which is written so
  this can be added without reworking eligibility.
### Fence models, phase 1 (2026-08-12)

Four things this phase deliberately parked. Each is a real weakness, not a rough edge;
each is recorded with the trigger that should end the deferral.

- ~~**A chosen SKU has no traceable explanation once a group has more than one
  member.**~~ **CLOSED 2026-08-12.** The trigger fired — models became authorable, so a
  user can now create a multi-member group whenever they like. `SupplyDecision` is a
  typed record carrying every candidate with its PLANNED cost and waste (an infeasible
  one carries `None`, never a zero, which would read as "free"), and
  `decisions/supply.py::with_supply_decisions` turns it into a `select_supply` node.
  The question of "where a fulfilment-time node lives" is answered: **nowhere
  persistent**. The nodes are DERIVED at read time from a pure function of
  `(graph, decisions)`, exactly as `report/structure.py` derives the setting-out sheet,
  so fulfillment never acquires a graph builder and the stored document is never
  rewritten — `test_reading_a_run_never_mutates_its_graph` and
  `test_the_stored_run_document_is_unchanged_by_being_explained` pin both halves. The
  sentence names the runner-up and the gap ("RAIL-3050 … costs 3700c against RAIL-3000
  at 4000c"), because "cheaper than the others" is not an explanation.

- ~~**`catalog_hash` is whole-catalog, so any product edit permanently 409s every prior
  run.**~~ **CLOSED 2026-08-12.** `GenerationRun.catalog_skus` records the products a run
  actually named — chosen SKUs, every eligibility RIVAL (the choice among them is made at
  read time, so a rival getting cheaper is exactly a reason to re-check), and an assembly
  kit's components transitively — and `catalog_hash(catalog, skus)` covers only those.
  Narrowing is safe precisely because eligibility is frozen into the run: a product that
  did not exist when it was generated can never change what it means. Adding a gate kit
  or repricing a product this job never bought no longer refuses; repricing one it did,
  or changing a stock length it cut from, still does. A run stamped before the narrowing
  has an empty `catalog_skus` and is still compared against the whole-catalog hash it was
  stamped with, so no stored run changes meaning. The original text follows.

  **`catalog_hash` is whole-catalog, so any product edit permanently 409s every prior
  run.** `/bom` and `/structure` compare the stamped hash against a hash of the entire
  catalog document, so changing one product's price — or adding an unrelated SKU — makes
  every previously generated run unreadable until it is regenerated. The refusal is
  correct in kind (stamping is not checking, and re-resolving supply against a moved
  catalog would silently change what a stored run meant) but far too broad in scope: it
  cannot tell "the product this run bought got cheaper" from "somebody added a gate kit".
  The narrow version hashes only the products a run actually resolved, which is
  computable — the requirement lines name them — but changes what the run-id digest
  covers, so it is a design change rather than a tweak. Versioning the catalog properly
  is the other answer and is a bigger one. **Trigger:** the first user who edits a
  catalog price and finds their existing quotes' working views all refuse.

- **`model_snapshot` is `(id, version)`, not a content hash — and `legacy_model()` mints
  materially different models under one ref.** The field exists to keep the run-id digest
  honest when a model changes; it records `("M-LEGACY", 1)`. But `legacy_model()` takes
  the knowledge-resolved `rail_sku`/`screw_sku`, so `M-LEGACY@v1` denotes a different
  panel depending on the knowledge base — and a model edited without bumping its version
  is invisible to the digest entirely. Both cases reproduce exactly the `INSERT OR
  IGNORE` collision the field was added to close: same run id, new meaning, and
  `/api/runs/{id}/bom` serving the old stored document for ever. It is survivable today
  only because the demand skus are *also* inputs to the digest via the knowledge
  snapshot, so the M-LEGACY case happens to be covered by a different input — an
  accident, not a guarantee. **Trigger:** the first editable model (phase 2 makes models
  data the user can change), or the first built-in model parameterised by anything the
  knowledge snapshot does not already cover.

- **Runs generated before this branch cannot be read at all.** A stored run has no
  `Span.panel`, `derive_requirements` refuses, and `/bom`, `/structure` and `/quote` all
  return 400 `run_predates_fence_model`. This is the right refusal — the alternative is
  falling back to `rail_count`/`screws_count` and quietly disagreeing with what the run
  recorded — but it means the fence-model branch is a hard break for existing data, and
  regenerating produces a *new* run id, so links to the old one stay dead. The refusal at
  least says so properly now: it carries `code + params` with entries in both locale
  bundles, and the structure tab names it instead of showing "no structure yet", which
  was false (there is structure; it cannot be laid out). **Trigger:** a deployment with
  stored runs that matter — at which point the answer is the migration the spec already
  specifies, back-filling `panel` onto stored runs before the legacy fields are removed.

- ~~Impact analysis is per-run only~~ **Done (2026-08-10)**: cross-project rule impact
  preview (`POST /api/knowledge/preview-impact`, `POST /api/candidates/{id}/{v}/preview`
  + UI buttons in the review queue and knowledge editor) — regenerate-and-diff across
  all projects; previews persist nothing. Remaining refinement: diff against *historical*
  accepted quotes once BOM snapshots exist (see below).

### Panel authoring, W1-W6 (2026-08-13)

What the panel waves deliberately did not build. Each is refused by
`validate_model` by name, so none of them can quietly half-work; what follows is
why, and what would end each deferral.

- **`excess='trim_last'` needs 2D cutting.** Trimming the last member means
  ripping it NARROWER, and `cutplan.py` cuts to length: nothing in the system can
  price a part whose width changed. This is the same non-goal as sheet and mesh
  infill, not a queued feature, and it was mislabelled "phase 2" until now.
  **Trigger:** 2D cutting arrives, for whatever reason brings it.

- **`excess='extension_clip'` is undesigned, not merely unbuilt.** `InfillSpec`
  has nowhere to name the clip product, and how many clips a residual needs
  depends on the justification — one at the far end, or one at each end whose
  opening is non-zero, which differ under `center`. Both readings are defensible,
  which is precisely why picking one here would ship the plausible-but-wrong
  answer the refusal table exists to prevent. **Trigger:** a real catalog with a
  clip in it, whose data settles where they go.

- **`InfillSpec.supply='assembly'`** — the infill bought as one pre-made unit
  rather than as N members. `resolve_panel` unconditionally emits a component
  slot per member, and turning that around raises questions the spec does not
  answer: what the assembly's eligibility looks like, how the parts ledger
  accounts for a unit whose members are still drawn, and whether the elevation
  still shows the members it no longer buys. **Trigger:** the first ready-made
  panel product in a catalog.

- **`Axis.available_when`** — an axis is answered by whoever chose the model,
  long before a bay exists, so there is no context to evaluate it against and no
  surface that could hide the question. **Trigger:** options answered per bay
  rather than per selection.

- **`Member.base_ref`/`top_ref` under any rule but `between_frame`.** Narrowed by
  the joint wave (2026-08-14) from "never read at all", which is what they were
  from phase 1 until then — refused by nothing while the model editor offered
  both selects to authors, the exact defect `_UNSUPPORTED` exists to catch and
  the one it missed. `between_frame` now reads them and cuts a member to the
  opening between the two frame members plus its engagements; under
  `panel_height` or a width rule they still reach nothing, so a member that says
  "starts at the bottom rail" would run past it to the ground. **Trigger:** a
  length rule that measures against the frame in some other way — a diagonal
  brace between two rails is the obvious candidate, and it needs a second axis
  the schema does not have.

- **Phase 3: arc-flow over multiple stock lengths and sources.** ADR-0007 already
  names it, and the spec is explicit that it is a planned door rather than a
  dependency argument: "when a real catalog has eligibility groups worth
  optimising over". Today's FFD + LP bound certifies optimality honestly and
  flags the plans it cannot certify, so the gap is a bound, not a wrong answer.
  It also adds an OR-Tools dependency, which is a cost worth incurring against a
  real catalog and not against the demo one. **Trigger:** the first job where the
  certificate says "heuristic" and the money is worth the solver.

- **Inventory is not part of a run's identity.** `_candidate_cost` plans cuts
  against inventory remnants, so which eligible product wins can change when
  stock does — and `inventory_hash` is stamped but compared to nothing, while
  `catalog_hash` is checked. An accepted quote is safe (it persists its own BOM),
  but `/explain` on the same run, read later, can name a different product from
  the one the quote bought. Making inventory part of the identity would 409 the
  money views every time stock moved, which is worse; dropping it from the cost
  tier changes what "cheapest" means. **Trigger:** the first user who reads an
  explanation that disagrees with their own accepted quote.

## Learning / AI

- **Stub proposer recognizes one demo pattern** (existing-foundation corrections);
  the Claude proposer port exists but only the interpreter has a Claude adapter.
- **Candidate rules carry an AddNote action** (advisory) rather than a structured
  condition — structuring happens at review-edit time; the review UI supports
  approve/reject/scope-restrict but not condition editing.
- **Tier-2 LLM explanation polish not implemented** — Tier-1 templates only (the
  architecture reserves the port; ADR-0009).
- **Claude adapter untested against the live API** in this environment (no key);
  contract tests cover the wire schema and fallback behavior.

## Platform

- **Single-tenant, no auth, no concurrent-writer support** (SQLite WAL, one process).
  Trigger for Postgres swap: multi-tenant or concurrent editing (ADR-0008).
- **Full topology replacement on edit** (PUT) — no fine-grained topology PATCH ops;
  event re-anchoring code exists but the UI path always rewrites whole topology.
- **Strategy statuses** (accepted/superseded) are persisted but there is no
  accept/compare-alternatives workflow in the UI.
- ~~BOMs recomputed, not snapshotted~~ **Done (2026-08-10)**: persisted quotes —
  `POST /api/runs/{id}/quote` freezes requirements+BOM with inventory + knowledge
  snapshot hashes; draft→accepted→superseded lifecycle (accept supersedes the
  project's prior accepted quote, atomically); quotes panel in the BOM tab; impact
  preview now also reports the delta vs each project's accepted quote. The live
  `/bom` endpoint still recomputes (by design — it's the working view).
- **The UI is pragmatic** (mission §13). UI v2 added direct canvas manipulation,
  undo/redo, the elevation side view, and Hebrew-first RTL; still missing: touch-optimized gestures beyond big targets,
  and interior-vertex drawing in one stroke (corners are made by chaining runs or
  inserting via midpoint handles). Zoom/pan/fit added 2026-08-10 (wheel zoom,
  middle/Ctrl-drag pan, ⤢ fit).
