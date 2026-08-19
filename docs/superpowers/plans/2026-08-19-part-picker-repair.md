# Part Picker Repair — Implementation Plan (arc A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the Models editor, which since the part library shipped shows every slot as having no product and refuses the save that would fix it.

**Architecture:** A slot names a part now, so the editor must pick parts rather than SKUs. One derived accessor tells the editor which of four kinds a slot is; two read-only routes give the browser the part library and its type labels; the inspector's product picker becomes a part picker; and the browser smoke suite gains the check whose absence let this ship.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest; vanilla ES modules + SVG, no build step; node for JS unit tests; CDP-driven browser smoke.

**Spec:** `docs/superpowers/specs/2026-08-19-part-picker-repair-design.md`

## Global Constraints

- **The compatibility gate must not move.** `uv run pytest tests/scenarios -q` stays at 183 passed and `tests/scenarios/compatibility_gate/*.json` stays unmodified. This arc changes no resolution and no field generation reads; a moved scenario means the change is wrong, not the scenario.
- **Read models are derived, never stored** (CLAUDE.md). `eligibility_source` is a property, never a field.
- **ES modules communicate ONLY via `state.js`**; no module touches another's DOM subtree. No framework, no build step, no CDN.
- **Every user-visible string goes through `t("key")` or `data-i18n`**, and `i18n/he.json` and `en.json` must keep identical key sets — `tests/web/test_locale_bundles.py` enforces it.
- **CSS uses logical properties only** (no `left`/`right`); SKUs/ids/dimensions get `.sku`/`.num`/`<bdi>` isolation.
- **Any user/expert text interpolated into `innerHTML` goes through `esc()`.**
- **Authoring errors carry no `code + params`** — they are English strings, per `validate_model`'s own docstring. Do not add locale codes for `validate_part`.
- Integer millimetres at rest (ADR-0002).

**Out of scope, and refused if a task seems to need it:** creating or editing parts, a Parts tab, the canvas drag-snap, `POST /api/parts/preview-eligibility`, connections (arc B), item tolerance (arc C).

---

### Task 1: `eligibility_source`

**Files:**
- Modify: `src/fenceai/fencemodel/model.py` (add a property to `PartRequirement`, which ends at the `eligibility: Eligibility = Eligibility()` line)
- Test: `tests/fencemodel/test_eligibility_source.py`

**Interfaces:**
- Consumes: `PartRequirement` as it stands — `part_id: str`, `eligibility: Eligibility` with `.members` and `.predicate`
- Produces: `PartRequirement.eligibility_source -> Literal["part", "authored_members", "authored_predicate", "unspecified"]`

- [ ] **Step 1: Write the failing test**

```python
# tests/fencemodel/test_eligibility_source.py
"""Which of four shapes a slot is — asked once, in Python, where a test can reach it.

The editor renders a different pane per shape. Inferring that in JavaScript by
checking three fields in order would put the rule where no test here could see it,
and the next reader of the model would have to derive it again.
"""

from fenceai.fencemodel.demo import demo_models
from fenceai.fencemodel.model import Eligibility, EligibleItem, PartRequirement
from fenceai.knowledge.ast import Cmp, FieldRef, Lit
from fenceai.parts.resolve import part_requirements


def test_a_slot_naming_a_part_says_so():
    assert PartRequirement(part_id="rail-38").eligibility_source == "part"


def test_authored_members_when_no_part():
    req = PartRequirement(
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]))
    assert req.eligibility_source == "authored_members"


def test_authored_predicate_when_no_part():
    req = PartRequirement(eligibility=Eligibility(
        predicate=Cmp(cmp="==", left=FieldRef(path="item.material"),
                      right=Lit(value="vinyl"))))
    assert req.eligibility_source == "authored_predicate"


def test_nothing_yet_is_unspecified():
    assert PartRequirement().eligibility_source == "unspecified"


def test_the_part_wins_over_anything_riding_along():
    """Resolution fills `predicate` on a part-named slot, so a resolved document
    would report `authored_predicate` if the part were not checked first — and the
    editor would offer to edit a rule the author never wrote."""
    req = PartRequirement(part_id="rail-38", eligibility=Eligibility(
        predicate=Cmp(cmp="==", left=FieldRef(path="item.material"),
                      right=Lit(value="vinyl"))))
    assert req.eligibility_source == "part"


def test_the_real_demo_models_cover_three_of_the_four_shapes():
    """Over the shipped models, not fixtures: a change to demo data that made every
    slot one shape would leave the fixtures passing and the editor untested."""
    found = {req.eligibility_source
             for model in demo_models().values()
             for _key, req in part_requirements(model)}
    assert found == {"part", "authored_members", "authored_predicate"}


def test_the_knowledge_sourced_slots_report_what_they_are_on_paper():
    """M-LEGACY's rail and screw have their members REPLACED per run from
    `demand_skus`. That is a generation-time behaviour with no trace on the authored
    document, so the property reports `authored_members` — what they are on paper —
    and the editor must not claim to know otherwise."""
    legacy = demo_models()["M-LEGACY"]
    sources = {key: req.eligibility_source for key, req in part_requirements(legacy)}
    assert sources["rail"] == "authored_members"
    assert sources["screw"] == "authored_members"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fencemodel/test_eligibility_source.py -q`
Expected: FAIL — `AttributeError: 'PartRequirement' object has no attribute 'eligibility_source'`

- [ ] **Step 3: Write the implementation**

Add to `PartRequirement` in `src/fenceai/fencemodel/model.py`, directly after its fields:

```python
    @property
    def eligibility_source(self) -> Literal[
        "part", "authored_members", "authored_predicate", "unspecified"
    ]:
        """Which of four shapes this slot is — one accessor, so the editor and the
        validator read the same answer.

        Derived, never stored, for the reason `Part.dimensions` is: a stored copy
        would be a second authority over facts these fields already encode.

        `part_id` is checked FIRST because resolution fills `predicate` on a
        part-named slot — a resolved document would otherwise report itself as
        rule-authored, and the editor would offer to edit a rule nobody wrote.

        There is a fifth shape it cannot report. M-LEGACY's rail and screw have
        their members REPLACED per run from `demand_skus`, so what a job buys there
        comes from company knowledge — but that is a generation-time behaviour with
        no trace on the authored document. Those slots report `authored_members`,
        which is what they are on paper. Claiming otherwise would be a guess dressed
        as a fact.
        """
        if self.part_id:
            return "part"
        if self.eligibility.predicate is not None:
            return "authored_predicate"
        if self.eligibility.members:
            return "authored_members"
        return "unspecified"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fencemodel/test_eligibility_source.py -q`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/fencemodel/model.py tests/fencemodel/test_eligibility_source.py
git commit -m "feat(fencemodel): a slot says which of four shapes it is

Derived, never stored, and part_id wins over a predicate resolution put
there — otherwise a resolved document reports itself as rule-authored and
the editor offers to edit a rule nobody wrote."
```

---

### Task 2: The two read-only routes

**Files:**
- Modify: `src/fenceai/api/app.py` (add beside the existing `@app.get("/api/catalog")`)
- Test: `tests/api/test_parts_routes.py`

**Interfaces:**
- Consumes: `Store.part_library() -> PartLibrary` (exists); `Part` with `id`, `type`, `name_i18n`, `status`, `version`, `spec: list[SpecField]`
- Produces: `GET /api/parts -> {"parts": [...]}`; `GET /api/part-types -> {"types": [{"key": str, "label_i18n": {...}}]}`

**Note on part types, from spec §3:** `PartType` is defined in `parts/model.py` but **nothing instantiates it** — the 1A fix wave deleted `demo_part_types()` as dead code. So this route derives the types actually in use from the part library rather than reading a library nobody writes to. A stored, editable `PartType` library belongs to the arc where parts are created and a type must be chosen for a new one.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_parts_routes.py
"""The two routes the picker needs, and nothing more.

No eligibility endpoint: `PreviewPart.eligible_skus` already carries the candidate
set per slot and `/api/fence-models/preview` already takes an unsaved document, so
the list the editor wants is already arriving in the browser and simply is not
displayed.
"""

from fastapi.testclient import TestClient

from fenceai.api.app import app

client = TestClient(app)


def test_the_library_is_listed_with_the_spec_each_part_declares():
    body = client.get("/api/parts").json()
    parts = {p["id"]: p for p in body["parts"]}
    assert "rail-rail-3000" in parts
    rail = parts["rail-rail-3000"]
    assert rail["type"] == "rail"
    assert rail["status"] == "active"
    assert rail["version"] >= 1
    # the spec travels: an author choosing a part should see WHY it is that part,
    # not only its name
    assert any(f["key"] == "sku" for f in rail["spec"])


def test_a_spec_field_keeps_its_three_parts():
    body = client.get("/api/parts").json()
    rail = next(p for p in body["parts"] if p["id"] == "rail-rail-3000")
    sku_field = next(f for f in rail["spec"] if f["key"] == "sku")
    assert sku_field["agree"] == "among"
    assert sku_field["value"] == ["RAIL-3000"]


def test_a_multi_candidate_part_is_offered_too():
    """`rail-38-vinyl` is specified by width and material rather than by sku. It is
    the case the whole entity exists for, and a picker that only ever showed
    sku-list parts would render the feature invisible."""
    ids = {p["id"] for p in client.get("/api/parts").json()["parts"]}
    assert "rail-38-vinyl" in ids


def test_the_types_in_use_are_offered_with_labels():
    body = client.get("/api/part-types").json()
    keys = {t["key"] for t in body["types"]}
    assert {"rail", "infill", "screw"} <= keys
    rail = next(t for t in body["types"] if t["key"] == "rail")
    assert rail["label_i18n"]["en"]
    assert rail["label_i18n"]["he"]


def test_types_are_derived_from_the_library_not_invented():
    """Nothing instantiates PartType, so a route over stored type data would return
    an empty list. These come from the parts that exist."""
    parts = client.get("/api/parts").json()["parts"]
    types = {t["key"] for t in client.get("/api/part-types").json()["types"]}
    assert types == {p["type"] for p in parts}


def test_the_types_are_sorted_so_the_picker_does_not_reshuffle():
    keys = [t["key"] for t in client.get("/api/part-types").json()["types"]]
    assert keys == sorted(keys)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_parts_routes.py -q`
Expected: FAIL — 404, the routes do not exist

- [ ] **Step 3: Write the implementation**

In `src/fenceai/api/app.py`, beside the catalog route. Read `@app.get("/api/catalog")` first and match its shape:

```python
@app.get("/api/parts")
def list_parts() -> dict:
    """The part library, for the Models editor's picker.

    Each part's spec travels with it: an author choosing "38mm vinyl rail" should be
    able to see WHY it is that, not only its name. Read-only — creating and editing
    parts is the arc that builds an editor for them.
    """
    library = state.store.part_library()
    return {"parts": [p.model_dump() for p in
                      sorted(library.parts, key=lambda p: (p.type, p.id, p.version))]}


@app.get("/api/part-types")
def list_part_types() -> dict:
    """The types actually in use, with a label per language.

    `PartType` exists as a model and nothing instantiates it, so a route over stored
    type data would return an empty list. These are derived from the library, which
    is the honest amount of vocabulary this arc needs; a stored, editable type
    library belongs to the arc where a NEW part must be given a type.

    The label comes from `part_type.<key>` in the locale bundles and falls back to
    the raw key, so a company that stocks something new gets a working picker before
    anyone writes it a word.
    """
    library = state.store.part_library()
    keys = sorted({p.type for p in library.parts})
    return {"types": [{"key": k, "label_i18n": _part_type_labels(k)} for k in keys]}


def _part_type_labels(key: str) -> dict[str, str]:
    labels = {}
    for lang in ("en", "he"):
        bundle = _locale_bundle(lang)
        labels[lang] = bundle.get(f"part_type.{key}", key)
    return labels
```

If no `_locale_bundle(lang)` helper exists in `app.py`, write one that reads
`src/fenceai/web/static/i18n/<lang>.json` once and caches it — and check first
whether the module already loads those bundles for another route.

- [ ] **Step 4: Add the type words to both bundles**

Add to BOTH `src/fenceai/web/static/i18n/en.json` and `he.json`, keeping key sets
identical (`test_locale_bundles.py` enforces it). Real Hebrew, not a copy of the
English:

```
part_type.rail    → "Rails"   / "שלבים"
part_type.infill  → "Boards"  / "קרשים"
part_type.screw   → "Fixings" / "אמצעי חיבור"
part_type.post    → "Posts"   / "עמודים"
part_type.cap     → "Caps"    / "כובעים"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_parts_routes.py tests/web/test_locale_bundles.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/api/app.py tests/api/test_parts_routes.py src/fenceai/web/static/i18n/
git commit -m "feat(api): the part library and the types in use, read-only

No eligibility route: the candidate set per slot is already on the preview
response and simply is not displayed. Types are derived from the library
because nothing instantiates PartType — a stored type library belongs to
the arc where a new part must be given one."
```

---

### Task 3: The picker, as a pure function

**Files:**
- Modify: `src/fenceai/web/static/js/panel-model.js` (add exports)
- Test: `tests/web/test_part_picker_module.py`

**Interfaces:**
- Consumes: the `/api/parts` payload shape from Task 2
- Produces, all exported from `panel-model.js`:
  - `eligibilitySource(req) -> "part" | "authored_members" | "authored_predicate" | "unspecified"`
  - `partsByType(parts) -> [{type, parts: [...]}]`, both levels sorted
  - `specChips(part) -> [{text, kind}]`
  - `partSummary(req, {parts, preview}) -> {source, part, chips, candidates, chosen, missing}`

**Why here:** `panel-model.js` is where this codebase keeps the pure, node-testable half of the editor (`spacingMode`, `defaultRequirement`, `duplicateOf`). `panel-inspector.js` is DOM. Putting the logic in the pure module is what makes Task 3 testable without a browser — the same split `base-top.js` already has, which CLAUDE.md names as a durable frontend principle.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_part_picker_module.py
"""The picker's logic, in node, against a REAL preview and the REAL part library.

The payloads are generated by the actual pipeline and interpolated into the script,
so a field renamed on the wire fails here rather than emptying the picker in a
browser nobody is watching — the pattern `test_part_drawer_module.py` established.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import demo_models
from fenceai.fencemodel.preview import PreviewRequest, preview_panel
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { eligibilitySource, partsByType, specChips, partSummary }
  from "./js/panel-model.js";

const parts = %(parts)s;
const preview = %(preview)s;
const out = {};

out.sources = {
  part: eligibilitySource({ part_id: "rail-38", eligibility: { members: [] } }),
  members: eligibilitySource({ part_id: "",
    eligibility: { members: [{ sku: "RAIL-3000" }] } }),
  predicate: eligibilitySource({ part_id: "",
    eligibility: { members: [], predicate: { op: "cmp" } } }),
  nothing: eligibilitySource({ part_id: "", eligibility: { members: [] } }),
  partWins: eligibilitySource({ part_id: "rail-38",
    eligibility: { members: [], predicate: { op: "cmp" } } }),
  missingReq: eligibilitySource(null),
};

const grouped = partsByType(parts);
out.groups = grouped.map((g) => [g.type, g.parts.map((p) => p.id)]);

out.chips = specChips(parts.find((p) => p.id === "rail-38-vinyl"))
  .map((c) => c.text);
out.chipsOfSkuPart = specChips(parts.find((p) => p.id === "rail-rail-3000"))
  .map((c) => c.text);
out.chipsOfNothing = specChips(null);

const summary = partSummary(
  { part_id: "rail-rail-3000", eligibility: { members: [] } },
  { parts, preview, slotKey: "rail" });
out.summary = { source: summary.source, id: summary.part?.id,
                candidates: summary.candidates, chosen: summary.chosen,
                missing: summary.missing };

out.unknownPart = partSummary(
  { part_id: "no-such-part", eligibility: { members: [] } },
  { parts, preview, slotKey: "rail" }).missing;

console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="node not available")
def test_the_picker_reads_the_real_library_and_the_real_preview(tmp_path):
    library = PartLibrary(parts=demo_parts())
    # `part_library=`, not `parts=` — preview_panel already has a local `parts`
    # (the priced rows it returns) and says so in its own signature comment
    preview = preview_panel(
        demo_models()["M-SLAT"], PreviewRequest(height_mm=1800, width_mm=2400),
        demo_catalog(), part_library=library)
    payload = SCRIPT % {
        "parts": json.dumps([p.model_dump() for p in library.parts]),
        "preview": preview.model_dump_json(),
    }
    script = STATIC / "_picker_test.mjs"
    script.write_text(payload)
    try:
        proc = subprocess.run(["node", str(script)], capture_output=True,
                              text=True, cwd=STATIC, timeout=60)
    finally:
        script.unlink()
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    # the four shapes, and the one that must win
    assert out["sources"] == {
        "part": "part", "members": "authored_members",
        "predicate": "authored_predicate", "nothing": "unspecified",
        "partWins": "part", "missingReq": "unspecified",
    }

    # grouped by type, both levels sorted, so the picker never reshuffles
    types = [g[0] for g in out["groups"]]
    assert types == sorted(types)
    for _type, ids in out["groups"]:
        assert ids == sorted(ids)
    assert "rail" in types

    # a spec-authored part shows what it requires; a sku-list part says so plainly
    assert any("38" in c for c in out["chips"])
    assert any("vinyl" in c.lower() for c in out["chips"])
    assert out["chipsOfSkuPart"]      # not empty — an sku list is still a fact
    assert out["chipsOfNothing"] == []

    # the summary joins the slot, the library and the preview
    assert out["summary"]["source"] == "part"
    assert out["summary"]["id"] == "rail-rail-3000"
    assert out["summary"]["candidates"] >= 1
    assert out["summary"]["chosen"]
    assert out["summary"]["missing"] is False

    # a part_id the library does not have is REPORTED, never rendered as empty
    assert out["unknownPart"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_part_picker_module.py -q`
Expected: FAIL — the node run exits non-zero, `eligibilitySource` is not exported

- [ ] **Step 3: Write the implementation**

Add to `src/fenceai/web/static/js/panel-model.js`:

```javascript
// --- the part picker's logic, kept pure so node can test it ------------------
// panel-inspector.js is DOM; this is not. The same split base-top.js already has,
// and the reason the picker can be tested without a browser.

/** Which of four shapes a slot is. Mirrors `PartRequirement.eligibility_source`
 *  exactly — two answers to one question would drift, and this one decides which
 *  pane an author sees. `part_id` first: resolution fills `predicate` on a
 *  part-named slot, and a resolved document must not read as rule-authored. */
export function eligibilitySource(req) {
  if (!req) return "unspecified";
  if (req.part_id) return "part";
  if (req.eligibility?.predicate) return "authored_predicate";
  if (req.eligibility?.members?.length) return "authored_members";
  return "unspecified";
}

/** Parts grouped by type, both levels sorted — a picker that reshuffles between
 *  renders makes an author lose their place. */
export function partsByType(parts) {
  const byType = new Map();
  for (const part of parts || []) {
    if (!byType.has(part.type)) byType.set(part.type, []);
    byType.get(part.type).push(part);
  }
  return [...byType.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([type, list]) => ({
      type, parts: list.slice().sort((a, b) => a.id.localeCompare(b.id)),
    }));
}

/** What the part requires, as short phrases. The author picked a name; this is how
 *  they see what the name MEANS without leaving the slot. */
export function specChips(part) {
  return (part?.spec || []).map((f) => ({ kind: f.agree, text: chipText(f) }));
}

function chipText(f) {
  if (f.agree === "supplies") return "cut from stock";
  if (f.agree === "among") return `${f.key}: ${(f.value || []).join(", ")}`;
  if (f.agree === "between") return `${f.key} ${f.value?.[0]}–${f.value?.[1]}`;
  if (f.agree === "==") return `${f.key} ${f.value}`;
  return `${f.key} ${f.agree} ${f.value}`;
}

/** Everything the slot pane needs about the part, joined from the slot, the
 *  library and the preview the editor already fetched.
 *
 *  `candidates` and `chosen` come off `PreviewPart.eligible_skus` and `.sku` — no
 *  new request, because the candidate set is already on the wire. */
export function partSummary(req, { parts = [], preview = null, slotKey = "" } = {}) {
  const source = eligibilitySource(req);
  const part = (parts || []).find((p) => p.id === req?.part_id) || null;
  const row = (preview?.parts || []).find((p) => p.slot_key === slotKey)
    || (preview?.unsupplied || []).find((p) => p.slot_key === slotKey) || null;
  return {
    source,
    part,
    chips: specChips(part),
    candidates: (row?.eligible_skus || []).length,
    eligibleSkus: row?.eligible_skus || [],
    chosen: row?.sku || "",
    // a slot naming a part the library does not have. Reported, never rendered as
    // an empty select — an empty select reads as "you never chose one".
    missing: source === "part" && !part,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/web/test_part_picker_module.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/panel-model.js tests/web/test_part_picker_module.py
git commit -m "feat(web): the part picker's logic, pure and node-tested

Kept out of panel-inspector.js on purpose: that file is DOM, this is not,
and the split is what lets a real preview and a real library drive the
picker in a test rather than in a browser nobody is watching."
```

---

### Task 4: The inspector pane

**Files:**
- Modify: `src/fenceai/web/static/js/panel-inspector.js` — `productField` (`:408-435`), `requirementAdvanced` (`:450-471`), `eligibilityList`, `addProductButton`
- Modify: `src/fenceai/web/static/js/builder-ui.js` (a parts cache beside the catalog cache at `:65-78`)
- Modify: `src/fenceai/web/static/i18n/en.json`, `he.json`
- Test: `tests/api/test_authoring_gaps.py` (append)

**Interfaces:**
- Consumes: `eligibilitySource`, `partsByType`, `specChips`, `partSummary` (Task 3); `GET /api/parts`, `GET /api/part-types` (Task 2)
- Produces: an inspector that writes `part_id` and never `eligibility.members` or `role`

- [ ] **Step 1: Write the failing test**

The regression was a frontend/backend contract break, so the test that would have
caught it is in Python — a JS-only test would not have, and did not.

```python
# tests/api/test_authoring_gaps.py  (append)

def test_the_editors_payload_for_a_part_named_slot_validates():
    """THE regression this arc repairs. The editor wrote `eligibility.members` and
    `role` onto a slot that names a part; the part is the one authority on both, and
    the validator refuses the pair. A payload shaped the way the editor now saves
    must survive a round trip."""
    from fenceai.fencemodel.demo import slat_model
    from fenceai.fencemodel.model import PartRequirement

    slot = slat_model().default_spec.frame[0]
    payload = slot.requirement.model_dump()
    # what the repaired editor sends: the part, and nothing that contradicts it
    assert payload["part_id"]
    assert payload["eligibility"]["members"] == []
    assert payload.get("role", "") == ""
    PartRequirement(**payload)          # raises if the editor's shape is refused


def test_the_old_editor_payload_is_still_refused():
    """The guardrail must not be relaxed to make the editor pass. A slot naming a
    part AND authoring members is the thing that was wrong, and it stays wrong."""
    import pytest
    from pydantic import ValidationError
    from fenceai.fencemodel.demo import slat_model
    from fenceai.fencemodel.model import PartRequirement

    payload = slat_model().default_spec.frame[0].requirement.model_dump()
    payload["eligibility"] = {"members": [
        {"kind": "catalog_item", "sku": "RAIL-3000", "priority": 1,
         "approval": "auto"}]}
    with pytest.raises(ValidationError, match="members"):
        PartRequirement(**payload)


def test_a_slot_that_names_no_part_may_still_author_members():
    """M-LEGACY's rail and screw. The preference list stays editable for exactly
    these, which is why the editor asks `eligibility_source` instead of assuming."""
    from fenceai.fencemodel.demo import legacy_model
    from fenceai.parts.resolve import part_requirements

    reqs = dict(part_requirements(legacy_model()))
    assert reqs["rail"].eligibility_source == "authored_members"
    assert reqs["rail"].eligibility.members
```

- [ ] **Step 2: Run the tests and expect them to PASS — this is a guard, not a red bar**

Run: `uv run pytest tests/api/test_authoring_gaps.py -q`
Expected: PASS, all three.

These three do not go red first, and that is honest rather than a broken TDD cycle:
the BACKEND is already correct — 1A made it so — and the bug lives entirely in the
JavaScript, which pytest cannot execute. What these pin is the CONTRACT the repaired
editor must satisfy, so that a future change to `PartRequirement` breaks a Python test
instead of silently breaking a screen again. The red bar for this task is Task 5's
browser check.

If any of the three FAILS, the demo data or the validator is wrong — report it rather
than editing the test.

- [ ] **Step 3: Add the parts cache**

In `src/fenceai/web/static/js/builder-ui.js`, beside the catalog cache. Read that
cache first — it exists because *"two caches, one populated before a catalog edit and
one after"* is a bug it already documents — and mirror it, including the
`.catch(() => { promise = null; return {}; })` reset so a failed fetch retries:

```javascript
let partsPromise = null;
export function loadParts() {
  partsPromise ??= apiGet("/api/parts")
    .then((body) => body.parts || [])
    .catch(() => { partsPromise = null; return []; });
  return partsPromise;
}

let partTypesPromise = null;
export function loadPartTypes() {
  partTypesPromise ??= apiGet("/api/part-types")
    .then((body) => body.types || [])
    .catch(() => { partTypesPromise = null; return []; });
  return partTypesPromise;
}
```

- [ ] **Step 4: Replace the product picker with the part picker**

In `panel-inspector.js`, `productField` becomes `partField`. It renders, per spec §4:

1. a `<select>` of parts grouped by type using `partsByType`, with the type's label
   from `/api/part-types`, writing `req.part_id` and nothing else;
2. the chips from `specChips`, each escaped with `esc()`;
3. `"N products can fill this"` as a `<details>`, expanding to `eligibleSkus` with
   the `chosen` one marked — SKUs wrapped in `<bdi>` with `.sku`;
4. the part's id and version as text. **Not a link** — there is no Parts tab in this
   arc, so a link would go nowhere.

Per spec §5, branch on `eligibilitySource(req)` first:

- `authored_predicate` → `t("model.slot.by_rule")`, plus the candidate count. The raw
  rule stays under Advanced.
- `authored_members` → `t("model.slot.by_listed_product")`, naming the SKU.
- `unspecified` → `t("model.slot.choose_part")`.
- `missing` → the part id with `t("model.part.not_in_library")`.

Per spec §6, in `requirementAdvanced`: **delete the `role` control entirely**, and
wrap `eligibilityList(req, ctx)` so it renders only when
`eligibilitySource(req) === "authored_members"`. Leave cut length, overlap, option
axis and SKU-per-option untouched — they are slot-local, and the first two are what
arc B proposes to delete.

- [ ] **Step 5: Add the locale keys**

Both bundles, identical key sets, real Hebrew:

```
model.part                     "Part"                        / "חלק"
model.slot.by_rule             "Chosen by a rule, not a part" / "נבחר לפי כלל, לא לפי חלק"
model.slot.by_listed_product   "A listed product, not a part" / "מוצר מפורש, לא חלק"
model.slot.choose_part         "Choose a part"                / "בחר חלק"
model.part.not_in_library      "not in the library"           / "לא נמצא בספרייה"
model.part.not_published       "not published"                / "לא פורסם"
model.part.can_fill            "{n} products can fill this"   / "{n} מוצרים יכולים למלא"
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/api/test_authoring_gaps.py tests/web/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/web/static/js/panel-inspector.js src/fenceai/web/static/js/builder-ui.js src/fenceai/web/static/i18n/ tests/api/test_authoring_gaps.py
git commit -m "fix(web): the slot inspector picks a part, not a sku

The picker wrote eligibility.members and role onto slots whose part owns
both, so every slot read 'no product' and the save that would fix it was
refused. Role leaves Advanced entirely; the preference list stays only for
the slots that genuinely author a sku list."
```

---

### Task 5: The smoke check whose absence let this ship

**Files:**
- Modify: `tools/ui_smoke.py` (the Models tab section around `:2102`)

**Interfaces:**
- Consumes: everything above

**Why this task exists:** the suite runs 183 checks and passed while the editor was
broken. It opens the Models tab (`:2102`, `:2238`, `:2707`) and immediately leaves —
it never selects a slot, never edits one, never saves. That is the blind spot, and
closing it is part of the repair rather than a nice-to-have.

- [ ] **Step 1: Add the check**

In the Models tab section, after the tab is opened and a model is loaded:

```python
        # --- the slot inspector saves what it shows ---------------------------
        # THE hole this arc repairs. The suite has always opened this tab and left
        # again, so a slot pane that showed "no product" for every slot and refused
        # the save that would fix it passed 183 checks. A tab that is opened and not
        # used is not covered.
        # `[data-slot]` is what panel-canvas.js actually marks a selectable element
        # with (`:120` — `ev.target.closest("[data-slot]")`), and the value is the
        # AUTHORED slot key. Verified against the source, not guessed.
        c.js("""
document.querySelector('[data-slot]')?.dispatchEvent(
  new MouseEvent('click', { bubbles: true })); 'ok'""")
        time.sleep(0.6)
        part_shown = c.js(
            "document.querySelector('[data-f=\"part\"]')?.value || ''")
        check("a slot pane names the part the slot names", bool(part_shown))

        chips = c.js(
            "document.querySelectorAll('[data-chip]').length")
        check("the part's spec is shown beside its name", (chips or 0) > 0)

        candidates = c.js(
            "document.querySelector('[data-candidates]')?.textContent || ''")
        check("the slot says how many products can fill it",
              any(ch.isdigit() for ch in candidates))

        # and the save that used to be refused
        saved = c.js("""
(async () => {
  const sel = document.querySelector('[data-f="part"]');
  const other = [...sel.options].find(o => o.value && o.value !== sel.value);
  if (!other) return 'no-alternative';
  sel.value = other.value;
  sel.dispatchEvent(new Event('change', { bubbles: true }));
  document.getElementById('btn-model-save')?.click();
  await new Promise(r => setTimeout(r, 1200));
  return document.querySelector('[data-f="part"]')?.value === other.value
    ? 'kept' : 'lost';
})()""")
        check("changing a slot's part saves and survives a reload",
              saved in ("kept", "no-alternative"))
```

Three of these selectors are verified against the source: `[data-slot]`
(`panel-canvas.js:120`), `#btn-model-save` (`model-editor.js:108`), and `data-f`
(the inspector's existing convention — `picker.dataset.f = "product"` at
`panel-inspector.js:420`, which Task 4 renames to `"part"`).

`data-chip` and `data-candidates` are NEW attributes Task 4 must render — they do not
exist yet, and adding them is part of Task 4's work, not a licence to invent
selectors here. **If any other selector does not exist, fix the check to match the
code — never add a selector to the code only to satisfy a check.**

- [ ] **Step 2: Run the smoke suite**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: all checks pass, total up from 183. Needs google-chrome. If Chrome is
unavailable, say so plainly rather than reporting a pass you did not observe.

- [ ] **Step 3: Commit**

```bash
git add tools/ui_smoke.py
git commit -m "test(smoke): the Models tab's slot pane is used, not just opened

183 checks passed while every slot showed 'no product' and the save that
would fix it was refused, because the suite opened this tab and left."
```

---

### Task 6: The gate and the docs

**Files:**
- Test: `tests/scenarios/` (run, do not modify)
- Modify: `docs/architecture/05-frontend.md`, `plan/current-status.md`

- [ ] **Step 1: Run the gates**

```
uv run pytest tests/scenarios -q     # 183 passed; compatibility_gate/*.json untouched
uv run pytest -q                     # full suite, zero failures
```

This arc changes no resolution and no field generation reads. **A moved scenario means
the change is wrong — do not update an expectation.**

- [ ] **Step 2: Update the docs**

`docs/architecture/05-frontend.md`: the slot inspector picks a part; `eligibility_source`
decides which pane; the preference list survives only for `authored_members`.

`plan/current-status.md`: a section in the established reflective voice — what broke,
that the smoke suite ran 183 green while it was broken and why, and the counts.

- [ ] **Step 3: Commit**

```bash
git add docs/ plan/current-status.md
git commit -m "docs: the slot inspector after the part library"
```

---

## Notes for the executor

**If the compatibility gate moves**, stop. Nothing in this arc touches resolution; a
moved BOM means something was changed that should not have been.

**Do not** add `code + params` to `validate_part`, build a Parts tab, add a
`preview-eligibility` route, or touch `length_rule`/`overlap_mm` — the last two belong
to arc B and touching them here entangles a repair with a redesign.
