// Inspector + run-editing side panel: decision trail, overrides, and the
// selected run's event list (events are ADDED via the canvas tools, Task 8).

import { apiGet, apiSend, esc } from "./api.js";
import { runLength, stationOfAnchor } from "./geom.js";
import { pushSnapshot } from "./history.js";
import { currentLocale, t } from "./i18n.js";
import { on, reloadProject, saveTopology, setSelection, state } from "./state.js";
import { fmt, fmtLen } from "./units.js";

export function initInspector() {
  const sel = document.getElementById("run-select");
  sel.addEventListener("change", () => setSelection({ runId: sel.value }));
  on("project-loaded", () => {
    renderRunSelectors(); syncRunSelect(); renderOverrides(); renderRunEvents();
  });
  on("result-changed", renderOverrides);
  on("selection-changed", () => { syncRunSelect(); renderRunEvents(); });
  on("locale-changed", () => { renderOverrides(); renderRunEvents(); });
  on("units-changed", () => {
    renderRunSelectors(); syncRunSelect(); renderOverrides(); renderRunEvents();
  });
}

function syncRunSelect() {
  const sel = document.getElementById("run-select");
  if (state.selection.runId && sel.value !== state.selection.runId)
    sel.value = state.selection.runId;
}

export async function inspect(elementId, label) {
  const body = document.getElementById("inspector-body");
  if (!state.result) return;
  body.innerHTML = `<strong>${esc(label)}</strong><div class="meta"><bdi>${esc(elementId)}</bdi></div>`;
  try {
    const exp = await apiGet(
      `/api/runs/${state.result.run.id}/explain/${encodeURIComponent(elementId)}?lang=${currentLocale()}`
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

function renderRunSelectors() {
  // run-select only; #ann-target belongs to the annotations tab (review #5)
  const sel = document.getElementById("run-select");
  sel.innerHTML = "";
  for (const r of state.project ? state.project.topology.runs : []) {
    const o = document.createElement("option");
    o.value = r.id;
    o.textContent = `${r.id} (${fmtLen(runLength(r))})`;
    sel.appendChild(o);
  }
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
