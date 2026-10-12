// A new interval of one kind takes the stretch it covers from every older
// interval of that kind — pure, no DOM, no state.
//
// Why it exists: the generator reads the FIRST interval event that covers a
// station (`generator._interval_at`), and the height tool used to append. So a
// height stated over an older one was never built — the office set 1750 over
// the salesperson's 1800, the screen showed 1750 in the event list, and the
// fence came out at 1800 (docs/superpowers/specs/2026-10-12-office-desk-
// without-ai-design.md, "a second height never wins").
//
// The model tool already replaces whatever its stretch touches, whole. A height
// is carved more carefully, because the older height is somebody's measurement
// and is still true wherever the new one does not reach: 1800 over 0–6000, then
// 1750 over 3000–6000, leaves 1800 over 0–3000.
//
// Anchors and ids come in as callbacks so this module stays node-testable and
// cannot grow a second implementation of anchoring — `geom.anchorFor` and
// `geom.stationOfAnchor` are the only ones, and they mirror the backend.

/** `events` with every `kind` event's overlap with `(start, end)` removed.
 *
 *  Covered → dropped. Overhanging one end → shortened, same id. Containing the
 *  new stretch → split: the part before keeps the id, the part after gets a new
 *  one and the same payload. Touching at a boundary is not overlap. Events of
 *  other kinds pass through untouched, in order. Returns a NEW array; neither
 *  the array nor any event in it is mutated. */
export function carveInterval(events, kind, start, end, { stationOf, anchorAt, newId }) {
  const out = [];
  for (const ev of events) {
    if (ev.payload?.kind !== kind) { out.push(ev); continue; }
    const s0 = stationOf(ev.start_anchor);
    const s1 = stationOf(ev.end_anchor);
    if (s1 <= start || s0 >= end) { out.push(ev); continue; }
    if (s0 < start)
      out.push({ ...ev, end_anchor: anchorAt(start) });
    // The second half of a split is its own event, so it gets its own payload:
    // two events sharing one object would let an in-place edit of one (the
    // inspector edits payloads in place) silently rewrite the other.
    if (s1 > end)
      out.push({
        ...ev,
        id: s0 < start ? newId() : ev.id,
        start_anchor: anchorAt(end),
        payload: s0 < start ? structuredClone(ev.payload) : ev.payload,
      });
  }
  return out;
}
