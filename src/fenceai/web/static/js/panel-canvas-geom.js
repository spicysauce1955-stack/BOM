// The panel canvas's pure half: where the handles are, and what a drag WRITES.
//
// Same division `base-top.js` has with `profile.js`, for the same reason —
// "make it that height" and "make this board wider" are point transforms, and a
// transform tangled with a pointer event is only testable by aiming a mouse at a
// browser. Nothing here touches the DOM, the document store or `state.js`.
//
// The drawing is NOT computed here. Every rectangle comes from the server's
// `PanelElevation` (`report/elevation.py`), because the fit that decides where a
// board sits has a justification x excess matrix behind it and a JS copy of it
// would eventually disagree with the cut list the same numbers produced. What
// this module owns is the INVERSE: a pointer landing at 445 mm means
// `width_mm = 145`.
//
// Two rules that look like details and are not:
//
//   * a WIDTH is read absolutely, a GAP and a MARGIN as DELTAS. Under
//     `excess: "space"` the fit spreads the leftover across the gaps, so the
//     drawn gap is not the authored one — reading it back absolutely makes the
//     first pixel of every drag on a spread pattern jump by the spread.
//   * a drag may not author what the publish gate refuses. `validate_model`
//     bounds a member's net advance (width + gap > 0), so the overlap a handle
//     can reach is bounded to it. The author meets the rule at the handle, where
//     it is a limit, rather than at the gate, where it is a rejection.
//
// Every transform returns a NEW object. Undo/redo restores a snapshot of the
// document (`history.js`), and a transform that edited its argument would have
// already spent the value that snapshot holds.

export const SNAP_MM = 5;

export const snap = (mm, step = SNAP_MM) => Math.round(mm / step) * step;

const clamp = (v, lo, hi) => Math.max(lo, Math.min(v, hi));

// --- placement ---------------------------------------------------------------

/** The placement a drag to (x_mm, y_mm) writes.
 *
 * Each kind is measured from the end it names, which is what makes them
 * different things rather than four spellings of a height: a `from_top` rail
 * stays 150 mm below the cap when the bay gets taller, and a `fraction` one
 * stays halfway up it.
 *
 * `distributed` has no per-member position at all — it spreads `count` members
 * between two insets — so only the outermost drawn member is placeable, and it
 * moves the inset on its own side. An interior rail returns the placement
 * unchanged; the canvas draws it no handle, and the inspector says why. */
export function placementFromDrag(placement, {
  orientation = "horizontal", index = 0, count = 1,
  height_mm = 0, width_mm = 0, x_mm = 0, y_mm = 0,
} = {}) {
  const axisLen = orientation === "vertical" ? width_mm : height_mm;
  const along = snap(clamp(orientation === "vertical" ? x_mm : y_mm, 0, axisLen));
  switch (placement?.kind) {
    case "from_bottom":
      return { ...placement, offset_mm: along };
    case "from_top":
      return { ...placement, offset_mm: axisLen - along };
    case "fraction":
      return { ...placement,
               permille: axisLen ? Math.round((along * 1000) / axisLen) : 0 };
    case "distributed": {
      if (index !== 0 && index !== count - 1) return { ...placement };
      const bottom = placement.bottom_inset_mm || 0;
      const top = placement.top_inset_mm || 0;
      return index === 0
        ? { ...placement,
            bottom_inset_mm: clamp(along, 0, Math.max(axisLen - top, 0)) }
        : { ...placement,
            top_inset_mm: clamp(axisLen - along, 0, Math.max(axisLen - bottom, 0)) };
    }
    default:
      return { ...placement };
  }
}

// --- the infill pattern ------------------------------------------------------

/** The width a drag of the trailing edge writes, absolutely.
 *
 * Floored at 1 mm, and at whatever this member's own overlap needs: a board
 * 120 mm inside its neighbour cannot be 100 mm wide, because that pattern never
 * advances and `fit_pattern` cannot lay it out at all. */
export function widthFromDrag(member, { x_mm, member_x_mm }) {
  const floor = Math.max(1, 1 - (member?.gap_after_mm || 0));
  return Math.max(floor, snap(x_mm - member_x_mm));
}

/** The gap a drag writes: the AUTHORED gap plus what the pointer moved.
 *
 * A delta rather than a measurement, because the fit spends the leftover on the
 * gaps and the drawn one is therefore not the authored one. May go negative —
 * that is an overlap, and board-on-board and shadowbox ARE that. Bounded only
 * where the gate bounds it. */
export function gapFromDrag(member, { delta_mm }) {
  const width = member?.width_mm || 0;
  return Math.max(1 - width, (member?.gap_after_mm || 0) + snap(delta_mm));
}

/** The edge margin a drag writes, by the same delta rule and never negative. */
export function marginFromDrag(infill, { delta_mm }) {
  return Math.max(0, (infill?.edge_margin_mm || 0) + snap(delta_mm));
}

/** The gap as a person reads it: "does it overlap, and by how much". */
export function overlapOf(member) {
  const gap = member?.gap_after_mm || 0;
  return { overlaps: gap < 0, amount_mm: Math.abs(gap) };
}

/** ... and back. The control owns the sign, so the author never has to. */
export const gapForOverlap = (overlaps, amount_mm) =>
  (overlaps ? -Math.abs(amount_mm) : Math.abs(amount_mm));

// --- handles -----------------------------------------------------------------

/** Every authored number a drag can reach on this drawing, as a point on it.
 *
 * One handle per NUMBER, never per rectangle: twenty slats of one pattern member
 * share one width, and twenty handles would be twenty ways to set it. `id` is
 * `kind:slot_key:index`, stable across a re-render — which is what lets a
 * re-price land under a hand that is still holding one. */
export function handlesFor(elev, spec) {
  const out = [];
  const members = elev?.members || [];
  const mid = (m) => [Math.round(m.x_mm + m.w_mm / 2), Math.round(m.y_mm + m.h_mm / 2)];

  for (const slot of spec?.frame || []) {
    const drawn = members
      .filter((m) => m.kind === "frame" && m.slot_key === slot.key)
      .sort((a, b) => (a.y_mm - b.y_mm) || (a.x_mm - b.x_mm));
    // a distributed slot's two insets are its only authored positions; every
    // other kind places every member at ONE offset, so any of them sets it
    const placeable = slot.placement?.kind === "distributed"
      ? [...new Set([0, drawn.length - 1])].filter((i) => i >= 0)
      : drawn.map((_, i) => i);
    for (const i of placeable) {
      const m = drawn[i];
      if (!m) continue;
      const [cx, cy] = mid(m);
      out.push({ id: `placement:${slot.key}:${i}`, kind: "placement",
                 slot_key: slot.key, index: i,
                 axis: slot.orientation === "vertical" ? "x" : "y",
                 x_mm: cx, y_mm: cy });
    }
  }

  const infill = spec?.infill;
  const vertical = (infill?.orientation ?? "vertical") === "vertical";
  const along = (m) => (vertical ? m.x_mm : m.y_mm);
  for (const member of infill?.pattern || []) {
    const drawn = members
      .filter((m) => m.kind === "infill" && m.slot_key === member.key)
      .sort((a, b) => along(a) - along(b));
    const first = drawn[0];
    if (!first) continue;
    const [cx, cy] = mid(first);
    const axis = vertical ? "x" : "y";
    out.push({ id: `width:${member.key}:0`, kind: "width", slot_key: member.key,
               index: 0, axis,
               x_mm: vertical ? first.x_mm + first.w_mm : cx,
               y_mm: vertical ? cy : first.y_mm + first.h_mm });
    // The gap handle sits in the middle of the gap AFTER this member, which is
    // where the eye looks for it — and there is one only when something follows,
    // across the WHOLE pattern rather than this member's own placements: in a
    // two-board pattern the thing after board A is board B.
    const next = members
      .filter((m) => m.kind === "infill" && along(m) > along(first))
      .sort((a, b) => along(a) - along(b))[0];
    if (next) {
      out.push({ id: `gap:${member.key}:0`, kind: "gap", slot_key: member.key,
                 index: 0, axis,
                 x_mm: vertical
                   ? Math.round((first.x_mm + first.w_mm + next.x_mm) / 2) : cx,
                 y_mm: vertical
                   ? cy : Math.round((first.y_mm + first.h_mm + next.y_mm) / 2) });
    }
    // `edge_margin_mm` lives on the INFILL, not on a member, so it gets ONE
    // handle however many members the pattern has — on the outermost drawn
    // board, which is the edge the margin actually measures to. A board-on-board
    // pattern was getting one per member, all writing the same number, and the
    // second sat nowhere near the margin it moved.
    if (!out.some((h) => h.kind === "margin")
        && along(first) === Math.min(...members
          .filter((m) => m.kind === "infill").map(along))) {
      out.push({ id: `margin:${member.key}:0`, kind: "margin", slot_key: member.key,
                 index: 0, axis,
                 x_mm: vertical ? first.x_mm : cx,
                 y_mm: vertical ? cy : first.y_mm });
    }
  }
  return out;
}
