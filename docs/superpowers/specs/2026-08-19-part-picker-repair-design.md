# The part picker — repairing the Models editor after the part library

Date: 2026-08-19. Status: design, awaiting review.
Arc A of three (A: this. B: connections. C: item tolerance).

Slice 1A moved a slot's eligibility onto the part it names. The Models editor was not
changed with it, so it still authors two fields that no longer mean what it thinks. An
expert opening the Models tab today sees every slot claiming **no product**, and the
save that would fix it is refused. This arc repairs that, and does nothing else.

---

## 1. The regression, reproduced

`panel-inspector.js` writes `req.eligibility.members` (its product picker, `:409-431`)
and `req.role` (`:454`). Slice 1A made both **resolved, not authored** — filled by
`parts.resolve.resolve_model_parts` from the part — and added a validator refusing them
beside a `part_id`. Against the shipped code:

```
slot part_id : 'rail-rail-3000'
slot role    : ''            ← editor renders this blank
slot members : []            ← editor renders "no product"
editor-shaped payload: REFUSED — "slot names part 'rail-rail-3000' and also
authors eligibility.members — the part is the one authority on what a piece is"
```

**Why 183/183 browser smoke did not catch it.** `tools/ui_smoke.py` exercises the model
TOOL — choosing a published model for a span — and never the Models tab's slot picker
save path. Task 9 of the 1A plan ran the smoke suite; nothing in it added a check for the
surface Task 6 had invalidated. §7 closes that hole, because a repair that leaves the
same blind spot is half a repair.

**Not in scope, and named so nothing reads as deferred-by-accident:** creating or editing
parts (arc B's editor, or its own arc), the Parts tab, the canvas drag-snap, the
eligibility-preview endpoint for an unsaved part, connections, item tolerance.

---

## 2. `eligibility_source` — one accessor, three answers

Four kinds of slot exist and the editor must render each differently:

| kind | authored as | in the demo |
|---|---|---|
| names a part | `part_id` | 9 of 13 slots |
| lists SKUs | `eligibility.members` | M-LEGACY rail, screw |
| carries a rule | `eligibility.predicate` | M-VINYL post, post.cap |
| nothing yet | — | mid-edit only |

Today "which kind is this?" is answerable only by checking three fields in order. That
inference would live in JavaScript, where no Python test can reach it, and the next
reader of the model would have to re-derive the rule.

```python
# fenceai/fencemodel/model.py, on PartRequirement
@property
def eligibility_source(self) -> Literal[
    "part", "authored_members", "authored_predicate", "unspecified"
]:
    if self.part_id: return "part"
    if self.eligibility.predicate is not None: return "authored_predicate"
    if self.eligibility.members: return "authored_members"
    return "unspecified"
```

**Derived, never stored** — the same shape `Part.dimensions` takes, and for the same
reason: a stored copy would be a second authority over facts the other fields already
encode (CLAUDE.md: read models are derived).

**There is a fifth kind it deliberately cannot report.** M-LEGACY's rail and screw have
their authored members REPLACED per run from `demand_skus`, so what a job actually buys
there comes from company knowledge rather than from the slot. That is a GENERATION-time
behaviour with no trace on the authored document, so the property reports those slots as
`authored_members` — which is what they are on paper — and the editor must not claim
otherwise. Saying "sourced from company rules" would be a guess dressed as a fact.

`"unspecified"` is the state the existing `part_id` validator refuses on publish, so it
appears only mid-edit.

---

## 3. The API: two routes, and one deliberately not built

**`GET /api/parts`** — the library the picker offers. Each part's `id`, `type`,
`name_i18n`, `status`, `version` and its `spec` rows. The spec is included because an
author choosing "38mm vinyl rail" should see WHY it is that, not only its name.

**`GET /api/part-types`** — and here the plan meets a fact. `PartType` is defined in
`parts/model.py` but **nothing instantiates it**: the 1A fix wave deleted
`demo_part_types()` as dead code, correctly, since nothing consumed it. There is no part
-type data anywhere, so a route over it would return an empty list.

So this route returns **the types actually in use**, derived from the part library, each
with a label resolved from `part_type.<key>` in the locale bundles and falling back to the
raw key. That keeps the picker grouped without inventing a library nobody writes to.

A real `PartType` library — stored, editable, with its own labels — belongs to the arc
where parts are CREATED and a type must be chosen for a new one. Deriving here is not a
shortcut around that; it is the honest amount of vocabulary this arc needs.

**No eligibility endpoint.** The original part-library spec proposed
`POST /api/parts/preview-eligibility`. It is not needed here: `PreviewPart.eligible_skus`
already carries the whole candidate set per slot, and `POST /api/fence-models/preview`
already accepts an unsaved document. The candidate list is **already arriving in the
browser and simply is not displayed**. A second way to compute it would be duplicate
machinery. The endpoint becomes necessary only when an author edits a PART with no model
to preview through — a later arc.

**`validate_part` keeps returning English strings, with no `code + params`.** The
part-library spec §10 promised localized codes; the established rule beats the promise.
`validate_model`'s own docstring: *"these are authoring errors, not user-facing warnings,
so they carry no code+params"*, and its route returns a single `fence_model_invalid`.
Authoring errors (shown to the expert building models) and user-facing warnings (shown to
whoever reads a quote) are different populations, and `validate_part` belongs to the
first. This also retroactively justifies the 1A fix wave deleting four unreachable locale
keys — they were never going to be emitted.

---

## 4. The picker

Chosen from three mocked options; this is the middle one. The slot pane shows:

* **the part**, as a select grouped by type;
* **its spec as chips** — `width 38` · `vinyl` · `cut from stock` — so the author can see
  what they picked without leaving the slot;
* **"N products can fill this"**, collapsed, expanding to the eligible items with prices
  and the chosen one marked;
* **the part's identity** — its id and version, as text. NOT a link: there is no Parts
  tab in this arc, so a link would either go nowhere or need a surface this arc has said
  it is not building. An author who needs to know more can read the chips; editing the
  part is the arc that builds the editor.

The rejected alternatives, with the reason: a bare name (leaves the author picking a word
with no way to see what it means) and a permanently expanded card (spends the inspector's
vertical space on candidates even for the common case of exactly one, where there is
nothing to choose).

**The count and the candidate list cost no new request.** They are read from the preview
response the editor already fetches.

---

## 5. The three slots that name no part

They must read as deliberate, because they are. Same pane, different content, selected by
`eligibility_source`:

* **`authored_predicate`** (M-VINYL post/cap) — "chosen by a rule, not a part", with a
  plain sentence saying the rule matches the panel's own rail heights, and the candidate
  count as usual. The raw rule stays under Advanced.
* **`authored_members`** (M-LEGACY rail/screw) — "a listed product, not a part", naming
  it, and saying company rules may replace it per job.
* **`unspecified`** — "choose a part". Publishing is already refused by the existing
  validator.

No "convert to a part" affordance in this arc: converting means creating a part.

---

## 6. What changes in Advanced

| today | after |
|---|---|
| **Role** select | **Removed.** Filled from the part's type at resolution; offering it invites an author to set a field resolution silently overwrites — the defect the `part_id` validator exists to refuse. |
| Cut length rule, overlap, option axis, SKU-per-option | Unchanged **in this arc**. All are slot-local, and the first two are exactly what arc B proposes to delete by deriving length from connections — left alone here deliberately, so the repair does not entangle itself with a redesign. |
| The preference list — drag-to-reorder products, an auto-substitute checkbox each | **Shown only when `eligibility_source == "authored_members"`.** |

That last one is why §2 exists. The list is dead for a part-named slot: candidate order is
the part's spec sorted by SKU, and preference is `select_supply`'s planned-cost decision.
But it is live for M-LEGACY, and deleting it outright would make the compatibility model
uneditable — the one model that exists so older projects keep working.

**Edge states.** A part with no active version renders its name with a "not published"
marker, never an empty select — an empty select reads as "you never chose one". A slot
whose `part_id` names an id absent from the library renders the id and says so.

---

## 7. Testing, and the hole that let this ship

* **A Python test asserting the editor's payload shape validates.** The regression was a
  frontend/backend contract break; a JS-only test would not have caught it and did not.
* **A browser smoke check for the Models tab slot picker save path** — open a model,
  change the part on a slot, save, reload, assert it persisted. This is the specific hole
  §1 describes, and closing it is part of the repair.
* `eligibility_source` returning the right answer for all four shapes, over the real demo
  models rather than fixtures, so a change to demo data cannot silently make the test
  vacuous.
* The picker rendering each of the three non-part kinds without throwing.
* Locale parity for any new key, enforced by the existing bundle test.
* **The compatibility gate must not move.** This arc changes no resolution and no
  schema field that generation reads; if a golden scenario moves, something is wrong with
  the change, not with the scenario.
