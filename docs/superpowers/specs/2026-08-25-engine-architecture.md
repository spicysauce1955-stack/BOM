# Engine architecture — phases, layers and seams

```text
Status:   Design. Internal to this repo — nothing here crosses the boundary, and
          none of it needs the Knowledge team's agreement. The four items that
          DO are in fence-rag/docs/integration/boundary-delta-v0.4.md.
Driven by: docs/reviews/planning-self-audit-2026-08-24.md — two passes, thirteen
          defects, of which the six in the second pass were all in things we
          ADDED to the other team's proposal rather than accepted from it.
Siblings: 2026-08-23-bom-engine-design.md · 2026-08-23-frontend-design.md
```

## 0. One word used for two things, which is why this needed writing down

We have been saying **stage** for both of these, and they are neither the same nor
parallel — one sits inside the other:

| | **Phase** | **Layer** |
|---|---|---|
| Is | a step in the pipeline; a function that runs | a slice of *what is knowable yet* |
| Count | 5 | 8 |
| Asks | "what happens next?" | "what do we know by now?" |
| Example | `fulfill()` — work out how much to buy | `station.*` — posts have positions, panels do not exist yet |

**Seven of the eight layers live inside phase 1.** Phase 1 is one walk down the layers;
the other four phases each sit at one layer and do a different *kind* of work.

Layers stop you reading a fact before it exists. Phases stop one kind of decision leaking
into another — which is why a price can never influence where a post goes.

---

## 1. The five phases

| Phase | Question | Hands on |
|---|---|---|
| 1 · `generate()` | *Where does everything go?* | a fence as objects — `posts · spans · gates` |
| 2 · `derive_requirements()` | *What does that need?* | `[DemandLine]` — a shopping list with no brands |
| 3 · `resolve_supply()` | *Which product?* | `[ResolvedSupplyLine]` — one SKU each, and why |
| 4 · `fulfill()` | *How much do we buy?* | `Bom` — cut plans, offcuts, allocations, price |
| 5 · read models | *Show me.* | sheet · elevation · assembly · groups |

Phases 2–4 live in `fulfillment/pipeline.py::price_strategy`, once, because four call
sites had already drifted.

**Phase 1 never sees a price; phases 3–4 never see a rule.** That is what lets a plan
drawn in March be re-priced against today's catalogue without moving a post, and why only
a regeneration can change what the fence *is*.

---

## 2. The eight layers, and the rule that orders them

A bay's clear opening is measured **to the faces of its posts**. So a post chosen using
that opening would be choosing itself. The engine already guards this by hand, with a
closed set of facts a post's predicate may read and a comment explaining the DAG. The
layers generalise it.

| Layer | Settled by now | A rule here may ask |
|---|---|---|
| `site` | what kind of place this is | exposure, hurricane zone, jurisdiction, code edition, material |
| `param` | every published table has been evaluated | max span, footing depth, rails per bay |
| `run` | the drawing has been read | length, closed, slope |
| `station` | posts have positions | end / corner / line / gate / junction / transition |
| `bay` | spans exist between stations | this bay's width and height |
| `panel` | a variant is chosen and resolved | rail positions, clear width |
| `host` | the containing part is chosen | the cavity a reinforcement must fit |
| `item` | a candidate product is on the table | its width, stock length, price |

> **The rule.** A construct's layer is the **deepest namespace its condition reads**. A
> condition reading deeper than its own layer is a cycle — refused at authoring, not
> discovered at generation, where the same mistake is either a hang or an arbitrary
> answer that reads as measured.

**Five existing mechanisms become sugar over one `Condition`:** a parameter row's
`conditions`, a variant's `condition`, an axis's `available_when`, a containment's
`required_by`, and `for_post_roles` (which is just `station.role in […]`).

**And it settles a question that was previously argued rather than checked:** a coverage
anchor may point at `param.footing_depth` because `param` is shallower than `host`.
Mechanical, not rhetorical.

---

## 3. Why things are hard to change today

One rule explains every case:

> A vocabulary is **open** when a general mechanism reads it, and **closed** when
> `if kind == "…"` branches on it somewhere.

| Open — a row, no release | Closed — a branch, needs a release |
|---|---|
| knowledge rules · part types · parts | `Action` kinds (10, discriminated union) |
| panel models · catalog products | joint kinds · placements · decision node kinds |
| overrides · warning codes | the layer list (hardcoded namespaces) |
| condition dimensions · source classes | |
| **objective presets** ✓ | |
| **fixing bases** ✓ | |
| **length rules** ✓ | |
| **the pricing phase chain** ✓ | |

> ✓ **Moved 2026-08-25** (build order items 3 and 4). The first three were a
> `Literal` naming the
> members plus a branch that knew what each meant; each is a `Registry` of named
> functions over one signature now (`core/registry.py`,
> `fencemodel/bases.py`, `fencemodel/lengths.py`, `fulfillment/presets.py`), and
> the `Literal` became a `str` validated against the registry — so a typo still
> fails at the boundary, with a message naming the alternatives, which the
> `Literal` never did as well.
>
> **The editor is now the closed half**, and that is visible rather than hidden:
> `js/panel-model.js` still carries hardcoded arrays, and
> `test_the_editor_and_the_backend_agree_on_the_vocabularies` asserts equality
> both ways — so registering `per_corner` makes it authorable through the API and
> turns that test red until the editor names it too. Closing it means serving
> `FIXING_BASES.names()` from a route the editor reads, and it is not done.
>
> **The pricing chain** (item 4) is not a registry and deliberately so: the ORDER
> is the design, so it lives in one declared tuple a reader can see whole
> (`fulfillment/phases.py`) rather than a name→function map assembled by import
> order. Each phase declares what it reads and writes, and `check_order` refuses a
> step placed before its input exists — so `credit_kits` inserted above
> `resolve_supply` fails at import instead of quietly crediting the empty list it
> was initialised with. `price_strategy(phases=…)` takes the chain as an argument,
> so a caller can run a different one without a mutable global.

Nothing about the *concepts* makes a fixing basis harder to extend than a part type. One
is data; the other is a branch.

---

## 4. Four seams

| Seam | Instead of | You would | Buys |
|---|---|---|---|
| **Handler registries** | a `Literal` plus a branch, per vocabulary | register a named function with a fixed signature — `BASES["per_corner"] = fn` | a new basis, length rule, preset or anchor kind is a plug-in |
| **A declared phase list** | `derive → resolve → fulfil` hardcoded | declare an ordered list of named steps, each with its input and output type | inserting *credit kits against assemblies* or *certify combinations* is a row |
| **A layer registry** | namespaces known only by being written into a context dict | an ordered list, each layer naming what populates it | a new layer — `zone.*` for a run crossing jurisdictions — without touching the evaluator |
| **A view registry** | each read model called explicitly by the API | a name plus a pure function over the stored run | a new document type ships without the pipeline knowing |

### The escalation test

> **Can the new thing be written as a function with the EXISTING signature?**
>
> **Yes** → register it. Configuration. No release.
> *(a `per_corner` fixing basis: `(panel) -> count`, the same shape as every other)*
>
> **No** → it needs a new shape, so it is a release — **and until that release it is
> published as a `Gap`.**
> *(a basis that must see the neighbouring bay: `(panel, neighbour) -> count`, because a
> panel does not know its neighbours)*

This is the test we already apply to the other team's extensions. The only change is
admitting our own vocabularies deserve the same question.

**Sequencing.** A registry introduced over three fixing bases is a three-call-site
refactor; the same registry over fifteen is a migration. None of this is urgent today and
all of it gets more expensive with every rule the Knowledge Platform publishes.

---

## 5. `Gap` as a return type — the one change that pays for itself twice

Two defects violate our own binding never-block obligation **today**:

- `strategy/generator.py:1521` — no `max_span_mm` rule applies → `GenerationFailure`. An
  uncovered exposure category produces **no plan at all**.
- `knowledge/evaluator.py:107` — two contenders tie, disagree, and both sit at authority
  ≤ `HARD_AUTHORITY_MAX = 3` → raise. Our expansion puts published rows at authority 1
  (structural) or 3 (everything else), so **both branches are inside the raise band**, and
  the exposure *scales with adoption*.

```python
resolve(…)      -> Value | Gap
resolve_panel() -> ResolvedPanel      # slots may carry Gaps
generate()      -> Plan               # never fails over a GAP
```

`KnowledgeVersion` gains `origin: authored | published`. A disagreeing tie between two
rules **we** wrote stays a build error; between two **published** rows it becomes a
`Conflict`, a warned line and a review task.

> **Corrected while building this, 2026-08-25.** The line above first read
> `generate() -> Plan  # ALWAYS. never raises.` That is not what the contract
> binds and not what was built: §3.2.4 forbids failing a run over a **gap**, and
> ten refusal sites survive the audit deliberately — a violated `hard_constraint`
> and input that cannot be carried out are neither of them gaps. Overstating the
> promise here is how the third conversion nearly became a fourth and a fifth.
> `docs/reviews/generation-failure-audit-2026-08-25.md` has the verdict on each.

**Two of the four disagreement channels already behave correctly** — `unresolved` demand
lines and `StrategyWarning` — and they are the model. A bill of materials that visibly
lacks something is more useful than no bill of materials.

This is also boundary-delta item 1, so building it delivers the Knowledge team's approval
item and closes both violations.

---

## 6. What was retracted, and why it is worth recording

**`Element` as a universal entity is withdrawn.** Reading the pipeline rather than the
boundary documents:

| Claimed it would fix | Reading the code |
|---|---|
| posts counted twice by two bays | not a real problem — `Post` has an id and demand loops over `strategy.posts` once |
| no traceability from BOM back to physical things | already exists: `pegs` threads element ids through demand, supply, BOM lines and allocations |
| bay-scoped versus panel-scoped needs unifying | already solved — posts hang off the model, spans carry panels, they never collide |
| a jig rail placed twice, bought once | real, but it needs a step-target kind, not an entity |
| **a member spanning two bays** | **real, and the only one needing structure** |

**The actual gap, stated precisely:** posts, spans and gates have ids; panel members do
not. A rail is `span.panel.slots["bottom_rail"]` — its identity derives from the span it
sits in, so it cannot span two. The proportionate fix is to promote the members that need
it, which is what `Member.continuity` is for.

**Why this happened, since it was the third time.** `Element` was designed from the
boundary documents, and those never mention pegs — because pegs never cross the boundary.
Every entity proposed and later retracted was invented while looking at the wrong artefact.

---

## 7. Build order

| # | Work | Blocked by |
|---|---|---|
| 1 | **`Gap` as a return type** — audit all 13 `GenerationFailure` sites; `origin` on `KnowledgeVersion` | nothing |
| 2 | `SiteConditions`, `site.*` binding, `site_revision` + the 409 guard | nothing |
| 3 | Handler registries for bases, length rules, presets | nothing |
| 4 | The declared phase list | 3 |
| 5 | `ParameterTable` loader — `value_type`, `domain_basis`, validity, `SetToken` | boundary v0.4 |
| 6 | The layer registry and stage derivation | 3, 5 |
| 7 | Source policy — a first implementation (currently zero lines) | 5 |
| 8 | Warning model, registry split, annexe rendering | 5 |
| 9 | `Member.continuity` and continuous-member promotion | boundary v0.4 |
| 10 | Containment → demand, with the kit-credit rule | 5 |

**Steps 1–4 need nothing from anybody.** Step 1 is first because it is the only item that
is simultaneously a live defect, a binding-obligation violation, a prerequisite for the
seams, and an approval item on the other team's desk.

**One honest note on ratio.** The design has now been audited three times and is in good
shape; what it has not had is a line of engine code. The risk has moved from designing it
wrong to not building it.
