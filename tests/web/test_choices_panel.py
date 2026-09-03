"""The choices panel's two pieces of arithmetic-shaped logic (static/js/choices.js).

The renderer is DOM and belongs in the smoke suite. `deltaLabel` and
`valueLabel` are the parts that are wrong at 3 a.m. — a sign, a plural, and an
obligation.

The bundle is served for real (the same stub `test_units_module.py` uses) rather
than faked: a test that stubbed `{u}` would pass while the shipped en.json was
missing `choices.value`, and every footing figure on screen would read
"610 choices.value". `deltaLabel`'s words come out of the same file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
globalThis.localStorage = {
  s: {},
  getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = { getElementById: () => null, querySelectorAll: () => [],
                        querySelector: () => null, documentElement: {} };
import { readFileSync } from "node:fs";
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { state } from "./js/state.js";
import { initI18n, setLocale } from "./js/i18n.js";
import { deltaLabel, valueLabel } from "./js/choices.js";

await initI18n();
// the app OPENS in Hebrew, so pin the language before anything reads a word or
// this file would be asserting whatever the default happens to be today
await setLocale("en");
state.units = "mm";

const out = {
  saving: deltaLabel({delta: {posts: -3, boards: -5}}),
  none: deltaLabel({delta: {}}),
  zeros: deltaLabel({delta: {posts: 0}}),
  worse: deltaLabel({delta: {cuts: 20}}),
  singular: deltaLabel({delta: {posts: -1, holes: 1}}),
  concrete: deltaLabel({delta: {concrete_l: -66, holes: -3}}),
  // the open registry: an axis no bundle has a word for still reaches the row
  unknown: deltaLabel({delta: {gizmos: -2}}),
  lexeme: valueLabel({bindings: {footing_depth_mm: 610},
                      lexemes: {footing_depth_mm: '24\\"'}}, "footing_depth_mm"),
  bare: valueLabel({bindings: {footing_depth_mm: 610}, lexemes: {}},
                   "footing_depth_mm"),
  absent: valueLabel({bindings: {}, lexemes: {}}, "footing_depth_mm"),
};

// the delta is measured in COUNTS and must not follow the length preference;
// the bound value is a length and must
state.units = "cm";
out.cm_delta = deltaLabel({delta: {posts: -3}});
out.cm_lexeme = valueLabel({bindings: {footing_depth_mm: 610},
                            lexemes: {footing_depth_mm: '24\\"'}}, "footing_depth_mm");

await setLocale("he");
state.units = "mm";
out.he_none = deltaLabel({delta: {}});
out.he_saving = deltaLabel({delta: {posts: -3}});
out.he_bare = valueLabel({bindings: {footing_depth_mm: 610}, lexemes: {}},
                         "footing_depth_mm");

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    # The line that makes this a test: without it a module that fails to parse
    # produces no assertion failure at all.
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_saving_reads_as_a_saving_with_a_real_minus_sign(out):
    """U+2212, not a hyphen. These sit next to numerals in a Hebrew-first UI,
    where a hyphen-minus reads as a dash and the row stops saying "fewer"."""
    assert out["saving"] == "−3 posts · −5 boards"
    assert "-" not in out["saving"]


def test_an_empty_delta_is_a_statement_and_not_a_blank(out):
    """The two answers cost the same, which is the reason the question exists.
    A blank cell reads as a panel that failed to load."""
    assert out["none"] == "no material change"
    assert out["zeros"] == "no material change"


def test_a_cost_carries_its_plus(out):
    assert out["worse"] == "+20 cuts"


def test_one_of_something_is_not_pluralised(out):
    assert out["singular"] == "−1 post · +1 hole"


def test_the_open_axes_reach_the_label(out):
    """`concrete_l` and `holes` come from the BOM layer and only exist on footing
    points — the fixed four-axis set this replaced printed "same posts, same
    boards" about two schedules 25% apart in concrete."""
    assert out["concrete"] == "−66 L concrete · −3 holes"


def test_an_axis_with_no_word_is_still_counted(out):
    """Axes are an open registry (spec §5.3): a difference the reader is being
    asked to weigh must not vanish because the bundles are behind."""
    assert out["unknown"] == "−2 gizmos"


def test_a_published_value_keeps_the_publishers_own_words(out):
    """Contract obligation 5: convert units once, at the boundary, and keep the
    source lexeme for display. A panel showing only our millimetres has thrown
    away what a reader checks the number against."""
    assert out["lexeme"] == '24" (610 mm)'


def test_no_lexeme_is_invented_where_the_publisher_gave_none(out):
    """The other half of the same obligation, and the worse failure: `610 mm`
    dressed up as `24"` attributes a form of words to somebody who never used
    it."""
    assert out["bare"] == "610 mm"
    assert out["absent"] == ""


def test_counts_ignore_the_length_preference_and_lengths_honour_it(out):
    """A post is a post in centimetres. 610 mm is 61 cm — and the quoted 24"
    is a quotation and converts to nothing."""
    assert out["cm_delta"] == "−3 posts"
    assert out["cm_lexeme"] == '24" (61 cm)'


def test_the_labels_are_localized_and_not_english_with_numbers_in_it(out):
    """The app opens in Hebrew. Every one of these strings goes through t()/tu(),
    so the Hebrew bundle answers for all three."""
    assert out["he_none"] != out["none"]
    assert out["he_saving"] == "−3 עמודים"
    assert out["he_bare"] == '610 מ"מ'
