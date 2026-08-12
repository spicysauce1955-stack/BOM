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
import { gapLine, hasNominal, highlightSlot, renderElevation } from "./elevation.js";
import { t } from "./i18n.js";
import { inspect } from "./inspector.js";
import { emit, on, setSelection, state } from "./state.js";
import {
  CONSUMABLE_ROLES, getReport, isStale, loadStructure, staleCode, staleKind,
} from "./structure-data.js";
import { enumWord, fmt, fmtLen, tu, unitLabel } from "./units.js";
import { supplyProblemsHtml } from "./warnings.js";

let detail = "installer";
let drawnBayId = null;       // the bay the elevation is showing
let elevationSvg = null;     // its drawing, so a clicked member can find its parts
let elevationSlot = null;    // the slot the drawing and the parts agree on

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
  on("selection-changed", () => { highlight(); renderBayElevation(); });
}

// ---------- rendering ----------

function render() {
  const body = document.getElementById("structure-body");
  const totals = document.getElementById("structure-totals");
  if (!body || !totals) return;
  const report = getReport();
  if (!report) {
    totals.innerHTML = "";
    // "no structure yet" is true for EXACTLY one of these: no run. Every other
    // branch is a run that exists and cannot be laid out, and saying "generate a
    // strategy" about it is a lie the user cannot act on.
    const emptyKey = !isStale() ? "structure.empty"
      : staleKind() === "catalog" ? "structure.catalog_changed"
      : staleKind() === "predates" ? "error.run_predates_fence_model"
      : staleKind() === "unknown" ? "structure.unreadable"
      : "structure.stale";
    body.innerHTML = `<div class="panel meta">${
      esc(t(emptyKey, { code: staleCode() }))}</div>`;
    return;
  }
  renderPrintTitle(report);
  totals.innerHTML = renderTotals(report.totals);
  // A part nothing can supply is missing from every bay row below — this sheet
  // goes to site, so it says so at the top rather than quietly listing a bay
  // one rail short. The tags are already indexed here, so the sentence names
  // the bay ("A/B3"), not the element id.
  body.innerHTML = supplyProblemsHtml(report.warnings, report.unresolved,
                                      { customer: detail === "customer" })
    + `<div class="panel" id="structure-elevation"></div>`
    + report.sections
      .map((s) => (detail === "customer" ? customerSection(s) : installerSection(s)))
      .join("");
  renderBayElevation();
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

// ---------- the selected bay, drawn ----------
//
// `Bay.elevation` rides along on the report this tab already holds — the
// rectangles are read from the structure-data cache, never fetched again. A
// second GET here would race the one in flight for the same run (see that
// module's in-flight guard: a fetch belongs to the run it was STARTED for) and
// could label one drawing with another run's schedule.

function bayToDraw(report) {
  const bays = report.sections.flatMap((s) => s.bays).filter((b) => b.elevation);
  if (!bays.length) return null;
  // the selection when it names a bay; otherwise the last bay drawn, so
  // clicking a POST in the schedule does not silently change the drawing
  return bays.find((b) => b.element_id === state.selection.elementId)
    || bays.find((b) => b.element_id === drawnBayId)
    || bays[0];
}

function renderBayElevation() {
  const host = document.getElementById("structure-elevation");
  if (!host) return;
  elevationSvg = null;
  const report = getReport();
  const bay = report ? bayToDraw(report) : null;
  if (!bay) {
    // a run generated before fence models carries no elevation on its bays;
    // `parts` still describes them, and the tables below already say so
    drawnBayId = null;
    host.innerHTML = `<div class="meta">${esc(t("elevation.none"))}</div>`;
    return;
  }
  if (bay.element_id !== drawnBayId) elevationSlot = null;
  drawnBayId = bay.element_id;
  const gaps = gapLine(bay.elevation);
  host.innerHTML = `<h3>${esc(t("elevation.bay_title", { tag: bay.tag }))}</h3>
    <div id="structure-elevation-draw"></div>
    <div class="meta">${esc(t("elevation.select_hint"))}${
      gaps ? ` · <bdi class="elev-gaps">${esc(gaps)}</bdi>` : ""}</div>`
    + (hasNominal(bay.elevation)
      ? `<div class="elevation-note"><span class="elev-swatch"></span>${
          esc(t("elevation.nominal_note"))}</div>`
      : "");
  const svg = renderElevation(bay.elevation, { onSelect: selectBaySlot });
  const draw = host.querySelector("#structure-elevation-draw");
  if (!svg) {
    draw.innerHTML = `<div class="meta">${esc(t("elevation.empty"))}</div>`;
    return;
  }
  draw.appendChild(svg);
  elevationSvg = svg;
  applyBaySlot();
}

function selectBaySlot(slotKey) {
  elevationSlot = elevationSlot === slotKey ? null : slotKey;
  applyBaySlot();
}

// which PART line a drawn member is: the bay's own row, not the whole sheet —
// every bay of the same model has a "slat" line, and lighting them all up would
// answer a question nobody asked
function applyBaySlot() {
  highlightSlot(elevationSvg, elevationSlot);
  const body = document.getElementById("structure-body");
  if (!body) return;
  for (const part of body.querySelectorAll(".part[data-slot]"))
    part.classList.toggle("selected",
      elevationSlot !== null && part.dataset.slot === elevationSlot
      && part.closest("[data-element]")?.dataset.element === drawnBayId);
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
  // the slot is what a rectangle on the elevation and a line in this cell have
  // in common — it is how clicking the drawing finds the row
  return `<div class="part" data-slot="${esc(part.slot_key || "")}">`
    + `<span class="num">${esc(String(part.qty))}</span>×`
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
