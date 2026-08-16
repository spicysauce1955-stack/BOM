# Part specs, item matching, and the fence-system level — design

Date: 2026-08-16. Status: approved for implementation.

A part stops being a list of SKUs somebody typed and becomes a **specification**;
an item in the catalog becomes eligible for that part when its own specs **cover**
it. Posts and caps join the fence model as parts on the same footing as rails and
slats, so a product line can finally describe the thing that holds it up. The
driving case is a routed vinyl fence, where the rails seat into holes punched in
the post and the panel is not expressible at all today.

---

## 1. Why this, and what it is not

Two facts about the code as it stands.

**Eligibility is authored, never derived.** `EligibleItem` carries a `sku` a human
typed into a slot. There is no path from "this part needs a 38 mm rail in vinyl
that seats into a 5×5 routed post" to a set of candidates. The schema has a field
for it — `Eligibility.predicate: Expr | None` — and `validate_model` refuses any
model that sets one, with the reason stated at `fencemodel/model.py:489`: *"it is
never evaluated and never frozen into the run's snapshot, so it would neither add
nor remove a candidate."*

**Posts and caps are outside the model.** Post SKUs resolve from knowledge roles
`post_ground`/`post_masonry`; cap and concrete from `DEMAND_ROLE_DEFAULTS` →
`DefaultComponent`. This was deliberate — `strategy/generator.py:305` says
*"swapping the whole fence system (e.g. to a Barrette catalog) is a rule change."*
That position is **superseded here for posts and caps**, and the trade-off is
recorded in §5 rather than glossed: a company-wide post standard no longer beats a
model's choice.

A third fact is a live defect, and §9 treats it as one: `clear_width_mm` has never
been computed. `strategy/generator.py:1332` reads `clear_width_mm=width, # face
widths arrive in phase 2`, so the clear opening equals the centre-to-centre width.

**Not in scope, and refused by name rather than half-built:**

* **No pair table in the catalog.** Compatibility is not authored as "these fit
  those" rows. It is a token both items declare plus a predicate that checks the
  numbers (§4). An O(n²) relation is the opposite of the goal, which is fewer
  items to keep track of.
* **No constraint solving.** Every relation is mediated by the panel or by an
  already-chosen item, so the predicate context is always one item at a time
  (§3). There is no pair of choices to solve simultaneously and no resolution
  order to invent.
* **Concrete stays knowledge.** A footing depth is a soil and site fact, not a
  product-line fact. `DEMAND_ROLE_DEFAULTS` keeps the `concrete` role.
* **No new rule language.** The predicate is the owned `Expr` AST and
  `evaluate_expr` from `knowledge/ast.py`. ADR-0005 stands: no rule exists only in
  a prompt, and none exists in a second evaluator either.
* **`members` and `predicate` are not combined.** A slot carries one or the other.
  "Intersect the typed list with the matched list" has two defensible readings and
  neither is needed yet.

---

## 2. The flow

1. An **item** in inventory carries specs — dimensions, profile, material, finish,
   how it connects.
2. A **panel** is made of parts. Each part declares the specs it *requires*, not a
   product.
3. An item **may serve** a part when its specs cover that part's requirements.
4. One item serves many parts across many panels. This is the goal, not a problem
   — and it already holds: `RAIL-3000` and `SCREW-S10` each serve parts in
   `M-LEGACY`, `M-SLAT@v1` and `M-SLAT@v2` (`fencemodel/demo.py:43,99,198,227`),
   and `fulfill()` pools demand per SKU across the whole run before cut planning.
5. When several items cover a part, one is chosen. **This half already exists**:
   `resolve_supply` → `select_supply` picks with the cut plan and writes a decision
   node naming the runner-up and the gap.

Only step 3 is missing. Steps 1, 2, 4 and 5 are either present or a widening of
something present.

---

## 3. The matcher

One new pure module, `fenceai/fencemodel/match.py`:

```
match(spec: Eligibility, catalog: Catalog, facts: dict) -> list[EligibleItem]
```

It produces the **existing data shape**. `resolve_supply`, `select_supply`,
`fulfill`, the parts ledger, the material drawer and the decision graph are
untouched.

**Freezing is free.** A run already snapshots its members, which is what keeps
`catalog_hash` narrowing safe (`catalog/model.py:150` — narrowing is sound
*because eligibility is frozen into the run*) and what makes an accepted quote mean
something. Deriving members changes when the list is computed, not whether it is
recorded.

**Determinism.** Derived members are emitted sorted by SKU at `priority=1,
approval="auto"`. `resolve_supply` groups by the `(sku, priority, approval)`
signature of the usable members, so a stable order keeps grouping stable — and
grouping decides which product is chosen, because cut planning is not additive.
Preference between matched items is `select_supply`'s planned-cost decision, with
the node it already writes.

**The panel is the mediator, which is what removes the hard part.** A post's
routing must match *the panel's* rail positions; a cap must fit *the post*. Neither
relation is item-against-item, so the predicate evaluates against a context holding
one candidate and one already-known datum:

| part | context |
|---|---|
| ordinary slot | `{item, panel}` |
| post | `{item, panel}` — height-derived facts only (§6) |
| cap | `{item, post}` |

**The model carries the predicate; the resolved slot carries the members.** The
matcher clears `predicate` on the `ResolvedSlot` it produces, so nothing downstream
can re-evaluate it against a moved catalog.

**`validate_model` gets stronger, not weaker.** Today it refuses a slot with no
eligible product, because such a slot publishes cleanly and then reports
`no_eligible_item` on every bay of every job built to it (`model.py:711`). For a
predicate slot that check becomes *"no item in your catalog covers this spec"* —
the same guardrail, a better sentence, at the same moment: authoring time, when the
author can still say what belongs there.

**The `_UNSUPPORTED` entry for `Eligibility.predicate` is deleted in the same
commit that makes the matcher evaluate it**, per `model.py:295`: *"the resolver
change and the entry's removal are then the same commit."*

---

## 4. Data model changes

**`Product.attrs` widens** from `dict[str, str | int | bool]` to also allow
`list[int] | list[str]`. A routed post declares `routed_heights_mm: [150, 1650]`,
which no scalar can hold. This preserves the principle `catalog/demo.py` states
outright — the vocabulary is data, so a company that stocks something new adds a
product and a locale word, not a release. The change is additive:
`_colour_is_a_swatch` and the locale-derived material vocabulary are unaffected.

**The interface token is an ordinary attr** — `interface: "vinyl-routed-5x5"`, or a
list for an item belonging to several systems (the widening pays for itself twice).
No new schema. The token asserts *these belong to one connection system*; the
predicate then checks the numbers, so a token that lies becomes a real error rather
than a silent pass.

**`Eligibility` gets its two modes made explicit.** A slot carries either authored
`members` or a `predicate`; `validate_model` refuses both together.

---

## 5. Posts and caps on the model

```python
class PostSlot(BaseModel):
    key: str
    requirement: PartRequirement        # role="post"
    cap: PartRequirement | None = None  # role="cap"


class FenceModel(BaseModel):
    ...
    post: PostSlot | None = None        # None = no opinion; knowledge sources it
```

The cap **nests inside** the post rather than sitting beside it, because a cap
exists *because* a post does, and its predicate reads the post it caps.

`post=None` means **no opinion**, not "must come from knowledge". It is what
`M-LEGACY` carries, and it is what makes a boundary post between an opinionated
model and a legacy one resolvable (§7).

**What is given up, stated plainly.** Post selection stops being run-wide
knowledge for any model that declares a `PostSlot`, so a company-wide post standard
can no longer beat a model's choice for those lines. This is a deliberate reversal
of `generator.py:305`, taken with the trade-off understood.

Knowledge keeps exactly one way in, and it is the existing one: it still sources
posts and caps for `post=None` models. **A knowledge rule contributing constraints
that tighten a part spec is NOT built in this arc** — it is an obvious next step and
it is named here so nobody reads it as working. Nothing evaluates such a
contribution, and a spec that silently ignored one would be the precise defect the
`_UNSUPPORTED` table exists to refuse.

---

## 6. Resolution order and the cycle rule

The order becomes a DAG, and this is the arc's main structural cost:

1. bay height and vertical mode *(as today)*
2. rail positions — `placement_positions` over the horizontal frame slots, driven
   by height and `rails_per_span`
3. **post** per station: predicate over `{item, panel}` → matched set → intersect
   across the adjacent bays' models → chosen product
4. **cap** per post: predicate over `{item, post}`
5. `clear_width` per bay, now that face widths exist
6. full panel resolution — infill fit, `between_frame`, the rest

Today post SKUs are chosen at `generator.py:1047`, *before* bay heights are known
at `1320`; spans are appended at `1355`. Step 3 must move after the heights
resolve. `_check_post_lengths` (`generator.py:147,1824`) already establishes the
pattern of a later pass writing back onto posts — `embed_mm`, `exposed_mm`,
`top_z_mm` — so this is a reordering of an existing shape, not a new one. It is
still the riskiest edit in the arc and the compatibility gate should be run on it
before anything else lands.

**The cycle rule.** Clear width depends on the post; the post must therefore not
depend on clear width. A post predicate may read only *height-derived* panel facts:

```python
POST_PREDICATE_PANEL_FACTS = frozenset({
    "height_mm", "rail_positions_mm", "vertical", "model_id",
})
```

`rail_positions_mm` is defined once, here: the placement positions of the panel's
**horizontal frame slots**, in panel coordinates (y = 0 at the bottom of the
opening), sorted ascending, with a `Distributed` slot contributing every one of its
positions. It is `placement_positions`' answer and never a second derivation of it —
the same rule W2's review round landed on, applied to a new consumer.

`validate_model` refuses a post predicate naming anything outside this set and says
why. This is deliberately the same shape as `SERIES_SCOPED_PARAMS`
(`fencemodel/model.py:327`): a closed set of names, a refusal, and a stated reason
for the boundary.

**`PanelContext` gains `post_face_width_start_mm` and `post_face_width_end_mm`**, so
`clear_width_mm` becomes `centre − ½·face_start − ½·face_end`. The two ends are
separate because a corner post and a line post need not be the same product. A post
product declaring no `face_width_mm` contributes zero and the bay says so, exactly
as `runview.js` already treats a nominal post face.

---

## 7. Boundary posts

`generator.py:1289`: *"a segment is the smallest stretch that has one model."* So a
post at a `fence_model` interval boundary — or a node post shared by two runs — is
adjacent to bays built to two different models.

This is **not an arbitration**. Both models' post specs apply to the one post, and
the candidate set is the **intersection** of their matched sets. An item covering
both is the ordinary case and the whole point of matching by spec. An empty
intersection is a true fact about that fence and is reported as one.

* one side opinionated, the other `post=None` → the opinionated side's spec
* neither side opinionated → today's knowledge path, unchanged
* a post whose only neighbour is a gate → no model claims it → knowledge path
  (this is the post `_check_post_lengths` already walks past)

---

## 8. Failure modes

Each carries `code + params` with entries in **both** locale bundles; the English
`message` is fallback only.

| code | severity | params |
|---|---|---|
| `post_routing_mismatch` | **error** (`GenerationFailure`) | station, model refs, the panel's rail positions, the post's routed heights |
| `post_spec_conflict` | **error** (`GenerationFailure`) | station, both model refs |
| `no_item_covers_part_spec` | **error** for a post; **warning** for a cap and every ordinary slot | slot key, role, model ref |

**Why routing is an error rather than a filter-and-warn.** A routed post's holes are
punched at the factory, so a post whose routing disagrees with the panel's rail
positions is not a worse choice — it is a fence that cannot be assembled. The
requirement lives *in the post part's spec*, so non-matching posts never become
candidates in the first place; the error is raised when **nothing in the catalog**
satisfies it, which is early enough to be fair and specific enough to act on.

**Which of the two post errors fires.** They do not overlap, and the distinction is
the whole value of the diagnostic:

* `post_routing_mismatch` — items covered every other term of the post spec and
  **routing alone** excluded all of them. The params carry both position sets, so
  the sentence can say *"the panel wants rails at 150 and 1650; this line's posts
  are routed at 200 and 1700."*
* `no_item_covers_part_spec` — nothing covered the spec, and routing was not the
  sole discriminator. The generic case; it names the slot, role and model.

This mirrors the split the codebase already draws between `no_feasible_item`
("candidates were tried and none fits") and `no_eligible_item` ("nothing is a
candidate"). A single merged code would leave *"no post found"* a mystery, which is
the outcome this design exists to avoid.

**Why a missing post is an error and a missing cap is not.** Every other unsupplied
slot today produces a warning and an `unresolved` line — a panel visibly one part
short. A post is not a line item; without one there is no fence to be short of. A
cap is cosmetic and keeps the existing behaviour.

---

## 9. Compatibility — the gate moves, deliberately

`resolve.py:466` fits a vertical infill across `ctx.clear_width_mm`. Because that
value has always equalled the centre-to-centre width, **every M-SLAT panel is
today fitted across an opening that includes half a post at each end**. The slat
count and spacing are computed over roughly one post-face more room than the bay
has. `clear_between_posts` (`resolve.py:292`) is wrong for the same reason; no
shipped model uses it, which is why only the infill case bites.

So this arc did **not** promise what every previous arc promised.

* **`M-LEGACY` stays byte-identical.** No infill, rails on `centre_to_centre`,
  `post=None`. Its requirement lines and BOM are unchanged, and that half of the
  compatibility gate remains the guarantee it has always been.
* **Infill fixtures were expected to be regenerated deliberately**, with the reason
  recorded in the fixture commit: the previous numbers were fitted over an opening
  that does not exist. A regeneration that is not explained in the same commit is
  indistinguishable from a regression.

### What W1 actually found (2026-08-16)

**The gate did not move at all.** The prediction above was wrong, in the safe
direction, and the reason is worth keeping.

The `slat` fixture is a 1500 mm bay whose opening is now 1420 mm. Twelve 100 mm
slats fit either way — thirteen would need 1300 mm plus twelve gaps and never fitted
— so the purchased quantities are identical. What changed is where the slats *sit*:
`spread_to_fit` had been widening the eleven gaps to 27–28 mm to absorb a residual
that was really **80 mm of post**, and they now sit at their designed 20 mm. The
outer slats had been overlapping the posts.

Gaps are not a purchased quantity, so nothing reached a requirement line or a BOM
line. The change is fully capable of moving the gate — at 1700 mm the member count
does change, which is how the panel-preview tests caught it — the committed widths
simply do not sit near a boundary.

One assertion in `test_compatibility_gate.py` did fail, and it was over-specific
rather than wrong: it demanded the fixture's gaps *differ*, which required a
non-zero residual — a property of the chosen bay width, not of the feature.
`tests/fencemodel/test_fit.py` owns the spreading arithmetic with a case built to
have a remainder. Replaced with the assertion the fixture is actually there to
make: the fitted count is a number the golden file is watching.

---

## 10. Testing

* **A new golden scenario** for the driving case — a routed vinyl line: a post
  routed at the panel's rail heights, rails engaged into the routing, slats between
  the rails, through to a priced BOM. `docs/scenarios/golden-scenarios.md` and
  `tests/scenarios/` change in the same commit; they are the behavioural contract.
* **`validate_model` refusals**, one test each: `members` and `predicate` both set;
  a post predicate naming a width-derived fact; a routing declared with no depth.
* **Mutation checks** — a green suite is this project's recurring failure mode, so
  four named mutants must die: the matcher ignoring the predicate and returning the
  whole catalog; a boundary post taking the union instead of the intersection;
  `clear_width` reverting to the centre width; the cap predicate ignoring the post
  it caps.
* **Locale bundles** for the three new codes, both languages, enforced by the
  existing guard — which scans `api/app.py` and both `code="..."` spellings.
* **Determinism**: the same topology and catalog produce the same matched member
  list, in the same order, across runs — the property the run-id digest rests on.

---

## 11. Implementation shape

This is an arc, not a slice, and it decomposes into four waves that each land
tested. The order is chosen so the riskiest edit is provable before anything
depends on it.

**W1 — the clear opening becomes real.** `PanelContext` gains the two face widths;
`clear_width_mm` is computed; `clear_between_posts` starts meaning what it says.
Face widths come from the post product already chosen by knowledge, so this wave
needs no matcher and no model change. It carries the deliberate infill-fixture
regeneration of §9, alone, where it can be inspected on its own.

**W2 — the matcher.** `fencemodel/match.py`, the `attrs` widening, the two
eligibility modes, the strengthened `validate_model` check, and the deletion of the
`Eligibility.predicate` entry from `_UNSUPPORTED`. Ordinary slots only — no posts
yet. The compatibility gate must not move in this wave: every shipped model still
authors `members`.

**W2, remaining — and one fork found while starting it (2026-08-16).**

The matcher, the `attrs` widening, the two eligibility modes, the strengthened
`validate_model` check and the `_UNSUPPORTED` deletion all landed. Engine
behaviour versions landed. Two items remain, and the first has a decision in it
that must be taken deliberately rather than during the edit:

*The `DemandLine` / `ResolvedSupplyLine` split.* `derive_requirements` does not
emit uniformly unresolved lines. Posts, caps, concrete and gate kits arrive with
a SKU already chosen — by knowledge, not by supply resolution — carrying an
**empty** eligibility; only panel slots arrive with eligibility and a blank sku.
`resolve_supply` therefore has two paths, and a `DemandLine` with no `sku` field
cannot express the first.

* **A — one path.** An authored SKU becomes a one-member eligibility, exactly as
  `legacy_model()` already seeds itself from `demand_skus`. Cleanest, matches the
  audit's design, and lets `fulfillment` stop importing `fencemodel`. **Costs a
  compatibility-gate regeneration**: the fence is byte-for-byte the same, but
  every post, cap, concrete and gate-kit line's `eligibility` field changes from
  empty to a one-member list. The gate would then be unable to say "nothing
  moved" for the very change that most needs it to.
* **B — two paths, named honestly.** `DemandLine` carries `authored_sku: str |
  None` — "the product knowledge already chose" — distinct from "the product
  supply resolution chose". Never blank-and-meaningless, so the audit's real win
  still holds: a resolved line cannot lack a SKU and an unresolved one cannot
  reach `fulfill()`. Gate stays byte-identical.

A is better design; B is better migration. The choice turns on whether the gate's
"nothing moved" guarantee is worth more than one unified path, and that is a
judgement about this project's risk posture rather than about the types.

*Typed catalog capabilities* has its own hazard, recorded here before it is
started: `catalog_hash` is computed over `Product.model_dump()`, so ADDING a
field to `Product` changes every product's hash and 409s every stored run. It
needs either a hash that ignores new fields or a stated, deliberate migration.

**W3 — posts and caps on the model.** `PostSlot`, the generator reordering of §6,
the cycle rule and its refusal, boundary-post intersection, and the three error
codes with both locale bundles. The riskiest wave; the gate is the check.

**W4 — the driving case.** A routed vinyl model in the demo library, the routing
predicate, the golden scenario, and the mutation battery of §10.

A wave that cannot hold its own acceptance gate is not done, and W1's gate is the
regenerated fixtures with their reason — not an unexplained diff.
