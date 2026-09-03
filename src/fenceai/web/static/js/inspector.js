// Inspector + run-editing side panel: decision trail, overrides, and the
// selected run's event list (events are ADDED via the canvas tools, Task 8).

import { apiGet, apiSend, esc } from "./api.js";
import { el, loadCatalogProducts, option, skuSelect } from "./builder-ui.js";
import { runLength, stationOfAnchor } from "./geom.js";
import { pushSnapshot } from "./history.js";
import { currentLocale, t } from "./i18n.js";
import { on, reloadProject, saveTopology, setSelection, state } from "./state.js";
import { currentUnit, enumWord, fmt, fmtLen, tu } from "./units.js";

export function initInspector() {
  const sel = document.getElementById("run-select");
  sel.addEventListener("change", () => setSelection({ runId: sel.value }));
  on("project-loaded", () => {
    renderRunSelectors(); syncRunSelect(); renderOverrides(); renderRunEvents();
  });
  on("result-changed", renderOverrides);
  on("selection-changed", () => { syncRunSelect(); renderRunEvents(); });
  on("locale-changed", () => { renderOverrides(); renderRunEvents(); replay(); });
  on("units-changed", () => {
    renderRunSelectors(); syncRunSelect(); renderOverrides(); renderRunEvents(); replay();
  });
  // a regenerated run invalidates the element ids the last explanation referenced
  on("result-changed", () => { lastInspect = null; });
}

function syncRunSelect() {
  const sel = document.getElementById("run-select");
  if (state.selection.runId && sel.value !== state.selection.runId)
    sel.value = state.selection.runId;
}

// last inspection, replayed when the language or the display unit changes (the
// label is re-rendered from its key + mm params, and the prose is re-fetched)
let lastInspect = null;

// Re-render the panel over whatever `state` holds now. Module scope rather than
// a closure inside initInspector(), because the post inspector below needs the
// same redraw after it has written a directive — and a second, slightly
// different "draw it again" is how the two would come to disagree about what a
// stored override looks like on screen.
function replay() {
  if (lastInspect) inspect(lastInspect.elementId, lastInspect.labelKey, lastInspect.params);
}

export async function inspect(elementId, labelKey, params) {
  lastInspect = { elementId, labelKey, params };
  const body = document.getElementById("inspector-body");
  if (!state.result) return;
  // Awaited BEFORE the body is rebuilt so everything after the explanation is
  // synchronous: the catalog promise is cached in builder-ui.js, so this costs
  // one fetch per session and nothing afterwards.
  const post = postOf(elementId);
  const products = post ? await loadCatalogProducts() : {};
  const label = params ? tu(labelKey, params) : labelKey;
  body.innerHTML = `<strong>${esc(label)}</strong><div class="meta"><bdi>${esc(elementId)}</bdi></div>`;
  try {
    const exp = await apiGet(
      `/api/runs/${state.result.run.id}/explain/${encodeURIComponent(elementId)}`
      + `?lang=${currentLocale()}&units=${currentUnit()}`
    );
    for (const line of exp.explanation) {
      const d = document.createElement("div");
      d.className = line.startsWith("  ←") ? "expl sub" : "expl";
      d.setAttribute("dir", "auto");  // Hebrew lines with LTR SKUs, or English in RTL chrome
      d.textContent = line;
      body.appendChild(d);
    }
  } catch {
    const d = document.createElement("div");
    d.className = "expl";
    d.textContent = t("inspect.no_decisions");
    body.appendChild(d);
  }
  if (post) body.appendChild(postPanel(post, products));
  const corr = document.createElement("div");
  corr.innerHTML = `<hr><em data-i18n="inspect.correction">${t("inspect.correction")}</em><br>
    <input id="corr-comment" placeholder="${esc(t("inspect.correction_placeholder"))}" size="34">
    <button id="btn-correct">${t("inspect.record_correction")}</button>`;
  body.appendChild(corr);
  document.getElementById("btn-correct").addEventListener("click", async () => {
    const comment = document.getElementById("corr-comment").value.trim();
    if (!comment) return alert(t("inspect.describe_correction"));
    await apiSend("POST", `/api/projects/${state.projectId}/corrections`, {
      generation_run_id: state.result.run.id, element_ref: elementId,
      before: {}, after: {}, comment, author: "expert",
    });
    alert(t("inspect.correction_recorded"));
  });
}

// ---------- the post inspector ----------------------------------------------
//
// `strategy/overrides.py` defines six directives and until now exactly ONE was
// reachable from a screen: `pin_post`, through the pin tool's popover.
// `force_post_sku`, `force_mounting`, `force_vertical` and `suppress_post` had
// no control and no locale key, while the generator has honoured all four for
// months. This panel is their first control.
//
// Nothing here regenerates. A directive is a fact about the PROJECT and is
// saved the moment it is chosen; the post in front of you — its product, its
// mounting, the bay beside it — is a fact about the last RUN, and has not been
// recomputed. The panel says so rather than papering over it: a select that
// silently regenerated would be doing the Generate button's job, and the two
// would then disagree about what pressing either one costs.

// SNAP_TOLERANCE_MM (core/units.py). The generator's `_near` matches a
// directive's station to a post's inside this window, so the panel has to use
// the same one to decide which stored directive belongs to the post in front of
// it — a narrower window here edits nothing and shows nothing; a wider one edits
// the neighbouring post's override. Mirrored and named after its source, as
// geom.js mirrors NUMERIC_TOLERANCE_MM.
const DIRECTIVE_SNAP_MM = 25;

// A catalog product is a post because its catalog data says so. Same test the
// gate picker makes for a kit: an opaque sku is not evidence, and "POST" in one
// is another catalog's naming accident.
const POST_TYPE = "post";

function postOf(elementId) {
  return (state.result?.strategy?.posts || []).find((p) => p.id === elementId) || null;
}

/** The (run, station) an override addressed to this post must be written to.
 *
 *  A post standing at a shared node carries `run_ref: "node:<id>"`, which is not
 *  a run and cannot anchor an override. The generator resolves such a post
 *  against every run that TOUCHES the node (`_generate_node_posts` accumulates
 *  `_matched_force_overrides` over all of them), so any touching run is a
 *  correct anchor; the lowest run id is picked so the answer is stable between
 *  two renders of the same post. */
function anchorOf(post) {
  if (!post.run_ref) return null;
  if (!post.run_ref.startsWith("node:"))
    return { runId: post.run_ref, station: post.station_mm };
  const nodeId = post.run_ref.slice("node:".length);
  const runs = (state.project?.topology.runs || [])
    .filter((r) => r.start_node_id === nodeId || r.end_node_id === nodeId)
    .sort((a, b) => (a.id < b.id ? -1 : 1));
  if (!runs.length) return null;
  const run = runs[0];
  return {
    runId: run.id,
    station: run.start_node_id === nodeId ? 0 : runLength(run),
  };
}

/** The bay this post's `force_vertical` control governs: the one that STARTS
 *  here, or — at the far end of a run, where nothing starts — the one that ends
 *  here. Bay bounds rather than a hand-typed interval, because `_forced_vertical`
 *  matches on the bay's midpoint: an interval that covers no midpoint is an
 *  override that reports itself orphaned. */
function bayOf(post, anchor) {
  if (!anchor) return null;
  const near = (v) => Math.abs(v - anchor.station) <= DIRECTIVE_SNAP_MM;
  const spans = (state.result?.strategy?.spans || [])
    .filter((s) => s.run_ref === anchor.runId);
  return spans.find((s) => near(s.start_station_mm))
    || spans.find((s) => near(s.end_station_mm)) || null;
}

/** Every stored override of one kind that this post's controls own. */
function directivesFor(post, anchor, kind) {
  if (!anchor) return [];
  const bay = kind === "force_vertical" ? bayOf(post, anchor) : null;
  return (state.project?.overrides || []).filter((ov) => {
    if (ov.run_id !== anchor.runId || ov.directive.kind !== kind) return false;
    const d = ov.directive;
    if (kind === "force_vertical") {
      if (!bay) return false;
      const mid = (bay.start_station_mm + bay.end_station_mm) / 2;
      return d.start_station_mm <= mid && mid <= d.end_station_mm;
    }
    return Math.abs((d.station_mm ?? 0) - anchor.station) <= DIRECTIVE_SNAP_MM;
  });
}

/** Why this post may NOT be suppressed, as a locale key + params — or null when
 *  it may.
 *
 *  The generator honours `suppress_post` in exactly one place: the loop over a
 *  segment's INTERIOR line posts (`stations[1:-1]`). Every other post is a
 *  boundary the layout is built around, so offering the control there would
 *  write an override that the very next generation reports back as
 *  `orphaned_override`. Refusing it here, with the reason, is the difference
 *  between a control that says no and a control that lies. */
function suppressRefusal(post, anchor) {
  // kind first: it is the post's own answer, and it is the one a reader
  // recognises ("this is a corner") rather than a fact about the data model
  if (post.kind !== "line")
    return { key: "inspect.post_suppress_only_line", params: { kind: post.kind } };
  if (post.pinned) return { key: "inspect.post_suppress_pinned", params: {} };
  if (!anchor || post.run_ref.startsWith("node:"))
    return { key: "inspect.post_suppress_node", params: {} };
  // A `line` post can still be a segment boundary for two reasons the post
  // itself does not record: it ends a locked bay, or the fence becomes a
  // different fence there. Both are readable from the project, and both make
  // the post a `fixed` station the suppression loop never sees.
  const run = state.project?.topology.runs.find((r) => r.id === anchor.runId);
  const near = (v) => Math.abs(v - anchor.station) <= DIRECTIVE_SNAP_MM;
  for (const iv of run?.interval_events || []) {
    if (iv.payload.kind !== "fence_model") continue;
    if (near(stationOfAnchor(run, iv.start_anchor))
      || near(stationOfAnchor(run, iv.end_anchor)))
      return { key: "inspect.post_suppress_boundary", params: {} };
  }
  for (const ov of state.project?.overrides || []) {
    if (ov.run_id !== anchor.runId || ov.directive.kind !== "lock_bay") continue;
    const start = ov.directive.at ? stationOfAnchor(run, ov.directive.at) : null;
    if (start === null) continue;
    if (near(start) || near(start + ov.directive.width_mm))
      return { key: "inspect.post_suppress_boundary", params: {} };
  }
  return null;
}

/** Is a directive stored for this post that the run on screen does not show?
 *
 *  Compared against the RUN rather than tracked as a flag: after a reload,
 *  after an undo, and in a second tab, the honest answer is the same one — the
 *  project says X and the drawing was built before X was said. */
function hasPendingDirective(post, anchor) {
  const bay = bayOf(post, anchor);
  return directivesFor(post, anchor, "suppress_post").length > 0
    || directivesFor(post, anchor, "force_post_sku")
      .some((ov) => ov.directive.sku !== post.sku)
    || directivesFor(post, anchor, "force_mounting")
      .some((ov) => ov.directive.mounting !== post.mounting)
    || (!!bay && directivesFor(post, anchor, "force_vertical")
      .some((ov) => ov.directive.mode !== bay.vertical));
}

/** One committed gesture: replace this post's directive of `kind` with
 *  `directive`, or drop it when `directive` is null.
 *
 *  DELETE-then-POST because there is no `PUT /overrides`: without the delete a
 *  second choice leaves two directives of the same kind at the same station and
 *  the generator honours whichever it reaches first.
 *
 *  `reloadProject()`, never `openProject()` — this is not a topology change, and
 *  reopening the project wipes the undo stack the snapshot above just pushed to. */
async function applyDirective(post, anchor, kind, directive) {
  if (!anchor) return;
  pushSnapshot(`post-${kind}`);
  for (const ov of directivesFor(post, anchor, kind))
    await apiSend("DELETE", `/api/projects/${state.projectId}/overrides/${ov.id}`);
  if (directive)
    await apiSend("POST", `/api/projects/${state.projectId}/overrides`,
      { id: "", run_id: anchor.runId, directive });
  await reloadProject();
  replay();  // the panel re-reads the project; state.result is left alone
}

const MOUNTINGS = ["ground", "masonry"];
const VERTICALS = ["level", "stepped", "raked"];

function labelled(labelText, control) {
  return el("div", {},
    el("label", { class: "builder-field" },
      el("span", { class: "meta", text: labelText }), control));
}

function postPanel(post, products) {
  const anchor = anchorOf(post);
  // `data-post` names WHICH post this panel is for. The panel is rebuilt from
  // scratch on every inspection, so without it a reader — a person glancing at
  // a stale panel, or a test — cannot tell a panel that failed to change from
  // one that did.
  const card = el("div", { class: "card", id: "post-inspector", "data-post": post.id },
    el("strong", { text: t("inspect.post_controls") }));
  if (!anchor) {
    card.appendChild(el("div", { class: "meta", text: t("inspect.post_no_run") }));
    return card;
  }

  // -- force_post_sku: the products this catalog files as posts ---------------
  const postSkus = Object.fromEntries(
    Object.entries(products).filter(([, p]) => (p.attrs || {}).type === POST_TYPE));
  const forcedSku = directivesFor(post, anchor, "force_post_sku")[0]?.directive.sku || "";
  if (Object.keys(postSkus).length) {
    // `skuSelect` (builder-ui.js) is the ONE place that knows a product reads as
    // "SKU — localized name"; a picker written here is how this panel would come
    // to name products differently from the model editor.
    const sel = skuSelect(postSkus, forcedSku, true, (sku) =>
      applyDirective(post, anchor, "force_post_sku",
        sku ? { kind: "force_post_sku", station_mm: anchor.station, sku } : null));
    sel.id = "post-force-sku";
    card.appendChild(labelled(t("inspect.post_product"), sel));
  } else {
    card.appendChild(el("div", { class: "meta", text: t("inspect.post_no_products") }));
  }

  // -- force_mounting: in the ground, or bolted to what it stands on ----------
  const forcedMount = directivesFor(post, anchor, "force_mounting")[0]?.directive.mounting || "";
  const mountSel = el("select", { id: "post-force-mounting" },
    option("", t("inspect.post_as_generated"), !forcedMount),
    ...MOUNTINGS.map((m) => option(m, enumWord(m), forcedMount === m)));
  mountSel.addEventListener("change", () =>
    applyDirective(post, anchor, "force_mounting",
      mountSel.value
        ? { kind: "force_mounting", station_mm: anchor.station, mounting: mountSel.value }
        : null));
  card.appendChild(labelled(t("inspect.post_mounting"), mountSel));

  // -- force_vertical: how the bay beside this post follows the ground --------
  const bay = bayOf(post, anchor);
  if (bay) {
    const forcedMode = directivesFor(post, anchor, "force_vertical")[0]?.directive.mode || "";
    const vertSel = el("select", { id: "post-force-vertical" },
      option("", t("inspect.post_as_generated"), !forcedMode),
      ...VERTICALS.map((m) => option(m, enumWord(m), forcedMode === m)));
    vertSel.addEventListener("change", () =>
      applyDirective(post, anchor, "force_vertical",
        vertSel.value
          ? {
            kind: "force_vertical",
            start_station_mm: bay.start_station_mm,
            end_station_mm: bay.end_station_mm,
            mode: vertSel.value,
          }
          : null));
    card.appendChild(labelled(
      tu("inspect.post_vertical",
        { start_mm: bay.start_station_mm, end_mm: bay.end_station_mm }),
      vertSel));
  } else {
    card.appendChild(el("div", { class: "meta", text: t("inspect.post_no_bay") }));
  }

  // -- suppress_post: only a line post, and the reason when it is not ---------
  const refusal = suppressRefusal(post, anchor);
  const btn = el("button", { id: "post-suppress", text: t("inspect.post_suppress") });
  if (refusal) btn.disabled = true;
  else {
    btn.addEventListener("click", () =>
      applyDirective(post, anchor, "suppress_post",
        { kind: "suppress_post", station_mm: anchor.station }));
  }
  const row = el("div", {}, btn);
  if (refusal)
    row.appendChild(el("span", {
      class: "meta", id: "post-suppress-why", text: tu(refusal.key, refusal.params),
    }));
  card.appendChild(row);

  if (hasPendingDirective(post, anchor))
    card.appendChild(el("div", {
      class: "meta", id: "post-pending", text: t("inspect.post_pending"),
    }));
  return card;
}

function renderRunSelectors() {
  // run-select only; #ann-target belongs to the annotations tab (review #5)
  const sel = document.getElementById("run-select");
  sel.innerHTML = "";
  const runs = state.project ? state.project.topology.runs : [];
  for (const r of runs) {
    const o = document.createElement("option");
    o.value = r.id;
    o.textContent = `${r.id} (${fmtLen(runLength(r))})`;
    sel.appendChild(o);
  }
  // The select shows the first run whether or not anything said so, so SAY it.
  // Another panel asking "which section is in front of me" must be able to read
  // `state.selection` rather than this element: modules talk through state.js,
  // and a reader of someone else's DOM works only while the listeners happen to
  // be registered in the right order.
  if (!state.selection.runId && runs.length) setSelection({ runId: runs[0].id });
}

function renderOverrides() {
  const div = document.getElementById("override-list");
  div.innerHTML = `<h3 data-i18n="inspect.overrides">${t("inspect.overrides")}</h3>`;
  for (const ov of state.project?.overrides || []) {
    const d = document.createElement("div");
    d.className = "card";
    const orphaned = state.result?.orphaned_overrides?.includes(ov.id);
    d.innerHTML = `<bdi>${esc(ov.directive.kind)}</bdi> @ <span class="num">${
      esc(ov.directive.station_mm == null ? "" : fmtLen(ov.directive.station_mm))}</span>
      · <bdi>${esc(ov.run_id)}</bdi>
      ${orphaned ? `<span class="tag rejected">${t("inspect.orphaned")}</span>` : ""}
      <button data-ov="${esc(ov.id)}">${t("common.remove")}</button>`;
    d.querySelector("button").addEventListener("click", async () => {
      pushSnapshot("delete-override");  // removal is a user gesture (review #3)
      await apiSend("DELETE", `/api/projects/${state.projectId}/overrides/${ov.id}`);
      await reloadProject();
    });
    div.appendChild(d);
  }
}

// ---------- selected run's events (delete each with ✕; add = canvas tools) ---
const EVENT_LABEL_KEYS = {
  gate: "events.gate",
  base: "events.base",
  base_top: "events.base_top",
  elevation_sample: "events.elevation",
  height_intent: "events.height",
  post_tilt: "events.post_tilt",
  fence_model: "events.fence_model",
};

function eventLabel(payload) {
  const name = t(EVENT_LABEL_KEYS[payload.kind] || payload.kind);
  if (payload.kind === "gate")
    return `${name} · <span class="num">${esc(fmtLen(payload.width_mm))}</span>`;
  if (payload.kind === "base") return `${name} · ${t("surface." + payload.surface)}`;
  if (payload.kind === "base_top")
    return `${name} · ${t("profile.top_points", { n: payload.points.length })}`;
  if (payload.kind === "elevation_sample")
    return `${name} · z=<span class="num">${esc(fmtLen(payload.z_mm))}</span>`;
  if (payload.kind === "height_intent")
    return `${name} · <span class="num">${esc(fmtLen(payload.height_mm))}</span>`;
  // the id, not the localized name: this list renders synchronously off the
  // topology, and the id is the durable handle a stale listing cannot mistranslate
  if (payload.kind === "fence_model")
    return `${name} · <bdi class="sku">${esc(payload.model_id)}</bdi>`;
  if (payload.kind === "post_tilt")
    return `${name} · ${t("tilt." + payload.mode)}${payload.mode === "custom"
      ? ` (<span class="num">${payload.tilt_deg}</span>°)` : ""}`;
  return name;
}

function renderRunEvents() {
  const div = document.getElementById("run-events");
  if (!div) return;
  div.innerHTML = `<h3 data-i18n="inspect.run_events">${t("inspect.run_events")}</h3>`;
  const runId = state.selection.runId || document.getElementById("run-select").value;
  const run = state.project?.topology.runs.find((r) => r.id === runId);
  if (!run) return;
  const rows = [];
  run.point_events.forEach((pe) => rows.push({
    list: "point_events", id: pe.id,
    html: `${eventLabel(pe.payload)} @ <span class="num">${fmt(stationOfAnchor(run, pe.anchor))}</span>`,
  }));
  run.interval_events.forEach((iv) => rows.push({
    list: "interval_events", id: iv.id,
    // base/base_top cover the whole section: label only, no station range
    html: iv.payload.kind === "base" || iv.payload.kind === "base_top"
      ? eventLabel(iv.payload)
      : `${eventLabel(iv.payload)} · <span class="num">${fmt(stationOfAnchor(run, iv.start_anchor))}–${fmt(stationOfAnchor(run, iv.end_anchor))}</span>`,
  }));
  if (!rows.length) {
    div.innerHTML += `<div class="meta">${t("inspect.no_events")}</div>`;
    return;
  }
  for (const row of rows) {
    const d = document.createElement("div");
    d.className = "event-row";
    d.innerHTML = `<span>${row.html}</span>
      <button class="event-delete" title="${esc(t("common.remove"))}">✕</button>`;
    d.querySelector("button").addEventListener("click", () => {
      // delete by id: a stale render must never splice the wrong event (review #3)
      const idx = run[row.list].findIndex((e) => e.id === row.id);
      if (idx < 0) return;
      pushSnapshot("delete-event");
      run[row.list].splice(idx, 1);
      saveTopology();
    });
    div.appendChild(d);
  }
}
