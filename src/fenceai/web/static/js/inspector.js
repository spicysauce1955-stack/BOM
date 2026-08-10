// Inspector + run-editing side panel. Task 8 replaces the event forms with
// on-canvas tools; the decision-trail and overrides views live here permanently.

import { apiGet, apiSend, esc } from "./api.js";
import { runLength } from "./geom.js";
import { pushSnapshot } from "./history.js";
import { currentLocale, t } from "./i18n.js";
import {
  addIntervalEvent, addPointEvent, on, refreshProject, saveTopology, state,
} from "./state.js";

export function initInspector() {
  setupForms();
  on("project-loaded", () => { renderRunSelectors(); renderOverrides(); });
  on("result-changed", renderOverrides);
  on("locale-changed", renderOverrides);
}

export async function inspect(elementId, label) {
  const body = document.getElementById("inspector-body");
  if (!state.result) return;
  body.innerHTML = `<strong>${esc(label)}</strong><div class="meta"><bdi>${esc(elementId)}</bdi></div>`;
  try {
    const exp = await apiGet(
      `/api/runs/${state.result.run.id}/explain/${encodeURIComponent(elementId)}`
    );
    for (const line of exp.explanation) {
      const d = document.createElement("div");
      d.className = line.startsWith("  ←") ? "expl sub" : "expl";
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
  const runs = state.project ? state.project.topology.runs : [];
  for (const selId of ["run-select", "ann-target"]) {
    const sel = document.getElementById(selId);
    if (!sel) continue;
    sel.innerHTML = "";
    if (selId === "ann-target") {
      const o = document.createElement("option");
      o.value = "project";
      o.textContent = t("annotations.whole_project");
      sel.appendChild(o);
    }
    for (const r of runs) {
      const o = document.createElement("option");
      o.value = selId === "ann-target" ? `run:${r.id}` : r.id;
      o.textContent = `${r.id} (${runLength(r)} mm)`;
      sel.appendChild(o);
    }
  }
}

function renderOverrides() {
  const div = document.getElementById("override-list");
  div.innerHTML = `<h3 data-i18n="inspect.overrides">${t("inspect.overrides")}</h3>`;
  for (const ov of state.project?.overrides || []) {
    const d = document.createElement("div");
    d.className = "card";
    const orphaned = state.result?.orphaned_overrides?.includes(ov.id);
    d.innerHTML = `<bdi>${esc(ov.directive.kind)}</bdi> @ ${esc(ov.directive.station_mm ?? "")}
      · <bdi>${esc(ov.run_id)}</bdi>
      ${orphaned ? `<span class="tag rejected">${t("inspect.orphaned")}</span>` : ""}
      <button data-ov="${esc(ov.id)}">${t("common.remove")}</button>`;
    d.querySelector("button").addEventListener("click", async () => {
      await apiSend("DELETE", `/api/projects/${state.projectId}/overrides/${ov.id}`);
      await refreshProject();
    });
    div.appendChild(d);
  }
}

// ---------- V1 event forms (removed in Task 8) ----------
function currentRunId() {
  return document.getElementById("run-select").value;
}

function setupForms() {
  const val = (id) => +document.getElementById(id).value;
  const bind = (id, fn) => document.getElementById(id)?.addEventListener("click", fn);

  bind("btn-add-gate", () => {
    pushSnapshot("gate");
    if (addPointEvent(currentRunId(), {
      kind: "gate", width_mm: val("gate-width"),
      kit_sku: document.getElementById("gate-kit").value || null,
    }, val("gate-station"))) saveTopology();
    else alert(t("editor.draw_first"));
  });
  bind("btn-add-base", () => {
    pushSnapshot("base");
    if (addIntervalEvent(currentRunId(), {
      kind: "base", surface: document.getElementById("base-surface").value,
    }, val("base-start"), val("base-end"))) saveTopology();
    else alert(t("editor.draw_first"));
  });
  bind("btn-add-elev", () => {
    pushSnapshot("ground");
    if (addPointEvent(currentRunId(), { kind: "elevation_sample", z_mm: val("elev-z") },
      val("elev-station"))) saveTopology();
    else alert(t("editor.draw_first"));
  });
  bind("btn-add-height", () => {
    pushSnapshot("height");
    if (addIntervalEvent(currentRunId(), {
      kind: "height_intent", height_mm: val("height-mm"), source: "user",
    }, val("height-start"), val("height-end"))) saveTopology();
    else alert(t("editor.draw_first"));
  });
  bind("btn-pin-post", async () => {
    const runId = currentRunId();
    if (!runId) return alert(t("editor.draw_first"));
    await apiSend("POST", `/api/projects/${state.projectId}/overrides`, {
      id: "", run_id: runId,
      directive: { kind: "pin_post", station_mm: val("pin-station") },
    });
    await refreshProject();
  });
}
