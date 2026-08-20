"""The slot pane's four shapes, rendered — in node, against the real payloads.

Spec §7. The pane branches on `eligibility_source` before it renders anything, and
until this file existed nothing but a human with a browser could tell whether it
branched CORRECTLY: the JS logic tests cover `partSummary`, and the Python tests
cover what the server will accept, and the regression this arc repairs lived in the
gap between them — a pane that read the document right and then drew the wrong
controls for it.

So `renderInspector` is driven for real, over a DOM stub with just enough of an
Element to build detached nodes, and the four panes are asserted on the elements
that distinguish them. The stub is deliberately small: it is not a browser, and the
things only a browser can answer (layout, direction, a click that reaches a
listener through the page) belong to `tools/ui_smoke.py`, which Task 5 extends.

The payloads come from the real library, the real models and a real preview,
interpolated into the script — the pattern `test_part_drawer_module.py` established
— so a field renamed on the wire fails here rather than emptying a pane in a browser
nobody is watching.
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

# A DOM stub, not a DOM. Every node the inspector builds is DETACHED — that is the
# pane's own contract ("`renderInspector` fills the host it is handed and reaches
# for no global id") — so what it needs from a document is createElement, a tree,
# and textContent. Anything more would be re-implementing a browser to test code
# whose whole discipline is not needing one.
STUB = """
class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.style = {};
    this.selected = false;
    this._text = "";
    this.className = "";
    this.classList = { add: (c) => { this.className = `${this.className} ${c}`.trim(); },
                       remove: () => {} };
  }
  get textContent() {
    return this._text + this.children.map((c) => c.textContent).join(" ");
  }
  set textContent(v) { this._text = String(v); this.children = []; }
  set innerHTML(v) { if (v === "") this.children = []; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  appendChild(c) { this.children.push(c); return c; }
  append(...cs) { for (const c of cs) if (c) this.children.push(c); }
  addEventListener(ev, fn) { (this._on ??= {})[ev] = fn; }
  fire(ev) { this._on?.[ev]?.({ preventDefault() {} }); }
  querySelector(tag) {
    for (const c of this.children) {
      if (c.tagName === tag.toUpperCase()) return c;
      const found = c.querySelector(tag);
      if (found) return found;
    }
    return null;
  }
  querySelectorAll() { return []; }
  get value() { return this._value ?? ""; }
  set value(v) { this._value = v; }
}

globalThis.document = {
  createElement: (tag) => new El(tag),
  createElementNS: (_ns, tag) => new El(tag),
  getElementById: () => null,
  querySelectorAll: () => [],
  documentElement: new El("html"),
};
globalThis.fetch = async (url) => ({
  ok: true,
  json: async () => JSON.parse(
    readFileSync(new URL(url, import.meta.url), "utf8")),
});

const flat = (node, out = []) => {
  out.push(node);
  for (const c of node.children) flat(c, out);
  return out;
};
const attr = (node, name, value = null) => flat(node).filter(
  (n) => n.attrs[name] !== undefined && (value === null || n.attrs[name] === value));
const cls = (node, name) => flat(node).filter(
  (n) => n.className.split(" ").includes(name));
"""

SCRIPT = """
import { readFileSync } from "node:fs";
%(stub)s
const { renderInspector } = await import("./js/panel-inspector.js");
const { loadLocale } = await import("./js/i18n.js");
const { state } = await import("./js/state.js");
await loadLocale("en");
await loadLocale("he");

const parts = %(parts)s;
const partTypes = %(types)s;
const models = %(models)s;
const preview = %(preview)s;
const vinylPreview = %(vinylPreview)s;
const out = {};

function pane(model, selection, { locale = "he", preview: pv = null,
                                  parts: ps = parts } = {}) {
  state.locale = locale;
  const host = new El("div");
  renderInspector(host, {
    selection, spec: model.default_spec, model, products: {}, parts: ps,
    partTypes, elevation: pv?.elevation, preview: pv,
  });
  return host;
}

function shape(host) {
  const picker = attr(host, "data-f", "part")[0] || null;
  const candidates = attr(host, "data-candidates")[0] || null;
  return {
    picker: !!picker,
    picked: picker ? picker.value : null,
    // the select's value is not set by the stub's option handling, so the pane's
    // OWN answer is which option it marked selected
    selected: picker
      ? flat(picker).filter((n) => n.tagName === "OPTION" && n.selected)
                    .map((n) => n.attrs.value ?? "") : [],
    selectedText: picker
      ? flat(picker).filter((n) => n.tagName === "OPTION" && n.selected)
                    .map((n) => n._text) : [],
    options: picker
      ? flat(picker).filter((n) => n.tagName === "OPTION" && n.attrs.value)
                    .map((n) => n.attrs.value) : [],
    chips: attr(host, "data-chip").map((n) => [n.attrs["data-chip"], n.textContent]),
    candidates: candidates ? candidates.attrs["data-candidates"] : null,
    prefList: cls(host, "pref-box").length > 0,
    roleControl: attr(host, "data-f", "role").length > 0,
    widthField: attr(host, "data-f", "width_mm").length > 0,
    thicknessField: attr(host, "data-f", "thickness_mm").length > 0,
    dims: attr(host, "data-dim").map((n) => [n.attrs["data-dim"], n.textContent]),
    text: host.textContent.replace(/\\s+/g, " ").trim(),
  };
}

const slat = models["M-SLAT"];
const railKey = slat.default_spec.frame[0].key;
const boardKey = slat.default_spec.infill.pattern[0].key;

// --- the four shapes ---------------------------------------------------------
out.part = shape(pane(slat, { kind: "frame", key: railKey }, { preview }));
out.board = shape(pane(slat, { kind: "infill", key: boardKey }, { preview }));
out.predicate = shape(pane(models.vinyl, { kind: "post", key: "post" }));
// ... and the same pane over a preview that ANSWERED. `preview_panel` emits rows
// for frame, infill and fixings only, so the post and the cap have no row — the
// count must be absent rather than zero.
out.predicateCounted = shape(pane(models.vinyl, { kind: "post", key: "post" },
                                  { preview: vinylPreview }));
out.vinylRail = shape(pane(models.vinyl,
  { kind: "frame", key: models.vinyl.default_spec.frame[0].key },
  { preview: vinylPreview }));
out.members = shape(pane(models.legacy,
  { kind: "frame", key: models.legacy.default_spec.frame[0].key }));

// ... and the fourth: a slot the "+ Add" button just made
const fresh = JSON.parse(JSON.stringify(slat));
const freshSlot = fresh.default_spec.frame[0];
freshSlot.requirement.part_id = "";
freshSlot.requirement.role = "rail";
out.unspecified = shape(pane(fresh, { kind: "frame", key: railKey }));

// every pane, in both languages, with no raw key left on screen
out.rawKeys = [];
for (const locale of ["he", "en"]) {
  for (const [model, selection] of [
    [slat, { kind: "frame", key: railKey }],
    [slat, { kind: "infill", key: boardKey }],
    [slat, { kind: "fixing", key: slat.default_spec.fixings[0].key }],
    [slat, { kind: "panel", key: null }],
    [models.vinyl, { kind: "post", key: "post" }],
    [models.legacy, { kind: "frame",
                      key: models.legacy.default_spec.frame[0].key }],
  ]) {
    const host = pane(model, selection, { locale, preview });
    out.rawKeys.push(...(host.textContent.match(/model\\.[a-z_.]+/g) || []));
  }
}

// --- naming a part is ONE act ------------------------------------------------
const doc = JSON.parse(JSON.stringify(slat));
const member = doc.default_spec.infill.pattern[0];
member.requirement.part_id = "";
member.requirement.role = "infill";
member.requirement.eligibility = { members: [] };
member.width_mm = 100;
member.thickness_mm = 20;
const host = pane(doc, { kind: "infill", key: boardKey });
const picker = attr(host, "data-f", "part")[0];
picker.value = "infill-slat-100";
picker.fire("change");
out.write = { part_id: member.requirement.part_id, role: member.requirement.role,
              members: member.requirement.eligibility.members.length,
              width_mm: member.width_mm, thickness_mm: member.thickness_mm };
out.beforeWrite = { widthField: attr(host, "data-f", "width_mm").length > 0 };

// --- two versions of one part ------------------------------------------------
// `/api/parts` returns every version ascending, drafts and retired included, and
// the document names the id alone — so the pane has to resolve the same version
// the generator will.
const v1 = parts.find((p) => p.id === "rail-38-vinyl");
const versioned = [
  ...parts,
  { ...v1, version: 2, status: "active",
    spec: [{ key: "width_mm", value: 44, agree: "==", unit: "mm" }] },
  { ...v1, version: 3, status: "draft",
    spec: [{ key: "width_mm", value: 99, agree: "==", unit: "mm" }] },
];
const twoVersions = JSON.parse(JSON.stringify(slat));
twoVersions.default_spec.frame[0].requirement.part_id = "rail-38-vinyl";
out.versioned = shape(pane(twoVersions, { kind: "frame", key: railKey },
                           { locale: "en", parts: versioned }));

// a part whose only version is a DRAFT still exists, and reads as itself
const draftOnly = [...parts, { ...v1, id: "rail-draft-only", version: 1,
                               status: "draft" }];
const namesDraft = JSON.parse(JSON.stringify(slat));
namesDraft.default_spec.frame[0].requirement.part_id = "rail-draft-only";
out.draftOnly = shape(pane(namesDraft, { kind: "frame", key: railKey },
                           { locale: "en", parts: draftOnly }));

// --- a part the library does not have ----------------------------------------
const gone = JSON.parse(JSON.stringify(slat));
gone.default_spec.frame[0].requirement.part_id = "no-such-part";
out.missing = shape(pane(gone, { kind: "frame", key: railKey },
                         { locale: "en" }));

console.log(JSON.stringify(out));
"""


def _payload() -> str:
    library = PartLibrary(parts=demo_parts())
    models = demo_models()
    preview = preview_panel(
        models["M-SLAT"], PreviewRequest(height_mm=1800, width_mm=2400),
        demo_catalog(), part_library=library)
    # named by SHAPE rather than by id: the point of each is which eligibility
    # source it carries, and an id in the assertions below hides that
    vinyl = next(m for k, m in models.items() if "VINYL" in k)
    legacy = next(m for k, m in models.items() if "LEGACY" in k)
    vinyl_preview = preview_panel(
        vinyl, PreviewRequest(height_mm=1800, width_mm=2400),
        demo_catalog(), part_library=library)
    return SCRIPT % {
        "stub": STUB,
        "vinylPreview": vinyl_preview.model_dump_json(),
        "parts": json.dumps([p.model_dump() for p in library.parts]),
        "types": json.dumps([
            {"key": k, "label_i18n": {"en": k, "he": k}}
            for k in sorted({p.type for p in library.parts})]),
        "models": json.dumps({"M-SLAT": models["M-SLAT"].model_dump(),
                              "vinyl": vinyl.model_dump(),
                              "legacy": legacy.model_dump()}),
        "preview": preview.model_dump_json(),
    }


@pytest.fixture(scope="module")
def pane():
    if not shutil.which("node"):
        pytest.skip("node not available")
    script = STATIC / "_inspector_test.mjs"
    script.write_text(_payload())
    try:
        proc = subprocess.run(["node", str(script)], capture_output=True,
                              text=True, cwd=STATIC, timeout=60)
    finally:
        script.unlink()
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_slot_that_names_a_part_shows_the_part_its_facts_and_its_candidates(pane):
    """The shape the whole arc is about, and the one that was broken: a slot whose
    part the library HAS must read as that part, not as "no product"."""
    part = pane["part"]
    assert part["picker"], part
    # the part the document names, and its NAME rather than its id
    assert part["selected"] == ["rail-rail-3000"], part["selected"]
    assert part["selectedText"] and "rail-rail-3000" not in part["selectedText"][0]
    assert part["chips"], "the part's declared facts are what make the name mean something"
    # off the preview's `eligible_skus`, not a request of its own
    assert int(part["candidates"]) >= 1


def test_a_slot_chosen_by_a_rule_says_so_and_offers_no_part(pane):
    """M-VINYL's post: its predicate agrees with a fact about the BAY, which no
    `SpecField` can state — so there is no part to offer, and offering one would
    author the pair `_part_or_authored` refuses."""
    assert pane["predicate"]["picker"] is False
    assert "כלל" in pane["predicate"]["text"]      # "…by a rule, not a part"
    assert pane["predicate"]["prefList"] is False


def test_a_slot_the_preview_never_answered_for_prints_no_count(pane):
    """M-VINYL's post, over a REAL preview of M-VINYL. `preview_panel` emits rows
    for the frame, the infill and the fixings — never for the post or the cap — so
    the candidate count for those two is UNKNOWN, not zero. It used to print "0
    products can fill this" about a supply nobody measured, on the two slots the
    rule-authored pane exists for: a zero reads as a measurement, and that one was
    a report of an absent question."""
    assert pane["predicateCounted"]["candidates"] is None, pane["predicateCounted"]
    # and it is suppression of the UNANSWERED, not of the pane: the same model's
    # rail has a row, and still says how many products can fill it
    assert int(pane["vinylRail"]["candidates"]) >= 1


def test_a_slot_with_an_authored_sku_list_keeps_its_list_and_offers_no_part(pane):
    """M-LEGACY's rail: its members are rebuilt per run from company knowledge, so
    a part would outrank the rule silently. The preference list stays — this is the
    one shape that still has one to edit."""
    members = pane["members"]
    assert members["picker"] is False
    assert "RAIL-3000" in members["text"]
    assert members["prefList"] is True


def test_a_slot_that_names_nothing_asks_for_a_part(pane):
    fresh = pane["unspecified"]
    assert fresh["picker"] is True
    # the empty entry is the PROMPT, not a value — an author landing on a fresh
    # slot must never read a part they did not choose
    assert fresh["selected"] == [""]
    assert fresh["chips"] == []


def test_no_pane_offers_the_role_control(pane):
    """The regression itself. `role` is the part's, `_part_or_authored` refuses a
    slot that authors one beside a part, and the control that wrote it is gone."""
    for name in ("part", "board", "predicate", "members", "unspecified"):
        assert pane[name]["roleControl"] is False, name


def test_no_pane_leaves_a_raw_locale_key_on_screen(pane):
    """Six panes, both languages. A computed key that lost its bundle entry renders
    as itself, which no key-parity test can see."""
    assert pane["rawKeys"] == []


def test_naming_a_part_clears_everything_the_part_now_owns(pane):
    """One act, three objects. `role` and the eligibility are on the requirement and
    `_part_or_authored` refuses them; `width_mm` and `thickness_mm` are on the
    HOLDER and `_refuse_authored_dimensions` refuses those — the same defect one
    level up, and the one a half-applied write would leave behind."""
    assert pane["write"] == {
        "part_id": "infill-slat-100", "role": "", "members": 0,
        "width_mm": 0, "thickness_mm": 0,
    }


def test_the_width_field_is_offered_only_while_the_member_owns_the_width(pane):
    """A width field on a member whose part declares the width is an invitation to
    a 422 the author cannot connect to anything they did."""
    assert pane["beforeWrite"]["widthField"] is True       # names no part yet
    assert pane["board"]["widthField"] is False            # names `infill-slat-100`
    assert pane["board"]["thicknessField"] is False
    # ... and the number is not hidden with the field: it is shown, read-only
    assert dict(pane["board"]["dims"])["width_mm"].strip() == "100"


def test_the_frame_slot_shows_the_thickness_its_part_owns(pane):
    """`FrameSlot.thickness_mm` is refused beside a part on the same terms. Its part
    declares none, so the pane says undeclared rather than drawing a zero."""
    assert dict(pane["part"]["dims"])["thickness_mm"].strip() == "—"


def test_the_pane_resolves_the_same_version_the_generator_will(pane):
    """`part_id` is unpinned, so `latest_active` is what a bare id MEANS. Showing
    v1's facts beside a bay priced against v2 is two answers to one question, and
    listing an id once per version is a duplicate the author has to guess between."""
    versioned = pane["versioned"]
    assert "@v2" in versioned["text"], versioned["text"]
    # v3 is a DRAFT: newer, and not what a bare id resolves to
    assert "44" in dict(versioned["chips"])["=="]
    assert "99" not in versioned["text"]
    # one option per id, whatever the library holds
    assert len(versioned["options"]) == len(set(versioned["options"]))


def test_a_part_that_has_only_ever_been_a_draft_still_exists(pane):
    """The fallback. Reading it as missing would send the author to a repair that is
    not the one they need — the part is there, it has simply not been published."""
    assert pane["draftOnly"]["picker"] is True
    assert "not in the library" not in pane["draftOnly"]["text"]
    assert "not published" in pane["draftOnly"]["text"]


def test_a_part_the_library_does_not_have_is_reported_not_blanked(pane):
    assert "no-such-part" in pane["missing"]["text"]
    assert "not in the library" in pane["missing"]["text"]
