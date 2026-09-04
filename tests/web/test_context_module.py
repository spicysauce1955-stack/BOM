"""The shape a drag describes (static/js/context.js).

`shapeFor` is pure — no DOM, no state — so the geometry of "drag a rectangle for
the house, a line for the street" is tested here rather than by aiming a mouse at
a canvas. What the browser smoke then has to prove is only that the gesture
reaches this function, which is a much smaller claim.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { DRAG_KINDS, nextLandmarkId, shapeFor } from "./js/context.js";

const out = {};
out.kinds = DRAG_KINDS;
out.house = shapeFor("house", [0, 0], [8000, 6000]);
out.house_backwards = shapeFor("house", [8000, 6000], [0, 0]);
out.street = shapeFor("street", [-2000, -3000], [20000, -3000]);
out.tiny = shapeFor("house", [0, 0], [100, 100]);
out.thin_street = shapeFor("street", [0, 0], [9000, 40]);
out.unknown = shapeFor("swimming-pool", [0, 0], [5000, 5000]);
out.no_drag = shapeFor("house", [0, 0], null);
out.id_empty = nextLandmarkId([]);
out.id_gap = nextLandmarkId([{id: "lm1"}, {id: "lm3"}]);
out.id_none = nextLandmarkId(null);
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_house_is_the_rectangle_the_drag_spanned(out):
    assert out["house"]["closed"] is True
    assert out["house"]["points"] == [[0, 0], [8000, 0], [8000, 6000], [0, 6000]]


def test_a_house_dragged_backwards_is_the_same_building(out):
    """A person drags from whichever corner they started at. The rectangle must
    not depend on which one — the corner order differs, the outline does not."""
    assert out["house_backwards"]["closed"] is True
    assert set(map(tuple, out["house_backwards"]["points"])) == \
           set(map(tuple, out["house"]["points"]))


def test_a_street_is_the_line_itself_and_never_a_box(out):
    """A road is not a rectangle. Squaring it off would put a corner where the
    salesperson drew none, and the office person would read a bend in the road
    that is not there."""
    assert out["street"]["closed"] is False
    assert out["street"]["points"] == [[-2000, -3000], [20000, -3000]]


def test_a_stray_click_leaves_no_invisible_building(out):
    """The house tool is active, somebody clicks. Without this there is a 3 mm
    landmark on the drawing that nobody can see and the office person then has
    to ask about."""
    assert out["tiny"] is None
    assert out["no_drag"] is None


def test_a_street_dragged_straight_along_one_axis_still_counts(out):
    """The minimum applies per axis, not to both at once: a street IS a long
    thin thing, and requiring 300 mm of drift in the short direction would
    refuse the most ordinary gesture in this tool."""
    assert out["thin_street"] is not None
    assert out["thin_street"]["points"] == [[0, 0], [9000, 40]]


def test_a_kind_that_is_not_dragged_produces_nothing(out):
    """`boundary` and `other` are authored on the backend and rendered here, but
    no drag makes one. Returning a shape anyway would put a landmark of an
    unknown kind on the project, which the API then refuses — failing far from
    the gesture that caused it."""
    assert out["unknown"] is None
    assert out["kinds"] == ["house", "street"]


def test_ids_are_sequential_rather_than_time_based(out):
    """Two landmarks drawn in the same millisecond would share a time-based id,
    and duplicate ids are exactly what the backend refuses. The gap case matters
    because a landmark can be deleted from the middle of the list."""
    assert out["id_empty"] == "lm1"
    assert out["id_gap"] == "lm2"
    assert out["id_none"] == "lm1"
