"""Display-unit conversion contract (static/js/units.js).

The unit toggle is a presentation preference: storage stays int mm (ADR-0002).
The property that matters is that a round trip through the display layer is
LOSSLESS at 1 mm resolution — a user working in cm must not silently rewrite
their millimetres. units.js is pure enough to import in node, so we test it
there rather than only through the browser smoke suite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
// units.js touches localStorage/DOM only in its stateful half — stub both so the
// harness exercises that half too, and so an unrelated module-scope DOM access
// can never turn a units regression into an opaque stderr dump
globalThis.localStorage = {
  s: {},
  getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = { getElementById: () => null, querySelectorAll: () => [],
                        documentElement: {} };
// money() reads the currency symbol out of the REAL locale bundle, so serve it:
// a test that stubbed the symbol would pass while the shipped bundle was missing
// the key, and every price on screen would read "units.currency1,234.56".
import { readFileSync } from "node:fs";
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { on, state } from "./js/state.js";
import { initI18n, setLocale } from "./js/i18n.js";
import {
  UNITS, currencySymbol, initUnits, inputStep, money, moneyDelta,
  parseTypedLength, setUnits, snapStep, toDisplayValue, toMm, toggleUnits,
  unitParams,
} from "./js/units.js";

await initI18n();
// the bundle is now REALLY loaded (money needs the symbol out of it), so pin the
// language before anything reads a word: `initI18n` opens in Hebrew, and a params
// assertion that drifted with the default locale would be testing the default
await setLocale("en");

const out = {};
out.units = UNITS;
out.mm_identity = [1234, 0, 7].map((v) => toDisplayValue(v, "mm"));
out.cm_display = [1234, 1200, 5, 0, -250].map((v) => toDisplayValue(v, "cm"));
// 1 mm resolution survives mm -> cm field -> mm
out.roundtrip = [0, 1, 7, 99, 1234, 1800, 2743, 123456]
  .map((v) => toMm(toDisplayValue(v, "cm"), "cm"));
out.parse_cm = [toMm("120.5", "cm"), toMm("120", "cm"), toMm(12.34, "cm")];
// sub-millimetre entry (possible despite step=0.1): half-up, never truncated
out.parse_sub = [toMm("0.05", "cm"), toMm("1.25", "cm"), toMm("-1.25", "cm")];
out.parse_bad = [toMm("", "cm"), toMm("abc", "mm"), toMm(null, "mm")];
out.step = { mm: inputStep("mm"), cm: inputStep("cm") };
out.snap_step = { mm: snapStep(10, "mm"), cm: snapStep(10, "cm") };

state.units = "mm";
out.params_mm = unitParams({ width_mm: 1234, min_mm: 900, mode: "level",
                             span_id: "s1", posts: 7, tilt_deg: 12 });
state.units = "cm";
out.params = unitParams({ width_mm: 1234, min_mm: 900, mode: "level",
                          span_id: "s1", posts: 7, tilt_deg: 12 });

// stateful half: stored preference, rejection of unknown units, one event per change
let events = [];
on("units-changed", (u) => events.push(u));
localStorage.setItem("fenceai.units", "furlong");
initUnits();
out.init_bad_stored = state.units;
localStorage.setItem("fenceai.units", "cm");
initUnits();
out.init_good_stored = state.units;
events = [];
setUnits("in");                      // unknown: ignored, no event
setUnits("cm");                      // already cm: no event
out.events_after_noops = events.length;
toggleUnits(); toggleUnits();
out.events_after_two_toggles = events.length;
out.unit_after_two_toggles = state.units;
out.persisted = localStorage.getItem("fenceai.units");
// typed draw lengths: an explicit suffix always wins; a bare number follows the
// active unit, except the mm-mode "under 100 is metres" shortcut
const typed = (unit) => Object.fromEntries(
  ["4", "9.5", "99", "100", "420", "4200", "0.5",
   "250cm", "80mm", "1.2m", "1.2מ", "", "abc", "0", "12cm34"]
    .map((s) => [s, parseTypedLength(s, unit)]));
out.typed_mm = typed("mm");
out.typed_cm = typed("cm");

// money: one formatter, from the bundle's symbol, in both languages
await setLocale("en");
out.symbol_en = currencySymbol();
out.money_en = [0, 5, 450, 180000, 123456789, -2500, null, undefined]
  .map((c) => money(c));
out.delta_en = [1200, -1200, 0].map((c) => moneyDelta(c));
await setLocale("he");
out.symbol_he = currencySymbol();
out.money_he = money(180000);
// a price never leaks a fractional cent: cents are integers at rest, and a
// float that reached here would otherwise print ".005"
out.money_rounded = [money(1234.4), money(1234.6)];
out.params_currency = unitParams({ width_mm: 100 }).c;

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def units():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_supported_units(units):
    assert units["units"] == ["mm", "cm"]


def test_mm_is_identity(units):
    assert units["mm_identity"] == [1234, 0, 7]


def test_cm_display_trims_whole_values(units):
    # 1200 mm reads "120", not "120.0"; odd millimetres keep their decimal
    assert units["cm_display"] == [123.4, 120, 0.5, 0, -25]


def test_roundtrip_is_lossless_at_one_mm(units):
    assert units["roundtrip"] == [0, 1, 7, 99, 1234, 1800, 2743, 123456]


def test_field_values_parse_back_to_int_mm(units):
    assert units["parse_cm"] == [1205, 1200, 123]


def test_unparseable_field_is_null_not_zero(units):
    # a blank field must not silently become 0 mm
    assert units["parse_bad"] == [None, None, None]


def test_only_mm_params_convert(units):
    p = units["params"]
    assert p["width_mm"] == 123.4 and p["min_mm"] == 90
    assert p["mode"] == "level" and p["span_id"] == "s1"
    # plain numbers are NOT lengths: counts and degrees must never be divided
    assert p["posts"] == 7 and p["tilt_deg"] == 12
    assert p["u"] == "cm"


def test_mm_params_pass_through_untouched(units):
    """The mm side must be exercised too, or a hardcoded-cm conversion passes."""
    assert units["params_mm"] == {
        "u": "mm", "c": "₪", "width_mm": 1234, "min_mm": 900,
        "mode": "level", "span_id": "s1", "posts": 7, "tilt_deg": 12,
    }


def test_sub_millimetre_entry_rounds_half_up(units):
    """Kills trunc/floor mutants in toMm that the integer round trip cannot see."""
    assert units["parse_sub"] == [1, 13, -12]


def test_field_step_preserves_one_mm_resolution(units):
    """step=1 in cm mode would silently coarsen every length field to whole cm."""
    assert units["step"] == {"mm": "1", "cm": "0.1"}
    assert units["snap_step"] == {"mm": "10", "cm": "1"}


def test_stored_preference_is_validated_and_events_are_exact(units):
    assert units["init_bad_stored"] == "mm"     # corrupt localStorage -> default
    assert units["init_good_stored"] == "cm"
    assert units["events_after_noops"] == 0     # unknown unit / no-op: no event
    assert units["events_after_two_toggles"] == 2
    assert units["unit_after_two_toggles"] == "cm"
    assert units["persisted"] == "cm"


def test_typed_length_suffixes_win_in_both_units(units):
    """An explicit unit means what it says, whatever the display unit is."""
    for table in (units["typed_mm"], units["typed_cm"]):
        assert table["250cm"] == 2500
        assert table["80mm"] == 80
        assert table["1.2m"] == 1200
        assert table["1.2מ"] == 1200      # Hebrew metre suffix


def test_bare_typed_length_follows_the_active_unit(units):
    mm, cm = units["typed_mm"], units["typed_cm"]
    # mm mode: a value under 100 is metres (typing "4" for a 4 m run)
    assert mm["4"] == 4000 and mm["9.5"] == 9500 and mm["99"] == 99000
    assert mm["100"] == 100 and mm["4200"] == 4200
    # cm mode: NO metres shortcut — sub-metre lengths are the common case there,
    # so "90" is 90 cm, not 90 metres (the trap this rule removed)
    assert cm["4"] == 40 and cm["9.5"] == 95 and cm["99"] == 990
    assert cm["100"] == 1000 and cm["420"] == 4200


def test_typed_length_rejects_what_it_cannot_read(units):
    for table in (units["typed_mm"], units["typed_cm"]):
        assert table[""] is None
        assert table["abc"] is None
        assert table["0"] is None          # zero-length segment is not a length
        assert table["12cm34"] is None     # unit must be a SUFFIX
    assert units["typed_cm"]["0.5"] == 5   # sub-centimetre entry still resolves


def test_the_currency_symbol_comes_from_the_bundle_in_both_languages(units):
    """One currency, ILS, and the symbol is a locale key rather than a literal in
    JS — which is what lets test_locale_bundles forbid a bare ₪ anywhere else."""
    assert units["symbol_en"] == "₪"
    assert units["symbol_he"] == "₪"
    assert units["money_he"] == "₪1,800.00"
    # tu()/unitParams carry it as {c}, the way they carry the unit label as {u}
    assert units["params_currency"] == "₪"


def test_money_groups_thousands_and_always_shows_two_decimals(units):
    """A quote figure is checked against another quote by eye: "₪180000" invites
    a factor-of-ten argument that "₪1,800.00" does not."""
    assert units["money_en"] == [
        "₪0.00", "₪0.05", "₪4.50", "₪1,800.00", "₪1,234,567.89", "-₪25.00",
        "₪0.00", "₪0.00",      # null/undefined price: free, never "NaN"
    ]


def test_money_rounds_to_the_cent_rather_than_printing_a_fraction(units):
    assert units["money_rounded"] == ["₪12.34", "₪12.35"]


def test_money_delta_signs_a_saving_and_a_cost_differently(units):
    """The "+" is the whole point: an impact preview is read to learn which way
    the money moved, and an unsigned figure answers a different question."""
    assert units["delta_en"] == ["+₪12.00", "-₪12.00", "₪0.00"]
