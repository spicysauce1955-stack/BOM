# The office desk, without AI

**Status:** agreed 2026-10-12 · slice 1 (the change log) in build · slices 2–3 outlined
**Plane:** People & work (slice 1), Engine + People & work (slices 2–3)
**Supersedes nothing.** It builds on `2026-09-15-backoffice-design.md` (§8 "the backoffice
may edit the drawing", §9 "doing it by hand") and `2026-09-03-design-choices-and-placement-design.md`.

---

## Why this document exists

The new owner set the AI features aside and described the company as people only:

> The sales agent inputs only the layout of the yard, house, heights, incline. The
> backoffice places the poles, sections, can edit heights, assign products to parts.

The first thing to get right is that taking AI out does **not** take away the
automatic post layout. `generate()` places posts by written rules (the 1800 mm
manufacturer span in the demo rules, a reinforced post either side of a gate, a post
at every end and corner). The AI plane only interprets notes, proposes rules,
critiques and advises, and all four already run as offline stubs. So "humans only"
is a question about the **office desk**: how much of the fence a person shapes by
hand, and whether the system keeps track of it.

The owner answered four questions:

| # | Question | Decision |
|---|---|---|
| 1 | Does the office start from the engine's draft, or from an empty fence line? | **The office person chooses.** |
| 2 | Who picks the fence model? | **Sales picks it; the office may change it.** |
| 3 | At what level does the office choose products? | **A fence model has parts and an assembly; the office assigns products to those parts.** |
| 4 | When the office changes what sales entered, what happens? | **Log it** — no approval, no notification. |

## What each answer needs

| # | Exists today | New | Slice |
|---|---|---|---|
| 2 | Sales picks the model on step 5; the office road's *blanks* step carries the same tool | nothing but the log | 1 |
| 4 | `audit_log` writes `save_project · user:… · <id>` on every save | **a per-job log that says what changed, from what, to what** | 1 |
| 3 | The part drawer lists, per part, the products that fit, their price and stock — as a *what-if*; supply always picks the cheapest that fits | the office's pick, saved on the job, per part of the model | 2 |
| 1 | Generate drafts; a post can be dragged, pinned or removed; `lock_bay` exists in the engine with no control | a per-section *by hand* mode | 3 |

Slice 1 comes first because it is the smallest, because answer 2 is complete the
moment it lands, and because slices 2 and 3 are office acts the log has to record.

---

## Slice 1 — the change log

### The story

Levi job, Herzl 12. Dana sold 1800 mm on both stretches and sent the job. Yossi reads
her note — *level with the neighbour's fence, about 1750* — and changes Section B to
1750.

**Today** the record of that is one row in an installation-wide table:

```text
2026-10-12T10:42  user:u_yossi  save_project  proj_7f…
```

It does not say what changed, and the job is one row that each save overwrites, so
the 1800 is gone. The backoffice design (§8) calls the drawing *recoverable and
attributed*; in the code it is attributed and not recoverable.

**After this slice**, the job's history reads:

```text
Yossi · 12 Oct 10:42
    Section B: height 1800 → 1750 (0–6000 mm)
Yossi · 12 Oct 10:31
    Job moved from waiting to planning
Dana · 11 Oct 18:05
    Job moved from drafting to waiting            ← the handover
Dana · 11 Oct 17:58
    Section B: height 1800 added (0–6000 mm)
    …
```

### What it is, next to what is already here

A **change entry** is the difference between the job before one save and the job
after it, in words, with who and when. It is *derived* — computed from two
documents — and *stored*, because the "before" document is overwritten by the save
it describes and cannot be recomputed later.

| Construct | Relation to a change entry |
|---|---|
| `audit_log` | Installation-wide, one row per store write of anything, an action name and an id — for an operator. A change entry is per job and says what changed — for the people on the job. Every save still writes its audit row; the change entry is written beside it. |
| `topology.revision` | A counter of saves, for staleness checks (`plan_stale`, the 409s). The change entry ignores it: a revision bump with nothing else different is not a change anybody made. |
| undo / redo (`js/history.js`) | The browser's own per-gesture stack, lost on reload. An undo PUTs a new forward revision, so it appears in the log as a change back — which is what happened. |
| desk commands (`POST /actions`) | A command moves the job; its effect on `status`, `assignee` and `committed_run_id` is a change like any other, and shows as one. The handover *is* the `drafting → waiting` entry. |
| annotations (notes) | A note is content. Adding one is a change entry that quotes it; the note itself stays where it is. |

### One door: `Store.save_project`

Every write of a job goes through `Store.save_project(project, actor)` — 16 call sites,
one function. That function now loads the stored document, computes
`diff_project(before, after)`, writes the job, the audit row and — when the diff is
non-empty — one `project_changes` row, then commits once.

Hooking the store rather than the routes is the point: a route added next month that
saves a job is logged without anybody remembering to log it. The diff itself is a
pure function in `fenceai/project/changes.py` (People & work), which reads the
topology through `topology.station` and letters sections with `report.sections.section_tag`
— the same letters the office's job screen and the setting-out sheet print.

A save that changes nothing writes no change row (it still writes its audit row).

### What an entry says

An entry is a list of `Change(code, params)`. Codes are platform text, so they follow
the warning registry's rule: `code + params`, and a `change.<code>` sentence in **both**
locale bundles. Lengths travel as `…_mm` params and render in the reader's unit.

| Area | Codes |
|---|---|
| The job | `job_created` · `name_changed` · `customer_changed` · `address_changed` · `sold_by_changed` · `sold_on_changed` |
| Whose desk | `status_changed` · `assignee_changed` · `plan_committed` · `plan_released` · `acknowledged` |
| The property | `landmark_added` · `landmark_removed` · `landmark_changed` |
| The fence line | `section_added` · `section_removed` · `section_length_changed` · `section_reshaped` |
| The side view | `height_added` · `height_removed` · `height_changed` · `base_added` · `base_removed` · `base_changed` · `ground_changed` · `ground_point_added` · `ground_point_removed` · `ground_point_changed` · `ground_point_moved` |
| Gates and model | `gate_added` · `gate_removed` · `gate_changed` · `gate_moved` · `gate_details_changed` · `model_added` · `model_removed` · `model_changed` · `default_model_changed` |
| Notes and claims | `note_added` · `stated_changed` |
| Anything else | `section_changed` · `area_changed` |

**Heights, bases and models are compared by what each stretch is BUILT to**, never by
their events (`topology.station.built_stretches`). These are the three kinds the
generator reads first-covering-wins, and how they are stored is not a fact about the
fence: carving stores one height as three events, a later height can sit hidden under
an earlier one, and the base tool replaces an event with an identical one under a new
id. Compared by events, the carving above credited the office with Dana's 1800, an
unchanged re-save wrote an entry, and reordering two heights — which changes the
fence — wrote none (architecture review, S1). Compared by what is built, a height
drawn over the second half of Dana's 1800 is one entry, *Section B: height 1800 →
1750 (3000–6000)*. The old events are resolved against the NEW geometry, so a
stretched section does not read as a moved height.

**Gates and ground points are matched by id**: a point is a thing at a place, and a
moved gate is the same gate. One removed and one added in one save is the same point
re-authored and reads as whatever differs between the two — nothing, when nothing does.

**A letter is a position; the run id is the name.** Every section-bearing change also
carries `run`, and the route re-letters it against the drawing as it is now
(`changes.reletter`): delete section A and the old "B" reads A. A section no longer
drawn keeps the letter it had, marked *no longer drawn*. Stored letters alone could not
be repaired once written (review B1).

### Nothing changes silently

The vocabulary will grow and will always be behind the model. So the diff has
completeness passes, over facts rather than storage — ids, storage order and revision
counters are not facts:

* per section: anything no sentence reads — kinds of event with no sentence, a model's
  options, a height hidden under another — gives `section_changed {section}`;
* the drawing: node kinds, loose nodes, and the order the sections are lettered in give
  `area_changed {drawing}`, even beside named changes;
* every other area of the job (`job`, `desk`, `property`, `model`, `notes`, `stated`,
  `site`, `posts`, `choices`, `policy`): if it differs and nothing named it,
  `area_changed {area}`.

Tests hold each pass, beside a named change as well as alone, and every `Project`
field belongs to exactly one area. Growing the vocabulary is then a matter of replacing
a fallback with a better sentence — never of discovering a change that was missed.

A defect in the diff never stops a save: the job is saved and the entry reads *the
job changed (the details could not be worked out)* (`changes.unreadable`).

### Names

The log stores the actor ref (`user:u_yossi`) and the raw assignee id, never a name — a
name can change and a ref cannot. `GET /api/projects/{id}/changes` resolves names at
read time from the users table (deactivated, never deleted, so people who left still
resolve). Non-person actors (`seed`, `proposer:…`, `agent:…`) are shown as the system.

### Where it shows

A collapsible **History** panel (`#change-log`, owned by `js/change-log.js`, with the
pure sentence builder in `js/change-text.js`):

* the office, **reading** a job (the screen it lands on);
* the office road, step 1 (*the sale*);
* the sales road, step 8 (*review*) — where Dana sees what the office changed;
* the admin's full view.

Newest first. A status change renders as a divider, so the handover is visible as a
line across the list. Nobody is notified — the owner's answer to question 4.

### Found while designing: a second height never wins

The height tool **adds** a height over the stretch and removes nothing
(`editor.js`, the `height` branch). The generator reads the **first** height that
covers a station (`generator._interval_at`). So when the office states 1750 over
Dana's 1800, the fence is still built at 1800 — measured with `generate()` on a 6 m
run: `1800` before, `1800` after. The log would faithfully report a change the
fence never received.

The base and model tools already replace what they cover. This slice makes the
height tool do the same, more carefully: the new height **carves** its stretch out of
any height it overlaps — trimming one that runs past either end, splitting one that
contains it, removing one it covers — so Dana's 1800 survives where Yossi did not
touch it. The carving is a pure function (`js/intervals.js`), tested in node.

The Levi figures in the owner's guide are unaffected: there, the note became a
*level top line*, which outranks any height.

*Not changed here:* `project/intents.py: confirm_intent` appends a confirmed height the
same way, and `PUT /topology` accepts overlapping heights from any client. The server
still builds the first. The history now reports what is built, so such a hidden height
is never logged as a change it is not; making the server refuse or normalise overlaps is
recorded in `docs/v1-known-limitations.md` with its trigger.

### Not in this slice, with triggers

| Not built | Trigger |
|---|---|
| Restoring the job to an earlier entry | Somebody needs a value back that the log shows but cannot re-enter by hand. The entries carry before-values, so restore is buildable from them. |
| Telling sales when the office changes her work | The trigger the backoffice design already names: a salesperson finding her measurements changed without being told. |
| Folding many small saves into one entry | A history where one drag of a corner fills a screen. Folding is a read-time view over the stored entries, so it can be added without touching what is stored. |
| Filtering by person or area | A job whose history is too long to scan. |

---

## Slice 2 — products to the model's parts (outline)

A fence model already has parts — M-SLAT is a rail, a slat and a screw, plus posts from
the rules — and every part says which products fit it (`PartRequirement.eligibility`,
built from the part library's spec). Supply picks among those by price
(`fulfillment/supply.py: _choose`, preset `least_cost`). The part drawer already
lists the products that fit, with price difference and stock, and narrows the part to
one product for a preview (`slot_skus`) — and saves nothing.

The slice: the office's pick is saved on the job, per *(model, part)*, and reaches
generation as a one-member eligibility — the path the supply code already takes for
a SKU that knowledge chose. Parts left alone keep today's behaviour. The office
chooses only among products that fit the part; adding a product to a part stays the
super user's job in the part library. Every pick is a change entry.

To settle when it starts: where on the office road the pick lives (the materials step
is the natural place), and what happens to a pick when the model is changed.

## Slice 3 — posts by hand (outline)

Per section, *Posts: draft* (today) or *by hand*. By hand, a section starts with only
the posts it cannot do without — its ends, its corners, and the two posts of a gate.
On the Levi street fence that is 4 posts and two 4 m gaps, where the draft places 8.
The office adds the rest; the engine adds nothing, and a bay wider than the rule is
built as placed and flagged on the plan and the quote (`span_placed_over_maximum`,
the behaviour `lock_bay` already has), never blocked.

To settle when it starts: where the setting is stored (a section is the drawing,
which is sales'; the setting is the office's), and what happens to the posts already
placed when a section is switched back to *draft*.

---

## Invariants, held by tests

1. Every save of a job that changes a fact writes exactly one change entry, in the
   same commit as the job; a save that changes no fact (a revision bump, an identical
   event under a new id) writes none.
2. For any two job documents that differ in a fact, `diff_project` is non-empty — alone
   or beside other changes (the completeness passes).
3. Every code `diff_project` can emit has a `change.<code>` sentence in both locale
   bundles, and the two bundles carry the same keys.
4. `diff_project` is pure: same two documents, same list, same order.
5. A new height over an older one is the height the fence is built to, and the older
   height survives wherever the new one does not reach.

## Seams left named

* **The vocabulary** (`CHANGE_CODES`): a new code is a branch in the diff plus two
  locale sentences; until then the completeness pass covers it.
* **The read view**: folding, filtering and restore all read the stored entries and
  change nothing about how they are written.
