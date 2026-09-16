"""The THREE implementations of "how high is the ground here" must agree.

`topology/station.py: ground_z` is the one the generator measures against.
`js/geom.js: groundZAt` is the app's existing mirror. `js/section-elevation.js`
grew a third when the office card had to draw a wall, because that module
imports nothing — which is what makes it node-testable, and is a defensible
reason for a second copy.

Three copies of a formula is a risk the repo accepts here. Three copies giving
DIFFERENT ANSWERS is not, and they did: at a vertical step — two samples at one
station, which is how a cliff is carried — `geom.js` took the left side while
the backend takes the right. On the demo job's section A that is a 1120 mm
disagreement at exactly the discontinuity the office screen exists to show.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.topology.model import ElevationSamplePayload, Node, Run, Topology
from fenceai.topology.station import ground_z
from tests.conftest import add_point_event

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

#: A run with a CLIFF at 4000: the ground jumps 1120 mm with no horizontal run,
#: which is section A of the demo job.
SCRIPT = """
import { groundZAt } from "./js/geom.js";

const samples = [{station: 0, z: 0}, {station: 4000, z: 0},
                 {station: 4000, z: 1120}, {station: 8000, z: 1120}];
console.log(JSON.stringify(
  [0, 2000, 3999, 4000, 4001, 8000].map((s) => groundZAt(samples, s))));
"""


def _topology() -> Topology:
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0, z_mm=0),
               Node(id="n2", x_mm=8000, y_mm=0, z_mm=1120)],
        runs=[Run(id="run1", start_node_id="n1", end_node_id="n2")],
    )
    add_point_event(topo, "run1", "ev-a", 4000, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "ev-b", 4000, ElevationSamplePayload(z_mm=1120))
    return topo


def test_the_browser_answers_the_ground_exactly_as_the_engine_does():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    from_js = json.loads(proc.stdout)

    topo = _topology()
    run = topo.run("run1")
    from_py = [ground_z(topo, run, s) for s in (0, 2000, 3999, 4000, 4001, 8000)]

    assert from_js == from_py, (
        f"the drawing and the engine disagree about the ground: "
        f"js={from_js} python={from_py}")


def test_the_right_side_of_a_step_is_the_answer():
    """Stated on its own, so the agreement test above cannot pass by both
    implementations being wrong in the same direction."""
    topo = _topology()
    assert ground_z(topo, topo.run("run1"), 4000) == 1120
