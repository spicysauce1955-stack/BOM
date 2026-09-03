"""The JS anchor resolver (static/js/geom.js), run in node against the Python one.

`geom.stationOfAnchor` mirrors backend `anchor_station` — the frontend contract
says "exactly" — and `Anchor.reanchor` gave that function a second behaviour to
mirror. An elevation sample re-anchors PROPORTIONALLY when its segment is
resized; a pinned post is RIGID, because 800 mm from the corner is what a person
measured (spec §10).

This file does not restate the expected numbers: every case is compared against
`fenceai.topology.station.anchor_station` over the same geometry. Two literals
agreeing is not the same property as two resolvers agreeing, and the failure
being prevented here is precisely divergence — the same pin drawn 800 mm apart
in the plan canvas and in the generator.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.topology.model import Anchor, Node, Run, Topology
from fenceai.topology.station import anchor_station, make_anchor

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { state } from "./js/state.js";
import { anchorFor, runById, stationOfAnchor } from "./js/geom.js";

// geom.js resolves node ids through the module-level `state`, so the geometry
// has to be installed there rather than passed in.
function straight(lengthMm) {
  state.project = { topology: {
    nodes: [{ id: "n1", x_mm: 0, y_mm: 0 }, { id: "n2", x_mm: lengthMm, y_mm: 0 }],
    runs: [{ id: "run1", start_node_id: "n1", end_node_id: "n2",
             interior_vertices: [] }],
  } };
  return runById("run1");
}

// Two legs: `firstLegMm` east, then `secondLegMm` north. A corner is what makes
// a segment-local offset a different number from an absolute station.
function bent(firstLegMm, secondLegMm) {
  state.project = { topology: {
    nodes: [{ id: "n1", x_mm: 0, y_mm: 0 },
            { id: "n2", x_mm: firstLegMm, y_mm: secondLegMm }],
    runs: [{ id: "run1", start_node_id: "n1", end_node_id: "n2",
             interior_vertices: [[firstLegMm, 0]] }],
  } };
  return runById("run1");
}

const rigid = (a) => ({ ...a, reanchor: "rigid" });
const out = {};

// ---- straight run ---------------------------------------------------------
straight(4000);
const a1000 = anchorFor("run1", 1000);
out.authored_1000 = a1000;
out.authored_carries_no_policy = !("reanchor" in a1000);
out.proportional_stretched = stationOfAnchor(straight(8000), a1000);
out.rigid_stretched = stationOfAnchor(straight(8000), rigid(a1000));

straight(4000);
const a3000 = anchorFor("run1", 3000);
out.rigid_clamped = stationOfAnchor(straight(1000), rigid(a3000));

const unchanged = straight(4000);
const a1200 = anchorFor("run1", 1200);
out.proportional_unchanged = stationOfAnchor(unchanged, a1200);
out.rigid_unchanged = stationOfAnchor(unchanged, rigid(a1200));

// ---- bent run: 800 mm into the second leg ---------------------------------
bent(4000, 3000);
const a4800 = anchorFor("run1", 4800);
out.authored_4800 = a4800;

// the EARLIER leg stretches: both policies shift by what it gained
out.bent_first_leg_rigid = stationOfAnchor(bent(9000, 3000), rigid(a4800));
out.bent_first_leg_proportional = stationOfAnchor(bent(9000, 3000), a4800);

// the anchor's OWN leg stretches: this is where the two disagree
out.bent_own_leg_rigid = stationOfAnchor(bent(4000, 6000), rigid(a4800));
out.bent_own_leg_proportional = stationOfAnchor(bent(4000, 6000), a4800);

// the anchor's own leg shrinks past the offset: clamp to THAT leg
bent(4000, 3000);
const a6500 = anchorFor("run1", 6500);
out.authored_6500 = a6500;
out.bent_own_leg_shrank_rigid = stationOfAnchor(bent(4000, 1000), rigid(a6500));

console.log(JSON.stringify(out));
"""


def _straight(length_mm: int) -> tuple[Topology, Run]:
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0), Node(id="n2", x_mm=length_mm, y_mm=0)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2")],
    )
    return topo, topo.run("run1")


def _bent(first_leg_mm: int, second_leg_mm: int) -> tuple[Topology, Run]:
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0),
               Node(id="n2", x_mm=first_leg_mm, y_mm=second_leg_mm)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2",
                  interior_vertices=[(first_leg_mm, 0)])],
    )
    return topo, topo.run("run1")


def _resolve(geometry: tuple[Topology, Run], anchor: Anchor, policy: str) -> int:
    topo, run = geometry
    return anchor_station(topo, run, anchor.model_copy(update={"reanchor": policy}))


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


def test_the_js_author_agrees_with_make_anchor(out):
    """`anchorFor` mirrors `make_anchor`, so the anchors the rest of this file
    resolves are the ones the backend would have written."""
    topo, run = _straight(4000)
    assert out["authored_1000"] == make_anchor(topo, run, 1000).model_dump(
        exclude={"reanchor"}
    )
    topo, run = _bent(4000, 3000)
    assert out["authored_4800"] == make_anchor(topo, run, 4800).model_dump(
        exclude={"reanchor"}
    )
    assert out["authored_6500"] == make_anchor(topo, run, 6500).model_dump(
        exclude={"reanchor"}
    )


def test_an_authored_anchor_carries_no_policy_and_still_resolves(out):
    """Every anchor stored in every existing project lacks the field. An absent
    `reanchor` must mean `proportional`, or reloading a saved project silently
    moves every elevation sample on a run that was ever resized."""
    assert out["authored_carries_no_policy"] is True
    topo, run = _straight(4000)
    stored = make_anchor(topo, run, 1000)
    assert out["proportional_stretched"] == anchor_station(*_straight(8000), stored)


def test_a_proportional_anchor_moves_with_its_stretched_segment(out):
    topo, run = _straight(4000)
    a = make_anchor(topo, run, 1000)
    assert out["proportional_stretched"] == _resolve(_straight(8000), a, "proportional")


def test_a_rigid_anchor_keeps_its_offset_through_a_stretch(out):
    topo, run = _straight(4000)
    a = make_anchor(topo, run, 1000)
    assert out["rigid_stretched"] == _resolve(_straight(8000), a, "rigid")
    # ...and the two policies really are different numbers here, or this file
    # would pass with the branch deleted
    assert out["rigid_stretched"] != out["proportional_stretched"]


def test_a_rigid_offset_past_a_shrunken_segment_clamps_rather_than_vanishing(out):
    topo, run = _straight(4000)
    a = make_anchor(topo, run, 3000)
    assert out["rigid_clamped"] == _resolve(_straight(1000), a, "rigid")
    assert isinstance(out["rigid_clamped"], int)  # never null


def test_the_policies_agree_on_an_unchanged_segment(out):
    """The branch a `reanchor` bug hides in: swap the two behaviours and every
    unresized run still draws correctly."""
    topo, run = _straight(4000)
    a = make_anchor(topo, run, 1200)
    assert out["rigid_unchanged"] == _resolve(_straight(4000), a, "rigid")
    assert out["proportional_unchanged"] == out["rigid_unchanged"]


def test_a_rigid_offset_is_measured_from_its_own_corner(out):
    """Stretching an EARLIER leg moves the absolute station by exactly what that
    leg gained, under both policies — the offset is segment-local. A resolver
    that pinned the absolute station instead would fail here and nowhere else."""
    topo, run = _bent(4000, 3000)
    a = make_anchor(topo, run, 4800)
    assert a.segment_index == 1 and a.offset_mm == 800
    assert out["bent_first_leg_rigid"] == _resolve(_bent(9000, 3000), a, "rigid")
    assert out["bent_first_leg_proportional"] == _resolve(
        _bent(9000, 3000), a, "proportional"
    )
    assert out["bent_first_leg_rigid"] == out["bent_first_leg_proportional"]


def test_the_two_policies_diverge_when_the_anchors_own_leg_is_resized(out):
    """The spec's worked example, in JS: the same pin 800 mm apart. This is the
    case a single-segment test cannot express, and the reason the canvas and the
    generator would have drawn a dragged post in two places."""
    topo, run = _bent(4000, 3000)
    a = make_anchor(topo, run, 4800)
    assert out["bent_own_leg_rigid"] == _resolve(_bent(4000, 6000), a, "rigid")
    assert out["bent_own_leg_proportional"] == _resolve(
        _bent(4000, 6000), a, "proportional"
    )
    assert out["bent_own_leg_proportional"] - out["bent_own_leg_rigid"] == 800


def test_the_clamp_is_segment_local_not_run_local(out):
    """On a two-leg run whose SECOND leg shrank, a rigid offset past its end
    lands on that leg's end — not the run's end, and not the first leg's."""
    topo, run = _bent(4000, 3000)
    a = make_anchor(topo, run, 6500)
    assert a.segment_index == 1 and a.offset_mm == 2500
    assert out["bent_own_leg_shrank_rigid"] == _resolve(_bent(4000, 1000), a, "rigid")
