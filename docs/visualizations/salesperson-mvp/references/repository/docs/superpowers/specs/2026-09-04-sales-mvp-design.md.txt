# The salesperson MVP

**Status:** ALL FOUR SLICES BUILT (2026-09-04). 2528 tests, browser smoke 342/342.

## Why this document exists

On 2026-09-03 a large amount of work landed correctly and was still the wrong
call. Backend tasks 1–9 and every frontend task of the choice-set feature were
implemented in two batches of concurrent agents with no working checkpoint
between them. Every test passed; the browser smoke passed 307/307. The user saw
the result for the first time at the end, and their verdict was *"we took a
bigger task then we could chew… tried implementing too much without checking in
between."*

The diagnostic tell was not in the code. It was that letting the user evaluate
their own product required writing them a **three-part guided tour with a lookup
table of which run lengths produce a question**. A system that needs a tour has
no path a person can walk and judge alone.

Nothing was deleted as a result. The conclusion was narrower: cut **one honest
path** through what exists, name who it is for, and declare everything off that
path *present but not claimed*.

## Who this is for

The product serves three people. They are **company roles**, not positions in
our pipeline:

| | Who | What they hold |
|---|---|---|
| 1 | **Salesperson** | Non-technical. Makes the sale; records the layout relative to the house, street and road — angles, heights, the model sold, what the fence sits on. |
| 2 | **Office person** | Receives the layout. Knows the inventory and the items; more technical; holds installation knowledge. |
| 3 | **Super user** | Knows the job best. Changes, alters, customises. The backbone of the company. |

**The MVP targets the salesperson only.**

`tools/persona_lab` already held a roster — `expert`, `knowledge-owner`,
`topology-author`, `fulfillment`, `approver`. Those name positions in our
pipeline, and the list contains **nobody non-technical**. That is the likeliest
reason the UI drifted into saying *"Height intent"*, *"Ground elevation point"*
and *"Topology & Strategy"* to a person whose job is selling fences. The two
rosters answer different questions and are deliberately not merged.

### How the salesperson actually works

Established by asking, not assumed:

- **Laptop, after the visit.** They sketch on paper at the property and enter it
  later. This is why the existing desktop canvas survives — no new UI is needed.
- **Measured with tape or laser.** Real dimensions the office can order from.
  Typed lengths already work (SketchUp-style: digits while drawing).
- **Rough price now, exact later.** They close at the house from experience.
  Because entry happens *after* the visit, the app's number is never what wins
  the deal — it is written confirmation, and what the office starts from. This
  lowers the stakes on pricing enough to put it last.

## The MVP, stated once

> **A sold job, captured completely enough that the office person never has to
> phone the salesperson.**

Not "draw a fence." The deliverable is a **handover**, and the success condition
is **completeness, not accuracy**.

## The one road

| Step | State |
|---|---|
| 1. New job — customer, address, who sold it, when | ✓ slice 1 |
| 2. Place the house and the street | ✓ slice 3 |
| 3. Draw the fence, typed measured lengths | ✓ already worked |
| 4. Per stretch: how tall, what it sits on, which model | ✓ modelled — words fixed in slice 2 |
| 5. Gates — where, how wide | ✓ already worked |
| 6. What the office still needs from you | ✓ slice 4 |
| 7. A ballpark, clearly marked an estimate | ✓ slice 4 |

## The slices

Each ends with the user opening the app and doing one named thing. **Nothing
starts until they have said it is right or wrong.** No concurrent agents inside a
slice — that is the mechanism that let the previous feature run away, and the
speed is not worth it.

### Slice 2 — plain language and one road (BUILT)

Subtraction first, because it is the fastest thing to see.

A `role` preference — `sales` / `office` / `all` — beside the unit toggle in the
header. `js/role.js` owns the hide-list; `style.css` obeys it via
`<html data-role>`; `t()` resolves `sales.<key>` ahead of `<key>` so the same
control gets a salesperson's *words* rather than a different control.

**Hidden from sales** — everything answering *how is this fence BUILT?*:
`#tool-pin`, `#override-list`, `#choices`, `#section-decisions`, `#inspector`,
`#gaps`, `#chk-overlay-label`, `#profile-exag`, and eight of the ten tabs.

`#gaps` deserves its place on that list: a gap is not about this job at all — it
reports what the knowledge behind *every* job cannot answer. To a salesperson it
reads as a fault in the sale they just made.

**Kept** — everything recording what was SOLD: what it sits on, heights, the
slope, gates, the model, the side view, warnings, and the drawing itself.

**Annotations stay, and they are the seam.** A salesperson may promise *"a post
clear of that window"*. That promise is part of the sale and must survive to the
office — but it is a **note**, not an override: an override is a technical
instruction that reaches generation, while a promise is a sentence a person has
to read and decide about. `Annotation.target_ref` already accepts `run:<id>`.

Three properties are held by tests rather than by care:

- `test_role_module.py::test_every_hidden_selector_exists` — a hide-list is the
  one kind of list that fails **silently**. Rename `#section-decisions` and sales
  mode simply starts showing a salesperson the decision graph, with every test
  green and the page looking fine. Every selector is resolved against the real
  page, including ids that modules create at runtime.
- `test_role_sync.py` — the list exists twice (CSS cannot read a JS array). The
  two copies must be **equal**, not overlapping.
- `test_locale_bundles.py::test_every_sales_override_is_a_string_the_STATIC_pass_can_reach`
  — `setRole` re-renders only the static `data-i18n` pass, which is sufficient
  exactly while every override targets a static attribute.

**Default is `all`**, i.e. today's app. Sales is the front door we are building
toward, but flipping the default would change what 307 browser-smoke checks are
looking at, in the same commit that introduces the mechanism. Flip it once the
sales path is the one we trust, as its own change.

### Slice 1 — a job is a job (BUILT)

Customer, address, salesperson, date. It sounds trivial and is not: it is what
makes every screen after it read as a real job instead of *"project 7"*, and it
is where the handover state lives. `Project` today is `id, name`.

### Slice 3 — the context layer (BUILT)

The house and the street as drawable references, and **the only genuinely new
domain concept in this MVP**. A salesperson does not think *"node at (0,0) to
node at (12000,0)"*; they think *"along the street side, about 12 m, then it
turns in toward the house."* Without it the office person cannot read the layout
as a place.

It must touch generation **nowhere** — a house changes no quantity. That
constraint is what keeps it cheap and keeps it from becoming topology.

### Slice 4 — the handover sheet (BUILT)

What is still missing (a checklist the office would otherwise phone about), and
the ballpark, marked an estimate with its exclusions stated on it.

## What this MVP does not claim

Choice sets, post placement, cut plans, the decision graph, the knowledge bench,
the fence-rag contract work — all of it stays, all of it still passes its tests,
and none of it is on the salesperson's road. It is the office person's and the
super user's, and their MVPs are not written yet.

**One known limit, named rather than discovered:** an `Annotation` attaches to a
run, not to a station. *"A post clear of that window"* can name the stretch but
not the spot. Acceptable for the MVP — the office person reads the sentence
either way — and the seam to fix it is `target_ref`.


---

## What the browser caught that 2528 unit tests could not

Recorded because it is the strongest argument for the checkpoint rhythm, and
because every one of these is a defect a person would have hit in the first
minute of using the thing.

| Slice | Defect | Why no unit test saw it |
|---|---|---|
| 2 | Hiding worked; the WORDS lagged one switch behind — switching back to the full app left a salesperson's vocabulary on an engineer's screen | `setRole` never re-ran the static i18n pass. Every unit test asserted the LIST, which was correct |
| 1 | Naming a job left the picker labelled by whatever it was called before | The picker is rebuilt only on project CREATE. Exactly the *"project 7"* surface the slice existed to fix |
| 3 | The house/street drag did nothing at all | An ORDERING bug: the landmark branch sat below the pan check, and a landmark is drawn on empty canvas **by definition** — the house goes where the fence is not — so panning swallowed every gesture |
| 4 | The panel told somebody who had just pressed ⚙ to press ⚙ | It read `doc.total_cents`; the route nests the `Bom`, and the outer object has no total. `undefined` is not finite, so it fell through to the "no run yet" sentence |
| 4 | The smoke chose a draft-only fence model and got a 422 | The listing keeps unpublished models visible on purpose, so they read as *not yet selectable* rather than vanishing |

Four of the five are silent: nothing throws, nothing looks broken, and the
feature is simply absent or wrong. That is the class of defect a green suite
cannot report, and the reason a slice ends with a person opening the app.

## Where the guards ended up

Three properties are now held by tests rather than by care, and each was earned:

- **`test_role_module.py::test_every_hidden_selector_exists`** — a hide-list is
  the one kind of list that fails silently. Every selector is resolved against
  the real page, including ids modules create at runtime.
- **`test_role_sync.py`** — the hide-list exists twice (CSS cannot read a JS
  array) and the copies must be EQUAL, not overlapping.
- **`test_locale_bundles.py`** — a sales override must reach the screen when the
  role changes, by one of exactly two routes; plus a test that the scan finds
  any role-aware module at all, so route 2 cannot silently become "anything
  goes". `handover.py` then arrived inside the `report/*.py` glob and the
  backend code scanner demanded the new family be declared, which is the guard
  working rather than a nuisance.

## What is still not claimed

Everything off the salesperson's road: choice sets, post placement, cut plans,
the decision graph, the knowledge bench, the fence-rag contract work. All of it
passes its tests; none of it is this persona's. **The office person's MVP and
the super user's are not written.**

Two known limits, named rather than discovered:

- An `Annotation` attaches to a run, not a station, so *"a post clear of that
  window"* names the stretch and not the spot. The seam is `target_ref`.
- `role` defaults to `all`. Sales is the front door we are building toward, and
  flipping the default is its own change with the smoke updated on purpose.
