"""Post-drag arithmetic (static/js/post-drag.js), run in node.

Two canvases drag a post: the plan view, where a pointer must be projected onto
the run's polyline, and the side view, where the axis is a chained global
coordinate. The arithmetic they share lives here so they cannot drift — the same
arrangement `base-top.js` has for the profile's base transforms.

`yieldThreshold` exists in Python too (`strategy/layout.py`), deliberately. The
grid below is the only thing keeping the two honest.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { layoutWithPin, snapCandidates, violations, yieldThreshold }
  from "./js/post-drag.js";

const grid = {};
for (const [s, k, p] of [[2000,3,1],[2000,3,2],[2000,3,3],[2000,0,2],
                         [2438,3,2],[6000,5,4],[0,3,2],[2000,3,0]]) {
  grid[`${s}/${k}/${p}`] = yieldThreshold(s, k, p);
}
console.log(JSON.stringify({
  grid,
  pinned: layoutWithPin([0, 5000], 5000, 2500, {maxSpanMm: 2000}).widths,
  snaps: snapCandidates({
    station: 3960, prev: 2000, next: 5000, maxSpanMm: 2000, minSpanMm: 0,
    displayUnit: "mm", stock: {lengthMm: 2000, kerfMm: 3},
    piecesPerBay: 10, pieceShorterByMm: 0,
  }).map((s) => [s.kind, s.station]),
  bad: violations([1281, 1281, 2438], {maxSpanMm: 1676, minSpanMm: 0}),
}));
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


def test_the_two_yield_thresholds_are_one_formula(out):
    """The Python side is the reference — NOT a second literal. Rev 1 hard-coded
    998 in both languages and called that pinning them together."""
    from fenceai.strategy.layout import yield_threshold
    for key, got in out["grid"].items():
        stock, kerf, pieces = (int(x) for x in key.split("/"))
        assert got == yield_threshold(stock, kerf, pieces), key


def test_a_pin_splits_a_run_and_the_maximum_still_applies(out):
    """Rev 1 asserted `[2500, 2500]` "because neither exceeds the maximum" —
    2500 exceeds 2000. The preview must be the layout the backend will build, or
    the drag is a half-priced promise."""
    from fenceai.strategy.layout import equal_layout
    assert out["pinned"] == [1250, 1250, 1250, 1250]
    assert out["pinned"] == equal_layout(2500, 2000) + equal_layout(2500, 2000)


def test_no_snap_is_offered_that_the_module_would_itself_refuse(out):
    """Rev 1's yield tick at 3998 made the PREVIOUS bay 1998 — and at 4002, 2002,
    2 mm over the maximum passed into the same call. A rail that offers a
    violation rewards a person with a permanent warning on the customer's
    quote."""
    stations = [s for _, s in out["snaps"]]
    assert stations, "some snap is offered"
    assert all(s - 2000 <= 2000 and 5000 - s <= 2000 for s in stations)


def test_a_violation_names_the_bay_the_code_and_the_overshoot(out):
    assert out["bad"] == [{"index": 2, "code": "span_placed_over_maximum",
                           "over_mm": 762}]
