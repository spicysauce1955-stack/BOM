# Planning & BOM Engine — design

```text
Status:   Design, third pass. Revised against the Knowledge team's audit
          (measured against their store), then against their review of that
          revision, then against THIS ENGINE — which found seven more defects,
          two of them in code this document had already published to them.
          See docs/reviews/planning-self-audit-2026-08-24.md.
Owner:    this repo (src/fenceai/)
Contract: docs/integration/ in fence-rag carries the boundary in full.
          audit-response-v0.1.md is their answer; audit-disposition-v0.1.md is
          our decision on all twenty-nine items it raised.
Siblings: 2026-08-23-frontend-design.md · fence-rag owns the Knowledge Platform.
```

## 0. The finding that shaped this document

Most of what the first draft proposed to build already exists. `fencemodel/`
carries panel specs, infill fitting with justification and excess policies, a
six-way fixing basis and placement rules. `parts/` carries part types, spec
fields with agreement operators, and predicate compilation. `learning/impact.py`
already regenerates every project under a hypothetical knowledge base and diffs
the result. A `GenerationRun` already pins five inputs and derived views already
refuse to render against any of them having moved.

So this is a small amount of new work threaded through a system that does the
hard parts. The sections below say what is genuinely new and what merely gains a
field.

**And the second finding, from the revision that followed.** The Knowledge team
answered this design's ten questions by *counting their corpus* rather than by
reading the types, and the corpus is stranger than either team assumed. Four
results changed the design rather than confirming it:

- **Only 19.9% of warnings sit on a step.** "A warning lives on its step" was an
  invariant we wrote with confidence, and it is false — 68% of the corpus's
  warnings are document-scoped. §5.
- **44–51% of installation steps are neither panel nor bay.** `scope: bay` was
  the right idea at half the size, and a 16 ft rail threaded through an
  intermediate post belongs to no bay at all. §5.
- **`Coverage`'s `Fraction` variant has zero instances**, while four real
  drawing-sheet cases fit none of the four kinds — including a stiffener *longer*
  than its host. Coverage is an anchored interval. §4.
- **The shipped source policy has no class for an installation manual**, which is
  44.6% of every fact in their store. That is not a vocabulary gap; it is a policy
  that would have shipped and been misdiagnosed as an extraction problem. §6 and
  the disposition's §3.2.

**And the third finding, which is the one to keep.** After two rounds of careful
document review the design was *internally consistent* and this engine could not
implement it. Auditing the agreed design against the code — the same method the
Knowledge team used against their corpus — produced seven more defects, including
three in the six-line expansion in §6 that we had published as reference. None was
visible from the documents, because the documents agree with each other.

A schema review answers whether a model is coherent. A census answers whether it
fits the data. Neither answers whether the code can run it, and **coherence is not
the test.**

---

## 1. Three tiers, and what this repo owns

| Tier | What | Owned here |
|---|---|---|
| **Shared vocabulary** | `PartType`, `SpecField`, `Quantity`, `SourceRef`, `Authorship`, `VersionRef` | schema yes, ships as a package |
| **Definitions** | `Part`, `FenceModel`, `PanelSpec`, `ParameterTable`, `Combination` | schema yes; instances authored here *or* by Knowledge |
| **Private** | `Product`, `Catalog`, `SkuLink`, `Project`, `Topology`, `GenerationRun`, decisions, BOM | entirely |

**Why the schemas that cross are owned here.** These types exist because this
engine computes with them — a `FrameSlot` carries an engagement because the cut
length needs one. The obligation that comes with it: a shared type cannot change
unilaterally, because Knowledge will have authored instances against it.

**Products and catalog stay here.** What a company can buy at what price is
commercial and per-tenant, not knowledge. `catalog_hash` already pins it per run.

---

## 2. Site conditions — the prerequisite

Nothing conditional works until a project can say what kind of site it is.
`exposure_category` is not expressible at any layer today, so every
`ParameterTable` would arrive with nothing to match against.

### 2.1 Model

```python
# fenceai/project/model.py
class SiteConditions(BaseModel):
    exposure_category: Literal["B", "C", "D"] | None = None
    hvhz: bool | None = None
    frost_depth_mm: Mm | None = None
    jurisdiction: str | None = None      # audit N20
    code_edition: str | None = None      # audit N21
```

On `Project`, because these are whole-site facts. **Anything that varies along
the run belongs in the topology instead**, as an interval payload — the pattern
`ElevationSamplePayload`, `WallProfilePayload` and `PostTiltPayload` already
establish. Soil class is the likely first case and should go there, not here.

The last two come from the audit and are not decoration. `jurisdiction` is what
`to be used in Miami Dade County and other areas where allowed by the Authority
Having Jurisdiction` needs to bind against. `code_edition` is what keeps one
manufacturer's `ASCE 7-10` and `ASCE 7-16` wind tables from colliding on the same
domain point under `hit_policy = unique` and failing the publish check for the
wrong reason — the two editions define exposure categories differently, so
`exposure_category: "C"` is not the same condition under each.

**Not here: the standards regime.** `us_astm` versus `cn_gb` is not a site
condition — it is the frame the whole rule set is written in, and a condition
dimension would let a GB row and an ASTM row sit in one table and be *selected
between*. It rides on the snapshot instead, and §11 carries the guard.

### 2.2 Binding

Site conditions reach rules through the **evaluation context**, not `scope`.
Verified: `FieldRef.path` is a dotted lookup into a plain dict that already
carries `scope` and `run`, so adding a `site` namespace is additive — no AST
change, no evaluator change. And `evaluator.py` already treats a missing context
field as *not applicable*, which is exactly the hook §2.3 needs rather than an
error path to build.

### 2.3 When a dimension is unknown

Keyed on the table's `task`:

| Task class | Behaviour |
|---|---|
| Structural | **Conservative** — strictest row across the domain, and warn |
| Commercial | Leave unset, warn, continue |
| Descriptive | Leave unset, no warning |

Conservative selection is what makes "never block" safe rather than reckless.

### 2.4 The guard this opens, which must close in the same slice

`api/app.py` guards derived views on `project.topology.revision !=
run.topology_revision`, raising `409 topology_changed`, with the reason in the
code: *"Laying a stored strategy over an edited drawing invents stations for
posts nobody placed, and that document goes to site."*

Site conditions are not part of `topology`, so that guard would not fire. Change
a project from Exposure B to C, the span limit changes, posts move — and the
structure sheet renders the old layout without complaint. Same failure, a door
the guard does not watch.

So the slice also adds `site_revision: int` on `GenerationRun`, extends the same
409 with a parallel `site_conditions_changed`, and adds
`warning.site_conditions_changed` to both locale bundles.

**New warning codes:** `site_condition_missing`, `conservative_parameter_used`,
`site_conditions_changed`.

---

## 3. The semantic package

A role is a **stable public name for a class of part**, so Knowledge can attach a
claim to rails in general without naming `rail-3000`.

It is not new. `PartType` is the role registry — an entity rather than a string
*because "rails" needs a Hebrew label*, data rather than an enum *because a
company that stocks a new kind of thing adds a row, not a release*. And
`PartRequirement.role` already carries it into `demand/derive.py` and the
decision graph, filled from `Part.type` during resolution and never authored.

```text
fenceai/semantic/
    types.py   PartType (+namespace, +parent) · SpecField · Quantity
    refs.py    EntityRef · RoleRef · VersionRef · SourceRef · Authorship
```

Two new fields on `PartType`: a **namespace**, so two companies may each have a
"clip"; and a **parent**, so a new kind of part inherits behaviour instead of
needing code. An extension declaring its own behaviour is a load error.

**Structure is the model's; numbers can be knowledge's.** `Distributed.count_param`
already states it: *"`count_param` names a KNOWLEDGE param so a company rule can
still win the count (rail count is a number, not structure); `count` is the
model's contributed default."* A `ParameterTable` lands on exactly that seam.

---

## 4. Containment — parts inside parts

New, and the one genuinely new structural concept.

```python
class ContainedSlot(BaseModel):
    key: str
    relation: Literal["reinforces", "lines", "sleeves", "fills", "caps", "retains"]
    coverage: Span                     # see below — was Full | Fixed | Fraction | At
    for_post_roles: list[str] = []     # audit N9; empty = every role
    required_by: str | None = None     # a knowledge param, or always
    requirement: PartRequirement
    contains: list["ContainedSlot"] = []   # depth capped at load
```

`FrameSlot`, `Member` and `PostSlot` each gain `contains: list[ContainedSlot]`.

**Three corrections the audit forced, each measured rather than argued.**

`insulates` has **zero instances** in the corpus and is dropped. `fills` (concrete
poured inside a post, which the guides treat as interchangeable with an aluminium
insert), `caps` (`F- INTERNAL POST CAP`) and `retains` (lock rings, bullet clips)
each have material behind them and are added. The vocabulary stays closed and
registry-extensible: a new word is a row, not a release.

`for_post_roles` keys against the six roles `strategy/model.py` **already
defines** — `end · corner · line · gate · junction · transition`. Whether a post
is reinforced turns out to depend on its role in the run, not on the bay, and two
manufacturers disagree about the corner case: Freedom says inserts are `not needed
in corner posts`, Bufftech says `Corner posts should be reinforced with concrete
and rebar`. Keyed on role, that is an ordinary conflict with an ordinary
resolution. Unkeyed, it is unrepresentable — a `PanelSpec` does not know what kind
of post bounds it.

**The line that keeps it general:** the structure says a rail contains a channel;
the catalog says whether a company buys that as one SKU or two. A pre-reinforced
rail and a rail-plus-channel are the same fence and different purchases. Model
containment as a kit and the structure changes with procurement, taking the
assembly plan and the drawing with it.

**Coverage is an anchored interval, and four literal kinds could not carry it.**
The first draft offered `Full | Fixed | Fraction | At`. Measured against the
sealed drawing sheets, `Fraction` has **no instance anywhere** and is unauthorable
in principle where the host publishes no length — Chesterfield's own `2 X 6 DECO
RAIL` carries none. Meanwhile four real cases fit none of the four:

| From the drawings | Why no literal kind fits |
|---|---|
| `POST REINF. FULL LENGTH -1"` | host length *minus a constant* |
| `POST LENGHT-(DEPTH+7)` | anchored to grade **and** to footing depth — itself a conditional value |
| `PANEL STIFFENER 70 1/4"` inside `SIMTEK PANEL 70"` | the insert is **longer than its host**; `Fixed` would validate a part that does not fit |
| `…to at least 22" above grade` | a *minimum* extent from a datum outside the host |

```text
Span { from: Anchor, to: Anchor, at_least: bool }

Anchor = HostStart(delta_mm) | HostEnd(delta_mm)
       | Datum(grade | hole_base, delta_mm)
       | SiblingSlot(slot_path, delta_mm)
       | Param(key, delta_mm)
```

`Full()` is `Span{HostStart(0), HostEnd(0)}`; `Fixed(l)` is
`Span{HostStart(0), HostStart(l)}`; `At([offsets])` survives unchanged for
discrete inserts. The over-long stiffener lands as `HostEnd(+6)` and is *visibly*
an overhang instead of a silent pass.

`Param` is the one that earns the machinery. Resolving `POST LENGHT-(DEPTH+7)` at
authoring time means publishing one coverage per footing depth — the same
collapse-a-table-into-a-scalar error that made a single `max_span_mm = 1800`
simultaneously unsafe on three documented sites and uncompetitive on three others.

**Fitting is checked by the existing matcher.** A contained part must agree with a
fact about its *host*, which is the routed-post problem again — so the same
authored predicate with one more namespace. The routed post compares against
`panel.*`; a contained slot compares against `host.*`:

```text
item.width_mm <= host.cavity_width_mm
```

A rail with no cavity spec field has no eligible contents, so a panel cannot
claim a reinforcement the rail cannot hold.

**But `cavity_width_mm` is never published, and the predicate has to be written
against a derivation.** The audit searched 2,147 pages: the only `Inside
Dimensions` in the corpus belong to storage sheds. Every profile publishes an
outside dimension and a wall thickness — `5X5 POST` is `4.940` OD with a `0.170`
wall — and never a cavity. So the host's cavity is `OD − 2 × wall`, and that
derivation must be **visible** rather than folded into a field name, or a reader
cannot tell a measured cavity from a computed one. This is also the one place
`insertion_margin_mm` becomes load-bearing, which is the argument for keeping a
field no document ever states — provided its absence publishes as a `Gap` and
never defaults to `0`. A `0` silently asserts *no clearance required*, which no
manufacturer said.

**Escalation:** a new relation word is a registry row; a new `Anchor` kind is new
arithmetic and therefore a release. Same test as everywhere else.

**One action generalises.** `RequirePostReinforcement{context: "gate", sku}`
hard-codes one host, one context and a named SKU. It becomes
`RequireContained{host_slot, relation, context}`, letting the predicate choose the
product. The old action stays valid as the special case it is.

**Fulfilment gains one rule:** if the host's SKU is an assembly kit already
listing the contained part, credit the contained requirement against it rather
than buying it twice. `Allocation` already carries pegs for this accounting.

---

## 5. Assembly steps

`AssemblyStep` today is `key`, `kind`, `slots`, `text_i18n`, ordered by list
position — a **total** order. The knowledge side's curation schema models a
partial order (`cur_step_requires`), warnings bound to steps
(`cur_step_warnings`), and figure references. Publishing a procedure today would
flatten all three.

```python
class AssemblyStep(BaseModel):
    key: str
    kind: Literal["assembly", "installation",
                  "preparation", "part_modification", "maintenance"] = "assembly"
    scope: Literal["panel", "bay", "post", "run", "site"] = "panel"
    slots: list[SlotTarget] = []       # a union, not only PanelSpec paths
    requires: list[Edge] = []          # Edge{kind: after|not_before|before|
                                       #      exclusive_with, step: key}
    cites: list[str] = []              # SourceRef ids
    text_i18n: dict[str, str] = {}
    # warnings do NOT live here — see below
```

`requires` makes list order **presentation**, not semantics. It needs an edge
*kind* because the corpus states negative and maximum dependencies as well as
ordinary ones — `do not add concrete… until later`, `before concrete sets` — and a
bare `requires: [key]` flattens those exactly the way list position flattens
prerequisites. Eight cases of mere print order were found against seven asserted
dependencies, and two of the eight **deny their own order in writing**:
`Assembly may be continued by installing all bottom rails first, or one section at
a time`. The distinction is real and readable from documents.

**Five scopes, not two, and the count is why.** `scope: bay` was the right idea at
half the size. Transcribed bullet by bullet across five manufacturers' guides,
**44–51% of steps are neither panel nor bay** — string lines, utility locates,
gravel bases, 72-hour cures, a rail used as a reusable spacer and then installed.
And one case makes `bay` not merely insufficient but unsound: `Standard rails are
supplied in 16 foot lengths` … `slide rail through second post`. A 16 ft rail
spans two bays and is threaded *through* the intermediate post. There is no bay
that step belongs to.

The tempting reply — declare everything above the panel out of scope, since a
gravel-base step produces no BOM line — is **rejected**. The structure sheet is a
fitter-facing document, not only an input to a price, and `report/assembly.py`
already argues that a sheet omitting half its parts reads as a finished panel.
Landing it takes two phases, because that function takes `(model, resolved panel)`
and structurally cannot place a post: `panel | bay | post` first, then `run |
site`, with unrendered scopes reported as present rather than dropped.

**Warnings move off the step, because the invariant was false.** A census of all
81,794 elements found 1,038 warning instances resolving to 226 distinct warnings —
and **only 19.9% sit inside a step that does something.** About 68% are
document-scoped (the front safety box, "BEFORE YOU BEGIN", a freeze-thaw footnote
printed at the foot of fourteen pages), 9.4% product- or certification-scoped,
2.7% warranty-scoped. Enforced literally, "a warning lives on its step" publishes
one warning in five and misattributes the rest.

```python
class Warning(BaseModel):
    text_raw: str                      # verbatim, never normalised
    lang: str
    cites: str                         # SourceRef, required
    attaches_to: WarningTarget         # step|procedure|document|product|
                                       # model|warranty|maintenance + ref
    severity_lexeme: str | None        # the publisher's own word, unnormalised
    code: str | None = None            # optional overlay
    params: dict | None = None         # only alongside a code
```

`severity_lexeme` stays unnormalised because `CAUTION` and `WARNING` are terms of
art with different legal weight in North American product literature. `params`
stays optional because they pay off only when one warning recurs with *different*
values, which is true of **3 of the 226**.

**This splits our own warning registry, and changes a rule in CLAUDE.md.**
Platform codes — engine warnings, gap codes, the `SOURCE_*` set — stay closed and
still require entries in both locale bundles, enforced by
`tests/web/test_locale_bundles.py`. Warnings **quoted from a document** are
verbatim, `lang`-tagged and exempt: zero of the corpus's 81,794 elements are
Hebrew, and translating a manufacturer's liability sentence to satisfy a key-set
test would be manufacturing a claim. Note the old rule failed precisely where it
was needed — a `text` fallback is by definition the case with no code, so it can
never satisfy "every code in both bundles".

**Where each kind renders**, which is what makes `attaches_to` usable:

| `attaches_to.kind` | Rendered |
|---|---|
| `step` | on that step in the structure sheet |
| `procedure` | at the head of that procedure |
| `product`, `model` | on the BOM lines using it, once per line group |
| `document`, `warranty`, `maintenance` | in the plan's **annexe**, once, never on a line |

So the freeze-thaw footnote's 83 instances become one annexe entry, and refusing to
attribute it to step 10 costs nothing.

**The placement invariant holds, and `unplaced` is expected to be large.** Every
member — including contained ones — is placed by exactly one step or reported
`unplaced`. Bufftech Chesterfield leaves 3 of ~11 named members unplaced, with the
line-post stiffener and the gravel fill appearing only in a figure caption. That
is a true fact about the document and we want it. A curator inventing a placement
to turn the check green converts a visible gap into an invisible error. A model
with no steps still yields `None`, not an empty plan.

---

## 6. The knowledge client

```text
fenceai/kplatform/
    client.py   fetch_snapshot · get_snapshot · resolve_source_ref · report_gap
    cache.py    content-addressed local store
    adapt.py    Snapshot -> KnowledgeBase | PartLibrary | FenceModelLibrary
    default/    a bundled snapshot, checked in
```

**Offline is the default.** A bundled snapshot ships in the repo; the scenario
suite must never open a socket, and that should be asserted rather than assumed.

**The adapter is where migration safety lives.** It maps the wire snapshot onto
domain types that already exist, so `generate()` and the evaluator are untouched
while the *source* of knowledge changes.

**`ParameterTable` expands into rules at load** — no evaluator change:

```python
KnowledgeVersion(
    # ONE object per ROW. Sharing an id across rows and varying `version` by row
    # index made `_beats` decide a same-id tie by row POSITION — see the audit.
    object_id=f"KP-{table.parameter}-{table.scope.id}-r{row_index}",
    version=table.version,
    type="hard_constraint" if table.task.is_structural else "fact",
    origin="published",              # never raises on a tie — see §6.1
    # an unconditioned `stated` row is a FALLBACK, not a peer: one tier weaker, so
    # any conditioned row beats it and a tie lands outside the hard-failure band.
    authority=None if row.conditions else _fallback_authority(table.task),
    scope={"product": table.scope.id},
    condition=And(*[Cmp("==", FieldRef(f"site.{k}"), Lit(v))
                    for k, v in row.conditions.items()]),
    actions=[SetParam(
        param=table.parameter,
        value=round(row.value.amount_milli / 1000),   # round, NEVER //
        value_milli=row.value.amount_milli,           # exact, for count arithmetic
    )],
    derived_from=[r.source_ref_id for r in row.provenance],
)
```

The hit-policy check happened on the knowledge side, so precedence never sees a
tie from one table.

### 6.1 Three defects this expansion had, and the audit that found them

`docs/reviews/planning-self-audit-2026-08-24.md` audited this design against the
engine rather than against the documents. Three of its seven findings are in the six
lines above, and all three were invisible from the design:

- **`//` truncates, downward, and it costs a post.** `2463800 // 1000` is 2463, not
  2464 — and `layout.py:27` does `n = ceil(length / max_span)`, so one millimetre
  adds a whole post on a 9 855 mm run. `round()`, and `value_milli` carries the exact
  value for any arithmetic that multiplies.
- **Rows shared an `object_id` and differed by `version = row_index`.** `_beats`
  ends `if a.object_id == b.object_id and a.version != b.version: return a.version >
  b.version` — so an always-true fallback row would beat every conditioned row of its
  own table by sitting lower in it. Silent, and attributed to a real source.
- **Every row landed inside the raise band.** `resolve()` raises `GenerationFailure`
  when two contenders tie, disagree, and both sit at authority ≤ `HARD_AUTHORITY_MAX
  = 3`; `hard_constraint` is 1 and `fact` is 3. So *adoption* scaled a never-block
  violation. `origin: authored | published` separates a genuine build error in our own
  rules from a conflict between two published rows, which warns.

Ties *between* tables — a model's `PolicyContribution` against a manufacturer table
— now surface as `Conflict` plus a warned line rather than raising, provided at
least one side is `published`.

**A table declares its value type; rows conform.** Not every parameter a planner
needs is a number: `stepped_only`, `not_rackable` and `gates are not rackable` are
values with no numeric form in any document. Letting *any row* be a quantity or a
token would put an angle and `not_rackable` in one column and force every consumer
to branch on the type of every cell. So the declaration sits on the table —
`value_type: quantity(<UnitCode>) | token(<closed set>)` — and the publish check
enforces it. `not_rackable` then belongs to a `slope_method` table, and `max_rack`
stays a real angle conditioned on `slope_method = rackable`.

This is what lets one printed cell — `▼ Racks up to 10 degrees 3' and 4' high, 5
degrees 5' and 6' high` — become two rows of a height-conditioned table rather
than a scalar that is wrong on half the range.

**`UnitCode` gains four entries**: `deg_milli`, `mph_milli`, `pa_milli`,
`second_milli`. Racking is stated in six mutually unconvertible forms across the
corpus and none of them could cross a boundary whose units were `mm | mm2 | mm3 |
each | gram_milli | cent`; wind speed is the second-largest numeric fact type
there and is the *design basis* of every structural table. The integers-only rule
is untouched: 115 mph is `115000 mph_milli`, 10° is `10000 deg_milli`.

**We do not ask the platform to normalise units for us.** Converting `1 inch per
foot` to 4.76° is an `atan` performed on a value nobody stated, and the result
would carry a `SourceRef` to a page that does not contain it. `value_raw` says
what was printed; the integer says what we compute with; invariant 7 exists to
keep the two visibly distinct. `value_raw` is a **list** for the same reason —
this corpus contains a CSI masterspec that states both units itself and gets them
wrong (`Height: 66 inch (16766 mm)`), and a single lexeme field would have to
either discard the contradiction or become unparseable.

**A `declared` domain is not a `measured` one.** 73 pages hold tables whose grid
could not be reconstructed; on those, `uncovered` is a promise about a space the
platform *asserted*, not one it read off the page. `domain.basis: measured |
declared` carries the difference, and the engine renders an `uncovered` hit
differently under each — *we may not know this table's real extent* is a different
warning from *this table really does not cover that point*.

**Units convert once, in `adapt.py`.** Use the two tolerances in
`core/units.py` — `SNAP_TOLERANCE_MM = 25`, `NUMERIC_TOLERANCE_MM = 1` — and add
no epsilon of your own; the module says so explicitly. `value_raw` travels with
the converted number so the decision graph quotes `88"` while the arithmetic uses
2235.

---

## 7. SkuLink — the only new private entity

A predicate proposes; a governed record decides.

```python
class SkuLink(BaseModel):
    sku: str
    definition_ref: str            # a published Part
    definition_version: int
    primary: bool = False          # many allowed; exactly one resolves
    valid_from: str
    valid_until: str | None = None # expiry BLOCKS, it does not warn
    proposed_by: str = ""          # agent id + confidence
    confirmed_by: str = ""         # a person, always, for structural parts
    basis: str = ""                # SourceRef
```

Each field earns its place from a system that was burned without it: `primary`
gives deterministic resolution without forbidding alternates; validity dates stop
a discontinued SKU silently satisfying a definition; the version stops a link
surviving a revision it was never checked against.

`Eligibility.predicate` is already cleared on the way into a resolved slot,
*"so a later reader cannot re-evaluate it against a moved catalog"* — the link is
that same insight made permanent rather than per-run.

---

## 8. Requirements, and never blocking

Requirements are stated in roles. Three ways one goes unfulfilled, all producing
a plan rather than an error:

| Cause | Code |
|---|---|
| No product fulfils the role | `no_product_for_role` |
| The role has no counting rule | `role_not_countable` |
| A parameter table left this point uncovered | `uncovered_condition` |

**The invariant**: a missing definition, an uncovered condition or an
unsatisfiable requirement produces a named, warned line — never a failed run. It
is what lets two teams iterate without blocking each other. Assert it with a
deliberately incomplete snapshot in the scenario suite, and make sure the failure
path is a warning rather than a `GenerationFailure`.

---

## 9. Impact preview — the review mechanism

`learning/impact.py` already regenerates every project under a hypothetical
knowledge base and diffs strategy and BOM — its own docstring calls it *"the
single highest-value review feature"*.

Everywhere this design says *a person reviews something*, the strong version is
to run the impact preview rather than show a diff. Adopting a new snapshot,
approving a candidate, confirming a `SkuLink`, taking a revised definition — the
useful question is always *which of my jobs change, by how many posts and how
many cents against the quote the customer accepted*.

Three details already right and worth not breaking: `baseline_failed` separates
"the change broke it" from "already broken"; the case binds the project's own
model and policy so the delta is not two changes attributed to one; and
`vs_accepted_delta_cents` compares against the number the customer actually saw.

What it needs: `ImpactCase` gains a hypothetical *snapshot*, not only a
hypothetical `KnowledgeVersion`.

---

## 10. Provenance in the decision graph

```text
BOM line → decision node → rule (object_id@vN) → SourceRef → crop
```

`SourceRef` is **opaque to the engine** — a string it stores and hands to the
frontend, which resolves it through the discovery API. The engine never fetches
an image.

Worth adding while here: minimal-conflict explanation. *"Why can't the spans be
wider?"* should return the smallest set of rules responsible, not the whole
graph. It is a specified algorithm and the most-requested thing in every
comparable system.

---

## 11. What a run pins

Five exist. Two are added, following the same pattern.

| Pin | Covers | Status |
|---|---|---|
| `topology_revision` | the drawing | exists |
| `snapshot_hash` + `knowledge_snapshot` | the rules | exists |
| `model_snapshot` | the panel designs | exists |
| `part_snapshot` | the parts, with content hashes | exists |
| `catalog_hash` + `catalog_skus` | the catalog, narrowed to what it named | exists |
| `site_revision` | the site conditions | **new** |
| `sku_links` | which SKU satisfied which definition | **new** |

Definitions arriving from the platform need no new pin: they land as `Part` and
`FenceModel`, and `part_snapshot` / `model_snapshot` already freeze them with
content hashes — for a reason that generalises, since two libraries can call
something `rail-3000@v1` and mean different documents.

**Two guards ride on the pins rather than on new state.**

`regime` — `us_astm`, `cn_gb` — is declared metadata inside the hashed snapshot,
and a project declares its own. Generating against a mismatched snapshot is
refused with a typed 409 in the same family as `topology_changed` and
`site_conditions_changed`. A standards regime is not a condition to select
between; GB and ASTM do not merely disagree about a number, they disagree about
what the conditions mean.

**Lapsed authority warns, it does not block.** `Combination` and
`ParameterTable` rows carry `valid_from` / `valid_until` / `authority`, and a run
warns on any line whose backing authority has expired relative to the run date.
This is a field rather than an `as_of_date` condition dimension on purpose: a
condition would force every table to enumerate a time domain, and `uncovered`
would then report every unenumerated date as a coverage hole — drowning the exact
signal it exists to carry. Expiry is a property of the authority, not of the site,
and it belongs beside the authority.

It matters more than it sounds: 40.7% of promoted facts in the corpus already cite
a superseded document, and an opaque `SourceRef` carries **zero** admissibility
bits across a boundary a run may not call. That is why `contributing_sources`
(`source_class`, `version_status`, `issue_date`, `expiration_date`,
`superseded_by`) is pinned into the snapshot alongside the definition, and why
`SourceRef` gains exactly one non-opaque field — `belongs_to`, the content hash —
so a field's citation joins to it. Duplication into the snapshot is not a second
authority; it is a **pinned copy**, which is what the whole snapshot design is.

---

## 12. Build order

| # | Work | Proves | Blocked by |
|---|---|---|---|
| 1 | `SiteConditions`, context binding, conservative policy, the `site_revision` guard | One rule on exposure yields two span limits on two sites | nothing |
| 2 | `fenceai/semantic/` + `PartType` namespace and parent | Requirements state roles; scenarios unchanged | nothing |
| 3 | `ContainedSlot` + `host.*` predicates + the fulfilment credit rule | A steel channel in a rail, bought either way | 2 |
| 4 | `AssemblyStep` — requires-edges, cites, `panel\|bay\|post` scope, slot targets; `Warning` off the step with the annexe rendering; the platform/source registry split | A procedure imports without losing its partial order, and a document-scoped warning lands once in the annexe rather than on every line | 3 |
| 5 | Requirements in roles + never-block warnings | A deliberately incomplete snapshot still plans | 2 |
| 6 | `kplatform/` client, bundled snapshot, adapter | S01–S14 pass from a snapshot, no socket opened | 2 |
| 7 | `ParameterTable` expansion | `max_span_mm` becomes 2235 at Exposure C, from evidence | 1, 6 |
| 8 | `SkuLink` + resolution | A published part is satisfied by a company SKU | 6 |
| 9 | Impact preview over snapshots | "What would adopting this do to my jobs" | 6 |
| 10 | Provenance slot in explain, gap reporting, minimal conflict | A BOM line renders its source ref | 6 |
| 11 | `AssemblyStep` phase two — `run` and `site` scopes, which need the bay's elements as a second input to `report/assembly.py` | A string line, a utility locate and a 72-hour cure appear on the sheet | 4 |

Steps 1 and 2 cross no boundary and need no contract agreement.

**Two things deliberately not in this list.** Gates are **out of scope** — named,
not forgotten. `FenceModel` and `PanelSpec` model no gate, a gate filed as a
`FenceModel` is a defect rather than an approximation, and the platform publishes
one as a `Gap` with `kind = "unmodellable_entity"` so the data is not silently
lost. Handedness, swing direction, the fixed leaf and hinge-selection-by-leaf-
weight are the four things a `FenceModel`-with-an-option-axis workaround cannot
carry, and three of them are pool-barrier safety facts. And **stock length does not
yet constrain layout**: a part may now declare a manufactured `nominal_length_mm`
(the invariant only ever forbade a value on `agree = "supplies"`, which is about
*cut* length), but making a 94″ Columbia rail determine a 94″ bay is a change to
`fit.py` with real consequences, and it is a follow-on rather than part of this
round.

---

## 13. Open

- **Contract v0.1 is unreviewed by the Knowledge team.** Steps 1–5 are unaffected
  either way.
- **Reviewer throughput is unmeasured.** An afternoon with a stopwatch, before the
  frontend queue is built around an assumption.
- **Tenancy.** Single-company for now; the snapshot request carries a company id
  and the run records it. One column now instead of a migration later.
- **Coverage variants.** Four proposed. The knowledge team may need a fifth.
