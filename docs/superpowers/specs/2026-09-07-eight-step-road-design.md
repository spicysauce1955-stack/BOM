# The eight-step road

Supersedes the step model in `2026-09-06-salesperson-road-design.md`. That
document's arguments for the road — a map rather than a wizard, derived state,
one navigation per screen, the frontend as its home — all stand and are not
re-litigated here. What changes is the steps themselves, and one signature.

## Why this document exists

The six-step road shipped with nine checks and **three steps that own none of
them**. `road-model.js` says so itself, of Gates, Notes and Review:

> Those three steps can therefore currently only ever read `done` (or
> `empty`/`unknown`): a green tick on one is a claim that no code is mapped to
> it YET, not that anything about it was checked.

That is the completeness lie the road exists to prevent, sitting inside the
road. A salesperson draws a fence and half the map turns green.

It is also not fixable by adding checks, which is why this is a design and not
a defect. The six-step spec is right that *"no gap reports a missing gate,
because a fence with no gate is a fence with no gate"* — and the same holds for
a promise nobody made. Absence is legitimate, and no server-side check can
distinguish it from neglect.

## The problem in one sentence

A step cannot report anything unless something can check it, and three of six
steps concern things only a person can confirm.

## The design

### One responsibility per step, and the checks follow

The four tools of the old step 3 — ground, base, height, model — were one step
with four jobs. Splitting them puts each check in the step whose tools fix it:
`height_assumed` and `base_assumed` are side-view facts and today sit in a step
whose panel is the plan canvas.

| | Step | Its single responsibility | `requires` | `wants` | Skip |
|---|---|---|---|---|---|
| 1 | The job | Who bought it, where, who sold it, when | `customer_missing`, `address_missing` | `sold_by_missing`, `sold_on_missing` | no |
| 2 | The property | Everything on the plot that is not the fence — house or apartment, the road, trees, pool, walls | `no_property_context` | — | no |
| 3 | The layout | The fence in plan, drawn to measured lengths | `no_fence_drawn` (the **anchor**) | — | no |
| 4 | The side view | Ground, base and height along each stretch | `height_assumed`, `base_assumed` | — | no |
| 5 | Which fence | The model this fence is built to | `no_model_chosen` | — | no |
| 6 | Gates & openings | Where, and how wide | `gates_contradicted` † | — | **yes** |
| 7 | Notes & promises | What was promised during the sale | `promises_contradicted` † | — | **yes** |
| 8 | Review & handover | What the office still needs, and the ballpark | — | — | no |

All nine existing checks are placed and **none is invented**. The two codes
marked † are new, and they exist only to catch a stated fact that has stopped
being true — see "A stated fact can be wrong" below. So `HANDOVER_CODES` goes
from nine entries to eleven, and every one of the original nine keeps its step.

Step 2 is named *the property* and deliberately not *the site*:
`#site-conditions` already exists and means soil, wind exposure and HVHZ — the
prerequisites for conditional rules. Two unrelated things under one word is the
B03 defect in miniature. *Property* is also the word `Landmark`'s own docstring
uses: *"something on the property that is NOT the fence."*

Step 5 stands alone rather than folding into step 4. Which model a fence is
built to is a product decision; ground, base and height are measurements of a
place. They are edited by different tools and answered by different people.

### `requires` versus `wants`, and why not `blocking`

Required-ness is a property of **the step that reads the check**, not of the
check. `sold_by_missing` is required for a salesperson's handover and
irrelevant to an office person's road over the same gaps, so the weighting
belongs to the road.

It may **not** ride on `HandoverGap.blocking`, which already means something
narrower — `report/handover.py:54`:

> Whether the office literally cannot start. Narrow on purpose — it gates the
> estimate, and calling everything blocking would gate it always.

A fence can be priced without an address. Making `address_missing` blocking
would withhold the estimate for a reason that has nothing to do with pricing.

A missing `wants` code is carried in `step.gaps` and rendered, but never stops a
step reading `done`. A nice-to-have that is absent is by definition not
incompleteness, and inventing a seventh state for it would put a colour on the
map that means "fine, but".

### The state ladder

Six states, in this order, first match winning:

```text
handover == null           -> unknown    no answer has arrived yet
anchor code in gaps        -> empty      this job has not started
stated fact true, no gap   -> skipped    stated, not silent
required gap, blocking     -> blocked    the office cannot start
any required gap           -> missing    a question remains
otherwise                  -> done       nothing required is open
```

Two orderings are load-bearing.

**`empty` beats `skipped`.** Evidence outranks assertion everywhere else in this
system, and a job with nothing drawn has not started regardless of what it
claims to lack. A road reporting `skipped` on a blank project would be
answering a question nobody has reached.

**`unknown` is never folded into `done` or into `null`.** `null` already means
"no road for this role". This repo shipped the other bug once — audit B01, a
`cache = null` painting a clean bill of health — and `js/handover.js`'s
`readinessShown` exists so readiness is only ever established by a *successful*
check. Every step reads `unknown` until the handover arrives.

### A skip is a stated fact, never a step key

Today "no gates on this job" and "nobody got to the gates" are the same bytes.
That is precisely the defect `height_assumed` exists to prevent: a fence left on
the silent 1800 mm default is *"indistinguishable from one confirmed at 1.8 m"*.

The fact is stored, not the step:

```python
class Stated(BaseModel):
    """What the salesperson has stated this job does NOT have.

    Named facts, never step keys. A step key would put a screen's structure
    into the project record — and `road_skips: ["gates"]` could be
    contradicted by nothing, because the road engine is pure and cannot see a
    gate. `no_gates` is a claim about the fence, so `handover_gaps` can check
    it against the drawing without knowing that a road or a step exists.
    """

    no_gates: bool = False
    no_promises: bool = False
```

On `Project`, beside `job` and `context`, and **unrevisioned** for their reason:
a claim about what is absent changes no quantity, so it must not bump the
topology revision and 409 every derived view.

`StepDef.satisfiedBy` names which fact answers a step, and skippability is
derived from it rather than declared twice: **a step is skippable exactly when
it has a `satisfiedBy`.** That is not a coincidence of this table — it is the
rule. A step is skippable precisely when nothing about the job itself can check
it, and skipping is how the person supplies the answer the server cannot.

### A stated fact can be wrong

If `no_gates` is true and the topology carries a gate, the claim is false. That
is a real question the office would otherwise phone about, so it is a check:

```text
gates_contradicted      no_gates is set and the drawing has a gate
promises_contradicted   no_promises is set and an annotation exists
```

Both are **registry additions** to `HANDOVER_CODES`, and each needs a
`handover.<code>` entry in BOTH locale bundles — the prefix the existing nine
already use (`handover.address_missing`, `en.json:412`), enforced by
`tests/web/test_locale_bundles.py`. Both are `blocking: false`: a contradicted
claim is a question the office asks, not a reason to withhold an estimate.

Each code goes in its own step's `requires`, and that forces one amendment to
the ladder. Walk step 6 with `no_gates` set and a gate on the drawing: the fact
is true, so a bare `skipped` rung would match and the contradiction would never
be seen — `skipped` sits above `missing`, and the first match wins.

So the `skipped` rung reads **the fact is true AND no required gap is open**,
which is how it appears in the ladder above. A skip that has stopped being true
stops being a skip, decided in the rung itself rather than by a special case
beside it.

This check is only expressible because the fact is stored semantically. It is
the whole argument for `Stated` over `road_skips`.

### The engine stops knowing what a project is

`road(project, handover, role)` takes `project` for exactly one purpose:
`const drawn = (project?.topology?.runs || []).length > 0`. Replace it with a
named check on the road:

```js
RoadDef  { role, steps: [StepDef], anchor: code | null }
StepDef  { key, panel, requires: [code], wants: [code], satisfiedBy: fact | null }
Step     { key, panel, state, gaps, skippable, skipped }

road(roadDef, gaps, stated) -> [Step]
```

The engine becomes a pure function of three plain values — no project, no DOM,
no state, no imports — and `empty` is derived from `anchor` being present rather
than from a shape it had to know. A role whose "not started" means something
else supplies a different `anchor` and changes no engine code.

Two consequences worth naming:

- **`panelFor` becomes road-scoped.** `panelFor(roadDef, key)` rather than a
  search over one global `STEPS`, so two roads may each have a `review` step.
  The current signature cannot express that and would silently return the
  first match.
- **Roles become a registry.** `if (role !== "sales") return null` becomes a
  lookup in `ROADS`, and an unknown role still returns `null` — refusing a road
  it has no definition for, which the six-step spec argued for and this keeps.

### Files, and what each owns

| File | Responsibility | Knows about |
|---|---|---|
| `js/road-model.js` | The engine: `road()`, `panelFor()`, the ladder | nothing — no imports |
| `js/roads.js` | The road definitions, as data | check codes, panel names, fact names |
| `js/road.js` | Rendering, and `setTab` | the DOM, `state.js` |
| `project/model.py` | `Stated`, one typed field on `Project` | — |
| `report/handover.py` | the two contradiction checks | `Stated`, the topology |

The split mirrors `base-top.js` / `profile.js`, which is CLAUDE.md's stated rule
for new frontend logic: the maths lives in a module with no DOM so it stays
testable in node.

### Reports must not group by step

`report/` may read gaps. It may not read steps. The six-step spec's reasoning is
the reason and is unchanged:

> A backend read model would put a presentation decision behind an API and make
> the second role's road an API change.

A step is a grouping of one role's screen, not a fact about the fence. If the
step→check mapping existed in `report/` as well as in `js/roads.js`, the two
would drift — the two-implementations-of-one-rule failure this project has hit
repeatedly, most recently across four rounds of contract verification.

## Invariants, held by tests rather than by care

- **Every check code is owned by exactly one step, and every step's codes
  exist.** Total in both directions over `HANDOVER_CODES`: a code with no step
  vanishes from the road while the API still reports it, and a step naming a
  code that does not exist reads `done` forever. `tests/web/test_road_module.py`.
- **The engine imports nothing.** The test is textual: `road-model.js` has no
  `import` line. The moment it computes coverage arithmetic there are two
  answers to *is this job complete?*
- **`road()` is called with no project.** Asserted by signature, so a future
  edit that reaches for the topology fails the test rather than the review.
- **A skippable step owns no `requires` other than its own contradiction
  check.** Otherwise skipping would hide a real gap — the completeness lie
  returning through the new door.
- **Both locale bundles carry every new code.** `test_locale_bundles.py`, which
  already enforces identical key sets.
- **`Stated` is unrevisioned.** A test that setting a fact does not change
  `topology.revision`, so no derived view 409s because somebody said there are
  no gates.

## Seams left named

- **`ROADS` is a registry.** Adding the office person's road is one entry and
  touches no engine code. Its `anchor` will not be `no_fence_drawn`.
- **More skippable steps** cost one `Stated` field, one `satisfiedBy`, one
  contradiction check and two locale entries. No engine change.
- **New landmark kinds** — pool, wall, existing fence — are three lines each:
  `LANDMARK_KINDS`, a `STYLE` entry, two locale keys. Streetview or Earth imagery
  later changes nothing here, being only another way of drawing the same
  landmarks.
- **Step 2's growth is where the evidence package attaches**, replacing the
  six-step spec's note that it attaches to Notes: attachments are about the
  property as much as the promise.

## Not claimed

- **A tree is a point, and the model forbids it.** `Landmark._is_a_shape`
  requires two points, three if closed. House, road, wall and pool are fine. A
  tree is one location and a canopy radius; encoding it as a 2 mm line to get
  past the validator is exactly the kind of thing this repo writes specs to
  avoid. Needs its own decision.
- **House-versus-apartment is not a landmark.** It is a fact about the job, and
  the first thing in this MVP that changes what installation *means* rather than
  where the fence goes. Out of scope here.
- **Step 8 owns nothing and this design does not fix that.** Review is the road
  looking at itself; it may not deserve a state at all. Left as it is rather
  than given a check that would be about the road rather than about the job.
- **The office road.** There is no `office_gaps()` anywhere in `src/`; "office"
  appears in the backend only as the audience of the salesperson's list. This
  design makes a second road cheap to add and does not make it possible.
- **The office person's job list.** Discussed and deliberately not folded in: it
  is a list of many projects, not a road over one, and `GET /api/projects`
  already loads every project in full while returning three fields. Its own
  spec.
