// NOTES ON THE DRAWING — a promise is attached to the THING it was made about.
//
// The Annotations tab asked a salesperson to pick "r2" from a `<select>`. Nobody
// standing in a customer's garden thinks in run ids: they think "keep the top
// level with the neighbour's fence" — said about *that stretch along the street*
// — or "leave the post clear of that window", which is said about the HOUSE and
// not about any run at all. So a note is attached by clicking the thing on the
// map, and every surface here names its target in words a person would use.
//
// **Verbatim human text is immutable** (CLAUDE.md). That is not a style note in
// this file, it is the shape of the module:
//   - the panel RENDERS notes and never edits them — no rewrite, no truncation,
//     no ellipsis, no "interpretation" shown as if it were what was said;
//   - there is no delete button, because there is no delete endpoint, because a
//     promise a person made is not ours to withdraw;
//   - the text goes out `dir="auto"` and comes back `dir="auto"` — a salesperson
//     writes Hebrew, the app is Hebrew-first, and nothing here translates or
//     normalises what was typed;
//   - a note OUTLIVES its referent. Delete the house and the note about the
//     house still stands: the note is immutable and the drawing is not, so every
//     ref is resolved defensively and an unresolvable one degrades to
//     `notes.target.gone` rather than vanishing or throwing.
//
// DOM ownership: `#notes-panel` (a panel in the side column) and `#g-notes` (a
// group inside `#canvas`). index.html is not this module's file — both hosts are
// LOOKED UP, never created and never moved, and either one being absent silently
// disables that half instead of building a host of its own.

import { apiSend, esc } from "./api.js";
import { landmarkById } from "./context.js";
import {
  clearGroup, el, nodeById, pointAtStation, runById, runLength, stationOfAnchor, toPx,
} from "./geom.js";
import { t } from "./i18n.js";
import { on, reloadProject, state } from "./state.js";

// ---------- target refs ------------------------------------------------------
//
// `Annotation.target_ref` is a free string on the backend and the documented set
// is `"project" | "run:<id>" | "node:<id>" | "event:<id>" | "landmark:<id>"`.
// Free ON PURPOSE: refusing to record a promise because its subject has an id
// shape we did not anticipate loses the promise, not the typo. Everything below
// therefore treats an unknown ref as TEXT, never as an error.

/** `"run:r1"` -> `{kind: "run", id: "r1"}`; `"project"` -> `{kind: "project"}`.
 *
 *  Split on the FIRST colon only: an id is allowed to contain one (a scope-like
 *  ref written by a future version), and swallowing the tail would silently
 *  point a note at a different object. */
function parseRef(ref) {
  const s = String(ref ?? "");
  if (!s) return null;
  const i = s.indexOf(":");
  if (i < 0) return { kind: s, id: "" };
  return { kind: s.slice(0, i), id: s.slice(i + 1) };
}

/** The point/interval event with this id, with the run it lives on, or null.
 *
 *  Searched across every run because a ref names the EVENT, not the run: the
 *  drawing may have been edited since, and a note that recorded a run id would
 *  point at nothing the first time a gate was moved to another stretch. */
function findEvent(id) {
  for (const run of state.project?.topology?.runs || []) {
    for (const ev of run.point_events || [])
      if (ev.id === id) return { run, ev, interval: false };
    for (const ev of run.interval_events || [])
      if (ev.id === id) return { run, ev, interval: true };
  }
  return null;
}

/** `t()` for a key that may not be in the bundle. `t` returns the KEY itself
 *  when nothing resolves, and "context.kind.pool" printed at a salesperson is
 *  worse than "pool": both are wrong, only one is readable. Used for the two
 *  registries that grow without a locale entry each — landmark kinds and event
 *  payload kinds — never for this module's own keys, which are always present. */
function tryT(key, fallback) {
  const s = t(key);
  return s === key ? fallback : s;
}

// Event payload kinds -> the locale keys that already name them. This MIRRORS
// `EVENT_LABEL_KEYS` in inspector.js, which is `const` and not exported; it is
// copied rather than shared because reaching into another panel module for a
// private table is exactly what the frontend module map forbids, and neither
// module may grow an import of the other. The keys are the real `payload.kind`
// values (`elevation_sample`, `height_intent`, `fence_model`) — NOT the tool
// names (`ground`, `height`, `model`), which are what the toolbar buttons say
// and are imperative sentences ("Place gate") rather than nouns.
const EVENT_LABEL_KEYS = {
  gate: "events.gate",
  base: "events.base",
  base_top: "events.base_top",
  elevation_sample: "events.elevation",
  height_intent: "events.height",
  post_tilt: "events.post_tilt",
  fence_model: "events.fence_model",
};

/** What this note is ABOUT, in words — the point of the whole feature.
 *
 *  A salesperson must read *"a note on the house"*, never *"lm3"*. Returns PLAIN
 *  TEXT, never markup: the callers escape it (`esc`) and the panel supplies the
 *  `<bdi>` isolation, because an id or a raw kind embedded in a Hebrew sentence
 *  needs bidi isolation wherever it is rendered, not only where it happened to
 *  fall back.
 *
 *  Never throws. A ref written by a future version, or one whose subject was
 *  deleted, degrades to text — blanking the panel because one note is about a
 *  driveway that is gone would hide the other nine. */
export function targetLabel(ref) {
  const parsed = parseRef(ref);
  if (!parsed) return String(ref ?? "");
  const { kind, id } = parsed;
  try {
    if (kind === "project") return t("notes.target.project");
    if (kind === "run") return t("notes.target.run", { id });
    if (kind === "node") return t("notes.target.node", { id });
    if (kind === "landmark") {
      const lm = landmarkById(state.project?.context?.landmarks, id);
      // The label wins over the kind: "the neighbour's side" and "Street" are
      // the same geometry and different things to the person reading it.
      if (!lm) return t("notes.target.gone");
      return lm.label || tryT(`context.kind.${lm.kind}`, lm.kind);
    }
    if (kind === "event") {
      const hit = findEvent(id);
      // An event is as deletable as a landmark, and the note about it is not:
      // same answer, same reason.
      if (!hit) return t("notes.target.gone");
      const evKind = hit.ev.payload?.kind || "";
      const name = tryT(EVENT_LABEL_KEYS[evKind] || `events.${evKind}`, evKind);
      return t("notes.target.event", { kind: name });
    }
  } catch {
    // a half-loaded project, a ref into a topology mid-swap: the ref itself is
    // still true and still printable
    return String(ref ?? "");
  }
  return String(ref ?? "");
}

/** Where the marker for this ref goes, in world millimetres (y-up), or `null`
 *  for a note that belongs to no point on the drawing.
 *
 *  `null` is not a failure and is not `[0, 0]`: a note on the whole job is about
 *  the job, and dropping a marker for it at the world origin would invent a
 *  place the salesperson never pointed at. Same for a ref that no longer
 *  resolves — the note still shows in the panel, it just has nowhere to sit. */
export function anchorPointFor(ref) {
  const parsed = parseRef(ref);
  if (!parsed || !state.project) return null;
  const { kind, id } = parsed;
  try {
    if (kind === "run") {
      const run = runById(id);
      if (!run) return null;
      // the midpoint: the one point on a stretch that is on the stretch whatever
      // shape it is, including an L with interior vertices
      return pointAtStation(id, Math.round(runLength(run) / 2));
    }
    if (kind === "node") {
      const n = nodeById(id);
      return n ? [n.x_mm, n.y_mm] : null;
    }
    if (kind === "landmark") {
      const lm = landmarkById(state.project?.context?.landmarks, id);
      if (!lm || !lm.points?.length) return null;
      return centroid(lm.points);
    }
    if (kind === "event") {
      const hit = findEvent(id);
      if (!hit) return null;
      // **Never `anchor.offset_mm`.** Anchors are SEGMENT-local (CLAUDE.md,
      // mirroring backend `anchor_station`): on a multi-segment run the offset
      // is a distance along one segment and reading it as a station puts the
      // marker on the wrong leg of an L. `stationOfAnchor` is the one resolver,
      // and it honours the anchor's own reanchor policy.
      const station = hit.interval
        // an interval event is a STRETCH; its marker sits in the middle of it,
        // which is also where a person would point when talking about it
        ? Math.round((stationOfAnchor(hit.run, hit.ev.start_anchor)
                    + stationOfAnchor(hit.run, hit.ev.end_anchor)) / 2)
        : stationOfAnchor(hit.run, hit.ev.anchor);
      return pointAtStation(hit.run.id, station);
    }
  } catch {
    // geom's lookups assume a loaded project; a marker is never worth a throw
    // that would leave the canvas half-drawn
    return null;
  }
  return null;
}

/** Average of the vertices. Good enough for both shapes a landmark can be — a
 *  closed outline and an open polyline — and it needs no special case for the
 *  degenerate ones (a two-point street, a zero-area rectangle). */
function centroid(points) {
  const n = points.length;
  let x = 0, y = 0;
  for (const p of points) { x += p[0]; y += p[1]; }
  return [Math.round(x / n), Math.round(y / n)];
}

// ---------- the markers ------------------------------------------------------

/** One marker per TARGET, not one per note. Three promises about the same gate
 *  are one thing to look at with a 3 on it; three marks stacked on one pixel are
 *  an illegible blob that also lies about how many there are. */
function markerGroups() {
  const byRef = new Map();
  for (const ann of state.project?.annotations || []) {
    const ref = ann.target_ref;
    const at = anchorPointFor(ref);
    if (!at) continue;               // project-wide, or a subject since deleted
    const seen = byRef.get(ref);
    if (seen) seen.count += 1;
    else byRef.set(ref, { ref, at, count: 1 });
  }
  return [...byRef.values()];
}

export function renderNoteMarkers() {
  if (typeof document === "undefined") return;
  // looked up first: `clearGroup` assumes the group is there, and this module
  // never creates a host it was not given
  if (!document.getElementById("g-notes")) return;
  const g = clearGroup("g-notes");
  for (const m of markerGroups()) {
    const [x, y] = toPx(m.at);
    // `pointer-events: none` throughout, and this is the same rule context.js
    // states for landmarks: the drawing's click handling belongs to editor.js,
    // and a marker that swallowed a click meant for the fence in front of it
    // would make the drawing HARDER to edit than it was before there was a note.
    // Quieter than the fence for the same reason — a note is an annotation on
    // the drawing, not a part of it.
    const none = { "pointer-events": "none" };
    el("circle", { cx: x, cy: y, r: 8, fill: "#fffbeb", stroke: "#d97706",
                   "stroke-width": 1.5, opacity: 0.9, class: "note-marker",
                   ...none }, g);
    el("text", { x, y: y + 3, "font-size": 9, "text-anchor": "middle",
                 class: "note-marker-glyph", ...none }, g).textContent = "📝";
    // the count only when there IS a count to report: a "1" beside every marker
    // is noise on the common case
    if (m.count > 1)
      el("text", { x: x + 10, y: y - 5, "font-size": 9, fill: "#b45309",
                   "text-anchor": "start", class: "note-marker-count num",
                   ...none }, g).textContent = String(m.count);
  }
}

// ---------- the popover ------------------------------------------------------
//
// Its own, deliberately: `editor.js` owns `openEventPopover` and importing it
// here would be a cycle (editor.js calls into this module). Same `.popover`
// class, same clamping arithmetic, same capture-phase outside-pointerdown —
// copied so the two behave identically, not shared through an import that would
// make the canvas and its annotations depend on each other.

let popover = null;

function onOutsidePointer(ev) {
  if (popover && !popover.contains(ev.target)) closeNotePopover();
}

/** Exactly one popover at a time — opening closes the previous one, and so does
 *  a project load (a note half-typed about a job you are no longer looking at
 *  must not be saveable against the new one). */
function closeNotePopover() {
  if (!popover) return;
  popover.remove();
  popover = null;
  document.removeEventListener("pointerdown", onOutsidePointer, true);
}

/** Write a note about `target` = `{ref, label}`, at the click.
 *
 *  The caller supplies the label because it knows what was clicked; a target
 *  without one is named by `targetLabel` so no caller can produce a popover
 *  headed by a raw ref. */
export function openNotePopover(target, clientX, clientY) {
  closeNotePopover();
  if (!target?.ref || !state.projectId) return;
  const what = target.label || targetLabel(target.ref);

  popover = document.createElement("div");
  popover.className = "popover note-popover";
  // `t()` substitutes first and `esc()` escapes the result: a landmark labelled
  // "<script>" is a label, and it reaches innerHTML as text.
  popover.innerHTML = `<h4>${esc(t("notes.on", { what }))}</h4>
    <textarea id="note-text" dir="auto" rows="3"
      placeholder="${esc(t("notes.placeholder"))}"></textarea>
    <div class="popover-actions">
      <button id="note-cancel">${esc(t("notes.cancel"))}</button>
      <button id="note-add" class="primary">${esc(t("notes.add"))}</button>
    </div>`;
  document.body.appendChild(popover);
  // positioned at the click and kept inside the viewport. Cursor-anchored, so
  // physical coordinates by nature — the canvas is never mirrored in RTL.
  popover.style.left = `${Math.max(4, Math.min(clientX + 8,
    window.innerWidth - popover.offsetWidth - 12))}px`;
  popover.style.top = `${Math.max(4, Math.min(clientY + 8,
    window.innerHeight - popover.offsetHeight - 12))}px`;

  const field = popover.querySelector("#note-text");
  const addBtn = popover.querySelector("#note-add");

  async function add() {
    const mine = popover;
    const text = field.value.trim();
    // An empty note is not a note. Nothing reaches the API, and the popover
    // stays open with the caret in the box rather than closing as if something
    // had been recorded.
    if (!text) { field.focus(); return; }
    // in-flight: a second press must not post the same promise twice
    addBtn.disabled = true;
    try {
      await apiSend("POST", `/api/projects/${state.projectId}/annotations`,
                    { target_ref: target.ref, text });
    } catch {
      // apiSend already logged the body and showed the dialog. The popover is
      // left OPEN with the text still in it — this is the one thing in the app
      // that cannot be reconstructed from anywhere else, and closing it here
      // would throw away a sentence a person said out loud in a garden.
      if (mine === popover) { addBtn.disabled = false; field.focus(); }
      return;
    }
    if (mine === popover) closeNotePopover();
    // `reloadProject`, never `openProject`: an annotation is a NON-topology
    // mutation and reopening the project would reset history — wiping the undo
    // stack of the salesperson who has been drawing (CLAUDE.md).
    await reloadProject();
  }

  popover.addEventListener("keydown", (ev) => {
    // the canvas has document-level shortcuts (tools, undo); typing prose must
    // not trigger them
    ev.stopPropagation();
    if (ev.key === "Escape") { closeNotePopover(); return; }
    // A note is typed PROSE: Enter makes a new line, which is why this popover
    // submits on Ctrl/Cmd+Enter where the event popover submits on Enter. The
    // buttons are the discoverable path; this is the shortcut for the person
    // writing their fifth note of the evening.
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      add();
    }
  });
  popover.querySelector("#note-cancel").addEventListener("click", closeNotePopover);
  addBtn.addEventListener("click", add);
  field.focus();
  // registered after this click, exactly as editor.js does, or the pointerdown
  // that opened the popover closes it again
  setTimeout(() => document.addEventListener("pointerdown", onOutsidePointer, true), 0);
}

// ---------- the panel --------------------------------------------------------

/** What has been promised on this job. A READING surface: no edit, no delete,
 *  no truncation, no interpretation — see the header. */
function renderPanel() {
  if (typeof document === "undefined") return;
  const host = document.getElementById("notes-panel");
  if (!host) return;
  const notes = state.project?.annotations || [];
  host.innerHTML = `<h3>${esc(t("notes.title"))}</h3>
    <div class="meta">${esc(t("notes.hint"))}</div>
    ${notes.length
      ? `<ul class="notes-list">${notes.map(noteRow).join("")}</ul>`
      : `<div class="meta">${esc(t("notes.empty"))}</div>`}`;
}

function noteRow(ann) {
  // `<bdi>` on the target because it can carry an id or a raw kind, and a Latin
  // id inside a Hebrew sentence reorders without isolation. `dir="auto"` on the
  // text because the salesperson chose its language, not us — and `esc()`
  // because what a person wrote is not markup.
  return `<li class="note-row">
    <div class="meta note-target"><bdi>${esc(targetLabel(ann.target_ref))}</bdi></div>
    <div class="verbatim" dir="auto">${esc(ann.text)}</div>
  </li>`;
}

// ---------- wiring -----------------------------------------------------------

export function initNotes() {
  const redraw = () => { renderPanel(); renderNoteMarkers(); };
  on("project-loaded", () => {
    // whatever was half-typed was about the project that was on screen
    closeNotePopover();
    redraw();
  });
  on("locale-changed", redraw);
  // every label here resolves `sales.<key>` first, so they go stale the instant
  // the role changes (i18n.js `lookup`)
  on("role-changed", redraw);
  // The drawing moved under the markers. The PANEL is redrawn with them for the
  // first two: deleting a landmark or an event does not change a note, but it
  // does change what that note's target is CALLED — the row has to start saying
  // "something no longer on the drawing" at the same moment the marker leaves.
  on("topology-changed", redraw);
  on("context-changed", redraw);
  // a pure view change: nothing is named differently, only drawn elsewhere
  on("fit-view", renderNoteMarkers);
  redraw();
}
