"""Pointer resolution + the elevation model (static/js/geom.js).

Two hit-tests used to answer the same pixel differently: the status readout
looped runs in array order while the click took SVG paint order, and the fat
hit band's ROUND end-cap made the second leg of an L a ~178 mm disc over the
first leg's last stations. A slope got recorded on the wrong leg and the first
leg's final station could not be reached at all (persona-lab run 2, B4).

The fix is one resolver — geom.runAtPoint — so there is exactly one answer per
pixel, plus geom.endpointNodeAt so an elevation authored at a shared corner
lands on the NODE both legs read. geom.js is pure enough to import in node, so
the arithmetic is pinned here; the browser smoke suite pins the wiring.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

# an L, exactly as finishDraft() emits it: TWO runs sharing the corner node n2
SCRIPT = """
globalThis.localStorage = {
  s: {},
  getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = { getElementById: () => null };

import { state } from "./js/state.js";
import {
  RUN_HIT_MM, endpointNodeAt, groundSamplesFor, groundZAt, runAtPoint,
} from "./js/geom.js";

const run = (id, a, b) => ({ id, start_node_id: a, end_node_id: b,
  interior_vertices: [], point_events: [], interval_events: [] });
state.project = { topology: {
  nodes: [{ id: "n1", x_mm: 0, y_mm: 0, z_mm: 0 },
          { id: "n2", x_mm: 6000, y_mm: 0, z_mm: 0 },
          { id: "n3", x_mm: 6000, y_mm: 4000, z_mm: 0 }],
  runs: [run("run1", "n1", "n2"), run("run2", "n2", "n3")],
} };
const topo = state.project.topology;
const at = (x, y) => {
  const hit = runAtPoint(x, y);
  return hit ? [hit.run.id, hit.station, Math.round(hit.dist)] : null;
};

const out = {};
out.tol = RUN_HIT_MM;
// walking the first leg towards the corner: it stays the first leg the whole
// way, including the stations the second run's end-cap used to swallow
out.approach = [3000, 5780, 5874, 5950, 5999].map((s) => at(s, 0));
// the corner belongs to the run that comes first, deterministically
out.corner = at(6000, 0);
// ... and the second leg answers as soon as the pointer is actually on it
out.second = [at(6000, 50), at(6000, 2000), at(6000, 4000)];
// perpendicular offsets: inside the band, then just outside it
out.offsets = [at(3000, RUN_HIT_MM - 1), at(3000, RUN_HIT_MM + 1)];
out.empty = at(-4000, -4000);
// a point equidistant from both legs resolves the same way every time
out.ties = [at(5900, 100), at(5900, 100), at(5900, 100)].map((h) => h[0]);

// endpoint capture: interior stations stay run-local, ends are the shared node
const r1 = topo.runs[0], r2 = topo.runs[1];
out.endpoints = [endpointNodeAt(r1, 3000), endpointNodeAt(r1, 0),
                 endpointNodeAt(r1, 6000), endpointNodeAt(r1, 5900),
                 endpointNodeAt(r2, 0)].map((n) => (n ? n.id : null));

// the shared corner is single-valued: one node z, both legs read it
topo.nodes[1].z_mm = 1000;
const zOf = (r) => {
  const s = groundSamplesFor(r);
  return [s[0].z, s[s.length - 1].z, groundZAt(s, 3000)];
};
out.ground_shared = [zOf(r1), zOf(r2)];
// an explicit endpoint sample still overrides for ITS run (backwards compatible
// with event-only runs) — which is exactly the contradiction the editor now
// avoids by writing the node instead
r1.point_events.push({ id: "e1", payload: { kind: "elevation_sample", z_mm: 0 },
  anchor: { segment_index: 0, offset_mm: 6000, seg_len_at_authoring_mm: 6000 } });
out.ground_contradicted = [zOf(r1), zOf(r2)];

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def geom():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_tolerance_matches_the_painted_hit_band(geom):
    # .run-hit is stroke-width 16 at SCALE 0.045 px/mm: half of it is 178 mm
    assert geom["tol"] == 178


def test_the_first_leg_keeps_its_stations_up_to_the_corner(geom):
    assert geom["approach"] == [
        ["run1", 3000, 0], ["run1", 5780, 0], ["run1", 5874, 0],
        ["run1", 5950, 0], ["run1", 5999, 0],
    ]


def test_the_corner_resolves_to_the_first_run_at_its_full_length(geom):
    # the station that no event tool could reach before
    assert geom["corner"] == ["run1", 6000, 0]


def test_the_second_leg_answers_where_the_pointer_is_on_it(geom):
    assert geom["second"] == [
        ["run2", 50, 0], ["run2", 2000, 0], ["run2", 4000, 0],
    ]


def test_resolution_stops_at_the_hit_band(geom):
    inside, outside = geom["offsets"]
    assert inside == ["run1", 3000, 177]
    assert outside is None
    assert geom["empty"] is None


def test_ties_are_deterministic(geom):
    assert geom["ties"] == ["run1", "run1", "run1"]


def test_run_ends_capture_to_the_shared_node(geom):
    interior, start, end, near_end, next_leg_start = geom["endpoints"]
    assert interior is None
    assert (start, end, near_end) == ("n1", "n2", "n2")
    assert next_leg_start == "n2"  # the same node the first leg ends on


def test_both_legs_read_one_elevation_for_the_shared_corner(geom):
    leg1, leg2 = geom["ground_shared"]
    assert leg1 == [0, 1000, 500]   # climbs 0 -> 1000 over 6 m
    assert leg2[0] == 1000          # and the second leg STARTS there
    assert leg1[1] == leg2[0]


def test_an_endpoint_sample_still_overrides_only_its_own_run(geom):
    # the legacy shape this fix exists to stop authoring: one leg says the corner
    # is at 0, the other says 1000 — a 1 m step that no one drew
    leg1, leg2 = geom["ground_contradicted"]
    assert leg1[1] == 0
    assert leg2[0] == 1000
