# Structure & parts review — findings and dispositions (2026-08-11)

Two adversarial reviews of the structure feature (`f4e6169`): `architecture-critic` on the
design and its stated properties, `test-reviewer` on whether the tests could tell the
difference. Both were run before the milestone was called done, per CLAUDE.md.

The short version: the *layout* half was sound and well pinned. The *parts* half was not —
four mutations that each produce a materially wrong setting-out sheet survived the whole
suite, and three of the spec's own "properties that must hold" were false in practice.

## Fixed — documents that would have gone to site with wrong numbers

| # | Finding | Fix |
|---|---------|-----|
| A1 | The endpoint laid a **stored run's strategy over today's topology**. Edit the drawing, reload, open Structure → "P5 @ 9000, spacing 4500" for a run whose posts stop at 6000. Reachable in the UI, not just via curl. | 409 `topology_changed` when `run.topology_revision` ≠ the project's; the tab says the drawing changed; tags disappear from both drawings with it. |
| A2 | The report was a function of **mutable inventory** with nothing recording which one — and the frontend cached by run id, so the sheet could name a bar the BOM had already stopped using. | `inventory_hash` stamped on the report (as `/bom` does); saving inventory invalidates the cache. |
| A3 | **Σ(parts) ≡ BOM was one-directional.** Fulfilment emits *no line* when stock covers demand, so 5 posts and 32 screws could vanish from the accounting with `unassigned: []`. | The ledger balances per `(sku, unit)` in both directions: `unassigned` (purchased beyond elements) and `from_stock` (asked but not purchased). |
| A4 | `unassigned` summed **across units** and could print a **negative quantity** when one SKU is demanded in two units (a tube bought as a post and cut as a rail). Data-reachable through knowledge. | Accounted per unit; negatives impossible by construction; pinned by a test. |
| A5 | A **shared corner post carried two different tags** (P4 in one section, P1 in the other) while the drawing can only print one — the exact property the feature exists to guarantee. Totals counted rows (7 posts for a 6-post fence) and the customer sheet billed the shared post to both sections. | Tags unique per element and section-qualified (`A/P1`); the borrowing section shows `shared_from`; totals count elements; the customer sheet dedupes. |
| A6 | The dimension chain treated **every post pair as a bay**, so a gate opening could be starred as the tolerance-absorbing one — telling a crew to lose their tape error into the one dimension that must be exact. | Bays and gates dimensioned distinctly; only a bay can close; the legend is anchored to the starred bay (so a reversed section keeps them together). |
| A7 | A **stale in-flight fetch** for run A was adopted as run B's schedule, permanently mislabelling the drawings. | Fetches keyed by run and dropped if the run moved on. |
| A13/T7 | A gate authored past the end of its section was **clamped silently**, and the kit was checked against the *authored* width — so "opening 600 · GATE-KIT-1000" reached the sheet. | New `gate_past_run_end` warning (both locales + explain templates), and the kit is re-checked against the opening that will exist. |
| T1 | **Peg identity was never tested.** Concrete on the wrong post and screws on the wrong bay both survived, because the only end-to-end property was a per-SKU grand total. | Every element asserts it gets what *it* asked for; verified by re-running the reviewer's mutations. |
| T2 | **`Part.role` correctness untested** — a cap labelled `post` passed, silently changing what a customer proposal itemises. | Role→SKU mapping pinned, plus which roles each kind of element may carry. |
| T3 | **Bar provenance asserted only by prefix** — every piece claiming bar #1 (eight rails from one 3 m stick) passed. | Bar labels checked against the cut plan's actual bars, piece for piece. |
| T4 | The `unassigned` test asserted `32 + 0 == 32`; its docstring described a mechanism that does not exist (rounding lives in `purchase_qty`, never in engineering demand). | Replaced with the real relationship between what is *fitted* and what is *bought*, read from the catalog rather than hardcoded. |
| T5 | The sum-back property never ran on a topology where it breaks. | It now runs on a corner, and requires a repeated row to announce itself. |
| T6 | `GateRow` had no `from_tag`/`to_tag` — the spec promised them and a hanging crew needs them. | Added, shown in the gate schedule, tested. |
| T8/T9 | Determinism covered only the last step; several assertions were of the "is not None" kind. | Whole-pipeline reproducibility; exact fixture counts; cut basis decided by `length_basis`. |
| T10 | Browser checks proved less than the commit claimed: "clicking a row selects the element" passed if *any* row was selected; the print checks read container `display` only. | Click asserts identity (that row, that explanation); print asserts rows and drawing tags survive; row count comes from the fetched document; a tautological `or True` clause removed. |
| A9/A10/A12/T11 | Section header named whichever base event was authored first; unpegged requirements went to a phantom `"—"` element that no table renders; the endpoint bypassed the 404 helper; the role vocabulary was pinned with `==` although picket packs are anticipated. | "mixed" when a section genuinely has two surfaces; unpegged → `unassigned`; `_project()`; `>=`. |
| A11 | The **print sheet** dropped the elevation when the side view was collapsed, printed one section's drawing beside all sections' schedules, and stamped UTC at render time. | The elevation always prints; printing shows the whole fence; the time is local and stamped at print. |

## Accepted, not changed

- **`structure.js` imports `inspector.js` directly.** The critic noted it and concluded it is
  the same deviation `editor.js` and `profile.js` already make; everything genuinely
  cross-cutting goes through `state.js`. Unifying that is a separate refactor.
- **Fixture coupling to demo catalog numbers** (element counts, `A/P1` tag format in two
  test modules). Real, but the alternative — indirection through helpers — costs more
  readability than it buys today. Noted here so the next author knows it is deliberate.

## Where both reviews found nothing

XSS (every interpolation goes through `esc`, including JSON in a data attribute), RTL (tags
and dimensions live inside `direction: ltr` drawings), tag ordering determinism (total sort
on `(station, id)`, no clock/RNG/dict-order dependence), reversed chain entries (the
station→x mapping handles them correctly), and module DOM ownership.

## Known gaps (next round)

- Two posts at the same station would silently share a bay linkage (`station_tag` is keyed
  by station). Not reachable with today's generator; worth a guard.
- `totals.per_sku` and the per-element index are built from different bases (requirements vs
  elements); identical today because every requirement pegs to exactly one element.
- The report is fetched per tab visit with no caching; fine at fence scale, unmeasured at
  portfolio scale.
