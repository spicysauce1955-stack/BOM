"""The supply-problems panel (static/js/warnings.js), rendered in node.

Two of its rules cannot be reached from the browser suite:

  * the CUSTOMER sheet describes fixings and concrete rather than itemising them
    — and no UI path makes a consumable unsuppliable, because a fixing carries no
    cut length so the feasibility gate never rejects one. A browser check for an
    absent screw count would pass with the filter deleted;
  * the role reads as a WORD inside a Hebrew sentence. The browser can see the
    happy case; only here can we assert that the raw English identifier is gone
    from every surface at once.

The module is pure string-building over its arguments, so node renders it against
the real he.json exactly as the browser would.
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

// warnings.js reaches i18n/units/structure-data, whose stateful halves touch
// localStorage and the DOM at call time — stub both, and serve the REAL locale
// bundle so what node renders is what the browser renders.
globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  documentElement: {},
};
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { setLocale } from "./js/i18n.js";
import { supplyProblemsHtml } from "./js/warnings.js";

const warn = (role, code) => ({
  code, severity: "error",
  message: `english fallback for ${role}`,
  params: { role, slot_key: role, skus: "RAIL-SHORT", pegs: "span@run1:0-1500" },
  element_refs: ["span@run1:0-1500"],
});
const line = (role, qty, cut) => ({
  role, slot_key: role, engineering_qty: qty, cut_length_mm: cut,
  pegs: ["span@run1:0-1500"],
});

// a rail (a named material) and a screw (a consumable) both unsuppliable
const warnings = [warn("rail", "no_feasible_item"), warn("screw", "no_eligible_item")];
const unresolved = [line("rail", 2, 1500), line("screw", 96, null)];

const out = {};
await setLocale("he");
out.he_installer = supplyProblemsHtml(warnings, unresolved);
out.he_customer = supplyProblemsHtml(warnings, unresolved, { customer: true });
out.he_customer_named_only = supplyProblemsHtml(
  [warn("rail", "no_feasible_item")], [line("rail", 2, 1500)], { customer: true });
out.empty = supplyProblemsHtml([], []);
out.empty_customer = supplyProblemsHtml([], [], { customer: true });

// a slot key that says something the role did not must still be printed
const distinct = warn("rail", "no_feasible_item");
distinct.params = { ...distinct.params, slot_key: "bottom_rail" };
out.he_distinct_slot = supplyProblemsHtml([distinct], []);

await setLocale("en");
out.en_installer = supplyProblemsHtml(warnings, unresolved);

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def panels():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_nothing_to_report_renders_nothing(panels):
    """The callers concatenate it unconditionally, so an empty panel must be an
    empty STRING, not an empty box above the BOM."""
    assert panels["empty"] == "" and panels["empty_customer"] == ""


def test_the_installer_sheet_itemises_every_unsuppliable_part(panels):
    html = panels["he_installer"]
    assert "מסילה" in html and "בורג" in html      # rail and screw, as words
    assert ">96<" in html                          # the screw count, itemised
    assert "1500" in html


def test_the_customer_sheet_does_not_itemise_an_unsuppliable_consumable(panels):
    """`structure.js`'s whole reason for a customer detail level: an itemised
    screw count on a proposal invites an argument about the screws that were not
    used. The panel prepends itself to that sheet, so it follows the same rule."""
    html = panels["he_customer"]
    assert "בורג" not in html, "the screw is named on a customer sheet"
    assert ">96<" not in html, "the screw count is itemised on a customer sheet"
    # ... and the customer is still TOLD, both about the rail and that something
    # else is missing too
    assert "מסילה" in html and ">2<" in html
    assert "חלק מהחיזוקים או הבטון" in html


def test_the_consumable_note_appears_only_when_one_was_hidden(panels):
    assert "חלק מהחיזוקים או הבטון" not in panels["he_customer_named_only"]
    assert "מסילה" in panels["he_customer_named_only"]


def test_a_quote_is_not_mentioned_on_a_customer_sheet(panels):
    """`supply.quote_blocked` is an instruction to the estimator, not to the
    customer reading the proposal."""
    assert "הצעת מחיר" in panels["he_installer"]
    assert "הצעת מחיר" not in panels["he_customer"]


def test_the_role_reads_as_a_word_not_a_raw_english_identifier(panels):
    """`{role}` is interpolated into the middle of a Hebrew sentence. It used to
    render "אף מוצר אינו יכול לספק rail" — untranslated English in a Hebrew-first
    UI, and the headline sentence on two money views."""
    html = panels["he_installer"]
    assert "מסילה" in html
    assert ">rail<" not in html and "לספק את הrail" not in html
    # the English bundle still says "rail", from its own key
    assert "rail" in panels["en_installer"]


def test_a_slot_key_identical_to_the_role_is_not_repeated(panels):
    """M-LEGACY's one rail slot is keyed "rail", so the sentence read
    "rail in rail" and the table column read "rail rail"."""
    assert "(rail)" not in panels["he_installer"]
    assert "(rail)" not in panels["en_installer"]


def test_a_slot_key_that_adds_information_is_kept(panels):
    """The suppression must be of the REDUNDANT case, not of the field: a panel
    with a top and a bottom rail needs to say which one."""
    assert "(bottom_rail)" in panels["he_distinct_slot"]


def test_the_bay_falls_back_to_the_element_id_when_no_report_is_loaded(panels):
    """`tagOf` answers null until the structure report arrives (the BOM tab can
    render first). An element id is a poor label and an infinitely better one
    than the nothing that was there before."""
    assert "span@run1:0-1500" in panels["he_installer"]
