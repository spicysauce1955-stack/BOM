# Plan — slice 1: the change log

Implements §"Slice 1" of `docs/superpowers/specs/2026-10-12-office-desk-without-ai-design.md`.
Branch `office-change-log`, from trunk `08e000b`.

Each task states the interface, what its tests must pin, and the files. Fixtures and
assertions are the executor's (see the plan rule in memory: plan code is written blind).

---

## Task 1 — a new height carves what it covers

**Interface.** New pure module `src/fenceai/web/static/js/intervals.js`, no DOM, no state:

```js
// events: a run's interval_events; kind: payload.kind to carve;
// [start, end]: the new interval in stations; stationOf(anchor) -> station;
// anchorAt(station) -> anchor; newId() -> fresh event id.
export function carveInterval(events, kind, start, end, { stationOf, anchorAt, newId })
  -> events'   // a NEW array; the input is not mutated
```

Events of other kinds pass through untouched and keep their order. For each event of
`kind` overlapping `(start, end)`: covered → dropped; overlapping one end → shortened
to the uncovered part (same id); containing → split into the part before (same id)
and the part after (new id, same payload). Touching at a boundary is not overlap.

`editor.js`'s `height` branch calls it before `addIntervalEvent`, inside the same
gesture (after `pushSnapshot`).

**Tests pin** (`tests/web/test_intervals_module.py`, node): each of the four overlap
cases; other kinds untouched; input not mutated; boundary-touching kept whole. One
backend test pins the consequence the spec states: an 1800 over 0–6000 carved by a
1750 over 0–6000 builds 1750; a 1750 over 3000–6000 builds 1800 on the first half
and 1750 on the second (`generate()`, `tests/strategy/`).

## Task 2 — `diff_project`

**Interface.** New `src/fenceai/project/changes.py`:

```python
class Change(BaseModel):
    code: str
    params: dict[str, str | int | bool | None] = {}

CHANGE_CODES: frozenset[str]          # every code diff_project can emit
AREAS: dict[str, tuple[str, ...]]     # area -> the Project fields it covers

def diff_project(before: Project | None, after: Project) -> list[Change]
```

Vocabulary as the spec's table. Sections are lettered with
`report.sections.section_tag` over the AFTER topology's run order (the BEFORE order
for a removed section); stations come from `topology.station.anchor_station`, lengths
from `run_length`. Events match by id; a removed-plus-added pair of one kind on one
section in one save is one `…_changed`. Ignored: `topology.revision`, `site.revision`.

**Tests pin** (`tests/project/test_changes.py`): `None → project` is `job_created`
only; each code fires from the smallest edit that should produce it, with its params;
the base tool's replace (remove + add) is one `base_changed`; a node move reports the
length of every section touching it; identical documents and revision-only bumps give
`[]`; **every Project field belongs to exactly one area** (a new field fails until
mapped); **for an edit to each area that no specific code names, the fallback fires**;
same inputs → same list, same order; every emitted code is in `CHANGE_CODES`.

## Task 3 — the store writes an entry beside every save

**Interface.** Table `project_changes (seq SERIAL PK, project_id, at, actor, doc)` plus
an index on `(project_id, seq)`. `save_project` loads the stored document, diffs, writes
the job + audit row + (if non-empty) one change row, one commit. New public
`project_changes(project_id, limit=200) -> list[dict]`, newest first, each
`{seq, at, actor, changes: [...]}`.

**Tests pin** (`tests/store/`, both backends via the existing fixture): a first save
writes `job_created`; a save that changes nothing writes no row and still an audit
row; two edits are two rows, newest first; `limit` holds; rows of another project are
not returned; a stored row survives reopening the store (file-backed).

## Task 4 — `GET /api/projects/{id}/changes`

Returns `{"entries": [...], "names": {ref_or_id: name}}`; 404 for an unknown job.
Names: every `user:<id>` actor and every user id in an `assignee_changed` param that
the users table knows. **Tests pin**: a PUT topology that changes a height appears as
`height_changed` with the caller as actor and their name in `names`; a desk command
appears as `status_changed`; unknown project 404. Update `docs/architecture/04-backend.md`
(route count, route table, table count, table list) in the same commit — the fitness
tests require it.

## Task 5 — locale

`change.<code>` for every code in both `en.json` and `he.json`, plus the area words
(`change.area.<area>`) and the panel's own strings. **Test pins**
(`tests/web/test_change_locale.py`): every `CHANGE_CODES` member and every `AREAS` key
has its sentence in both bundles. (The bundles' key-set equality is already tested.)

## Task 6 — the History panel

`js/change-text.js` (pure): `changeHtml(change, { t, names })` → escaped HTML, params
bidi-isolated, lengths through `unitParams`, state / surface / landmark words looked up
(`queue.status.*`, `surface.*`, `context.kind.*`). `js/change-log.js` owns
`#change-log` (a `<details>` host in the side column): fetches on `project-opened` and
after every project save, renders entries newest first, a status change as a divider.

Visible per the spec: office reading mode (CSS exception beside `#job-screen`), office
road step `sale`, sales road step `review`, admin full view. `step-surfaces.js` and its
`style.css` mirror move together. **Tests pin** (node): every code renders without a
raw `{param}` left in it, in both locales; user text is escaped. Then a headless-Chrome
check: Levi-shaped job, Yossi changes a height, the panel shows the line; in Hebrew too.

## Task 7 — docs and status

`docs/architecture/people-and-work.md` (the change log), `02-entities.md`
(`ChangeEntry`), `05-frontend.md` (two modules), `docs/v1-known-limitations.md`
(`confirm_intent` appends heights), `plan/current-status.md` checkpoint.

## Verification

Full suite with CI's extras (`uv sync --extra postgres --extra iap`, `uv run pytest -q`),
the scenarios gate, `tools/ui_smoke.py`, then `architecture-critic` and `test-reviewer`
with named doubts; then commit, PR, merge.
