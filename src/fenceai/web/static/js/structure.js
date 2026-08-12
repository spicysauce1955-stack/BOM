// Structure tab: how the fence is laid out, and what each piece consists of.
//
// The drawing shows WHERE things are and the decision trail says WHY they are
// there; this panel says WHAT they are — a setting-out table a crew can measure
// from, a bay schedule, and the parts of every element. It renders the derived
// report from /api/runs/{id}/structure and owns no numbers of its own.
//
// Two detail levels, per trade practice: the installer sheet itemises everything,
// the customer sheet names posts, panels and gates but DESCRIBES fixings and
// concrete — an itemised screw count on a proposal invites an argument about the
// screws that were not used.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { inspect } from "./inspector.js";
import { emit, on, setSelection, state } from "./state.js";
import { getReport, isStale, loadStructure, staleKind } from "./structure-data.js";
import { enumWord, fmt, fmtLen, tu, unitLabel } from "./units.js";

let detail = "installer";

const CONSUMABLE_ROLES = new Set(["screw", "concrete"]);   // described, not itemised

export function initStructure() {
  const sel = document.getElementById("structure-detail");
  detail = localStorage.getItem("fenceai.structure.detail") === "customer"
    ? "customer" : "installer";
  sel.value = detail;
  sel.addEventListener("change", () => {
    detail = sel.value;
    localStorage.setItem("fenceai.structure.detail", detail);
    render();
  });
  document.getElementById("btn-structure-print").addEventListener("click", () => {
    emit("fit-view");          // frame the plan on the fence before it goes to paper
    setTimeout(() => window.print(), 60);
  });
  // re-stamp the title block at print time, however the print was triggered
  window.addEventListener("beforeprint", () => {
    const report = getReport();
    if (report) renderPrintTitle(report);
  });

  on("tab-changed", (tab) => { if (tab === "structure") loadStructure(); });
  on("structure-loaded", render);
  on("locale-changed", render);
  on("units-changed", render);
  on("selection-changed", highlight);
}

// ---------- rendering ----------

function render() {
  const body = document.getElementById("structure-body");
  const totals = document.getElementById("structure-totals");
  if (!body || !totals) return;
  const report = getReport();
  if (!report) {
    totals.innerHTML = "";
    const emptyKey = !isStale() ? "structure.empty"
      : staleKind() === "catalog" ? "structure.catalog_changed"
      : staleKind() === "predates" ? "error.run_predates_fence_model"
      : "structure.stale";
    body.innerHTML = `<div class="panel meta">${esc(t(emptyKey))}</div>`;
    return;
  }
  renderPrintTitle(report);
  totals.innerHTML = renderTotals(report.totals);
  body.innerHTML = report.sections
    .map((s) => (detail === "customer" ? customerSection(s) : installerSection(s)))
    .join("");
  for (const row of body.querySelectorAll("[data-element]")) {
    row.addEventListener("click", () => {
      const runId = row.dataset.run;
      const elementId = row.dataset.element;
      setSelection({ runId, elementId });
      inspect(elementId, row.dataset.labelKey, JSON.parse(row.dataset.labelParams || "{}"));
    });
  }
  highlight();
}

function highlight() {
  const body = document.getElementById("structure-body");
  if (!body) return;
  for (const row of body.querySelectorAll("[data-element]"))
    row.classList.toggle("selected", row.dataset.element === state.selection.elementId);
}

// A drawing goes to site with a title block: whose job it is, what is on the
// sheet, and when it was printed — a sheet with no date is a sheet nobody trusts.
function renderPrintTitle(report) {
  const box = document.getElementById("print-title");
  if (!box) return;
  // local time, stamped when the sheet is produced (see the beforeprint hook):
  // a UTC time rendered hours earlier is worse than no time at all
  const now = new Date();
  const printed = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 16).replace("T", " ");
  box.innerHTML = `
    <div class="print-title-row">
      <b dir="auto">${esc(state.project?.name || "")}</b>
      <span>${esc(t("structure.title"))}</span>
      <span class="meta">${esc(tu("strategy.length",
        { total_mm: report.totals.fence_length_mm }))}</span>
      <span class="meta">${esc(t("structure.printed", { at: printed }))}</span>
      <span class="meta"><bdi>${esc(report.run_id)}</bdi></span>
    </div>`;
}

function renderTotals(totals) {
  const stat = (n, key) =>
    `<span class="stat"><b class="num">${esc(String(n))}</b> ${esc(t(key))}</span>`;
  const heights = totals.height_min_mm === null ? ""
    : totals.height_min_mm === totals.height_max_mm
      ? tu("structure.height_one", { height_mm: totals.height_min_mm })
      : tu("structure.height_range",
           { min_mm: totals.height_min_mm, max_mm: totals.height_max_mm });
  const bucket = (key, rows) => (rows || []).length
    ? `<div class="meta">${esc(t(key))} `
      + rows.map((u) =>
          `<span class="sku">${esc(u.sku)}</span> <span class="num">${esc(String(u.qty))}</span>`)
        .join(" · ") + "</div>"
    : "";
  const unassigned = bucket("structure.unassigned", totals.unassigned)
    + bucket("structure.from_stock", totals.from_stock);
  return `<div class="summary-line">
      ${stat(totals.posts, "strategy.posts")}
      ${stat(totals.bays, "structure.bays")}
      ${totals.gates ? stat(totals.gates, "strategy.gates") : ""}
      <span class="stat">${esc(tu("strategy.length", { total_mm: totals.fence_length_mm }))}</span>
      <span class="stat meta">${esc(heights)}</span>
    </div>${unassigned}`;
}

function sectionHead(section) {
  const bits = [
    `<b>${esc(t("structure.section", { tag: section.tag }))}</b>`,
    `<bdi class="meta">${esc(section.run_id)}</bdi>`,
    `<span class="num">${esc(fmtLen(section.length_mm))}</span>`,
    esc(enumWord(section.base_surface)),
  ];
  if (section.height_mm !== null && section.height_mm !== undefined)
    bits.push(esc(tu("structure.height_one", { height_mm: section.height_mm })));
  if (section.post_tilt !== "plumb")
    bits.push(esc(t("popover.post_tilt")) + " · " + esc(enumWord(section.post_tilt)));
  return `<div class="summary-line">${bits.join(" · ")}</div>`;
}

// A part, as a line: "2 × RAIL-3000, cut 1200 mm (bar #1, #2)"
function partLine(part) {
  const bars = part.from_bars?.length
    ? ` <span class="meta">(${part.from_bars.map((b) => esc(b)).join(", ")})</span>` : "";
  const cut = part.cut_length_mm
    ? ` · ${esc(tu("structure.cut", { cut_mm: part.cut_length_mm }))}`
      + (part.length_basis ? ` <span class="meta">${esc(t("structure.basis." + part.length_basis))}</span>` : "")
    : "";
  return `<div class="part"><span class="num">${esc(String(part.qty))}</span>×`
    + ` <span class="sku">${esc(part.sku)}</span>${cut}${bars}</div>`;
}

const partsCell = (parts) => parts.map(partLine).join("");

function rowAttrs(runId, elementId, labelKey, labelParams) {
  return `data-run="${esc(runId)}" data-element="${esc(elementId)}"`
    + ` data-label-key="${esc(labelKey)}"`
    + ` data-label-params="${esc(JSON.stringify(labelParams))}"`;
}

function installerSection(section) {
  const settingOut = section.setting_out.map((s) => `
    <tr ${rowAttrs(section.run_id, s.element_id, "inspect.post",
                   { sku: s.sku, station_mm: s.station_mm })}>
      <td><b>${esc(s.tag)}</b>${s.shared_from
        ? ` <span class="meta">${esc(t("structure.shared_from", { tag: s.shared_from }))}</span>` : ""}</td>
      <td class="num">${esc(fmt(s.station_mm))}</td>
      <td class="num">${s.spacing_mm === null ? "—" : esc(fmt(s.spacing_mm))}</td>
      <td>${esc(enumWord(s.kind))}${s.pinned ? ` <span class="tag">${esc(t("inspect.pinned"))}</span>` : ""}</td>
      <td><span class="sku">${esc(s.sku)}</span></td>
      <td class="num">${esc(fmt(s.base_z_mm))}</td>
      <td>${partsCell(visibleParts(s.parts))}</td>
    </tr>`).join("");

  const bays = section.bays.map((b) => `
    <tr ${rowAttrs(section.run_id, b.element_id, "inspect.span",
                   { width_mm: b.width_mm, height_mm: b.height_mm, mode: b.vertical })}>
      <td><b>${esc(b.tag)}</b></td>
      <td>${esc(b.from_tag || "")}–${esc(b.to_tag || "")}</td>
      <td class="num">${esc(fmt(b.width_mm))}</td>
      <td class="num">${esc(fmt(b.height_mm))}</td>
      <td>${esc(enumWord(b.vertical))}</td>
      <td>${partsCell(visibleParts(b.parts))}</td>
    </tr>`).join("");

  const gates = section.gates.map((g) => `
    <tr ${rowAttrs(section.run_id, g.element_id, "inspect.gate", { kit: g.kit_sku || "" })}>
      <td><b>${esc(g.tag)}</b></td>
      <td>${esc(g.from_tag || "")}–${esc(g.to_tag || "")}</td>
      <td class="num">${esc(fmt(g.start_station_mm))}</td>
      <td class="num">${esc(fmt(g.opening_mm))}</td>
      <td><span class="sku">${esc(g.kit_sku || "—")}</span></td>
      <td>${partsCell(visibleParts(g.parts))}</td>
    </tr>`).join("");

  const u = unitLabel();
  return `<div class="panel structure-section">
    ${sectionHead(section)}
    <h4>${esc(t("structure.setting_out"))} <span class="meta">${esc(t("structure.setting_out_hint"))}</span></h4>
    <table class="structure-table"><tr>
      <th>${esc(t("structure.tag"))}</th>
      <th>${esc(t("structure.station"))} (${esc(u)})</th>
      <th>${esc(t("structure.spacing"))} (${esc(u)})</th>
      <th>${esc(t("structure.kind"))}</th>
      <th>${esc(t("bom.sku"))}</th>
      <th>${esc(t("structure.stands_on"))} (${esc(u)})</th>
      <th>${esc(t("structure.parts"))}</th></tr>${settingOut}</table>
    ${section.bays.length ? `<h4>${esc(t("structure.bays_title"))}</h4>
    <table class="structure-table"><tr>
      <th>${esc(t("structure.tag"))}</th>
      <th>${esc(t("structure.between"))}</th>
      <th>${esc(t("structure.width"))} (${esc(u)})</th>
      <th>${esc(t("structure.height"))} (${esc(u)})</th>
      <th>${esc(t("structure.mode"))}</th>
      <th>${esc(t("structure.parts"))}</th></tr>${bays}</table>` : ""}
    ${section.gates.length ? `<h4>${esc(t("structure.gates_title"))}</h4>
    <table class="structure-table"><tr>
      <th>${esc(t("structure.tag"))}</th>
      <th>${esc(t("structure.between"))}</th>
      <th>${esc(t("structure.station"))} (${esc(u)})</th>
      <th>${esc(t("structure.opening"))} (${esc(u)})</th>
      <th>${esc(t("structure.kit"))}</th>
      <th>${esc(t("structure.parts"))}</th></tr>${gates}</table>` : ""}
  </div>`;
}

// the customer sheet: scope, not a parts explosion
function customerSection(section) {
  const spacings = section.setting_out.map((s) => s.spacing_mm).filter((v) => v !== null);
  const spacing = spacings.length
    ? (Math.min(...spacings) === Math.max(...spacings)
        ? tu("structure.spacing_even", { spacing_mm: spacings[0] })
        : tu("structure.spacing_range",
             { min_mm: Math.min(...spacings), max_mm: Math.max(...spacings) }))
    : "";
  const named = new Map();      // named materials: everything but the consumables
  let consumables = false;
  const counted = new Set();    // a shared corner post is set out twice, bought once
  for (const element of [...section.setting_out, ...section.bays, ...section.gates]) {
    if (counted.has(element.element_id)) continue;
    counted.add(element.element_id);
    for (const part of element.parts) {
      if (CONSUMABLE_ROLES.has(part.role)) { consumables = true; continue; }
      named.set(part.sku, (named.get(part.sku) || 0) + part.qty);
    }
  }
  const materials = [...named.entries()].sort()
    .map(([sku, qty]) => `<div class="part"><span class="num">${esc(String(qty))}</span>×`
      + ` <span class="sku">${esc(sku)}</span></div>`).join("");
  const gates = section.gates.map((g) =>
    esc(tu("structure.gate_scope", { opening_mm: g.opening_mm }))).join(" · ");
  return `<div class="panel structure-section">
    ${sectionHead(section)}
    <div class="summary-line meta">
      ${esc(tu("structure.posts_scope", { n: section.setting_out.length }))} · ${esc(spacing)}
      ${section.bays.length ? " · " + esc(tu("structure.bays_scope", { n: section.bays.length })) : ""}
      ${gates ? " · " + gates : ""}
    </div>
    <div class="customer-materials">${materials}</div>
    ${consumables ? `<div class="meta">${esc(t("structure.consumables"))}</div>` : ""}
  </div>`;
}

function visibleParts(parts) {
  return detail === "customer"
    ? parts.filter((p) => !CONSUMABLE_ROLES.has(p.role))
    : parts;
}
