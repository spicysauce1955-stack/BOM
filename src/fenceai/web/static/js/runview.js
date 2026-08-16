// The macro viewport's geometry: a StructureReport, unrolled into an elevation.
//
// The fence STANDING UP, end to end — what the plan canvas cannot show (it looks
// down) and what the profile side view deliberately does not show (it draws the
// ground and the post tops so they can be EDITED, at 5x vertical exaggeration,
// which is a measuring instrument rather than a picture of a fence).
//
// This module PLACES, it does not compute. Every station, elevation, height,
// width and embedment on its output is a field of the structure report — which
// is itself a derived read model that "must never recompute a quantity". A macro
// view that derived a bay width from two stations would be a third opinion about
// a number the report and the BOM already agree on, and the first one to drift.
//
// The ONE transform it owns is the same one `elevation.js` owns: world
// millimetres to drawing units, y flipped (elevation grows up, SVG y grows
// down), ONE scale for both axes. A drawing stretched to fill its box would make
// a 600 mm footing and a 1800 mm panel look like the same thing.
//
// Pure: no DOM, no state, no fetch. `assembly.js` places what this returns.
// (Same split as `base-top.js` / `profile.js`, and for the same reason — the
// maths is testable under node and the wiring is not.)

// Disconnected sections are drawn on one line with a gap between them, exactly
// as the side view chains them: the same 600 mm, so a fence read in one panel
// and then the other does not appear to change length.
export const SECTION_GAP_MM = 600;

// What a post is drawn as when its product declares no `face_width_mm`. Reported
// as `declared: false` so the drawing can say the width is a nominal, the way the
// panel elevation already says it for an undeclared member face. Never silently
// widened into a measured-looking figure.
export const NOMINAL_POST_FACE_MM = 80;

// A footing is drawn wider than the post it holds, because that is what a footing
// is. This is a DRAWING convention, not a dimension: nothing dimensions it, and
// the concrete quantity is the BOM's (`CoverageBased`, per post footing), never
// this rectangle's area.
const FOOTING_FLARE = 1.9;

/** Which stations carry concrete — i.e. which posts are drawn standing in one. */
const hasFooting = (station) =>
  (station.parts || []).some((p) => p.role === "concrete" && p.qty > 0);

/** The macro model: everything the drawing needs, in world millimetres.
 *
 * `x` runs along the unrolled fence (0 at the first section's first station),
 * `z` is elevation, positive up, in the topology's own datum.
 *
 * `faceWidths` maps sku -> declared face width (from the catalog, which the
 * caller already caches). Absent is the normal case and is not an error.
 */
export function macroModel(report, { faceWidths = {}, gapMm = SECTION_GAP_MM } = {}) {
  const out = {
    sections: [], posts: [], bays: [], gates: [], steps: [],
    total_mm: 0, z_min_mm: 0, z_max_mm: 0, run_id: report?.run_id || "",
  };
  if (!report?.sections?.length) return out;

  let cursor = 0;
  for (const section of report.sections) {
    const x0 = cursor;
    const stations = [...(section.setting_out || [])]
      .sort((a, b) => a.station_mm - b.station_mm);
    const at = (station_mm) => x0 + station_mm;

    out.sections.push({
      tag: section.tag,
      run_id: section.run_id,
      x0_mm: x0,
      length_mm: section.length_mm,
      base_surface: section.base_surface,
      height_mm: section.height_mm ?? null,
      // the ground under this section, as the report samples it: one point per
      // station, which is exactly where the ground elevation is known
      ground: stations.map((s) => [at(s.station_mm), s.ground_z_mm]),
      // where a post stands on something built rather than on the ground
      base: stations.map((s) => [at(s.station_mm), s.base_z_mm]),
    });

    // --- bays -----------------------------------------------------------
    // A bay is a parallelogram, not a rectangle: a raked bay's two ends sit at
    // different elevations and its top follows. Drawing it as a rectangle would
    // erase the one thing a raked bay looks like.
    for (const bay of section.bays || []) {
      out.bays.push({
        element_id: bay.element_id,
        tag: bay.tag,
        run_id: section.run_id,
        x0_mm: at(bay.start_station_mm),
        x1_mm: at(bay.end_station_mm),
        width_mm: bay.width_mm,
        height_mm: bay.height_mm,
        vertical: bay.vertical,
        bottom_start_z_mm: bay.bottom_z_start_mm,
        bottom_end_z_mm: bay.bottom_z_end_mm,
        top_start_z_mm: bay.bottom_z_start_mm + bay.height_mm,
        top_end_z_mm: bay.bottom_z_end_mm + bay.height_mm,
        elevation: bay.elevation || null,
        from_tag: bay.from_tag || null,
        to_tag: bay.to_tag || null,
      });
    }

    // --- gates ----------------------------------------------------------
    // A gate has no panel and no height of its own on the report. It is drawn to
    // the height of the fence it interrupts — the neighbouring bays', or the
    // section's single height — and to nothing at all when neither is known,
    // rather than to an invented default.
    for (const gate of section.gates || []) {
      const neighbours = (section.bays || [])
        .filter((b) => b.end_station_mm <= gate.start_station_mm
                    || b.start_station_mm >= gate.end_station_mm);
      const height = section.height_mm
        ?? (neighbours.length ? Math.max(...neighbours.map((b) => b.height_mm)) : null);
      const bottom = groundAt(stations, gate.start_station_mm);
      out.gates.push({
        element_id: gate.element_id,
        tag: gate.tag,
        run_id: section.run_id,
        x0_mm: at(gate.start_station_mm),
        x1_mm: at(gate.end_station_mm),
        opening_mm: gate.opening_mm,
        kit_sku: gate.kit_sku || null,
        height_mm: height,
        bottom_z_mm: bottom,
        declared_height: height !== null,
      });
    }

    // --- posts ----------------------------------------------------------
    for (const station of stations) {
      const x = at(station.station_mm);
      const declaredFace = faceWidths[station.sku];
      const face = Number.isFinite(declaredFace) && declaredFace > 0
        ? declaredFace : NOMINAL_POST_FACE_MM;
      // The post's TOP is the fence's top where it meets it — the tallest thing
      // this post carries. Drawn to the design line rather than to the stock
      // length: `post_length_mm` is the bar that arrives, and a post drawn to it
      // stands proud of the fence by however much the installer cuts off.
      const carried = adjacentTops(out, station, x);
      out.posts.push({
        element_id: station.element_id,
        tag: station.tag,
        run_id: section.run_id,
        sku: station.sku,
        kind: station.kind,
        x_mm: x,
        face_mm: face,
        declared_face: Number.isFinite(declaredFace) && declaredFace > 0,
        ground_z_mm: station.ground_z_mm,
        base_z_mm: station.base_z_mm,
        top_z_mm: carried !== null ? carried : station.base_z_mm,
        declared_top: carried !== null,
        // 0 is a real answer here and means "embeds nothing" (a masonry post),
        // not "unknown": the generator resolves embedment for every post before
        // it decides whether there is a bay to measure exposure against.
        embed_mm: station.embed_mm || 0,
        post_length_mm: station.post_length_mm ?? null,
        footing: hasFooting(station),
        pinned: !!station.pinned,
        reinforced: !!station.reinforced,
        shared_from: station.shared_from || null,
      });
    }

    cursor = x0 + section.length_mm + gapMm;
  }

  // --- steps -------------------------------------------------------------
  // Where the fence changes level between two adjacent bays. Read off the bays'
  // own bottom elevations rather than off the ground, because a stepped fence
  // steps where the LAYOUT says it does — which is the decision the drawing is
  // there to show, and it does not always land on a change in the grade.
  const byRun = new Map();
  for (const bay of out.bays) {
    if (!byRun.has(bay.run_id)) byRun.set(bay.run_id, []);
    byRun.get(bay.run_id).push(bay);
  }
  for (const bays of byRun.values()) {
    const ordered = [...bays].sort((a, b) => a.x0_mm - b.x0_mm);
    for (let i = 0; i + 1 < ordered.length; i += 1) {
      const a = ordered[i];
      const b = ordered[i + 1];
      const rise = b.bottom_start_z_mm - a.bottom_end_z_mm;
      if (rise === 0) continue;
      out.steps.push({
        x_mm: (a.x1_mm + b.x0_mm) / 2,
        from_z_mm: a.bottom_end_z_mm,
        to_z_mm: b.bottom_start_z_mm,
        rise_mm: Math.abs(rise),
        from_tag: a.tag,
        to_tag: b.tag,
      });
    }
  }

  out.total_mm = out.sections.length
    ? Math.max(...out.sections.map((s) => s.x0_mm + s.length_mm)) : 0;
  const zs = [
    ...out.posts.flatMap((p) => [p.top_z_mm, p.base_z_mm - p.embed_mm, p.ground_z_mm]),
    ...out.bays.flatMap((b) => [b.top_start_z_mm, b.top_end_z_mm,
                                b.bottom_start_z_mm, b.bottom_end_z_mm]),
  ];
  out.z_min_mm = zs.length ? Math.min(...zs) : 0;
  out.z_max_mm = zs.length ? Math.max(...zs) : 0;
  return out;
}

/** The top of everything this post carries, or null when it carries nothing.
 *
 * A post between two bays of different heights is drawn to the taller one: that
 * is what is actually built, and it is how a step reads as a step. A post with no
 * bay at all — a gate hung at the end of a run — has no design top to be drawn
 * to, and the caller says so (`declared_top: false`) instead of inventing one. */
function adjacentTops(out, station, x) {
  // Matched by position within the chain. NOT a cross-section lookup: each
  // section is unrolled at its own offset, so a corner post's two copies sit at
  // two different x and can never see each other's bays — claiming otherwise
  // here was a comment describing behaviour the code does not have.
  const tops = [];
  for (const bay of out.bays) {
    if (bay.x0_mm === x) tops.push(bay.top_start_z_mm);
    if (bay.x1_mm === x) tops.push(bay.top_end_z_mm);
  }
  for (const gate of out.gates) {
    if (gate.height_mm === null) continue;
    if (gate.x0_mm === x || gate.x1_mm === x)
      tops.push(gate.bottom_z_mm + gate.height_mm);
  }
  return tops.length ? Math.max(...tops) : null;
}

/** The ground elevation at a station, linearly between the two it lies between.
 *
 * The report samples the ground AT the stations, so this interpolates between
 * two known points and never extrapolates past the ends — a gate leaf hanging
 * below a guessed ground line is a drawing that argues with the site. */
export function groundAt(stations, station_mm) {
  if (!stations.length) return 0;
  let previous = stations[0];
  for (const station of stations) {
    if (station.station_mm === station_mm) return station.ground_z_mm;
    if (station.station_mm > station_mm) {
      const span = station.station_mm - previous.station_mm;
      if (span <= 0) return station.ground_z_mm;
      const t = (station_mm - previous.station_mm) / span;
      return Math.round(previous.ground_z_mm
        + (station.ground_z_mm - previous.ground_z_mm) * t);
    }
    previous = station;
  }
  return previous.ground_z_mm;
}

/** World millimetres -> drawing units.
 *
 * One scale for both axes, fitted to the drawing rather than to a fixed box, so
 * a short fence is not drawn as a stripe across a wide sheet. The padding is
 * asymmetric because the annotations are: the height dimension runs up the start
 * edge, the length dimension under the whole thing, and the embed dimension
 * needs room below the deepest footing. */
export function macroPlacement(model, {
  maxWidth = 1180, maxHeight = 430,
  padStart = 64, padEnd = 24, padTop = 34, padBottom = 62,
} = {}) {
  const w = Math.max(model.total_mm, 1);
  const h = Math.max(model.z_max_mm - model.z_min_mm, 1);
  const s = Math.min(maxWidth / w, maxHeight / h);
  const dw = w * s;
  const dh = h * s;
  return {
    scale: s,
    x0: padStart,
    y0: padTop,
    width: dw,
    height: dh,
    viewBox: { w: padStart + dw + padEnd, h: padTop + dh + padBottom },
    // z flipped: the model's z grows up, SVG's y grows down
    px: (mm) => padStart + (mm - 0) * s,
    pz: (mm) => padTop + (model.z_max_mm - mm) * s,
    len: (mm) => mm * s,
  };
}

/** The dimensions this drawing carries, in world millimetres.
 *
 * Descriptors, not geometry: each says WHAT is being measured and between which
 * two world coordinates, and the renderer decides where the witness lines go.
 * Kept here so the set of dimensions is testable without a DOM — "the drawing
 * dimensions every bay" is a claim about this list.
 *
 * Every value is a field of the report. Nothing here measures the drawing. */
export function macroDimensions(model, { bays = true, heights = true,
                                         embed = true, steps = true,
                                         total = true } = {}) {
  const dims = [];
  if (total && model.total_mm > 0)
    dims.push({ kind: "total", axis: "x", from_mm: 0, to_mm: model.total_mm,
                value_mm: model.total_mm });
  if (bays)
    for (const bay of model.bays)
      dims.push({ kind: "bay", axis: "x", ref: bay.element_id, tag: bay.tag,
                  from_mm: bay.x0_mm, to_mm: bay.x1_mm, value_mm: bay.width_mm,
                  z_mm: Math.min(bay.bottom_start_z_mm, bay.bottom_end_z_mm) });
  if (heights)
    for (const bay of model.bays)
      dims.push({ kind: "height", axis: "z", ref: bay.element_id, tag: bay.tag,
                  from_mm: bay.bottom_start_z_mm, to_mm: bay.top_start_z_mm,
                  value_mm: bay.height_mm, x_mm: bay.x0_mm });
  if (embed)
    for (const post of model.posts) {
      if (!post.embed_mm) continue;
      dims.push({ kind: "embed", axis: "z", ref: post.element_id, tag: post.tag,
                  from_mm: post.base_z_mm - post.embed_mm, to_mm: post.base_z_mm,
                  value_mm: post.embed_mm, x_mm: post.x_mm });
    }
  if (steps)
    for (const step of model.steps)
      dims.push({ kind: "step", axis: "z", from_mm: Math.min(step.from_z_mm, step.to_z_mm),
                  to_mm: Math.max(step.from_z_mm, step.to_z_mm),
                  value_mm: step.rise_mm, x_mm: step.x_mm,
                  tag: `${step.from_tag}–${step.to_tag}` });
  return dims;
}

/** The footing under a post, as a trapezoid in world millimetres, or null.
 *
 * A drawing convention with no dimension on it: the concrete quantity is the
 * BOM's (a coverage-based application per footing), and a shape here that could
 * be measured would invite someone to measure it. */
export function footingShape(post, { flare = FOOTING_FLARE } = {}) {
  if (!post.footing || !post.embed_mm) return null;
  const half = (post.face_mm * flare) / 2;
  const top = post.base_z_mm;
  const bottom = post.base_z_mm - post.embed_mm;
  return [
    [post.x_mm - post.face_mm / 2, top],
    [post.x_mm + post.face_mm / 2, top],
    [post.x_mm + half, bottom],
    [post.x_mm - half, bottom],
  ];
}
