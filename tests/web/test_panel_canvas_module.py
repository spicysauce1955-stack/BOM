"""What the canvas commits, and what it selects (static/js/panel-canvas.js).

The wiring between the pure drag arithmetic and the document. `panel-canvas-geom`
proves that 445 mm means a width of 145; this proves that the WIDTH handle is the
one that asks it, and that the gap and margin handles ask with a DELTA instead —
which is the rule that makes a drag on a `spread_to_fit` pattern not jump.

A browser can only show that something moved. Which authored field moved with it
is what breaks silently, and it is pure, so it is tested here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { selectionForSlot, valueFor } from "./js/panel-canvas.js";

// panel-canvas.js reaches i18n.js and units.js, whose stateful halves touch
// localStorage and the DOM at call time. The two exports under test do not.
globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  getElementById: () => null, querySelectorAll: () => [], querySelector: () => null,
  documentElement: {}, createElementNS: () => ({ setAttribute() {}, appendChild() {} }),
};

const W = 2400, H = 1800;
const ELEV = {
  width_mm: W, height_mm: H,
  members: [
    {slot_key: "rail", role: "rail", kind: "frame", index: 0,
     x_mm: 0, y_mm: 0, w_mm: W, h_mm: 60},
    {slot_key: "rail", role: "rail", kind: "frame", index: 1,
     x_mm: 0, y_mm: 1740, w_mm: W, h_mm: 60},
    {slot_key: "slat", role: "infill", kind: "infill", index: 0,
     x_mm: 300, y_mm: 0, w_mm: 100, h_mm: H},
    {slot_key: "slat", role: "infill", kind: "infill", index: 1,
     x_mm: 420, y_mm: 0, w_mm: 100, h_mm: H},
  ],
};
const spec = () => ({
  frame: [{key: "rail", orientation: "horizontal",
           placement: {kind: "from_bottom", offset_mm: 100}}],
  infill: {orientation: "vertical", edge_margin_mm: 40,
           pattern: [{key: "slat", width_mm: 100, gap_after_mm: 20}]},
  fixings: [{key: "screw", basis: "per_panel"}],
});

const handle = (kind, extra = {}) =>
  ({id: `${kind}:slat:0`, kind, slot_key: "slat", index: 0, axis: "x", ...extra});

const out = {};

// --- which authored field each handle kind writes ------------------------
out.placement = valueFor(
  {...handle("placement"), slot_key: "rail", axis: "y"},
  spec(), ELEV, [0, 500], [0, 640]);

// a WIDTH reads the pointer absolutely: the board starts at 300, the pointer
// is at 445, so the width is 145 — whatever the drag started from
out.width_from_far = valueFor(handle("width"), spec(), ELEV, [1000, 900], [445, 900]);
out.width_from_near = valueFor(handle("width"), spec(), ELEV, [310, 900], [445, 900]);

// a GAP reads the DISTANCE MOVED: the same pointer, two different starts, two
// different answers — because the drawn gap is not the authored one
out.gap_moved_30 = valueFor(handle("gap"), spec(), ELEV, [400, 900], [430, 900]);
out.gap_moved_back = valueFor(handle("gap"), spec(), ELEV, [400, 900], [330, 900]);
out.margin_moved_25 = valueFor(handle("margin"), spec(), ELEV, [300, 900], [325, 900]);

// the INTERIOR rail of a distributed slot has no authored position to write —
// three drawn rails, and the one in the middle is neither inset
const distributed = spec();
distributed.frame[0].placement = {kind: "distributed", count: 3,
                                  bottom_inset_mm: 0, top_inset_mm: 0};
const THREE_RAILS = {...ELEV, members: [
  ...ELEV.members,
  {slot_key: "rail", role: "rail", kind: "frame", index: 2,
   x_mm: 0, y_mm: 870, w_mm: W, h_mm: 60},
]};
out.interior = valueFor(
  {...handle("placement"), slot_key: "rail", index: 1, axis: "y"},
  distributed, THREE_RAILS, [0, 900], [0, 950]);
// ... while the outermost of the same three writes its own inset
out.outer = valueFor(
  {...handle("placement"), slot_key: "rail", index: 0, axis: "y"},
  distributed, THREE_RAILS, [0, 0], [0, 200]);

// a handle naming something the spec no longer has writes nothing
out.orphan = valueFor({...handle("width"), slot_key: "gone"}, spec(), ELEV,
                      [300, 900], [445, 900]);

// --- what a click on the drawing selects ---------------------------------
out.selects = ["rail", "slat", "screw", "nothing-like-this"].map(
  (key) => selectionForSlot(spec(), key));

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def c():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_placement_handle_writes_the_placement(c):
    assert c["placement"]["kind"] == "placement"
    assert c["placement"]["placement"] == {"kind": "from_bottom", "offset_mm": 640}


def test_the_placement_readout_is_the_number_being_written(c):
    """Not where the pointer is. For `from_top` and `fraction` the two differ,
    and a readout showing one while the field takes the other is the drag
    disagreeing with itself."""
    assert c["placement"]["readout_mm"] == 640


def test_a_width_handle_reads_the_pointer_absolutely(c):
    """Where the drag STARTED cannot matter: a board's width is its width."""
    assert c["width_from_far"]["width_mm"] == 145
    assert c["width_from_near"]["width_mm"] == 145


def test_a_gap_handle_reads_the_distance_moved(c):
    """The authored gap plus the drag, never the drawn distance. `excess: space`
    spends the leftover on the gaps, so reading the drawing back absolutely
    would make the first pixel of every drag jump by the spread — and the same
    pointer would mean two different gaps depending on where the hand started,
    which is the shape this pins."""
    assert c["gap_moved_30"]["gap_after_mm"] == 50      # authored 20 + 30
    assert c["gap_moved_back"]["gap_after_mm"] == -50   # authored 20 - 70
    assert c["margin_moved_25"]["edge_margin_mm"] == 65


def test_each_handle_kind_writes_its_own_field_and_no_other(c):
    """Swapping two arms of the commit is invisible to a browser: something
    moves either way."""
    assert set(c["width_from_far"]) == {"kind", "width_mm", "readout_mm"}
    assert set(c["gap_moved_30"]) == {"kind", "gap_after_mm", "readout_mm"}
    assert set(c["margin_moved_25"]) == {"kind", "edge_margin_mm", "readout_mm"}


def test_a_handle_with_nothing_to_write_writes_nothing(c):
    """An interior rail of an evenly-spaced slot has no authored position, and a
    handle naming a slot the spec no longer has has nothing to name. Both must
    come back empty rather than as a value the commit would then apply."""
    assert c["interior"] is None
    assert c["orphan"] is None
    # and the contrast, so "returns None" is not passing for the wrong reason
    assert c["outer"]["placement"]["bottom_inset_mm"] == 200


def test_clicking_the_drawing_selects_the_authored_thing(c):
    """`data-slot` is the authored key — `resolve_panel` builds every slot key
    from the spec — so this is a lookup. A rectangle whose key matches nothing
    selects the panel rather than inventing an element for it."""
    assert c["selects"] == [
        {"kind": "frame", "key": "rail"},
        {"kind": "infill", "key": "slat"},
        {"kind": "fixing", "key": "screw"},
        {"kind": "panel", "key": None},
    ]
