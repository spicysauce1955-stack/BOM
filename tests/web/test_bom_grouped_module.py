"""The grouped-BOM panel and the assembly sheet (tabs.js, panel.js), in node.

Both were reachable only through the browser suite, which checks the happy path
of each and cannot reach the cases that matter most: an unresolved line (nothing
in the demo fails to supply), an empty plan, and the escaping of catalogue text.

The one rule these two panels exist to keep is that nothing is lost — an
unresolved line and an unplaced part must both appear — and until now neither was
asserted anywhere.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { readFileSync } from "node:fs";

globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  querySelector: () => null,
  createElement: () => ({ style: {}, classList: { add() {} }, appendChild() {} }),
  documentElement: {},
};
// A real StructureReport, trimmed to the two fields its index reads (dumped
// from `build_structure` over an L of run1 + run2 meeting at n2). It is the ONE
// tag source: the schedule, the plan canvas and this panel all name an element
// from here, which is the whole point of tagging a drawing against a schedule.
const STRUCTURE = {
  run_id: "r1",
  sections: [
    { tag: "A", run_id: "run1",
      setting_out: [{ tag: "A/P1", element_id: "post@node:n1" },
                    { tag: "A/P2", element_id: "post@run1:1500" },
                    { tag: "A/P5", element_id: "post@node:n2" }],
      bays: [{ tag: "A/B1", element_id: "span@run1:0-1500" },
             { tag: "A/B2", element_id: "span@run1:1500-3000" }],
      gates: [] },
    { tag: "B", run_id: "run2",
      // the post at n2 is BORROWED by the second section and keeps A's tag
      setting_out: [{ tag: "A/P5", element_id: "post@node:n2" }],
      bays: [{ tag: "B/B1", element_id: "span@run2:0-1334" }],
      gates: [] },
  ],
};
globalThis.fetch = async (url) => ({
  ok: true,
  json: async () => (url.startsWith("/api/")
    ? STRUCTURE                                  // the structure route
    : JSON.parse(readFileSync(url, "utf8"))),    // the locale bundles, off disk
});

import { setLocale } from "./js/i18n.js";
import { setUnits } from "./js/units.js";
import { state } from "./js/state.js";
import { loadStructure } from "./js/structure-data.js";
import { groupedBomHtml } from "./js/tabs.js";
import { assemblyPlanHtml } from "./js/panel.js";

const EN = JSON.parse(readFileSync("./i18n/en.json", "utf8"));
const out = {};
await setLocale("en");

// The tag source the panel reads. `structure-data.js` had never been loaded in
// this harness, so `tagOf`/`sectionOf` answered null for everything and EVERY
// group took the unknown-element fallback — the three lookups that actually
// name a group were exercised by nothing.
state.result = { run: { id: "r1" } };
await loadStructure();

// element id -> exactly what the group head says, so an assertion can compare a
// tag rather than search for one ("A" occurs inside "A/P1" and "A/B1" too)
const heads = (html) => {
  const out = {};
  const re = /data-group="([^"]*)"[\\s\\S]*?<div class="group-head"><strong>([\\s\\S]*?)<\\/strong>/g;
  let m;
  while ((m = re.exec(html))) out[m[1]] = m[2];
  return out;
};

const PRODUCTS = {
  "RAIL-3000": { sku: "RAIL-3000", name: "Rail stock 3000 mm",
                 name_i18n: { he: 'מוט מסילה' } },
  "<script>": { sku: "<script>", name: "<img src=x onerror=alert(1)>" },
};

const GROUPED = {
  groups: [
    { kind: "section", element_id: "run1", chosen: "", rejected: [], preset: "",
      lines: [{ sku: "RAIL-3000", qty: 8, unit: "cut", role: "rail",
                slot_key: "rail", cut_length_mm: 1500, length_basis: "width" }] },
    { kind: "bay", element_id: "span@run1:0-1500", chosen: "", rejected: [], preset: "",
      lines: [{ sku: "RAIL-3000", qty: 2, unit: "cut", role: "rail",
                slot_key: "rail", cut_length_mm: 1500, length_basis: "width" }] },
    { kind: "node", element_id: "node:n1", chosen: "", rejected: [], preset: "",
      // a post shared at a node belongs to no run: the group names `node:n1`
      // and the POST standing there is `post@node:n1`
      lines: [{ sku: "POST-70", qty: 1, unit: "each", role: "post",
                slot_key: "post", cut_length_mm: null }] },
    { kind: "bay", element_id: "span@run9:0-1000", chosen: "", rejected: [],
      // an element this report does not name — the shape a stale or partial
      // report leaves behind
      preset: "", lines: [{ sku: "RAIL-3000", qty: 1, unit: "cut", role: "rail",
                slot_key: "rail", cut_length_mm: 1000, length_basis: "width" }] },
    { kind: "decision", element_id: "s0a1b2c3d4e5", chosen: "RAIL-3000",
      rejected: ["RAIL-3050"], preset: "least_cost",
      lines: [{ sku: "RAIL-3000", qty: 8, unit: "cut", role: "rail",
                slot_key: "rail", cut_length_mm: 1500, length_basis: "width" }] },
  ],
  unassigned: [], from_stock: [],
  unresolved: [{ slot_key: "slat", role: "infill", engineering_qty: 9 }],
};

out.plain = groupedBomHtml(GROUPED, PRODUCTS);
out.heads = heads(out.plain);
// the two buckets the module promises are "reported, never balanced away" —
// GROUPED leaves both empty, so that branch rendered in no test at all
out.buckets = groupedBomHtml({
  ...GROUPED,
  unassigned: [{ sku: "SCREW-S10", qty: 7, unit: "each" }],
  from_stock: [{ sku: "POST-CAP", qty: 2, unit: "each" }],
}, PRODUCTS);
out.empty = groupedBomHtml({ groups: [], unassigned: [], from_stock: [],
                             unresolved: [] }, PRODUCTS);
out.money = (out.plain.match(/[\\u20aa\\u20ac$]/g) || []).length;
out.runner_up = out.plain.includes("RAIL-3050");

// a product whose NAME is markup: catalogue text is data
out.escaped = groupedBomHtml({
  groups: [{ kind: "section", element_id: "run1", chosen: "", rejected: [],
             preset: "", lines: [{ sku: "<script>", qty: 1, unit: "each",
             role: "rail", slot_key: "r", cut_length_mm: null }] }],
  unassigned: [], from_stock: [], unresolved: [],
}, PRODUCTS);

// The SAME payload rendered in both display units. A qty is a count unless its
// unit says it is a length, and every test here had rendered in mm only — so
// pushing counts through the mm -> display converter was invisible.
const WITH_A_LENGTH = { ...GROUPED, groups: [{
  kind: "section", element_id: "run1", chosen: "", rejected: [], preset: "",
  lines: [
    { sku: "RAIL-3000", qty: 8, unit: "cut", role: "rail", slot_key: "rail",
      cut_length_mm: 1500, length_basis: "width" },
    // a product measured in mm — the one case where the number IS converted,
    // and where the unit LABEL has to travel with it
    { sku: "BAR-6000", qty: 6000, unit: "mm", role: "rail", slot_key: "bar",
      cut_length_mm: null },
  ] }], unassigned: [{ sku: "SCREW-S10", qty: 7, unit: "each" }] };
// a step whose `qty` is a COUNT of members: `StepPart` carries no unit, and its
// length is the separate field beside it
const PLAN_FOR_UNITS = { model_ref: "M@v1", unplaced: [], steps: [
  { key: "frame", kind: "assembly", text_i18n: { en: "Fit the rails." },
    parts: [{ slot_key: "rail", role: "rail", qty: 3, length_mm: 1500 }] }] };
const nums = (html) => [...html.matchAll(/class="num">([^<]*)</g)].map((m) => m[1]);
const unitCells = (html) => [...html.matchAll(/<td>(each|cut|mm|cm)<\\/td>/g)].map((m) => m[1]);
setUnits("mm");
out.mm_nums = nums(groupedBomHtml(WITH_A_LENGTH, PRODUCTS));
out.mm_units = unitCells(groupedBomHtml(WITH_A_LENGTH, PRODUCTS));
out.mm_steps = nums(assemblyPlanHtml(PLAN_FOR_UNITS));
setUnits("cm");
out.cm_nums = nums(groupedBomHtml(WITH_A_LENGTH, PRODUCTS));
out.cm_units = unitCells(groupedBomHtml(WITH_A_LENGTH, PRODUCTS));
out.cm_steps = nums(assemblyPlanHtml(PLAN_FOR_UNITS));
setUnits("mm");

await setLocale("he");
out.he_name = groupedBomHtml(GROUPED, PRODUCTS).includes("מוט מסילה");
// A decision's runner-up is a Latin sku and a preset name inside a Hebrew
// sentence. Escaping AFTER interpolating leaves them unisolated, and they
// reorder on screen beside the sentence's own parentheses.
out.he_beat = groupedBomHtml(GROUPED, PRODUCTS);
await setLocale("en");

// --- the assembly sheet ----------------------------------------------------
out.no_plan = assemblyPlanHtml(null);
const PLAN = {
  model_ref: "M-X@v1",
  steps: [
    { key: "frame", kind: "assembly", text_i18n: { en: "Fit the rails." },
      parts: [{ slot_key: "rail", role: "rail", qty: 2, length_mm: 1500,
                sku: "RAIL-3000" }] },
    { key: "cure", kind: "installation", text_i18n: { en: "Leave overnight." },
      parts: [] },
  ],
  unplaced: [{ slot_key: "slat", role: "infill", qty: 9, length_mm: 1470, sku: "S" }],
};
out.sheet = assemblyPlanHtml(PLAN);
out.sheet_escaped = assemblyPlanHtml({
  model_ref: "M@v1", unplaced: [],
  steps: [{ key: "k", kind: "assembly", text_i18n: { en: "<b>bold</b> & <img>" },
            parts: [] }],
});
// --- step scopes and the partial order -------------------------------------
// A sheet is for ONE bay, so `run` and `site` steps are carried and not drawn
// (contract obligation 12's "present-and-unrendered"), and a numbered list that
// does not say the order was a CHOICE is the flattening obligation 11 forbids.
const SCOPED = {
  model_ref: "M@v1", unplaced: [],
  unplaced_bay: [{ slot_key: "cap", role: "cap", qty: 2, belongs_to: "bay" }],
  order: { basis: "requires", unique: false, stages: [["stand"], ["frame", "setout"]],
           conflicts: [], concurrent: [], exclusive: [] },
  steps: [
    { key: "stand", kind: "assembly", scope: "post", stage: 0,
      text_i18n: { en: "Set the posts." },
      parts: [{ slot_key: "post", role: "post", qty: 2, belongs_to: "bay" }] },
    { key: "frame", kind: "assembly", scope: "panel", stage: 1,
      text_i18n: { en: "Fit the rails." },
      parts: [{ slot_key: "rail", role: "rail", qty: 2, length_mm: 1500 }] },
    { key: "setout", kind: "installation", scope: "run", stage: 1,
      text_i18n: { en: "Set the line out from the corner." }, parts: [] },
    { key: "tidy", kind: "installation", scope: "site", stage: 1,
      text_i18n: { en: "Clean down." }, parts: [] },
  ],
};
out.scoped = assemblyPlanHtml(SCOPED);
out.authored = assemblyPlanHtml({ ...SCOPED, unplaced_bay: [],
  order: { basis: "authored", unique: false, stages: [["stand", "frame"]] } });
out.only = assemblyPlanHtml({ ...SCOPED, unplaced_bay: [],
  order: { basis: "requires", unique: true, stages: [["stand"], ["frame"]] } });
out.cyclic = assemblyPlanHtml({ ...SCOPED, unplaced_bay: [],
  order: { basis: "requires", unique: false, stages: [["a", "b"]],
           conflicts: [["a", "b"]], concurrent: [], exclusive: [] } });
// an older payload has neither `order` nor `scope`: the sheet must still draw
out.legacy_shape = assemblyPlanHtml(PLAN);

out.keys = {
  unresolved: EN["bom.group_unresolved"], unplaced_prefix: EN["assembly.unplaced"].slice(0, 12),
  no_parts: EN["assembly.no_parts"],
  unassigned: EN["bom.group_unassigned"], from_stock: EN["bom.group_from_stock"],
  order_authored: EN["assembly.order_authored"], order_choice: EN["assembly.order_choice"],
  order_only: EN["assembly.order_only"],
  cycle_prefix: EN["assembly.order_cycle"].slice(0, 20),
  withheld_prefix: EN["assembly.scope_withheld"].split("{n}")[1].slice(0, 20),
  bay_prefix: EN["assembly.unplaced_bay"].slice(0, 20),
  scope_post: EN["assembly.step_scope.post"],
};

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def rendered():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- the grouped BOM ---------------------------------------------------------

def test_a_line_nothing_can_supply_appears_in_the_grouped_view(rendered):
    """The finding the architecture review raised: `unresolved` was carried by
    the API and rendered by nothing, and an unresolved line PEGS to a section —
    so a section missing a part read as complete in the one view built to show
    what a section needs."""
    assert rendered["keys"]["unresolved"] in rendered["plain"]
    assert "slat" in rendered["plain"]


def test_no_group_carries_money(rendered):
    """A purchase is pooled across the whole job, so a per-section price would be
    an apportionment nothing measured."""
    assert rendered["money"] == 0


def test_a_decision_group_names_the_runner_up_it_beat(rendered):
    """"Cheaper than the others" is not an explanation. This is the view that
    raises the question, so it is where the answer belongs."""
    assert rendered["runner_up"]


def test_a_product_name_is_data_and_never_markup(rendered):
    """Catalogue text is authored by a person and rendered to everyone who opens
    the project."""
    assert "<img src=x" not in rendered["escaped"]
    assert "&lt;img src=x" in rendered["escaped"]


def test_a_product_name_follows_the_readers_language(rendered):
    """It bypassed `name_i18n`, so the Hebrew UI printed "Rail stock 3000 mm"
    directly above "מוט מסילה" for one sku."""
    assert rendered["he_name"]


def test_nothing_grouped_renders_nothing(rendered):
    """An empty panel with a heading reads as an answer. There is no answer to
    give before a fence is generated."""
    assert rendered["empty"] == ""


# --- the assembly sheet ------------------------------------------------------

def test_a_model_with_no_order_shows_no_sheet(rendered):
    assert rendered["no_plan"] == ""


def test_a_step_that_fits_nothing_says_so_rather_than_looking_empty(rendered):
    assert rendered["keys"]["no_parts"] in rendered["sheet"]


def test_a_part_no_step_fits_is_called_out(rendered):
    """The governing property, on screen: a sheet that quietly omits the boards
    reads as a finished panel to the person holding it."""
    assert rendered["keys"]["unplaced_prefix"] in rendered["sheet"]
    assert "slat" in rendered["sheet"]


def test_installation_steps_are_distinguishable_from_assembly_ones(rendered):
    """They are different instructions — one fits a part, the other is about the
    job — and the CSS hangs off this attribute."""
    assert 'data-kind="installation"' in rendered["sheet"]
    assert 'data-kind="assembly"' in rendered["sheet"]


def test_an_authors_prose_is_escaped(rendered):
    """`text_i18n` is expert-authored and goes to `innerHTML`."""
    assert "<b>bold</b>" not in rendered["sheet_escaped"]
    assert "&lt;b&gt;bold&lt;/b&gt;" in rendered["sheet_escaped"]


def test_the_two_buckets_it_promises_never_to_hide_are_rendered(rendered):
    """"Reported, never balanced away" is the module's own phrase, and the
    fixture left both lists empty — so the branch that renders them appeared in
    no test. A `bucket()` that dropped every row passed."""
    assert rendered["keys"]["unassigned"] in rendered["buckets"]
    assert rendered["keys"]["from_stock"] in rendered["buckets"]
    assert "SCREW-S10" in rendered["buckets"] and "POST-CAP" in rendered["buckets"]
    assert ">7<" in rendered["buckets"].replace(" ", "")


def test_a_quantity_lands_in_the_quantity_column(rendered):
    """No test at any level read a NUMBER out of this table — so a renderer that
    printed the cut length where the quantity belongs passed everything."""
    plain = rendered["plain"].replace("\n", " ")
    assert 'class="num">2<' in plain, "the bay's rail quantity"
    assert 'class="num">8<' in plain, "the section's rail quantity"


def test_each_group_is_addressable_by_what_it_is(rendered):
    """`data-group` and `data-kind` are what a later click-through and the
    browser check both hang off."""
    assert 'data-group="span@run1:0-1500"' in rendered["plain"]
    assert 'data-kind="bay"' in rendered["plain"]
    assert 'data-kind="decision"' in rendered["plain"]


def test_each_kind_of_group_is_named_by_the_tag_its_OWN_id_resolves_to(rendered):
    """Three kinds of id, one tag source, three different lookups: a section's
    `element_id` is a RUN id (which the element index does not hold), a node's
    names the post standing there (`post@<node>`), and a bay's IS an element id.
    Getting one wrong is not a crash — it is `run1` printed in the panel where
    the schedule and both drawings say `A`, a third name for one thing, which is
    exactly what a single tag source exists to prevent.

    Asserted as equality per group: "some tag appeared" would pass with the
    section head printing the bay's."""
    heads = rendered["heads"]
    assert heads["run1"] == "A", "a section is named by its SECTION tag"
    assert heads["node:n1"] == "A/P1", "a node is named by the post standing there"
    assert heads["span@run1:0-1500"] == "A/B1", "a bay's key is already an element id"


def test_an_element_the_tag_source_cannot_name_still_says_which_element_it_is(rendered):
    """A stale or partial report leaves groups whose element it never tagged. A
    blank head reads as "no section"; the raw id is at least the machine identity
    the user can match against, isolated so RTL cannot reorder it."""
    assert rendered["heads"]["span@run9:0-1000"] == "<bdi>span@run9:0-1000</bdi>"


def test_a_count_is_not_a_length_and_survives_the_display_unit(rendered):
    """The defect this closes, and the reason it hid: every test here rendered in
    mm, where the mm -> display converter is the identity. `fmt` is that
    converter and nothing else, so putting a COUNT through it reported `0.8 each`
    to anyone who had switched the app to cm — wrong by a factor of ten, in the
    one table built to answer "what does this section need", while the priced
    table on the same screen said 8.

    A count is the same number in every display unit. Only the mm-unit line
    moves."""
    counts = [n for n in rendered["mm_nums"] if n in ("8", "7")]
    assert counts == ["8", "7"], "the fixture must carry a count in a group and in a bucket"
    assert [n for n in rendered["cm_nums"] if n in ("8", "7")] == counts
    assert rendered["mm_steps"] == ["3"] and rendered["cm_steps"] == ["3"], \
        "a step fits three rails whatever unit the reader prefers"


def test_a_length_qty_converts_with_its_label_or_neither(rendered):
    """The other half, and the one that reads as a contradiction on screen: when
    the unit IS `mm` the number must convert AND the label must be swapped for
    the reader's. Converting the number alone put `600` under a literal `mm`
    beside a priced table saying `600 cm` for the same line."""
    assert "6000" in rendered["mm_nums"] and "mm" in rendered["mm_units"]
    assert "600" in rendered["cm_nums"] and "cm" in rendered["cm_units"], \
        "the number moved to cm, so the label must too"
    assert "mm" not in rendered["cm_units"], "a converted figure under a literal mm"


def test_a_runner_up_sku_is_direction_isolated_in_a_hebrew_sentence(rendered):
    """`esc(t(key, params))` escapes AFTER interpolating, which leaves a Latin
    sku unisolated inside a Hebrew sentence — and this one sits in parentheses,
    which mirror. Asserted against the bundle's own shape rather than the copy,
    so rewording is not a regression."""
    assert "<bdi>RAIL-3050</bdi>" in rendered["he_beat"]
    assert "<bdi>least_cost</bdi>" in rendered["he_beat"]


def test_the_unresolved_bucket_states_how_many_are_missing(rendered):
    """Its quantity was pinned nowhere: mapping it to `qty: 0` left every test
    green while the panel told a reader that a part it could not supply is needed
    zero times — which reads as "nothing is missing", the exact opposite of what
    this bucket exists to say."""
    assert ">9<" in rendered["plain"].replace(" ", "")


def test_a_product_name_carries_its_own_direction(rendered):
    """Catalogue text is expert-authored and may be Hebrew or Latin in either
    UI; the priced table marks the same field `dir="auto"` and the grouped copy
    dropped it."""
    assert 'dir="auto"' in rendered["plain"]


# --- step scopes, and an order that is one of several ------------------------

def test_a_run_or_site_step_is_carried_but_not_drawn_on_a_panel_sheet(rendered):
    """Contract obligation 12: `run` and `site` are present-and-unrendered until
    phase two. Drawing "set the whole line out" on a sheet for one bay would
    claim a per-bay instruction that is not one; dropping it silently would make
    the sheet disagree with the model it was rendered from, so the sheet SAYS how
    many it withheld."""
    html = rendered["scoped"]
    assert 'data-step="frame"' in html and 'data-step="stand"' in html
    assert 'data-step="setout"' not in html and 'data-step="tidy"' not in html
    assert rendered["keys"]["withheld_prefix"] in html


def test_a_step_that_is_not_about_the_panel_says_which_scope_it_is(rendered):
    """A post step and a panel step read identically as sentences. The reader is
    standing at one bay and needs to know which of the two they are looking at."""
    assert rendered["keys"]["scope_post"] in rendered["scoped"]
    assert 'data-scope="post"' in rendered["scoped"]


def test_the_sheet_says_when_the_order_is_one_of_several(rendered):
    """The failure obligation 11 names, on screen. A numbered list reads as THE
    order; after `requires` it is one linearisation of a partial order, and a
    fitter planning a crew around a sequence the model never claimed is the whole
    cost of not saying so."""
    assert rendered["keys"]["order_choice"] in rendered["scoped"]
    assert 'data-unique="0"' in rendered["scoped"]


def test_print_order_is_not_dressed_up_as_a_dependency(rendered):
    """A model with no `requires` asserts nothing about its order, and the sheet
    must not imply it did. Three distinct sentences, and this is the one that
    would be easiest to drop into "one of several"."""
    assert rendered["keys"]["order_authored"] in rendered["authored"]
    assert rendered["keys"]["order_choice"] not in rendered["authored"]
    assert 'data-order="authored"' in rendered["authored"]


def test_a_single_valid_order_is_allowed_to_say_it_is_the_only_one(rendered):
    assert rendered["keys"]["order_only"] in rendered["only"]
    assert 'data-unique="1"' in rendered["only"]


def test_a_circle_of_prerequisites_is_shown_as_a_warning(rendered):
    """It is refused at authoring, so seeing one means an invalid draft is being
    previewed — which is exactly the moment the author needs telling."""
    assert rendered["keys"]["cycle_prefix"] in rendered["cyclic"]


def test_a_bay_part_no_step_places_is_called_out_like_a_panel_member(rendered):
    """Obligation 9's shape, one level out: a model that stands the posts and
    forgets the caps has an incomplete procedure, and the sheet is where a fitter
    would otherwise believe the bay finished."""
    assert rendered["keys"]["bay_prefix"] in rendered["scoped"]
    assert "cap" in rendered["scoped"]


def test_a_payload_without_the_new_fields_still_renders(rendered):
    """A plan from an older response carries no `order` and no `scope`. The sheet
    is the whole Panel tab's last section — a throw here takes the parts table
    and the price with it."""
    assert 'data-step="frame"' in rendered["legacy_shape"]
    assert rendered["keys"]["order_authored"] not in rendered["legacy_shape"]
