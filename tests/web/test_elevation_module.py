"""The panel elevation renderer (static/js/elevation.js), run in node.

The drawing itself needs a browser (tools/ui_smoke.py checks that it appears,
that it is clickable and that Hebrew does not mirror it). What node can check is
the part that would be wrong SILENTLY: the axis flip, the paint order, and the
rule that decides which fitted gap may be dimensioned.

It runs against the REAL `panel_elevation` output rather than a hand-written
fixture, so the one transform this module owns — panel y (up from the opening's
bottom-left) into SVG y (down from the top) — is checked against the coordinates
the server actually sends. A fixture would keep passing after the read model
changed its mind about where y = 0 is.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_LEGACY, M_SLAT
from fenceai.fencemodel.preview import PreviewRequest, preview_panel

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { readFileSync } from "node:fs";

// elevation.js reaches i18n/units through geom/state, whose stateful halves
// touch localStorage and the DOM at call time — stub both, and serve the REAL
// locale bundle so what node renders is what the browser renders.
globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  documentElement: {},
};
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { setLocale } from "./js/i18n.js";
import { setUnits } from "./js/units.js";
import {
  edgeMargins, elevationRects, gapDimension, gapLine, gapSummary, hasNominal,
  pitchDimension,
} from "./js/elevation.js";

const SLAT = %(slat)s;
const LEGACY = %(legacy)s;
const INSET = %(inset)s;

const out = {};
const rects = elevationRects(SLAT);
out.count = rects.length;
out.slats = rects.filter((r) => r.slot_key === "slat").length;
out.rails = rects.filter((r) => r.slot_key === "rail").length;
// the panel is 1800 high: a full-height slat starts at SVG y 0, the bottom rail
// (panel y 0, 72 thick) is drawn at the BOTTOM of the picture
out.first_slat = rects.find((r) => r.slot_key === "slat");
out.rail_ys = rects.filter((r) => r.slot_key === "rail").map((r) => r.y_mm);
out.rail_panel_ys = SLAT.members.filter((m) => m.slot_key === "rail").map((m) => m.y_mm);
out.keys_unique = new Set(rects.map((r) => r.key)).size === rects.length;
out.x_order = rects.filter((r) => r.slot_key === "slat").map((r) => r.x_mm);

// a back face is painted first, whatever order it arrives in
const shadowbox = {
  width_mm: 1000, height_mm: 1000, gaps_mm: [],
  members: [
    { slot_key: "front", role: "infill", index: 0, x_mm: 0, y_mm: 0,
      w_mm: 100, h_mm: 1000, face: "front", declared: true, sku: "A" },
    { slot_key: "back", role: "infill", index: 0, x_mm: 50, y_mm: 0,
      w_mm: 100, h_mm: 1000, face: "back", declared: true, sku: "B" },
  ],
};
out.paint_order = elevationRects(shadowbox).map((r) => r.slot_key);

out.gaps = gapSummary(SLAT);
out.legacy_gaps = gapSummary(LEGACY);
out.nominal = [hasNominal(SLAT), hasNominal(LEGACY)];
out.declared = {
  slat: rects.find((r) => r.slot_key === "slat").declared,
  rail: rects.find((r) => r.slot_key === "rail").declared,
};

out.dim = gapDimension(SLAT);
out.legacy_dim = gapDimension(LEGACY);

// gaps that no adjacent pair confirms get NO dimension line: the wire does not
// say which slot the fitted list belongs to, so an unconfirmed pair would be a
// number invented in JS
const unconfirmed = {
  width_mm: 1000, height_mm: 1000, gaps_mm: [999],
  members: [
    { slot_key: "s", role: "infill", index: 0, x_mm: 0, y_mm: 0,
      w_mm: 100, h_mm: 1000, face: "front", declared: true, sku: "A" },
    { slot_key: "s", role: "infill", index: 1, x_mm: 120, y_mm: 0,
      w_mm: 100, h_mm: 1000, face: "front", declared: true, sku: "A" },
  ],
};
out.unconfirmed_dim = gapDimension(unconfirmed);

// a horizontal pattern: the same lookup, one axis over
const horizontal = {
  width_mm: 1000, height_mm: 1000, gaps_mm: [30, 30],
  members: [
    { slot_key: "board", role: "infill", index: 0, x_mm: 0, y_mm: 0,
      w_mm: 1000, h_mm: 100, face: "front", declared: true, sku: "A" },
    { slot_key: "board", role: "infill", index: 1, x_mm: 0, y_mm: 130,
      w_mm: 1000, h_mm: 100, face: "front", declared: true, sku: "A" },
  ],
};
out.horizontal_dim = gapDimension(horizontal);

// the sentence beside the drawing, in both languages and both display units
await setLocale("en");
out.en_gaps = gapLine(SLAT);
setUnits("cm");
out.en_gaps_cm = gapLine(SLAT);
setUnits("mm");
await setLocale("he");
out.he_gaps = gapLine(SLAT);
out.he_empty = gapLine(LEGACY);

// a range rather than one figure — the reason gaps_mm is a LIST
out.he_range = gapLine({ ...SLAT, gaps_mm: [20, 21, 20] });

// --- pitch and edge margins, the two dimensions a slat fence is specified by
out.pitch = pitchDimension(SLAT);
out.pitch_legacy = pitchDimension(LEGACY);
// an UNEVEN pattern has no single pitch, and one quoted over it is a figure an
// installer would set out from and be wrong by the last bay
const uneven = { ...SLAT, members: SLAT.members.map(
  (m) => (m.slot_key === "slat" && m.index === 3 ? { ...m, x_mm: m.x_mm + 7 } : m)) };
out.pitch_uneven = pitchDimension(uneven);
// two members show a gap, not a rhythm
out.pitch_two = pitchDimension({
  ...SLAT,
  members: SLAT.members.filter((m) => m.slot_key === "slat" && m.index < 2),
});
// M-SLAT fills its bay exactly: 21 slats at 120 centres is 2500 mm, flush at
// both ends, so there is no margin to call out. The pattern WITH a margin is
// built by hand, because no demo model authors one.
out.margins = edgeMargins(SLAT);
// the FIT's own margins, off the wire. The far-end clearance is the end margin
// PLUS the residual: `truncate` leaves the remainder beyond it, and a client
// that measured the last rectangle instead would report only one of the two.
out.margins_from_fit = edgeMargins(INSET);
out.inset_fit = { start: INSET.edge_margin_start_mm, end: INSET.edge_margin_end_mm,
                  residual: INSET.residual_mm };
out.margins_inset = edgeMargins({
  width_mm: 1000, height_mm: 1000, gaps_mm: [100, 100],
  members: [0, 1, 2].map((i) => ({
    slot_key: "s", role: "infill", kind: "infill", index: i,
    x_mm: 50 + i * 200, y_mm: 0, w_mm: 100, h_mm: 1000,
    declared: true, face: "front", sku: "A",
  })),
});
// a FRAME slot is never mistaken for the pattern: two rails inset from the top
// and bottom of the opening are not an edge margin anyone sets out
out.margins_frame_only = edgeMargins({
  width_mm: 1000, height_mm: 1000, gaps_mm: [],
  members: [0, 1].map((i) => ({
    slot_key: "rail", role: "rail", kind: "frame", index: i,
    x_mm: 0, y_mm: 100 + i * 700, w_mm: 1000, h_mm: 40,
    declared: true, face: "front", sku: "R",
  })),
});
// flush at both ends: nothing to call out, rather than two zeros
const flush = {
  width_mm: 300, height_mm: 1000, gaps_mm: [100],
  members: [
    { slot_key: "s", role: "infill", index: 0, x_mm: 0, y_mm: 0, w_mm: 100,
      h_mm: 1000, declared: true, face: "front", sku: "A" },
    { slot_key: "s", role: "infill", index: 1, x_mm: 200, y_mm: 0, w_mm: 100,
      h_mm: 1000, declared: true, face: "front", sku: "A" },
  ],
};
out.margins_flush = edgeMargins(flush);
out.pitch_flush = pitchDimension(flush);   // only two members: no rhythm

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def ev():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    catalog = demo_catalog()
    req = PreviewRequest(height_mm=1800, width_mm=2500)
    inset = M_SLAT.model_copy(deep=True)
    inset.default_spec.infill.edge_margin_mm = 50
    inset.default_spec.infill.justification = "center"
    inset.default_spec.infill.excess = "truncate"
    script = SCRIPT % {
        "slat": preview_panel(M_SLAT, req, catalog).elevation.model_dump_json(),
        "legacy": preview_panel(M_LEGACY, req, catalog).elevation.model_dump_json(),
        "inset": preview_panel(inset, req, catalog).elevation.model_dump_json(),
    }
    proc = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_every_member_the_server_places_is_drawn(ev):
    """21 slats and 2 rails — one rectangle per bought member, no more."""
    assert (ev["slats"], ev["rails"]) == (21, 2)
    assert ev["count"] == 23
    assert ev["keys_unique"], "a rectangle must be identifiable: slot + index"


def test_panel_y_is_flipped_into_svg_y(ev):
    """The one transform this module owns. Panel y grows UP from the bottom of
    the opening; SVG y grows down — so the rail the server puts at y = 0 is the
    one drawn at the BOTTOM of the picture."""
    assert ev["rail_panel_ys"] == [0, 1728]      # what the server sends
    assert ev["rail_ys"] == [1728, 0]            # what gets drawn
    slat = ev["first_slat"]
    assert (slat["y_mm"], slat["h_mm"]) == (0, 1800)   # full height, top to bottom


def test_the_drawing_keeps_the_servers_left_to_right_order(ev):
    """Never mirrored: the slats are drawn in increasing x whatever the page
    direction is, because reversing them would disagree with the plan."""
    assert ev["x_order"] == sorted(ev["x_order"])
    assert ev["x_order"][:3] == [0, 120, 240]


def test_a_back_face_is_painted_before_the_front(ev):
    assert ev["paint_order"] == ["back", "front"]


def test_the_fitted_gaps_are_reported_as_a_range_not_a_number(ev):
    assert ev["gaps"] == {"count": 20, "min_mm": 20, "max_mm": 20}
    assert ev["legacy_gaps"] is None      # a frame-only panel fits nothing


def test_an_undeclared_face_size_is_flagged_as_nominal(ev):
    """RAIL-3000 carries no face width, so its 72 mm is a nominal the read model
    invented; the slat's 100 mm is product data. The drawing must be able to
    tell them apart, or it claims a precision the catalog does not have."""
    assert ev["nominal"] == [True, True]
    assert ev["declared"] == {"slat": True, "rail": False}


def test_the_dimensioned_gap_is_looked_up_never_measured(ev):
    """`gaps_mm[i]` is the gap after placed member i, and a member carries that
    i as its index — so the dimension is the server's figure. The pair still has
    to sit exactly that far apart before it is drawn."""
    assert ev["dim"] == {"axis": "x", "gap_mm": 20, "start_mm": 100, "end_mm": 120,
                         "cross_mm": 1800, "slot_key": "slat"}
    assert ev["legacy_dim"] is None
    assert ev["horizontal_dim"]["axis"] == "y"
    assert ev["horizontal_dim"]["gap_mm"] == 30


def test_an_unconfirmed_gap_gets_no_dimension_line(ev):
    """The wire does not say which slot the fitted list belongs to. Where the
    drawing does not already show the listed distance, it says nothing — a
    dimension no rectangle supports is a number invented in the client."""
    assert ev["unconfirmed_dim"] is None


def test_the_gap_line_localizes_and_converts(ev):
    assert ev["en_gaps"] == "20 gaps, each 20 mm"
    assert ev["en_gaps_cm"] == "20 gaps, each 2 cm"
    assert "20" in ev["he_gaps"] and "מרווחים" in ev["he_gaps"]
    assert "gaps" not in ev["he_gaps"] and "mm" not in ev["he_gaps"]
    assert ev["he_empty"] == ""
    assert "20–21" in ev["he_range"]


# --- pitch and edge margins -------------------------------------------------

def test_the_pattern_pitch_is_the_number_a_slat_fence_is_specified_by(ev):
    """"100 at 120 centres" — a figure neither the member width nor the gap
    states on its own, and the one an installer sets out from."""
    assert ev["pitch"]["value_mm"] == 120
    assert ev["pitch"]["axis"] == "x"
    assert ev["pitch"]["slot_key"] == "slat"


def test_an_uneven_pattern_gets_no_pitch_rather_than_an_average(ev):
    """`spread_to_fit` absorbs its remainder into the gaps, so its members are
    not evenly pitched. One pitch quoted over that is a number that is wrong by
    the last bay — and the gap line beside the drawing already says the honest
    thing ("20-21 mm")."""
    assert ev["pitch_uneven"] is None
    assert ev["pitch_two"] is None, "two members are a gap, not a rhythm"
    assert ev["pitch_flush"] is None
    assert ev["pitch_legacy"] is None, "a frame-only panel has no pattern at all"


def test_the_edge_margins_are_reported_as_a_pair(ev):
    """The two ends differ under start/end justification, so one figure would
    name the wrong end. 50 in at the start, 1000 - (450 + 100) = 450 at the far
    end."""
    assert ev["margins_inset"]["start_mm"] == 50
    assert ev["margins_inset"]["end_mm"] == 450
    assert ev["margins_inset"]["axis"] == "x"
    # M-SLAT fills its own bay exactly — 21 slats at 120 centres is 2500 mm
    assert ev["margins"] is None


def test_a_frame_slot_is_never_read_as_the_pattern(ev):
    """Two rails inset from the top and bottom of an opening are not an edge
    margin: nobody sets out from that figure, and `kind` is on the wire so a
    client does not have to guess which slot is the infill."""
    assert ev["margins_frame_only"] is None


def test_a_pattern_flush_at_both_ends_gets_no_margin_dimension(ev):
    """A dimension line of length zero is a tick with a 0 beside it, which reads
    as a mistake rather than as "flush"."""
    assert ev["margins_flush"] is None


def test_the_edge_margin_is_the_fits_own_number_not_a_measurement(ev):
    """Spec §3.3: the annotation is `fit.edge_margin_start_mm`. Measuring it back
    off the drawn rectangles was a client-side re-derivation of a number the fit
    had already produced and spent — and the two diverge exactly where it
    matters, because `truncate` leaves the residual BEYOND the end margin."""
    fit = ev["inset_fit"]
    drawn = ev["margins_from_fit"]
    assert drawn is not None
    assert drawn["start_mm"] == fit["start"]
    assert drawn["end_mm"] == fit["end"] + fit["residual"]
    assert fit["start"] > 0, "the fixture must actually inset its pattern"
