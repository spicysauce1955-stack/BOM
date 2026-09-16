// ONE STRETCH OF FENCE, FROM THE SIDE — the drawing on an office job card.
//
// The office opens a job it did not draw and has to understand it. A plan says
// where the fence goes; only a side view says what it DOES — that this stretch
// stands on a wall which steps up halfway along, and that above the step there
// is no fence at all.
//
// **Pure, and it imports nothing.** That is the `js/elevation.js` contract and
// it is what makes `bayRects` testable in node with no browser
// (`tests/web/test_section_elevation_module.py`). `renderSectionElevation`
// creates and RETURNS a detached `<svg>`; it subscribes to nothing, reads no
// state, and takes interactivity as an opt-in callback. Nothing here owns a DOM
// id — the caller decides where the element goes.
//
// **Deliberately not `js/profile.js`.** The full side view — dimensions, intent
// dashes, drag handles, the base-height toolbar — is that module's job and it is
// where editing lives. Extracting it for a read-only thumbnail would mean
// refactoring the most tangled module on the page in the same slice as a new
// screen, and a card does not want it anyway: what a card draws is bay
// rectangles on their base, straight off the structure report's own numbers.
// See docs/superpowers/specs/2026-09-16-office-job-screen-design.md §10, which
// carries the trigger for changing this.
//
// **It recomputes nothing.** Every rectangle is a stored bay's `bottom_z_*`,
// `height_mm` and `width_mm`. This module scales them into a box and stops.
//
// **The station axis never mirrors.** Station 0 is at the left in every locale,
// like the plan canvas and the profile (CLAUDE.md), because the drawing has to
// stay geometrically consistent with the plan beside it — and because a
// stationed elevation reads 0 upward from the left in every civil drawing
// anybody in this trade has seen.

/** Padding inside the box, in svg units. Big enough that a full-height panel
 *  does not touch the edge and read as clipped. */
const PAD = 5;

/** A bay carrying no fence is drawn as a MARK, not as a zero-height rectangle.
 *  A rectangle of height 0 is invisible, so a stretch where the wall rose above
 *  the fence top would render as plain wall — which is indistinguishable from
 *  a stretch nobody has looked at, and is the single thing the demo job's
 *  section A exists to show. `empty` is what lets the renderer draw it loudly. */
function isEmpty(bay) {
  return !(Number(bay.height_mm) > 0);
}

function bottomOf(bay) {
  // The two ends of a sloping base. The higher of them is what the panel sits
  // on at its tallest, and taking the average would put a panel through the
  // ground at one end of a steep bay.
  return Math.max(Number(bay.bottom_z_start_mm) || 0,
                  Number(bay.bottom_z_end_mm) || 0);
}

function topOf(bay) {
  return bottomOf(bay) + (Number(bay.height_mm) || 0);
}

/** The vertical range this drawing has to hold: ground at its lowest, fence at
 *  its highest. Zero is always included, because the ground line is the reader's
 *  reference and a drawing that cropped it would float. */
function zRange(section) {
  const bays = section.bays || [];
  const ground = section.ground || [];
  const zs = [0];
  for (const g of ground) zs.push(Number(g.z_mm) || 0);
  for (const b of bays) { zs.push(bottomOf(b)); zs.push(topOf(b)); }
  // A stretch with a stated height and no bays still wants room for it, or a
  // pre-generation card draws a flat line and says nothing.
  if (!bays.length && Number(section.height_intent_mm) > 0) {
    zs.push(Number(section.height_intent_mm));
  }
  const min = Math.min(...zs);
  const max = Math.max(...zs);
  // Never zero: a perfectly flat stretch would divide by it.
  return { min, max, span: max - min || 1 };
}

/** The geometry of one section's thumbnail, in svg units.
 *
 *  Accepts either a `Section` from the structure report (it has `bays`) or a
 *  `SectionFacts` from `report/sections.py` (it has `ground` and no bays). Both
 *  are stretches of the same fence at different moments in their life, and a
 *  card must draw the one it has — a screen that could only draw generated
 *  sections would go blank exactly when somebody opens a job to find out why it
 *  has not been generated.
 *
 *  @returns {{bays: object[], ground: {x: number, y: number}[],
 *             width: number, height: number, pad: number}}
 */
export function bayRects(section, width, height) {
  const pad = PAD;
  const length = Number(section.length_mm) || 0;
  const inner = Math.max(1, width - pad * 2);
  const { min, span } = zRange(section);

  const xOf = (station) => pad + (length ? (station / length) * inner : 0);
  const yOf = (z) => height - pad - ((z - min) / span) * (height - pad * 2);

  const bays = (section.bays || []).map((bay) => {
    const start = Number(bay.start_station_mm) || 0;
    const end = start + (Number(bay.width_mm) || 0);
    const x = xOf(start);
    const bottom = bottomOf(bay);
    const empty = isEmpty(bay);
    const panelY = yOf(topOf(bay));
    return {
      tag: bay.tag || "",
      elementId: bay.element_id || "",
      stationMm: start,
      widthMm: Number(bay.width_mm) || 0,
      heightMm: Number(bay.height_mm) || 0,
      bottomZMm: bottom,
      empty,
      x,
      w: Math.max(0, xOf(end) - x),
      // The fence panel. Zero-height when there is none, and `empty` is what
      // the renderer reads rather than this.
      panelY,
      panelH: Math.max(0, yOf(bottom) - panelY),
      // What it stands on, from the ground line up to the base top.
      baseY: yOf(bottom),
      baseH: Math.max(0, yOf(min) - yOf(bottom)),
    };
  });

  const ground = (section.ground || []).map((g) => ({
    x: xOf(Number(g.station_mm) || 0),
    y: yOf(Number(g.z_mm) || 0),
  }));

  return { bays, ground, width, height, pad };
}

const NS = "http://www.w3.org/2000/svg";

function el(name, attrs) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, String(v));
  return node;
}

/** A detached `<svg>` of one stretch, ready to be put wherever the caller wants.
 *
 *  @param section a `Section` or a `SectionFacts` — see `bayRects`.
 *  @param opts `{width, height, label, onSelectBay}`. `onSelectBay` is the only
 *         interactivity and it is OPT-IN: without it the drawing is inert, which
 *         is what a reading surface wants. With it, each bay becomes a button —
 *         the seam for selecting one bay (spec §3).
 */
export function renderSectionElevation(section, opts = {}) {
  const width = opts.width || 300;
  const height = opts.height || 80;
  const geom = bayRects(section, width, height);

  const svg = el("svg", {
    class: "section-elev",
    viewBox: `0 0 ${width} ${height}`,
    // An image to a screen reader, with the caller's sentence: the shapes carry
    // no text and a reader hearing "graphic" learns nothing.
    role: "img",
    "aria-label": opts.label || "",
  });

  for (const bay of geom.bays) {
    // What it stands on, drawn first so the fence overlaps it rather than the
    // other way round.
    if (bay.baseH > 0) {
      svg.appendChild(el("rect", {
        class: "section-elev-base",
        x: bay.x, y: bay.baseY, width: bay.w, height: bay.baseH,
      }));
    }
    if (bay.empty) {
      // No fence here, and it has to be LOUD — see `isEmpty`.
      svg.appendChild(el("line", {
        class: "section-elev-nofence",
        x1: bay.x, y1: bay.baseY, x2: bay.x + bay.w, y2: bay.baseY,
      }));
    } else {
      const rect = el("rect", {
        class: "section-elev-panel",
        x: bay.x, y: bay.panelY, width: bay.w, height: bay.panelH,
      });
      svg.appendChild(rect);
    }
    if (opts.onSelectBay && bay.elementId) {
      // A transparent target over the whole bay, so a thin panel is still
      // clickable and a zero-height one is clickable at all.
      const hit = el("rect", {
        class: "section-elev-hit",
        x: bay.x, y: geom.pad, width: bay.w, height: height - geom.pad * 2,
        "data-element-id": bay.elementId,
      });
      hit.addEventListener("click", () => opts.onSelectBay(bay.elementId));
      svg.appendChild(hit);
    }
  }

  if (geom.ground.length > 1) {
    svg.appendChild(el("polyline", {
      class: "section-elev-ground",
      points: geom.ground.map((p) => `${p.x},${p.y}`).join(" "),
    }));
  }

  return svg;
}
