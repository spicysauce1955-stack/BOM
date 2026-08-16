// The joint, drawn as a section: how one member actually meets the one it lands
// on, at a scale where 15 mm is legible.
//
// The panel elevation cannot show this and should not try. A 15 mm engagement on
// an 1800 mm panel is eight thousandths of the drawing — at that scale a slat
// seated into a channel and a slat butted onto a rail are the same picture, and
// they are 135 mm apart on the cut list. So the joint gets its own view at its
// own scale, beside the panel rather than on top of it.
//
// Pure: a `JointDetail` in, bands and dimensions out, in millimetres along the
// member's own axis. No DOM, no state, no fetch — `assembly.js` places it.
//
// The coordinate this section is measured along runs from the FLOOR of the
// housing outward into the panel, because that is the datum every number on a
// `JointDetail` is stated against: the channel is `channel_depth_mm` deep from
// the floor, the member is engaged `engagement_mm` in from the mouth, and the
// margin is the clearance the member must leave above the floor.

// What a member with no declared face height is drawn as, as a fraction of the
// housing it enters. The same choice the panel elevation makes, and reported the
// same way (`declared: false`) rather than passed off as measured.
const NOMINAL_MEMBER_PERMILLE = 600;

// How much of the member is drawn beyond the mouth of the housing: enough to
// read as "and it continues", not so much that the joint becomes a sliver.
const EXPOSED_PERMILLE = 900;

/** One joint as a section, or null when there is nothing to draw.
 *
 * A butt landing with no housing and no engagement is not a section: two faces
 * meeting is what the elevation already shows, and an empty detail box invites
 * the reader to look for something that is not there.
 */
export function jointSection(detail) {
  if (!detail) return null;
  const depth = detail.channel_depth_mm || 0;
  const engagement = detail.engagement_mm || 0;
  if (depth <= 0 && engagement <= 0) return null;

  // the member's tip, measured from the floor of the housing. Engaged from the
  // MOUTH inward, so a 15 mm engagement into a 20 mm channel leaves the tip
  // 5 mm above the floor — and the margin says that clearance is intended.
  const tip = Math.max(depth - engagement, 0);
  const exposed = Math.max((depth * EXPOSED_PERMILLE) / 1000, engagement, 1);
  const declaredMember = (detail.member_thickness_mm || 0) > 0;
  const member = declaredMember
    ? detail.member_thickness_mm
    : Math.max(Math.round((depth * NOMINAL_MEMBER_PERMILLE) / 1000), 1);

  const bands = [];
  // the clearance below the tip is the void the margin is about: drawn, because
  // "is there room for it to sit down" is exactly what a fitter asks of a
  // channel, and an unlabelled empty band answers it
  if (tip > 0) bands.push({ role: "clearance", from_mm: 0, to_mm: tip });
  if (depth > tip) bands.push({ role: "seated", from_mm: tip, to_mm: depth });
  bands.push({ role: "exposed", from_mm: depth, to_mm: depth + exposed });

  const dims = [];
  if (depth > 0)
    dims.push({ kind: "channel", from_mm: 0, to_mm: depth, value_mm: depth });
  if (engagement > 0)
    dims.push({ kind: "engagement", from_mm: tip, to_mm: depth, value_mm: engagement });
  if (detail.margin_mm > 0)
    dims.push({ kind: "margin", from_mm: 0, to_mm: detail.margin_mm,
                value_mm: detail.margin_mm });

  return {
    key: detail.key,
    member_slot: detail.member_slot,
    frame_slot: detail.frame_slot,
    end: detail.end,
    kind: detail.kind || "butt",
    // the housing's own face height, across the section: the member enters it,
    // so it has to be drawn wider than the member or the picture says the
    // opposite of what it means
    frame_thickness_mm: detail.frame_thickness_mm || 0,
    member_thickness_mm: member,
    declared: !!detail.declared && declaredMember,
    tip_mm: tip,
    extent_mm: depth + exposed,
    bands,
    dims,
  };
}

/** Every section for one member slot, base end first.
 *
 * Both ends, because a member can be housed at both and one of the two is not
 * "the" joint — which is also how the ambiguous `JointDetail.key` is settled:
 * the pair (member_slot, end) is what a reader selects on, and showing both
 * removes the choice rather than guessing it. */
export function sectionsFor(elevation, memberSlot) {
  return (elevation?.details || [])
    .filter((d) => d.member_slot === memberSlot)
    .sort((a, b) => (a.end === b.end ? 0 : a.end === "base" ? -1 : 1))
    .map(jointSection)
    .filter(Boolean);
}

/** Millimetres along the member axis -> drawing units, for one section box.
 *
 * ONE scale for both axes here too, for the same reason the elevation states:
 * a section whose depth was stretched to fill its box would make a 3 mm margin
 * and a 20 mm channel look like the same clearance. */
export function sectionPlacement(section, {
  maxWidth = 240, maxHeight = 190, padStart = 46, padEnd = 14,
  padTop = 16, padBottom = 30,
} = {}) {
  const across = Math.max(section.frame_thickness_mm,
                          section.member_thickness_mm * 2, 1);
  const along = Math.max(section.extent_mm, 1);
  const s = Math.min((maxWidth - padStart - padEnd) / across,
                     (maxHeight - padTop - padBottom) / along);
  return {
    scale: s,
    // the axis runs UP the box: the floor of the housing at the bottom, the
    // panel above it, which is how a fitter looks at a bottom channel
    px: (mm) => padStart + mm * s,
    py: (mm) => padTop + (along - mm) * s,
    across_mm: across,
    viewBox: { w: padStart + across * s + padEnd,
               h: padTop + along * s + padBottom },
  };
}
