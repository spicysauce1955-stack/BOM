"""A change in a job's history, as a sentence (static/js/change-text.js).

Every code the backend can emit is rendered against the REAL locale bundles in
both languages, and no `{placeholder}` may survive: a sentence that prints
`{from_mm}` is the failure mode a code-plus-params registry exists to prevent,
and it is invisible to a test that only checks the key exists.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.project.changes import CHANGE_CODES

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

#: One value for every param name any code carries. A code reads the ones it
#: needs; a placeholder whose param is missing here would survive and fail.
PARAMS = {
    "section": "B", "name": "Levi", "from": "Herzl 12", "to": "Herzl 14",
    "from_mm": 1800, "to_mm": 1750, "value_mm": 1000, "start_mm": 0, "end_mm": 6000,
    "at_mm": 4000, "length_mm": 9000, "from_state": "waiting", "to_state": "planning",
    "from_person": None, "to_person": "u_yossi", "run_id": "run_1",
    "landmark": "house", "label": "", "surface": "soil", "from_surface": "masonry_wall",
    "to_surface": "soil", "model": "M-SLAT", "from_model": None, "to_model": "M-SLAT",
    "text": "level with the neighbour", "area": "posts", "value": True,
}


def _changes() -> list[dict]:
    out = []
    for code in sorted(CHANGE_CODES):
        params = dict(PARAMS)
        params["what"] = "sale_read" if code == "acknowledged" else "no_gates"
        out.append({"code": code, "params": params})
    return out


SCRIPT = """
globalThis.localStorage = {
  s: {},
  getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = { getElementById: () => null, querySelectorAll: () => [],
                        documentElement: {} };
import { readFileSync } from "node:fs";
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { initI18n, setLocale } from "./js/i18n.js";
import { setUnits } from "./js/units.js";
import { actorName, changeHtml, isMilestone } from "./js/change-text.js";

const CHANGES = __CHANGES__;
const names = { "user:u_yossi": "Yossi", u_yossi: "Yossi" };
await initI18n();
const out = {};
for (const lang of ["en", "he"]) {
  await setLocale(lang);
  out[lang] = Object.fromEntries(CHANGES.map((c) => [c.code, changeHtml(c, { names })]));
}
await setLocale("en");
out.escaped = changeHtml({ code: "note_added",
                           params: { text: "<b>bold</b> & co", section: "" } });
out.unknown = changeHtml({ code: "not_a_code", params: {} });
out.blank_from = changeHtml({ code: "address_changed", params: { from: "", to: "Herzl 14" } });
out.blank_section = changeHtml({ code: "gate_added", params: { section: "", value_mm: 1000 } });
out.unstated = changeHtml({ code: "stated_changed", params: { what: "no_gates", value: false } });
out.braces = changeHtml({ code: "note_added",
                          params: { text: "check {section} and {to_mm}", section: "B" } });
out.gone = changeHtml({ code: "gate_moved", params: { section: "B", run: "side",
                                                      section_gone: true } });
setUnits("cm");
out.cm = changeHtml({ code: "height_changed", params: {
  section: "B", from_mm: 1800, to_mm: 1750, start_mm: 0, end_mm: 6000 } });
setUnits("mm");
out.actor = [actorName("user:u_yossi", names), actorName("user:u_gone", names),
             actorName("seed", names), actorName("agent:advisor", names)];
out.milestone = [isMilestone({ code: "status_changed" }),
                 isMilestone({ code: "height_changed" })];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def rendered():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = SCRIPT.replace("__CHANGES__", json.dumps(_changes()))
    proc = subprocess.run([node, "--input-type=module", "-e", script],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("lang", ["en", "he"])
def test_every_code_renders_with_no_placeholder_left(lang, rendered):
    leftover = {code: html for code, html in rendered[lang].items()
                if "{" in html or "change." in html}
    assert not leftover, leftover


def test_the_owners_example_reads_as_a_sentence(rendered):
    assert rendered["en"]["height_changed"] == (
        "Section <bdi>B</bdi>: height <bdi>1800</bdi> → <bdi>1750</bdi> <bdi>mm</bdi> "
        "(<bdi>0</bdi>–<bdi>6000</bdi> <bdi>mm</bdi>)")
    assert rendered["he"]["height_changed"].startswith("מקטע <bdi>B</bdi>: גובה <bdi>1800</bdi> ←")


def test_words_are_looked_up_not_shown_raw(rendered):
    assert "<bdi>waiting</bdi>" in rendered["en"]["status_changed"]
    assert "<bdi>ממתין</bdi>" in rendered["he"]["status_changed"]
    assert "masonry wall" in rendered["en"]["base_changed"]
    assert "<bdi>posts placed by hand</bdi>" in rendered["en"]["area_changed"]


def test_a_person_is_named_and_nobody_is_said(rendered):
    assert rendered["en"]["assignee_changed"] == (
        "Assigned to: <bdi>nobody</bdi> → <bdi>Yossi</bdi>")


def test_a_blank_reads_as_a_dash(rendered):
    assert "<bdi>—</bdi> → <bdi>M-SLAT</bdi>" in rendered["en"]["default_model_changed"]


def test_a_notes_text_is_escaped(rendered):
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; co" in rendered["escaped"]
    assert "<b>" not in rendered["escaped"]


def test_lengths_follow_the_readers_unit(rendered):
    assert "<bdi>180</bdi> → <bdi>175</bdi> <bdi>cm</bdi>" in rendered["cm"]


def test_an_unknown_code_still_says_something_true(rendered):
    # the fallback sentence, never the raw key it failed to find
    assert rendered["unknown"] == "Changed: <bdi>not_a_code</bdi>"


def test_a_note_that_contains_braces_is_shown_as_written(rendered):
    """One pass over the template: a param's VALUE is never searched for more
    placeholders, so the salesperson's words are not rewritten."""
    assert "check {section} and {to_mm}" in rendered["braces"]


def test_a_section_no_longer_drawn_says_so(rendered):
    assert rendered["gone"] == "Section <bdi>B (no longer drawn)</bdi>: gate moved"


def test_a_stated_claim_reads_yes_or_no_the_right_way_round(rendered):
    assert rendered["en"]["stated_changed"] == "Stated: <bdi>no gates</bdi> — <bdi>yes</bdi>"
    assert rendered["unstated"] == "Stated: <bdi>no gates</bdi> — <bdi>no</bdi>"


def test_a_landmark_is_named_in_the_readers_language(rendered):
    assert rendered["en"]["landmark_added"] == "Property: <bdi>House</bdi> added"
    assert "<bdi>בית</bdi>" in rendered["he"]["landmark_added"]


def test_a_blank_value_or_section_reads_as_a_dash(rendered):
    assert rendered["blank_from"] == "Address: <bdi>—</bdi> → <bdi>Herzl 14</bdi>"
    assert rendered["blank_section"].startswith("Section <bdi>—</bdi>:")


def test_who_did_it(rendered):
    assert rendered["actor"] == ["Yossi", "u_gone", "the system", "the system"]


def test_a_status_change_is_the_line_across_the_list(rendered):
    assert rendered["milestone"] == [True, False]
