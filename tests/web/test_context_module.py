"""What the canvas layer does with a landmark (static/js/context.js).

The GEOMETRY itself no longer lives here: gestures, rectangles, circles and
their inverses moved to `js/landmark-shape.js` when the house became a
click-built polygon and the street became a rectangle, and they are covered in
`test_landmark_shape_module.py`. `context.js` re-exports `shapeFor` so its
callers did not have to move with it, and what is left to prove here is what
context.js still owns: the hit test a move-drag needs, ids that do not collide,
and the draft group being cleared.

The re-export is checked through the same `shapeFor` the canvas calls, so a
mistake in the wiring — importing the wrong name, or leaving the old inline
implementation behind — fails here rather than in a browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { DRAG_KINDS, landmarkAt, nextLandmarkId, shapeFor } from "./js/context.js";

const out = {};
out.kinds = DRAG_KINDS;
out.house = shapeFor("house", [0, 0], [8000, 6000]);
out.street = shapeFor("street", [-2000, -3000], [20000, -3000]);
out.unknown = shapeFor("swimming-pool", [0, 0], [5000, 5000]);
out.id_empty = nextLandmarkId([]);
out.id_gap = nextLandmarkId([{id: "lm1"}, {id: "lm3"}]);
out.id_none = nextLandmarkId(null);

// --- landmarkAt: the hit-test a move-drag needs -----------------------------
const house = { id: "lm1", kind: "house", closed: true,
  points: [[0, 0], [8000, 0], [8000, 6000], [0, 6000]] };
const street = { id: "lm2", kind: "street", closed: false,
  points: [[-2000, -3000], [20000, -3000]] };
const marks = [house, street];
const idOf = (lm) => lm ? lm.id : null;
out.house_hit_inside = idOf(landmarkAt(marks, [4000, 3000], "house"));
out.house_hit_outside = idOf(landmarkAt(marks, [9000, 3000], "house"));
out.street_hit_on = idOf(landmarkAt(marks, [5000, -3000], "street"));
out.street_hit_near = idOf(landmarkAt(marks, [5000, -3150], "street"));
out.street_hit_far = idOf(landmarkAt(marks, [5000, -8000], "street"));
out.house_wrong_kind = idOf(landmarkAt(marks, [4000, 3000], "street"));
out.street_wrong_kind = idOf(landmarkAt(marks, [5000, -3000], "house"));
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


def test_a_house_drag_makes_nothing_because_a_house_is_built_by_clicking(out):
    """A house used to be the bounding box of one drag. It is not: a building
    has as many corners as it has, and a drag can only ever describe four of
    them, so an L-shaped house came out square and the office person read a
    wall that is not there.

    The house tool now collects clicks (`polygonFromClicks`), and `shapeFor`
    refuses the kind outright rather than quietly handing back a box — a
    fallback rectangle here would be indistinguishable, on the canvas, from a
    house somebody meant to draw that way. The box gestures that kept this
    exact geometry (`pool`, `boundary`, `other`) are covered in
    `test_landmark_shape_module.py`.
    """
    assert out["house"] is None


def test_a_street_is_a_rectangle_because_a_road_has_width(out):
    """A street used to be the bare two-point line of the drag. A line reads as
    "the fence runs to here", not as the road the salesperson pointed at, and
    it left the office person no width to check a setback against. The drag now
    describes the road's CENTRE LINE and the shape is the band around it — a
    closed rectangle whose width is editable afterwards, which is what a
    salesperson means when they say the street is wider on that side."""
    assert out["street"]["closed"] is True
    assert len(out["street"]["points"]) == 4
    # 4 m of carriageway, centred on the line that was dragged
    assert out["street"]["points"] == [[-2000, -1000], [20000, -1000],
                                       [20000, -5000], [-2000, -5000]]


def test_a_kind_that_is_not_dragged_produces_nothing(out):
    """Returning a shape for an unknown kind would put a landmark the API then
    refuses onto the project — failing far from the gesture that caused it.

    `DRAG_KINDS` is now every kind EXCEPT the house: the house is the one thing
    on the property built click-by-click, and everything else — street,
    sidewalk, pool, tree, boundary, other — is still one press-drag-release.
    """
    assert out["unknown"] is None
    assert "house" not in out["kinds"]
    assert set(out["kinds"]) == {"street", "sidewalk", "pool", "tree",
                                 "boundary", "other"}


def test_ids_are_sequential_rather_than_time_based(out):
    """Two landmarks drawn in the same millisecond would share a time-based id,
    and duplicate ids are exactly what the backend refuses. The gap case matters
    because a landmark can be deleted from the middle of the list."""
    assert out["id_empty"] == "lm1"
    assert out["id_gap"] == "lm2"
    assert out["id_none"] == "lm1"


def test_a_point_inside_a_house_hits_it(out):
    assert out["house_hit_inside"] == "lm1"


def test_a_point_outside_a_house_does_not_hit_it(out):
    """Outside the rectangle a press must fall through to 'draw a new house',
    the same as empty canvas — a house has no fuzzy halo around its outline."""
    assert out["house_hit_outside"] is None


def test_a_point_on_a_street_line_hits_it(out):
    assert out["street_hit_on"] == "lm2"


def test_a_point_near_a_street_line_hits_it_within_tolerance(out):
    """A street is a line with no interior to land inside of — unlike a house,
    it needs a tolerance band or it would be nearly impossible to grab."""
    assert out["street_hit_near"] == "lm2"


def test_a_point_far_from_a_street_line_does_not_hit_it(out):
    assert out["street_hit_far"] is None


def test_a_house_is_not_returned_when_the_kind_asked_for_is_street(out):
    """With the house tool active, a press over a street must fall through to
    'draw a new house' rather than silently start moving the street — and vice
    versa. Only landmarks of the ACTIVE tool's kind are hit-testable."""
    assert out["house_wrong_kind"] is None
    assert out["street_wrong_kind"] is None


def test_a_loaded_project_clears_a_half_drawn_landmark():
    """The bug behind four symptoms at once.

    The rubber band lives in `g-context-draft`, its own group, so that a
    redraw of the committed landmarks cannot wipe it — which also means
    `render()` never wipes it. It was cleared in exactly one place: the
    pointerup that commits a landmark. A gesture that never reached that path
    left a street-shaped line that could not be clicked (a draft carries
    `pointer-events: none`), could not be deleted (it is no landmark, so it has
    no row in the panel), and survived opening another job.

    Textual, because the alternative is a DOM: what matters is that the
    `project-loaded` redraw calls `clearDraft`, so a new job cannot inherit
    somebody's abandoned gesture.
    """
    src = (STATIC / "js" / "context.js").read_text()
    redraw = src[src.index("const redraw = "):]
    redraw = redraw[:redraw.index(";") + 1]
    assert "clearDraft()" in redraw, (
        "the project-loaded redraw must clear the draft group, or an abandoned "
        f"landmark gesture outlives the job it was made in: {redraw!r}")


def test_escape_cancels_a_landmark_gesture_too():
    """`cancelDraft` is what Escape calls, and a salesperson means by "the
    draft" whatever they are half-way through drawing — a half-drawn house is
    exactly that. Without this, Escape cleared the fence draft and left the
    landmark band behind."""
    src = (STATIC / "js" / "editor.js").read_text()
    body = src[src.index("function cancelDraft()"):]
    body = body[:body.index("\n}\n")]
    assert "clearContextDraft()" in body, (
        "Escape must clear the landmark rubber band as well as the fence draft")
