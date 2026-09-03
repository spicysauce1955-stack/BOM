// Pure drag arithmetic for a post: what the layout becomes, where it may snap,
// and what rule a placement breaks. No DOM, no state, no view imports — and no
// units.js, which imports state.js. The plan canvas and the side view both call
// this, and the only way they cannot drift is if neither of them owns it.
// Tested in node (tests/web/test_post_drag_module.py), as base-top.js is.
//
// It computes POSITIONS. It never computes a quantity: every board count on the
// panel comes from the backend, because a second implementation of the packing
// would eventually advertise a saving the cut list does not deliver — and
// plan_cuts packs GLOBALLY, pairing a 998 with a 1002 across bays, so per-bay
// yield is not decomposable into a run-level promise anyway.

// Millimetres per display unit — the one fact this module needs from units.js,
// which it may not import. `displayUnit` arrives as a parameter for the same
// reason: a pure module cannot read `state.units`.
const MM_PER_DISPLAY_UNIT = { mm: 1, cm: 10 };

// mm -> display number. Mirrors units.js::toDisplayValue: cm keeps one decimal
// with the trailing ".0" trimmed by Number division.
function toDisplay(mm, displayUnit) {
  const r = Math.round(mm);
  return displayUnit === "cm" ? r / 10 : r;
}

// The tick spacing a person would call round: ten of whatever unit is on screen
// — 10 mm reading millimetres, 100 mm reading centimetres, both of which render
// as "10". Rounding to a single millimetre is not a snap, it is the pointer.
function roundStepMm(displayUnit) {
  return 10 * (MM_PER_DISPLAY_UNIT[displayUnit] ?? 1);
}

/** The longest PIECE that still yields `pieces` per stock length. Mirrors
 *  strategy/layout.py::yield_threshold — and tests/web/test_post_drag_module.py
 *  compares the two over a grid rather than trusting two literals.
 *
 *  The guards are not decoration: `pieces` of 0 makes an unguarded JS version
 *  return Infinity (Python raises instead), and either way a caller would place
 *  a tick off the end of the run. */
export function yieldThreshold(stockMm, kerfMm, pieces) {
  if (pieces < 1 || stockMm <= 0) return 0;
  return Math.floor((stockMm + kerfMm) / pieces) - kerfMm;
}

// One free gap, laid out the way the backend will lay it out. Mirrors
// strategy/layout.py::equal_layout exactly — n = ceil(L / max), then divmod with
// the remainder spread one millimetre at a time to the FIRST spans. The node
// test compares this against the Python function rather than against literals,
// because a preview that is not the layout the backend builds is a wrong price
// shown confidently.
function equalLayout(lengthMm, maxSpanMm) {
  if (lengthMm <= 0) return [];
  // Python raises ZeroDivisionError here; JS would spin forever on n = Infinity,
  // so a nonsensical maximum yields the single span it describes.
  if (!(maxSpanMm > 0)) return [lengthMm];
  const n = Math.ceil(lengthMm / maxSpanMm);
  const base = Math.floor(lengthMm / n);
  const rem = lengthMm - base * n;
  const out = [];
  for (let i = 0; i < n; i++) out.push(i < rem ? base + 1 : base);
  return out;
}

/** Insert `stationMm` into the fixed stations and fill every resulting gap.
 *
 *  A pin does not exempt the run from the maximum span — it only says where one
 *  post goes. Pinning the middle of a 5 m run under a 2 m maximum gives four
 *  bays of 1250, not two of 2500: the engine still fills each side, and a
 *  preview claiming otherwise is a half-priced promise.
 *
 *  `minSpanMm` is accepted and deliberately unused by the arithmetic, matching
 *  `layout_segment`, which only WARNS about slivers — merging spans to avoid one
 *  would violate the maximum. `violations()` is what reports it. */
export function layoutWithPin(fixedStations, lengthMm, stationMm, { maxSpanMm, minSpanMm } = {}) {
  void minSpanMm;
  if (!(lengthMm > 0)) return { widths: [] };
  const clamp = (s) => Math.min(Math.max(Math.round(s), 0), lengthMm);
  const nodes = [0, lengthMm, ...(fixedStations || []).map(clamp)];
  if (stationMm != null) nodes.push(clamp(stationMm));
  const cuts = [...new Set(nodes)].sort((a, b) => a - b);
  const widths = [];
  for (let i = 0; i + 1 < cuts.length; i++)
    widths.push(...equalLayout(cuts[i + 1] - cuts[i], maxSpanMm));
  return { widths };
}

/** Which bays break which rule. `over_mm` is the distance from the rule in both
 *  directions — the overshoot past the maximum, or the shortfall under the
 *  minimum — because that difference is what the plan and the quote carry
 *  alongside the approved and placed figures (spec §11: `2438` against `1676`,
 *  `+762`).
 *
 *  A bay over the maximum is reported instead of, not as well as, a sliver: the
 *  two can only coexist if the maximum is below the minimum, and then the hard
 *  rule is the one worth naming. */
export function violations(widths, { maxSpanMm, minSpanMm } = {}) {
  const out = [];
  (widths || []).forEach((w, index) => {
    if (maxSpanMm > 0 && w > maxSpanMm)
      out.push({ index, code: "span_placed_over_maximum", over_mm: w - maxSpanMm });
    else if (minSpanMm > 0 && w < minSpanMm)
      out.push({ index, code: "sliver_span", over_mm: minSpanMm - w });
  });
  return out;
}

/** Snap ticks worth offering for a post being dragged between `prev` and `next`.
 *
 *  **Every candidate is filtered through `violations()` before it is returned.**
 *  A rail that offers a tick breaking the same maximum passed into the same call
 *  rewards a person with a permanent warning on a customer's quote — rev 1's
 *  yield tick put the neighbouring bay 2 mm over.
 *
 *  The yield tick converts a PIECE threshold into a BAY width by adding
 *  `pieceShorterByMm`: an infill piece is cut to the clear opening, one whole
 *  post face narrower than the bay holding it. Getting that wrong advertises the
 *  saving in the wrong place. It is labelled per bay and never as a board count,
 *  because counts come from the backend.
 *
 *  `label` is the targeted bay width as a bare number in the display unit; the
 *  adapter adds the unit and the wording through `tu()`, since a pure module can
 *  neither translate nor name a unit. */
export function snapCandidates({
  station, prev, next, maxSpanMm, minSpanMm,
  displayUnit = "mm", stock = null, piecesPerBay = 0, pieceShorterByMm = 0,
}) {
  const out = [];
  if (!(next > prev)) return out;
  const limits = { maxSpanMm, minSpanMm };
  const seen = new Set();

  // `bayMm` is the bay this tick was built to size — the previous one, except
  // for the yield tick measured back from `next`.
  const offer = (candidate, kind, bayMm = null) => {
    const s = Math.round(candidate);
    if (!(s > prev && s < next)) return;   // a tick on a neighbour is not a bay
    if (seen.has(s)) return;
    if (violations([s - prev, next - s], limits).length) return;
    seen.add(s);
    out.push({
      station: s, kind,
      label: String(toDisplay(bayMm == null ? s - prev : bayMm, displayUnit)),
    });
  };

  const step = roundStepMm(displayUnit);
  offer(Math.round(station / step) * step, "round");
  offer((prev + next) / 2, "equal");

  if (stock && stock.lengthMm > 0 && piecesPerBay >= 1) {
    const bay = yieldThreshold(stock.lengthMm, stock.kerfMm || 0, piecesPerBay)
      + pieceShorterByMm;
    if (bay > 0) {
      offer(prev + bay, "yield", bay);
      offer(next - bay, "yield", bay);
    }
  }
  return out;
}
