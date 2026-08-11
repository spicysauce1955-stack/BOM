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
import { state } from "./js/state.js";
import { toDisplayValue, toMm, unitParams, UNITS } from "./js/units.js";

const out = {};
out.units = UNITS;
out.mm_identity = [1234, 0, 7].map((v) => toDisplayValue(v, "mm"));
out.cm_display = [1234, 1200, 5, 0, -250].map((v) => toDisplayValue(v, "cm"));
// 1 mm resolution survives mm -> cm field -> mm
out.roundtrip = [0, 1, 7, 99, 1234, 1800, 2743, 123456]
  .map((v) => toMm(toDisplayValue(v, "cm"), "cm"));
out.parse_cm = [toMm("120.5", "cm"), toMm("120", "cm"), toMm(12.34, "cm")];
out.parse_bad = [toMm("", "cm"), toMm("abc", "mm"), toMm(null, "mm")];
state.units = "cm";
out.params = unitParams({ width_mm: 1234, min_mm: 900, mode: "level", span_id: "s1" });
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
    assert p["u"] == "units.cm"  # locale table absent in node: t() falls back to the key
