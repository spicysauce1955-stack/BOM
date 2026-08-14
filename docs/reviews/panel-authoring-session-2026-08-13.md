# Panel authoring: what the session found

Record of the work behind `docs/superpowers/specs/2026-08-12-panel-authoring-design.md`
(W1–W6), `main` `cbf7870..bd3a26f`, 28 commits. 585 → 863 pytest · 126 → 145 golden
scenarios · 107 → 137 browser checks.

This is the findings log. The verdicts and their dispositions are here; the deferrals and
their triggers are in `docs/v1-known-limitations.md`; the narrative is in
`plan/current-status.md`.

---

## 1 · Defects found and fixed

Ordered by how badly each would have hurt, not by when it was found. "Green suite" below
means the whole test suite passed with the defect present.

### Two projects served each other's fence

`project_id` is bound as an evaluation-scope dimension, so a project-scoped rule changes
the strategy — and it was **not in the run-id digest**. Two projects with the same topology
produced the same `run.id`, and `save_run`'s `INSERT OR IGNORE` dropped the second. Its user
pressed Generate, saw their own answer in the response, and every later read — `/bom`,
`/structure`, `/quote`, `/explain` — served the first project's fence. Green suite.
Pre-existing on `main`, surfaced because W1 rewrote that expression.

### A live 500 the Python suite is architecturally incapable of seeing

`Store` shared one `sqlite3.Connection` across FastAPI's threadpool with
`check_same_thread=False` silencing the guard rather than solving anything. Two overlapping
fetches interleaved statements on one cursor and raised `InterfaceError: bad parameter or
other API misuse` straight out of a route. `TestClient` serialises requests, so **no pytest
test can reach it**; the browser smoke suite was the only detector, and it was red on the
branch while green on `main`. Found independently by the test review and by the authoring
agent (48 failures in ~540 overlapping requests). Every store method is serialised now,
held for the whole call because several read then write.

### The child-head gap check measured the wrong openings

`clear_gap_exceeded` measured `fit.gaps_mm` — the holes **between** members — and nothing
else. `center` justification folds the entire residual into the two edge margins and zeroes
`residual_mm`, so a 2000 mm opening with 300 mm members and a `truncate` excess stood with
two 150 mm holes **against the posts** while every measured gap read 50 mm. Both checks
passed. `FitResult.openings_mm` is now the complete set, and a test asserts the openings
tile the axis exactly.

The irony worth recording: the check's own docstring correctly explained why a single
rounded gap defeats the sphere test, and then measured the wrong set.

### A model choice bought no slats at all

A vertical slat had no way to get its length: every `LengthRule` derived from the bay's
**width**. Authoring one would have stamped 2400 mm on a part the fence cuts to 1800.
Authoring none was worse — a divisible product asked for with no cut length plans no bars,
so the panel priced **no slats**, and the parts ledger read the gap as demand met from
stock. New `panel_height` rule; `validate_model` now refuses the silent version of that hole
at authoring time.

### The picker, the preview and the fence disagreed about M-LEGACY

`_pick_model` short-circuited on the model id **before** consulting the library and
regardless of `version_pin`. A published `M-LEGACY@v2` was offered by the picker, priced by
the preview, reported on by the impact preview and accepted by the project-default route —
then ignored at generation. The id is reserved at the route now (`fence_model_reserved`,
409): M-LEGACY is the compatibility path, not a model anybody authors.

### Three more wrong answers behind a green suite

- **A multi-member pattern drew a wrong picture beside right numbers.** The elevation walk
  approximated the cycle as "this member, repeated", so a two-member pattern drew thirteen
  wide slats where seven were bought, running clean out of the panel. The real cycle now
  travels on the slot.
- **An exact bay width lost to a `min()` with nothing recorded** — producing bays of
  *neither* width and then reporting the width nobody used. It is a conflict between a
  manufactured dimension and a hard maximum; it is surfaced as one, citing both refs.
- **The preview double-counted money** whenever two slots shared a SKU — the ordinary case
  for a frame with named top and bottom rails, on the one surface built so a person can
  compare what two models cost. Rows are apportioned and sum to the total.

### `per_gap` counted pieces, not positions

Found by a test written *for* the review rather than by the review. A member with `qty=2` is
two pieces at **one** position (a batten pair); it makes no extra gap. A 12-position panel
ordered 17 spacers.

### The impact preview lied about which model a job is built to

`_spine` never passed the project's default model, so an M-SLAT job was regenerated as
M-LEGACY on **both** sides of the diff and the report attributed two changes to one rule.
Introduced by W1 and caught while wiring W4's prerequisite. The test is mutation-verified:
"the delta is non-zero" would have passed with the bug intact, so it compares the delta for
an M-SLAT job against the delta for an M-LEGACY one.

### The locale guard could not see a single code any route emits

`test_backend_code_list_is_current` scanned five files for `code="x"`. Routes live in
`api/app.py` (not scanned) and write `"code": "x"` (not matched) — invisible twice over.
Extending it immediately caught **four codes shipping untranslated**, including two 409s a
user meets whenever they edit a catalog or a drawing.

### Authoring gaps

A slot with **no eligible product** published cleanly and then reported `no_eligible_item`
on every bay of every job built to it. One **already-broken project** 500'd the whole
portfolio impact preview, at the moment a user most needs an answer. With **two drafts**,
`listing()` reported the highest and the save took the first — silently different versions.
An **abandoned draft stayed for ever**, and the editor's first design saved on every
keystroke, so a half-typed model id left a library row per character.

---

## 2 · Coverage gaps found

The suite was green for all of the above. What let it be:

- **The infill path — the whole point of this work — sat outside both batteries.** Every
  invariant fixture and every golden-gate artifact was M-LEGACY (two rails, eight screws).
  Dropping infill lines from `BomLine.pegs` broke the BOM → requirement → element → decision
  traceability invariant with a green suite. Two M-SLAT fixtures now join both; the existing
  eight gate files are byte-identical, so the compatibility claim still holds.
- **Nine single-line pass-throughs in `resolve_panel` had no test at all** —
  `edge_margin_mm`, `justification`, `face_offset_mm`, a member's own `qty`, a **vertical**
  frame slot, `per_end_member`, `per_gap`. Each was an equivalent mutant against the demo
  models, which use the default for every one of them — and the authoring API accepts all of
  them. One panel that uses the non-default value of each now pins them. It found the
  `per_gap` defect.
- **No concrete BOM quantity for a generated slat run** — membership and length were
  asserted, never a count, and `asked == bought` is self-consistent when the derivation is
  wrong. A hand-derived 48 slats → 16 bars now stands.
- **Nothing pinned that a stored run survives a model edit.** The catalog half was
  thoroughly covered; the model half rested on nothing.
- One **vacuous assertion** (`declared is True` on slats, where the field's default made it
  true for every possible input) — the flag now means something in both directions, which
  required making a frame member's face height authorable.

---

## 3 · Still open — suggestions, in the order I would take them

1. **Prices render in €.** Your persona lab flagged this in run 1 and it is still true. The
   market this ships into quotes ₪ (and ₪/מטר רץ, which `LinearPrice` now supports). This is
   a small change with a large credibility effect and it is the first thing a Hebrew-speaking
   estimator will see.

2. **`_skus_used` fails open.** The narrowed `catalog_hash` is correct today — I traced every
   read path — but it is a hand-maintained inventory of that path, and a missed SKU means
   *no* 409 and a silently re-priced stored run: strictly worse than the over-broad version
   it replaced. A test that walks a priced read and asserts every `catalog.products[...]`
   access is in `run.catalog_skus` would make the narrowing safe rather than
   currently-correct. The test reviewer suggested this and I agree with it.

3. **Inventory is not part of a run's identity** (recorded in known-limitations). Which
   eligible product wins depends on remnant stock, `inventory_hash` is stamped and compared
   to nothing, and `/explain` can therefore name a different product from the one an accepted
   quote bought. Neither obvious fix is right — 409ing the money views whenever stock moves
   is worse, and dropping inventory from the cost tier changes what "cheapest" means. It
   needs a decision, not a patch.

4. **The doc ⇄ code disagreement is still open.** `docs/scenarios/golden-scenarios.md:23`
   says rails are cut to clear width; `demand/derive.py` cuts to centre-to-centre. Both
   built-in models declare `centre_to_centre` deliberately so nothing moved, but the
   disagreement is now embedded in two models instead of one place. It matters numerically —
   at clear width an S07 rail drops from 1500 to ~1420 mm, which is two pieces per bar
   instead of one, i.e. **half the rail BOM**. CLAUDE.md routes this through the
   `golden-scenarios` skill; it should be settled before a third model inherits it.

5. **`catalog/demo.py` claims to be "the one defined in golden-scenarios.md"** and now
   carries SLAT-100, which is not in that table. Precedent exists (the gate-kit components
   are also absent), but the docstring is drifting from the truth.

6. **Determinism is tested single-process.** `f(x) == f(x)` inside one interpreter cannot
   catch hash-ordering nondeterminism. The golden files cover it cross-process, and now do so
   for M-SLAT too — but a `PYTHONHASHSEED=0` vs `=1` run would say it directly.

7. **Route-level TOCTOU remains.** Serialising `Store` fixed the corruption; two requests
   that each read-then-write across *separate* store calls can still interleave. ADR-0008
   records what the lock does and does not cover.

8. Smaller: distributed rails land flush with the panel edges (correct per spec, reads oddly
   as a fence — a demo-data choice, not a code one); a fixings-only model draws nothing and
   says so; `NOMINAL_THICKNESS_PERMILLE` is not on the wire, so a client can say "not
   measured" but not what the nominal came from.

---

## 4 · What was deliberately not built

Five features, each refused **by name** in `validate_model` so none can quietly half-work,
and each recorded in `docs/v1-known-limitations.md` with the trigger that should end the
deferral: `excess='trim_last'` (needs 2D cutting — a standing non-goal, and it was
mislabelled a phase-2 deferral until this session), `excess='extension_clip'` (undesigned:
nothing names the clip product and the clip count depends on the justification),
`InfillSpec.supply='assembly'`, `Axis.available_when`, and **phase 3's arc-flow over
multiple stock lengths**.

Phase 3 is the one worth stating plainly: it adds an OR-Tools dependency for a solver
ADR-0007 says to reach for "when a real catalog has eligibility groups worth optimising
over". Today's FFD + LP bound certifies optimality honestly and flags the plans it cannot
certify, so the gap is a **bound, not a wrong answer**. Taking on that dependency against
the demo catalog rather than a real one is a call for the project owner.

---

## 5 · Method note

Five agents ran: two building isolated slices, three reviewing (`architecture-critic`,
`test-reviewer`, and the authoring agent's own pair). The two adversarial reviews found
between them one blocker each and eleven further defects, all dispositioned above. Both
review reports were worth more than the code they reviewed, and the single highest-value
finding of the session — the threading 500 — came from a reviewer noticing that the smoke
suite was red while the pytest suite was green, and asking why.

Worth repeating next time: **run the browser suite, not just pytest.** Three of this
session's defects were invisible to `TestClient` by construction.
