"""`moveGateNodes` / `repointGateEnd` (static/js/gates.js).

These two are the whole of "a gate can be moved, and it joins a stretch drawn
after it", and neither had a test in any layer: not here, not in pytest, not in
the browser suite. Two mutations survived the full gate — deleting the re-point
call in `editor.js`'s drop path (a gate can then never join a later stretch, the
commit's headline behaviour), and rewriting `moveGateNodes` to resolve the two
node ids ONCE into a caller-held pair, which is exactly the design its own
docstring says the ENDS naming exists to prevent.

That second one is the interesting property and it is why this is a test rather
than a comment: a re-point can happen MID-GESTURE, so a caller that resolved
`start_node_id` once goes on writing to the node the gate no longer hangs on.
The assertion below is therefore not "the gate moved" but "the write landed on
the node the gate hangs on NOW, and the one it used to hang on did not move".

Node rather than the browser, for `gate-geom.js`'s reason: this is bookkeeping
over the topology object, and aiming a mouse at an SVG to test it would say less
and take a hundred times longer.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { moveGateNodes, repointGateEnd } from "./js/gates.js";
import { state } from "./js/state.js";

const out = {};
const topo = () => ({
  revision: 0,
  nodes: [
    { id: "n1", x_mm: 0, y_mm: 0 },
    { id: "n2", x_mm: 5000, y_mm: 0 },
    { id: "n3", x_mm: 6000, y_mm: 0 },
    { id: "n4", x_mm: 11000, y_mm: 0 },
  ],
  runs: [{ id: "rA", start_node_id: "n1", end_node_id: "n2", point_events: [],
           interval_events: [] }],
  gates: [{ id: "g1", start_node_id: "n2", end_node_id: "n3", leaf: "single" }],
});
const load = () => { state.project = { topology: topo() }; return state.project.topology; };
const node = (t, id) => t.nodes.find((n) => n.id === id);

// -- an ordinary move: both ends, integer millimetres at the boundary --------
let t = load();
out.moved = moveGateNodes("g1", { start: [5000, 1000.4], end: [6000.6, 1000] });
out.after_move = [node(t, "n2").y_mm, node(t, "n3").x_mm];

// -- one end only leaves the other exactly where it was ----------------------
t = load();
moveGateNodes("g1", { end: [6500, 250] });
out.one_end_only = [node(t, "n2").x_mm, node(t, "n2").y_mm,
                    node(t, "n3").x_mm, node(t, "n3").y_mm];

// -- THE property: re-point mid-gesture, then move by END name ---------------
// The gate's `end` hangs on n3. Re-point it to n4, then ask to move `end`.
// The write must land on n4 — and n3, which the gate no longer hangs on, must
// not move. A caller holding resolved ids writes to n3 here.
t = load();
out.repointed = repointGateEnd("g1", "end", "n4");
out.ends_after_repoint = [t.gates[0].start_node_id, t.gates[0].end_node_id];
moveGateNodes("g1", { end: [12000, 700] });
out.new_node_moved = [node(t, "n4").x_mm, node(t, "n4").y_mm];
out.old_node_untouched = [node(t, "n3").x_mm, node(t, "n3").y_mm];

// -- re-point refusals -------------------------------------------------------
t = load();
out.refuse_same_as_other = repointGateEnd("g1", "end", "n2");   // both ends on n2
out.refuse_unchanged = repointGateEnd("g1", "end", "n3");       // already there
out.refuse_missing = repointGateEnd("g1", "end", "nope");       // no such node
out.refuse_no_gate = repointGateEnd("ghost", "end", "n4");
out.ends_unchanged = [t.gates[0].start_node_id, t.gates[0].end_node_id];

// -- a node that went away under the gesture: write NOTHING, answer false ----
t = load();
t.nodes = t.nodes.filter((n) => n.id !== "n3");
out.move_with_missing_node = moveGateNodes("g1", { start: [1, 2], end: [3, 4] });
out.start_node_untouched = [node(t, "n2").x_mm, node(t, "n2").y_mm];

out.move_missing_gate = moveGateNodes("ghost", { start: [1, 2] });

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.skip("node not available")
    script = STATIC / "_gate_move_test.mjs"
    script.write_text(SCRIPT)
    try:
        proc = subprocess.run(["node", str(script)], cwd=STATIC,
                              capture_output=True, text=True, timeout=60)
    finally:
        script.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_move_writes_integer_millimetres(result):
    """ADR-0002 at the boundary: the drag hands over floats, the topology stores
    whole millimetres."""
    assert result["moved"] is True
    assert result["after_move"] == [1000, 6001]


def test_moving_one_end_leaves_the_other_exactly_where_it_was(result):
    assert result["one_end_only"] == [5000, 0, 6500, 250]


def test_a_move_after_a_repoint_writes_to_the_node_the_gate_hangs_on_NOW(result):
    """The reason `moves` names ENDS and not node ids.

    `repointGateEnd` can change which node an end hangs on mid-gesture. A caller
    that resolved `start_node_id`/`end_node_id` once — the obvious refactor —
    goes on writing to the node it started from, silently dragging the stretch
    the gate just LEFT and leaving the one it just joined behind.
    """
    assert result["repointed"] is True
    assert result["ends_after_repoint"] == ["n2", "n4"]
    assert result["new_node_moved"] == [12000, 700], "the write missed the new node"
    assert result["old_node_untouched"] == [6000, 0], \
        "the node the gate no longer hangs on was dragged with it"


def test_a_gate_may_not_point_both_ends_at_one_node(result):
    """The opening IS the distance between the two nodes, so a gate from a node
    to itself has no opening — and `Topology`'s validator answers 422 rather
    than storing one."""
    assert result["refuse_same_as_other"] is False
    assert result["refuse_unchanged"] is False
    assert result["refuse_missing"] is False
    assert result["refuse_no_gate"] is False
    assert result["ends_unchanged"] == ["n2", "n3"], "a refusal that still wrote"


def test_a_node_that_vanished_mid_drag_writes_nothing_at_all(result):
    """An undo landing mid-gesture. A half-moved gate — one end written, the
    other refused — is not a state this can reach: the writes are collected
    first and applied only once every node is known to exist."""
    assert result["move_with_missing_node"] is False
    assert result["start_node_untouched"] == [5000, 0], "a partial write"
    assert result["move_missing_gate"] is False
