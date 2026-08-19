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
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { setLocale } from "./js/i18n.js";
import { groupedBomHtml } from "./js/tabs.js";
import { assemblyPlanHtml } from "./js/panel.js";

const EN = JSON.parse(readFileSync("./i18n/en.json", "utf8"));
const out = {};
await setLocale("en");

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
    { kind: "decision", element_id: "s0a1b2c3d4e5", chosen: "RAIL-3000",
      rejected: ["RAIL-3050"], preset: "least_cost",
      lines: [{ sku: "RAIL-3000", qty: 8, unit: "cut", role: "rail",
                slot_key: "rail", cut_length_mm: 1500, length_basis: "width" }] },
  ],
  unassigned: [], from_stock: [],
  unresolved: [{ slot_key: "slat", role: "infill", engineering_qty: 9 }],
};

out.plain = groupedBomHtml(GROUPED, PRODUCTS);
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

await setLocale("he");
out.he_name = groupedBomHtml(GROUPED, PRODUCTS).includes("מוט מסילה");
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
out.keys = {
  unresolved: EN["bom.group_unresolved"], unplaced_prefix: EN["assembly.unplaced"].slice(0, 12),
  no_parts: EN["assembly.no_parts"],
  unassigned: EN["bom.group_unassigned"], from_stock: EN["bom.group_from_stock"],
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
