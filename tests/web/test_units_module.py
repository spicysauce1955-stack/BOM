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
globalThis.document = { getElementById: () => null };

import { on, state } from "./js/state.js";
import {
  UNITS, initUnits, inputStep, setUnits, snapStep, toDisplayValue, toMm,
  toggleUnits, unitParams,
} from "./js/units.js";

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
    assert p["u"] == "units.cm"  # locale table absent in node: t() falls back to the key


def test_mm_params_pass_through_untouched(units):
    """The mm side must be exercised too, or a hardcoded-cm conversion passes."""
    assert units["params_mm"] == {
        "u": "units.mm", "width_mm": 1234, "min_mm": 900,
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
