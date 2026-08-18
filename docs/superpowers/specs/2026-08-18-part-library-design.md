# The part library — design

Date: 2026-08-18. Status: design, awaiting review. Slice 1 of two.

A part stops being an anonymous block inside one panel slot and becomes a **named,
versioned, shared thing**: it declares what it is, an item may serve it when the two
agree field by field, and one edit to a part reaches every model that names it.
Items and parts are filed under the same **types**, so "which rails do we stock" and
"which rails does this panel need" are the same question asked from two sides.

Slice 2 — the Items tab, where an item's own specs are authored and the reverse view
("which parts is this item eligible for") is read — is named in §12 and is not built
here.

---

## 1. Why this, and what it is not

Three facts about the code as it stands.

**A part is anonymous and inline.** `PartRequirement` lives inside a `FrameSlot`, a
`Member`, a `FixingRule` or a `PostSlot` (`fencemodel/model.py:92`). Nothing names it,
nothing else can reach it, and a company with one rail standard re-authors that
standard in every slot of every model. `RAIL-3000` backs a rail slot in three shipped
models today (`fencemodel/demo.py:44,100,199`) as three separate acts of authoring.

**Type exists on one side only.** `PartRequirement.role` is a free string whose
vocabulary lives in a code comment — `post | cap | concrete | rail | screw | infill |
spacer`. `Product` carries no type at all: a rail and a screw are distinguishable only
by what a predicate happens to ask about them.

**Matching never happens at authoring time.** `match_eligibility` runs during
generation. In the editor, `panel-inspector.js:413` sees a predicate, prints "this slot
uses a predicate" and disables the picker — so the one question an author most wants
answered while writing a spec ("what would this actually match?") is answerable only by
generating a fence.

What is NOT missing, and is therefore reused rather than rebuilt: the matcher itself
(`fencemodel/match.py`), the freezing of members into a run, `resolve_supply` /
`select_supply` / `fulfill()`, the decision graph, and the `Expr` AST with its single
evaluator.

**Not in scope, and refused by name rather than half-built:**

* **No second rule language.** A part's spec compiles to the owned `Expr` AST and is
  evaluated by `evaluate_expr`. ADR-0005 stands.
* **No new resolution order.** Compilation happens strictly before the existing
  matcher, so the `height → rail positions → post → clear width → infill` DAG is
  untouched. This arc must not reorder `generator.py`.
* **No item-authoring surface.** Items keep arriving through `tools/load_catalog.py`
  and `catalog/demo.py`. Slice 2.
* **No pair table.** Compatibility stays a token both sides declare plus an agreement
  that checks it — the position `2026-08-16-part-specs-and-fence-system-design.md` §1
  took, unchanged.
* **No authored preference order on a part.** See §12.

---

## 2. The entity

A third citizen of the pattern knowledge objects and fence models already follow.

```python
class Part(BaseModel):
    id: str
    version: int
    status: Literal["draft", "active", "retired"] = "active"
    type: str                      # "rail" | "post" | "cap" | … — data, not an enum
    name_i18n: dict[str, str] = {}
    spec: list[SpecField] = []     # §3
```

**Storage** is a `parts (part_id, version, status, doc)` table mirroring
`fence_models`: content immutable, status the only mutation, the same
`_STATUS_TRANSITIONS` guard, the same audit rows, publishing an active version retires
its predecessor. Nothing is invented; this is `store/db.py`'s pattern applied a third
time.

**The type vocabulary is a small entity, not a Python enum**: `PartType {key,
label_i18n}`. It must be data because a company that stocks a new kind of thing adds a
row rather than shipping a release — the rule `catalog/demo.py` already states about
materials — and it must be an entity rather than a bare string because "rails" needs a
Hebrew label and a free string has nowhere to put one. The same `type` field is added
to `Product`, as `type: str = ""`. It must default, because every existing product has
none — and until slice 2 authors them, **no migrated part matches on it** (§7). An item
with no type simply fails any `type ==` agreement, by the ordinary missing-field rule.

> **Corrected by implementation (Task 8).** `type` did NOT become a typed field on
> `Product`. It lives in `Product.attrs["type"]` instead, because a new typed field
> changes `Product`'s shape, and `catalog/model.py` bumps `CATALOG_SCHEMA_VERSION`
> whenever that shape changes — which feeds `catalog_hash`, which every stored run's
> `/bom` and `/structure` read CHECK, not merely stamp. Adding the field as designed
> here would have refused every previously generated run at its next read, over a
> field nothing yet matches on. `attrs` is exactly where `catalog/model.py`'s own rule
> already sends data read by a predicate rather than by code, so this is not a
> departure from that rule — it is the rule, applied to `type` as it should have been
> proposed here in the first place.

### 2.1 A model names a part by id, unpinned

A slot stores `part_id`. Generation resolves `latest_active`. The run stamps what it
resolved (§6).

This is **forced by the shared-entity decision**: a slot storing `RAIL-38@v3` would mean
fixing a rail spec requires republishing every model that names it, which is the entire
reason the shared entity was chosen over a copied template. It is also the arrangement
a project already uses for its fence model — `Project.fence_model` is unpinned and
`GenerationRun.model_snapshot` records the version.

**What is given up, stated plainly.** `fencemodel/model.py`'s opening docstring says *"a
run stamps the model versions it resolved, so editing a model cannot change what an old
run meant."* That stays true — runs are stamped. What stops being true is that an
**active model version means one fixed thing forever**: publishing a part changes what
every model naming it builds next time. That is the requested behaviour and it is the
same bargain the model library already makes with unpinned projects. Two things keep it
honest:

* **Publishing a part runs an impact preview first.** `POST
  /api/fence-models/{id}/preview-impact` already does this job one level up; parts get
  the equivalent, so "this changes 3 models and 2 open quotes" is on screen before the
  button rather than after it.
* **Retiring or deleting a part a published model still names is refused**, at the
  moment `validate_model` already refuses a slot no product can fill: authoring time,
  when the author can still say what belongs there.

**What a Part deliberately does not carry:** quantity, length rule, placement, joint,
engagement. Those are facts about where a piece goes in one panel, not about the piece.
§5 draws the line.

---

## 3. The spec: declared fields, with agreement

```python
class SpecField(BaseModel):
    key: str                                          # "width_mm" | "material" | "interface" | "type" | "sku"
    value: int | str | bool | list[int] | list[str] | None = None   # what the PART declares
    agree: Literal["==", "!=", ">=", "<=", "supplies", "covers", "among", "between"] = "=="
    unit: Literal["mm"] | None = None                 # value is an int-mm measurement
```

**Both sides declare; only the part declares the agreement.** The item states what it
is; the part states what it is *and* how an item must relate to it. An item carries no
`agree` because an item has no requirement. That asymmetry is the correct one.

**Agreement is authored per part** — not derived from the field name (which would put
the matching vocabulary in Python, exactly what `match.py`'s docstring refuses) and not
declared by the type (which would make the type a schema and force a release for a
company with an unusual dimension). The cost is accepted knowingly: two rails may
disagree about what `width` means, and nothing stops them.

**Every field reads left to right as a sentence about the item.** One direction always,
because the alternative is an editor where half the rows are read forwards and half
backwards and the author has to remember which side they are standing on.

| authored on the part | means | compiles to |
|---|---|---|
| `width_mm 38 ==` | same width | `item.width_mm == 38` |
| `face_width_mm 90 >=` | item at least this wide | `item.face_width_mm >= 90` |
| `length_mm supplies` | can be supplied by the length | see §3.1 |
| `material "vinyl" ==` | same material | `item.material == "vinyl"` |
| `interface "vinyl-routed-5x5" covers` | item belongs to this system | `covers(item.interface, "vinyl-routed-5x5")` |
| `routed_at [150,1650] covers` | item is punched at both | `covers(item.routed_at, [150,1650])` |
| `sku ["RAIL-3000"] among` | the migrated SKU list | `In(item.sku, ["RAIL-3000"])` |

The whole list compiles to `And(items=[…])` in authored order. `match_eligibility` is
untouched, `evaluate_expr` remains the only evaluator, and because the result is a
conjunction of terms **`sole_excluding_term` keeps working** — which is what preserves
"your posts are punched 300 mm from where this bay wants its rails" instead of a bare
"no match".

### 3.1 `supplies` — the one consumption-aware agreement

`length_mm supplies` carries **no value**. It means *this item can be supplied by the
length* — it declares a stock length, as divisible bar stock or as a fixed piece:

```python
Cmp(cmp=">=", left=FieldRef(path="item.stock_length_mm"), right=Lit(value=0))
```

One term, not a disjunction over consumption kinds — because `stock_length_mm` is
already defined for both (§3.1 below). An item declaring neither a purchase length nor a
`capabilities.length_mm` has no such key, `lookup` raises `MissingField`, and `_covers`
reads that as "has not covered the requirement". So the comparison IS the null check,
using the mechanism the matcher already relies on rather than a second one. This is
exactly what `_can_supply_length` asks, promoted from a hardcoded validator into the
authored vocabulary.

**A part cannot declare its length**, and this is why `supplies` takes no number. The
same rail part serves a 2400 bay and an 1800 bay: length is the slot's `length_rule`
answering per bay, not a fact about the part. The number is also unavailable when
matching runs — `match_eligibility` evaluates against `{item, panel}` where panel facts
are height, centre width, clear width and vertical (`match.py::panel_facts`), while a
slot's cut length resolves later in `resolve_panel`. A length agreement carrying a
literal would be either unevaluable or evaluated against the wrong number. The actual
millimetres are checked where they already are: cut planning, with kerf and remnants, in
`fulfill()`.

**`supplies` requires one addition to `_item_ctx`: `stock_length_mm`** —
`purchase_length_mm` for divisible stock, `capabilities.length_mm` otherwise. That
number is reachable by no predicate today (`_item_ctx` merges attrs, capabilities, sku
and consumption *kind*, so a bar's length is invisible), while `_can_supply_length`
reaches into the consumption object for it. After this there is one definition of "how
long a piece can you get", and `_can_supply_length` becomes `stock_length_mm is not
None`.

**`supplies` does not belong on a post part.** A 2400 post backing a 2100 requirement is
not an eligibility question; `_check_post_lengths` owns it, after embedment resolves. A
`supplies` row on a post part would be harmless but misleading, and a *literal* length
agreement there would delete posts that work today. Said in the schema comment, not only
here.

### 3.2 `covers` and `among` — the two set agreements

`covers` reads *the item's declared set includes everything the part declares*, treating
a scalar as a one-element set. It subsumes "my token is among yours" and "your holes
include mine" without the author telling them apart.

`among` is its mirror and reads *the item's value is one of the ones the part lists*.
Both are needed and neither subsumes the other: `covers` asks about a set the ITEM
declares, `among` about a set the PART declares. Compiling one as the other with the
arguments swapped was the first draft of this section, and it was wrong — a two-SKU
`covers` list would have collapsed to equality against one of them.

It needs the AST's unused extension point and nothing else. `In.options` is a literal
`list[Any]`, not an `Expr` (`knowledge/ast.py:46`), so `In` can test "a computed value is
in a fixed list" but not "a fixed value is in a computed list" — which is what an item's
interface list needs. `FnCall` + `register_function` is the seam built for exactly this
(`ast.py:59,77`), `field_paths` already walks `FnCall` args (`ast.py:123`), and
`match.py` registers `covers`. No AST change, no second evaluator, no migration of
stored knowledge rules.

**Nothing registers a function today**, so this is that mechanism's first real user and
its first real test. Worth watching in review.

**`among` needs no new machinery at all.** `In` already holds an `Expr` item and a
literal `options` list (`knowledge/ast.py:46`), which is exactly its shape — a computed
item value tested against a fixed set. It is `covers` that needed the function seam,
precisely because it wants the other side computed.

### 3.3 Validation

`validate_part` refuses:

* a duplicate `key` — two authorities over one field;
* `supplies` on a field with no `unit: "mm"`, or carrying a value;
* a **set-valued** agreement (`among`, `between`) whose value is not a list, and a
  `between` whose list is not two ints. Stated over the set of set-valued
  agreements rather than over `between` alone, so a third one cannot be added
  without arriving here: `among` with a bare string compiles to
  `In(options=['w','h','i','t','e'])` and publishes clean while matching nothing;
* a **published** part whose spec no product in the catalog satisfies, in the voice
  `validate_model` already uses for a slot with no eligible product.

A **draft** may hold anything. That is the existing draft bargain, and it is what lets
an author write a spec before the item exists.

**Where it runs.** At the STORE, on the two calls that publish: `save_part` for any
non-draft status, and `set_part_status(..., "active")`. Not only at generation —
`validate_model` calls it too, but reaching it there means the author is handed a 422
on a job they were pricing rather than a refusal on the part they were writing, which
is the opposite of what "refusals a part earns at authoring time" promises. The store
answers `None` from `load_catalog()` by skipping the catalog-dependent refusal, the
same `library is None` bargain `validate_model` strikes.

**The two invariants that live beside it in the store**, because `Part.status`
defaults to `"active"` and `save_part` is therefore a second door into the state
`set_part_status` guards:

* **one active version per id.** `save_part` refuses inserting a second one — a save
  is not a publication, and retiring a predecessor is a lifecycle act with its own
  audit line. Publishing is `save_part(draft)` then `set_part_status(active)`.
* **retirement is refused only when it would leave the id with NO active version.**
  A model names the id, unpinned, and resolution takes `latest_active`; retiring one
  version while another stays active takes nothing from any slot. Asking the question
  of the VERSION left every abandoned draft of an in-use part stuck forever, `draft ->
  {active, retired}` being the only transitions it has.

`set_part_status` is a multi-statement write behind one `commit()`, so it carries the
same `try/except BaseException: rollback()` as `replace_active_version` and
`apply_review_outcome`.

---

## 4. Dimensions are derived, never stored

There is no `Dimension` class. A dimension is a view over `SpecField`:

```python
def is_dimension(f: SpecField) -> bool:
    return f.unit == "mm" and f.agree == "==" and isinstance(f.value, int)

@property
def dimensions(self) -> dict[str, Mm]:      # on Part
    return {f.key: f.value for f in self.spec if is_dimension(f)}
```

Three orthogonal fields doing three jobs, and a dimension is what falls out when they
line up:

* **`unit`** — the value is a measurement rather than a token.
* **`agree`** — whether the part's number and the item's number are *the same number*.
  Under `==` they are, so "the part's width" is well defined. Under `>=`, `between` or
  `covers` it is not: `face_width_mm 90 >=` is a floor on the item, and the part has no
  face width of its own.
* **`key`** — *which* measurement, and the only part code knows by name.

| field | dimension? | why |
|---|---|---|
| `width_mm 38 ==` | yes | mm, and both sides quote the same number — drawn and matched |
| `thickness_mm 20 ==` | yes | same; the elevation knows this key |
| `opening_width_mm 900 ==` | yes | a real property of a 900 gate part, just not one the elevation draws |
| `face_width_mm 90 >=` | no | a floor on the item |
| `length_mm supplies` | no | no value; the bay resolves the length |
| `material "vinyl" ==` | no | not a measurement |

Deriving rather than storing is the house rule, not a new idea: **read models are
derived, never stored** (CLAUDE.md; `fenceai/report/` is built on it). A stored
dimension beside the spec field producing it would be two authorities and eventually two
answers.

**The consequence, named rather than discovered: every drawn number is also a matched
constraint.** You cannot say "draw 38, accept 36–40" — a `between` field is not a
dimension and does not draw. If a real nominal-vs-tolerance case appears, that is an
explicit nominal field added then, with its reason. Not now.

**Code reaches a dimension through a typed door, not by rummaging.** `Part.width_mm` and
`Part.thickness_mm` are read-only properties over the spec. Those two keys are the ones
code knows by name, documented as such — the rule `Capabilities` already states: data
read by CODE is typed and named; data read by a predicate stays open. `face_width_mm` is
a typed capability for exactly this reason.

---

## 5. What the panel slot becomes

```python
class PartRequirement(BaseModel):
    part_id: str                        # resolved latest_active at generation
    qty: int = 1
    length_rule: LengthRule | None = None
    overlap_mm: Mm = 0
    option_axis: str | None = None
    sku_by_option: dict[str, str] = {}
```

> **Corrected by implementation (Task 8).** `part_id` is `str = ""`, not required —
> `""` means *this slot names no part*, and it is not an authoring convenience. Two
> demo slots cannot be expressed as a part under this spec's own vocabulary:
> `routed_vinyl_model`'s post and cap compare an ITEM fact to a BAY fact
> (`item.routed_at_mm == panel.rail_positions_mm`, `item.fits_face_mm ==
> post.face_width_mm`), and a `SpecField` (§3) only ever compiles to
> `item.<key> <agree> <literal>` — there is no field-reference right-hand side, so a
> part cannot state a fact about the panel it has not been placed in. And
> `legacy_model`'s rail and screw eligibility is rebuilt PER RUN from the run's
> resolved `demand_skus` (a knowledge `DefaultComponent` reaching the BOM,
> `generator._pick_model`) — naming a part there would overwrite that with a fixed
> SKU and silently outrank the rule that sources it. Both slots keep their authored
> `Eligibility` and `part_id=""`; `validate_model` refuses a slot that names no part
> AND declares no eligibility, so the empty default cannot be a silent way to author
> nothing. **The proper fix is a `SpecField` whose right-hand side may be a panel
> `FieldRef`** rather than only a literal, which would let a part state
> `item.routed_at_mm == panel.rail_positions_mm` the way the old predicate did. It is
> NOT built in this arc — the two slots above still name SKUs directly, which is the
> two-ways-to-fill-a-slot maintenance burden this design set out to remove, for
> exactly these two slots.

Gone from AUTHORING: `eligibility` (the part owns it) and `role` — not gone from the
system. `role` came back as a RESOLVED, not authored, field:
`PartRequirement.role: str = ""`, filled by `parts.resolve.resolve_model_parts` from
the resolved part's `type`. It could not simply disappear — `fencemodel/resolve.py`
reads `req.role` at three call sites (the frame-slot, member and fixing-rule resolvers)
to write `ResolvedSlot.role`, and `demand/derive.py` consumes that `role` downstream
when it derives a `RequirementLine`. Deleting the field outright breaks every one of
those reads; the part's `type` is still "the same fact, said once" — said once on the
`Part`, and copied onto the resolved slot at generation time rather than authored
twice.

**Naming a part and authoring what it is are exclusive, and refused on the AUTHORED
document.** `PartRequirement` itself rejects a `part_id` beside authored
`eligibility.members`, an authored `eligibility.predicate` or an authored `role`; and
`FrameSlot`/`Member` reject a `part_id` beside an authored `thickness_mm`/`width_mm`.
Without that, resolution overwrote the authored half without a word — a slot naming
`rail-rail-3000` beside an `EligibleItem(sku="RAIL-40", approval="suggest_only")`
resolved to `members=[]`, taking a human sign-off flag with it, and a part declaring
no thickness silently ZEROED an authored one (0 being what the elevation renders as
`declared=False`, not a neutral value). The refusal cannot live in `validate_model`,
which reads the document AFTER resolution has already wiped the evidence.

**`Eligibility` and `EligibleItem` themselves survive unchanged.** They stop being
something an author writes on a slot and remain what they always were downstream: the
shape `match_eligibility` returns and a `ResolvedSlot` freezes. That is the reason
`resolve_supply`, `select_supply`, `fulfill()`, the parts ledger, the material drawer and
the decision graph need no change — the authored source moves, the resolved shape does
not.

The line is **what the piece is** versus **where it goes**:

| leaves → the part | stays on the slot |
|---|---|
| `Member.width_mm`, `Member.thickness_mm` | `placement`, `orientation`, `justification` |
| `FrameSlot.thickness_mm` | `joint`, `channel_depth_mm`, `insertion_margin_mm` |
| | `base_ref` / `top_ref`, `base_engagement_mm`, `top_engagement_mm` |
| | `face_offset_mm`, `gap_after_mm`, `edge_margin_mm` |

A joint is a relationship between two members in a panel, not a property of a rail — the
same rail seats into a channel in one model and butts in another. Engagement likewise.
But a rail's width is the rail's, and keeping it on the slot is what let a model draw 38
while buying 45.

**`FrameSlot.thickness_mm` changes meaning.** Today `0` means undeclared and the
elevation flags it. After this it is read from the part's `thickness_mm` dimension, so
"undeclared" moves from the slot to the part — the flag stays, the source moves, and
`report/elevation.py`'s `declared=False` path is untouched.

**`sku_by_option` survives as-is, deliberately.** It is a per-slot narrowing keyed to an
option axis (colour, finish) that names SKUs directly. Making it "a part per option
value" would multiply the library by every colour a company sells, and `_chosen_option`
already resolves it.

---

## 6. Resolution, freezing, run identity

**When `part_id` resolves.** At generation, per segment, when the model's `PanelSpec` is
read — `latest_active`. The spec compiles to an `Expr`, and `match_spec` →
`match_eligibility` proceeds unchanged. Compilation is strictly upstream of the existing
matcher, so **this arc adds no new ordering**. That matters: reordering `generator.py`
was the riskiest edit of the previous arc and this one does not need it.

**Freezing comes free, again.** `match_eligibility` already returns members and clears
the predicate; `ResolvedSlot` already records them. A part is a new *source* for the
predicate, not a new lifetime — so `catalog_hash` narrowing stays sound for the reason
`catalog/model.py:150` gives, and an accepted quote still means what it meant.

**What the run stamps**, mirroring `ModelUse` field for field:

```python
class PartUse(BaseModel):
    part_id: str
    version: int
    content_hash: str = ""
```

`content_hash` exists because **a draft is mutable** — versions are immutable only once
active, so a run that drew on a draft needs the content, not just the number. Not a new
precaution; the one already taken one level up.

`part_snapshot: list[PartUse] = []` on `GenerationRun`, and **it belongs in the run id**,
on `model_snapshot`'s argument: two runs building the identical fence from different part
versions were not generated from the same thing. `[]` means a run generated before parts
existed — the same readable-old-runs convention as `catalog_skus = []` meaning "hashed
over the whole catalog" — and needs no validator, because it is the default.

> **Noted by implementation (Task 7).** `part_snapshot` joining the digest inputs meant
> `RUN_DIGEST_VERSION` (`strategy/generator.py`) bumped from `digest-v1` to `digest-v2`
> — a digest input that is genuinely new cannot join without changing the id it feeds,
> or the digest would be lying about what it covers. **Newly generated runs get new
> ids; stored runs keep the ids they were given and stay readable**, because nothing
> re-hashes a row already in the append-only runs table. The acceptance gate (§11) is
> byte-identical on the BOM, the decision graph and resolved geometry — the fence
> itself — and explicitly NOT on run id, by design; a run id differing from what an
> external system recorded before this branch, after a regeneration it asked for
> anyway, is the expected and accepted shape of this change.

**No new staleness gate.** The catalog has one because `/bom` and `/structure` genuinely
re-price against live products. Nothing recomputes against a part after generation, so a
moved part makes no stored run unreadable. `part_snapshot` is provenance and identity,
not a refusal.

**With one exception, and it is the one that bites.** `bay_preview_plan` reloads the
model document by its **stamped** version, explicitly never `latest_active` — because the
drawer once marked one product chosen while the run had bought another, and the comment
in `api/app.py` is that scar. An unpinned `part_id` inside a stamped document reopens the
identical bug by a new door: the preview would resolve today's part spec against a run
that resolved yesterday's. **The panel preview resolves parts from the run's
`part_snapshot`**, falling back to `latest_active` only when the snapshot is empty. It
gets a test that moves a part between generation and preview and pins the preview to the
old spec.

**Lifecycle refusals**, at authoring time where they are actionable: publishing a model
naming a part with no active version; retiring or deleting a part a published model still
names.

---

## 7. Migration

**Four models**: `legacy_model`, `slat_model`, `channel_slat_model`,
`routed_vinyl_model`, plus their published versions. Every slot in them names exactly one
SKU, so this is mechanical.

> **Corrected by implementation (Task 8).** "Every slot names exactly one SKU" is
> false. `M-SLAT@v2`'s top rail draws `RAIL-3000` at a declared 40 mm face
> (`thickness_mm == 40`) that `M-SLAT@v1`'s rail slot leaves undeclared, and a
> missing field is not the same fact as a 40 mm one (§7 below: "a missing field reads
> as 'does not cover'"). Collapsing both into one part would write 40 mm onto a slot
> that had declared nothing — a drawing change, not a document change. `RAIL-3000`
> therefore migrated as **two** parts, `rail-rail-3000` and `rail-rail-3000-40`, not
> one, and the dedupe below is real but not as total as this line claims.

**Each inline requirement becomes a part**, deduplicated across models on `(role, sku
list, width, thickness)`. That dedupe is the payoff landing on day one: `RAIL-3000` backs
a rail slot in three models today, and afterwards those are one part, edited once.

A migrated part's spec is only what was authored:

```
sku        ["RAIL-3000"] among
width_mm   38  ==                 ← only if the slot carried one
```

with `type: "rail"` on the Part entity itself, taken from the old `role`.

**A migrated part emits no `type ==` row**, and this is load-bearing rather than
fastidious. `Product.type` is empty on every existing product, so a `type ==` agreement
would match nothing and every migrated slot would resolve to no eligible item — the
compatibility gate would not merely move, it would collapse. The SKU list is already the
whole constraint, so a type row would add nothing even if the data supported it. Type
rows are for parts authored *after* this lands, on items that declare one.

`Product.type` is still backfilled from the roles that named each SKU, because the Parts
tab groups by type and an untyped catalog groups into one heap. It is **read by the UI
and matched by nothing** until an author writes a `type` agreement. A SKU named at two
different roles is reported and stops the migration, on the same argument as the width
conflict below.

**The width is the one non-mechanical step.** A missing field reads as "does not cover"
in `_covers` — deliberately, so a post whose face width nobody recorded does not quietly
satisfy a comparison. So moving `Member.width_mm = 100` onto the part as a matched `==`
field would newly exclude `SLAT-100` if that product declares no width, and the slot
would match nothing.

The fix is to take the assertion seriously rather than route around it: **the model was
already claiming that slat is 100 wide.** Migration writes that number onto the product,
where it belongs, and the part and item then agree because they quote the same fact.

Where two models draw the same SKU at different widths, **migration reports and stops
rather than picking**. That is not a migration failure but a real contradiction in
existing data surfaced for the first time. Checked: the demo catalog has none —
`SLAT-100` is drawn at 100 in both models that use it, `SLAT-V-150` at 150 in the vinyl
model.

**`approval: "suggest_only"` cannot be migrated silently.** Derived members are emitted
`auto`, and promoting a `suggest_only` member would let the system substitute a product a
human said needs sign-off. Migration **refuses** rather than converting. The demo has
none.

**Stored runs need nothing.** Members are frozen, `part_snapshot` defaults to `[]`, and
old runs re-read exactly as they do now.

**Nothing comes out of `_UNSUPPORTED`.** `Eligibility.predicate` was removed by the
matcher arc; the only surviving entry is `Eligibility.group`, which is unrelated and
stays.

---

## 8. API and editor

**Lifecycle routes mirror fence models**, because the lifecycle is the fence model's:
`GET /api/parts`, `GET /api/parts/{id}/{version}`, `POST /api/parts`, `PUT
/api/parts/{id}/draft`, `POST …/publish`, `POST …/status`, `DELETE`, and `POST
/api/parts/{id}/preview-impact`. Plus `GET /api/part-types`.

**The one new endpoint takes an unsaved part document:**

```
POST /api/parts/preview-eligibility   { part: {…}, panel?: {…} }
```

Unsaved because `/api/fence-models/preview` established why, and its docstring is the
argument: charging a keystroke to the database *"writes a library row per typed character,
an audit row per pause, and turns 'a draft may be saved invalid' into a licence to save
when the user did not ask."* It stores nothing and refuses nothing a draft may hold.

It returns two lists:

* **Eligible** — each matching product with a per-field breakdown: key, what the part
  declares, what the item declares, agreed or not.
* **Near misses** — products excluded by *exactly one* field, with the field named.
  `sole_excluding_term` already computes this shape, and it is the actionable half:
  "SLAT-90 would fit if width were ≥ 90 rather than = 100."

**In the Models editor**, `panel-inspector.js`'s product picker becomes a part picker
grouped by type. The draggable eligible-items list, the per-row approval checkbox and the
priority renumbering all go away, replaced by the part's name, its spec at a glance, and a
link into the part editor.

**A Parts tab** beside Models — the pattern Knowledge, Models and Inventory already
follow. Two ES modules, `parts.js` and `part-editor.js`, communicating only through
`state.js`, neither reaching into another's DOM subtree.

**The eligibility panel refreshes as you type, debounced.** It resolves nothing,
generates nothing and touches no run: generation stays behind its button.

---

## 9. The authoring flow

### Building a panel out of parts

Today an author draws a board 100 wide and *separately* picks a SKU — two acts, two
numbers, nothing stopping them disagreeing. After this, **picking the part sets the
drawing**. The inspector's "what is this" control is a row of part swatches filtered to
the slot's type, and choosing *Slat 100 vinyl* draws the board 100 wide because the part
says it is.

Beneath it, a line the author did not have to ask for: **"4 products can fill this."**
Clicking it expands the eligibility table in place. The question "will this be buildable"
is asked while looking at the panel, not while writing the spec.

**Dragging a board's width changes meaning, and this is the arc's one new interaction.**
Width used to be slot-local, so dragging changed a number; it now belongs to a shared
part, and dragging would silently edit every model using it. **Dragging snaps through the
parts that exist**: drag a 100 board wider and it snaps to the 150 part and redraws, the
parts of that type being the stops. A width no part has is not buildable, so it is not
draggable-to. Dragging past the last stop offers *"create a new part at 175 mm"*,
pre-filling the flow below.

The alternatives were silently editing a shared part, or a "this instance or all?" dialog
on every drag. Both are worse.

### Adding a new part

Two doors into one editor.

**From the Parts tab** — "New part", pick a type, name it, then rows of *field ·
agreement · value* with the eligible-items panel beside them updating as you type. The
candidate list narrows as constraints are added and the near-miss list says what was just
excluded: "SLAT-90 dropped out when width became exactly 100." "Duplicate" is
`duplicateOf()` one level down from where it already works for models — an independent
draft the moment it is made, with no special state to escape.

**From the canvas** — when nothing in the library fits, "create a part from this" opens
the same editor pre-filled with the slot's type and whatever width was dragged to. It
saves as a draft in the library, so a part invented for one panel is available to every
other one, which is the shared library's whole point.

### Editing an existing part

* A **draft** edits freely.
* An **active** part is immutable, so the first edit opens a new draft version — what
  already happens when a published model is edited.
* **Publishing runs the impact preview first**: "this changes 3 models and 2 open
  quotes." That screen is the honest cost of the shared-entity choice.

The canvas inspector carries an "edit part" link into the same editor, with **"used in 3
models"** visible before any change is made, so shared-ness is on screen at the moment it
matters rather than discovered at publish.

### A blank panel

A slot with no part draws a flagged nominal and the inspector says "choose a part" — the
`declared=False` treatment an undeclared thickness already gets. Every starter template
names parts, so the blank path stays the rare one it already is.

---

## 10. Failure modes

Each carries `code + params` with entries in **both** locale bundles; the English
`message` is fallback only, and `tests/web/test_locale_bundles.py` enforces the pair.

| code | severity | params | when |
|---|---|---|---|
| `part_spec_matches_nothing` | error | `part_id` | publishing a part no product satisfies |
| `part_has_no_active_version` | error | `part_id`, `model_id`, `slot` | publishing a model naming a draft-only part |
| `part_still_referenced` | error | `part_id`, `model_ids` | retiring or deleting a referenced part |
| `part_dimension_conflict` | error | `key`, `part_id` | a key declared twice |
| `part_length_not_suppliable` | warning | `part_id`, `sku` | a matched item declares no stock length |
| `part_migration_width_conflict` | error | `sku`, `widths`, `model_ids` | migration only; two models draw one SKU at two widths |
| `part_migration_approval_lost` | error | `sku`, `model_id`, `slot` | migration only; a `suggest_only` member |

Spec values are author-written text landing in the eligibility table's `innerHTML`, so
every one goes through `esc()`; SKUs and dimensions get `.sku` / `.num` / `<bdi>`
isolation so an RTL layout does not reorder a part number.

---

## 11. Testing and acceptance

**The acceptance test is the compatibility gate, byte-identical.** Migration moves where
a spec is written, not what it says, so every golden scenario S01–S14 must produce an
identical BOM, an identical decision graph and identical resolved geometry across the
whole change. Anything that moves is a migration bug, not a new behaviour — a far
stronger check than any test written for the new code.

> **Narrowed by implementation (Task 7).** "An identical run digest" is dropped from
> this list, deliberately. `part_snapshot` genuinely joined the run id's inputs
> (§6), so `RUN_DIGEST_VERSION` became `digest-v2` and a newly generated run's id
> changes. Excluding a real new input from the digest would let two runs built from
> different part versions collide on one id — the exact defect the snapshot exists to
> prevent — so the id was the one thing this arc could not hold constant without
> lying about what it covers. The gate is byte-identical on the fence itself — BOM,
> decision graph, resolved geometry — never on the run's address. A stored run keeps
> the id it was given and stays readable regardless.

Beyond the gate:

* **Compilation** — a table test over every `agree` value, pinning the emitted `Expr`.
  A new agreement operator without a row is a missing test, visibly.
* **`covers` as the first registered function** — that `field_paths` sees through it,
  that an unregistered name raises `MissingField` rather than passing.
* **`stock_length_mm`** — that `_can_supply_length` and the new context field agree for
  every consumption kind, so the two definitions cannot drift.
* **Dimension derivation** — that `agree != "=="` yields no dimension, and that the
  elevation draws `declared=False` for a part with no `thickness_mm`.
* **The preview trap** — move a part between generation and preview; the bay preview must
  show the run's spec, not today's.
* **Lifecycle refusals** — each row of §10 asserted with its params, and each code present
  in both bundles.
* **Mutation** — the previous arc found that every demo slot naming one product made the
  drawer's alternatives untested (`0 == 0`). A part with **several** eligible items is
  seeded in the demo data specifically so the eligibility table, the near-miss list and
  the drawer are rendered by something.
* **Browser smoke** — create a part, watch the eligible list narrow, assign it to a slot,
  drag a board and watch it snap to the next part, publish and see the impact screen.

---

## 12. Deferred, by name

Named here so nothing below reads as working.

* **The Items tab (slice 2).** Authoring an item's own specs, browsing items by type, and
  the reverse view "which parts is this item eligible for". Items keep arriving through the
  catalog loader until then. This is purely additive and blocks nothing here.
* **Authored preference order on a part.** Derived members are emitted sorted by SKU at
  `priority=1`, so "prefer A over B at equal cost" is not expressible. Preference becomes
  `select_supply`'s planned-cost decision with the node it already writes. Nothing is lost
  in the demo data — every slot names exactly one SKU — but a company may want this.
* **`approval: "suggest_only"` on a part.** Migration refuses one rather than dropping it
  (§7); expressing it on a part is a follow-up.
* **A nominal separate from the matched value.** "Draw 38, accept 36–40" (§4).
* **Knowledge contributing constraints that tighten a part spec.** Named as an obvious
  next step by the 2026-08-16 spec and still unbuilt; nothing evaluates such a
  contribution.
