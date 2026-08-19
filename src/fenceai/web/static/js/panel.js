// The Panel tab, and the canvas aside's model row.
//
// What it answers, in the user's own words: "I don't see an option to see the
// Panel spec and choose a model before the strategy — the Model affects the
// Panel and the Panel affects the materials, sizes and structure." Every clause
// was true of the code: `variant` and `preset` had ZERO hits across the whole
// frontend, and the only product choice anywhere in the app was the gate kit
// picker. The causal chain the user names is real (`Span.panel` ->
// derive_requirements -> resolve_supply -> BOM/structure); what was missing was
// any surface at which a human meets it BEFORE pressing Generate.
//
// Every number rendered here comes from POST /api/fence-models/{id}/{v}/preview,
// which drives the SAME resolve_panel -> derive_requirements -> resolve_supply
// pipeline a real bay does. A preview computed by a second, simpler code path
// would eventually disagree with the fence the user then gets, and a preview
// that lies is worse than no preview. It is emphatically not a run: nothing is
// stored, nothing is quotable, and the tab says so.
//
// DOM ownership: `#panel-picker` and `#panel-preview` (the Panel tab) and
// `#model-row` (in the canvas tab's aside). No other module writes those three,
// and this module writes nothing else.

import { apiSend, esc } from "./api.js";
import { gapLine, hasNominal, highlightSlot, renderElevation } from "./elevation.js";
import { isSelectable, loadModelListing, modelName, modelOptionLabel, rowFor } from "./fence-models.js";
import { currentLocale, t } from "./i18n.js";
import { on, reloadProject, state } from "./state.js";
import {
  fmt, fmtLen, inputStep, money, roleWord, toDisplayValue, toMm, tu, unitParams,
} from "./units.js";
import { warningRowHtml } from "./warnings.js";

// The bay a preview is imagined into. Millimetres at rest, exactly like storage
// and the API payload — `toDisplayValue`/`toMm` convert at the field boundary
// and nowhere else, so flipping mm <-> cm cannot round the user's figure away.
const DEFAULT_HEIGHT_MM = 1800;
const DEFAULT_WIDTH_MM = 2500;
const PREVIEW_DEBOUNCE_MS = 250;

let listing = [];
let modelId = null;
let heightMm = DEFAULT_HEIGHT_MM;
let widthMm = DEFAULT_WIDTH_MM;
let preview = null;          // the last PanelPreview, or null before the first
let previewError = null;     // a locale KEY, never a server sentence
let pending = null;          // debounce timer
let previewSeq = 0;          // only the newest request may paint
let selectedSlot = null;     // the slot the drawing and the table agree on
let elevationSvg = null;     // the last drawing, so the table can light it up

const panelTabActive = () =>
  !!document.getElementById("tab-panel")?.classList.contains("active");

// A locale sentence whose params are ids, names or dimensions: escape the
// template first, then drop each param in bidi-isolated. Same shape (and same
// reason) as warnings.js's localizedByCode — a model name is expert-authored
// text, and an id or a figure inside a Hebrew sentence needs its own direction.
function sentence(key, params = {}) {
  let s = esc(t(key));
  for (const [k, v] of Object.entries(unitParams(params)))
    s = s.replaceAll(`{${k}}`, `<bdi>${esc(String(v))}</bdi>`);
  return s;
}

export function initPanel() {
  ensureListing().then(renderModelRow);
  on("tab-changed", (tab) => { if (tab === "panel") openPanelTab(); });
  // the project default is part of the answer to "what is this fence built
  // from", so it re-renders whenever the project does
  on("project-loaded", async () => {
    await ensureListing();
    renderModelRow();
    if (panelTabActive()) renderPicker();
  });
  // Someone authored, published or retired a model in the Models tab. The
  // listing this picker renders is a cache, so without this a model published
  // one tab over stays invisible here until a page reload — and a retired one
  // stays offered.
  on("fence-models-changed", async () => {
    await ensureListing();
    renderModelRow();
    if (panelTabActive()) { renderPicker(); schedulePreview(0); }
  });
  on("locale-changed", () => {
    renderModelRow();
    if (panelTabActive()) { renderPicker(); renderPreview(); }
  });
  on("units-changed", () => {
    // the fields hold mm; re-rendering re-converts them, so a width typed in mm
    // reads as the same width in cm rather than as a tenth of one
    if (panelTabActive()) { renderPicker(); renderPreview(); }
  });
}

async function ensureListing() {
  listing = await loadModelListing();
  return listing;
}

// The model the picker opens on: the project's default when it is still
// selectable, else the first model that can actually be previewed.
function initialModelId() {
  const chosen = state.project?.fence_model?.model_id;
  if (chosen && isSelectable(rowFor(listing, chosen))) return chosen;
  return listing.find(isSelectable)?.id || null;
}

async function openPanelTab() {
  await ensureListing();
  if (!modelId || !rowFor(listing, modelId)) modelId = initialModelId();
  renderPicker();
  // re-priced on every open: the catalog may have moved since the last look,
  // and a stale price is the one number a picker must not show
  schedulePreview(0);
}

// ---------- the picker ----------

function renderPicker() {
  const host = document.getElementById("panel-picker");
  if (!host) return;
  const options = listing.map((row) =>
    `<option value="${esc(row.id)}" dir="auto"${row.id === modelId ? " selected" : ""}`
    + `${isSelectable(row) ? "" : " disabled"}>${esc(modelOptionLabel(row))}</option>`
  ).join("");
  host.innerHTML = `<h3>${esc(t("panel.title"))}</h3>
    <div class="meta">${esc(t("panel.hint"))}</div>
    <div class="toolbar">
      <label class="builder-field"><span class="meta">${esc(t("panel.model"))}</span>
        <select id="panel-model">${options}</select></label>
      <label class="builder-field"><span class="meta">${esc(tu("panel.height"))}</span>
        <input id="panel-height" type="number" step="${inputStep()}"
          value="${esc(String(toDisplayValue(heightMm)))}"></label>
      <label class="builder-field"><span class="meta">${esc(tu("panel.width"))}</span>
        <input id="panel-width" type="number" step="${inputStep()}"
          value="${esc(String(toDisplayValue(widthMm)))}"></label>
      <button id="btn-panel-use" class="primary">${esc(t("panel.use_for_project"))}</button>
      <button id="btn-panel-clear">${esc(t("panel.clear_default"))}</button>
    </div>
    <div id="panel-default" class="meta">${defaultLineHtml()}</div>`;
  if (!listing.length)
    host.innerHTML += `<div class="meta">${esc(t("panel.no_models"))}</div>`;

  // a select change is one deliberate gesture, not a keystroke: price it now
  host.querySelector("#panel-model").addEventListener("change", (ev) => {
    modelId = ev.target.value;
    // another model is another panel: a slot highlighted on the old one names
    // nothing here, and carrying it over would light up a coincidence
    selectedSlot = null;
    schedulePreview(0);
  });
  for (const [id, set] of [["panel-height", (mm) => { heightMm = mm; }],
                           ["panel-width", (mm) => { widthMm = mm; }]]) {
    const field = host.querySelector(`#${id}`);
    field.addEventListener("input", () => {
      // a blank or unparseable field is NOT a zero-height panel: flag it and
      // keep the last good figure, rather than previewing a fence of nothing
      const mm = toMm(field.value);
      const ok = mm !== null && mm > 0;
      field.classList.toggle("invalid", !ok);
      if (!ok) return;
      set(mm);
      schedulePreview(PREVIEW_DEBOUNCE_MS);
    });
  }
  host.querySelector("#btn-panel-use").addEventListener("click", () => setProjectModel(modelId));
  host.querySelector("#btn-panel-clear").addEventListener("click", () => setProjectModel(null));
}

function defaultLineHtml() {
  const choice = state.project?.fence_model;
  if (!choice) return esc(t("panel.default_none"));
  const named = modelName(rowFor(listing, choice.model_id)) || choice.model_id;
  return sentence("panel.default_is", { model: named })
    + (choice.version_pin ? ` <span class="num">v${esc(String(choice.version_pin))}</span>` : "");
}

// Setting (or clearing) the project default is NOT a topology change: it pushes
// no history snapshot, and it reloads with `reloadProject` rather than
// `openProject`, or choosing a model would silently wipe the user's undo stack.
async function setProjectModel(id) {
  if (!state.projectId) return;
  const url = `/api/projects/${state.projectId}/fence-model`;
  await apiSend("PUT", url, id ? { model_id: id } : undefined);
  await reloadProject();
}

// ---------- the preview ----------

function schedulePreview(delay) {
  clearTimeout(pending);
  pending = setTimeout(runPreview, delay);
}

async function runPreview() {
  const row = rowFor(listing, modelId);
  if (!isSelectable(row)) {
    preview = null;
    previewError = listing.length ? "panel.no_published_version" : "panel.no_models";
    renderPreview();
    return;
  }
  const seq = ++previewSeq;
  try {
    const out = await apiSend(
      "POST", `/api/fence-models/${encodeURIComponent(row.id)}/${row.active_version}/preview`,
      { height_mm: heightMm, width_mm: widthMm }, { quiet: true }
    );
    if (seq !== previewSeq) return;   // a later request already answered
    preview = out;
    previewError = null;
  } catch {
    if (seq !== previewSeq) return;
    preview = null;
    previewError = "panel.preview_failed";
  }
  renderPreview();
}

function renderPreview() {
  const host = document.getElementById("panel-preview");
  if (!host) return;
  if (previewError) {
    host.innerHTML = `<div class="panel meta">${esc(t(previewError))}</div>`;
    return;
  }
  if (!preview) {
    host.innerHTML = `<div class="panel meta">${esc(t("panel.computing"))}</div>`;
    return;
  }
  // The gap FIRST, above the priced table, because it changes how that table
  // must be read: a panel one part short must not preview as complete, and the
  // total below it is the total of what CAN be supplied.
  host.innerHTML = unsuppliedHtml() + warningsHtml() + elevationHtml()
    + partsHtml() + assemblyHtml();
  mountElevation();
  for (const row of host.querySelectorAll("#panel-parts tr[data-slot]"))
    row.addEventListener("click", () => selectSlot(row.dataset.slot));
  applySlotSelection();
}

// ---------- the drawing ----------
//
// The rectangles come from the server (PanelPreview.elevation): this tab picks
// where they go on the page and what the table does when one is clicked, and
// computes no geometry of its own. The drawing sits ABOVE the priced table
// because it is what the table is a list OF — "the Model affects the Panel" is a
// claim you can check at a glance in a picture and only arithmetically in rows.

function elevationHtml() {
  const gaps = gapLine(preview.elevation);
  return `<div class="panel" id="panel-elevation">
    <h3>${esc(t("elevation.title"))}</h3>
    <div id="panel-elevation-draw"></div>
    <div class="meta">${esc(t("elevation.select_hint"))}${
      gaps ? ` · <bdi class="elev-gaps">${esc(gaps)}</bdi>` : ""}</div>`
    + (hasNominal(preview.elevation)
      ? `<div class="elevation-note"><span class="elev-swatch"></span>${
          esc(t("elevation.nominal_note"))}</div>`
      : "")
    + "</div>";
}

function mountElevation() {
  elevationSvg = null;
  const host = document.getElementById("panel-elevation-draw");
  if (!host) return;
  const svg = renderElevation(preview.elevation, { onSelect: selectSlot });
  if (!svg) {
    host.innerHTML = `<div class="meta">${esc(t("elevation.empty"))}</div>`;
    return;
  }
  host.appendChild(svg);
  elevationSvg = svg;
}

// Clicking the same slot twice clears it: a highlight with no way off is a
// highlight the user has to re-render the tab to be rid of.
function selectSlot(slotKey) {
  selectedSlot = selectedSlot === slotKey ? null : slotKey;
  applySlotSelection();
}

function applySlotSelection() {
  for (const row of document.querySelectorAll("#panel-parts tr[data-slot]"))
    row.classList.toggle("selected", row.dataset.slot === selectedSlot);
  highlightSlot(elevationSvg, selectedSlot);
}

function partsHtml() {
  const p = preview;
  let html = `<div class="panel" id="panel-parts">
    <h3>${esc(t("panel.parts_title"))} — <bdi class="sku">${esc(p.model_ref)}</bdi></h3>
    <div class="meta">${sentence("panel.bay_line",
      { width_mm: p.width_mm, height_mm: p.height_mm })}</div>
    <div class="meta">${esc(t("panel.not_a_quote"))}</div>
    <table><tr><th>${esc(t("panel.slot"))}</th><th>${esc(t("panel.role"))}</th>
      <th>${esc(t("panel.qty"))}</th><th>${esc(tu("panel.length"))}</th>
      <th>${esc(t("panel.item"))}</th><th>${esc(t("panel.unit_price"))}</th>
      <th>${esc(t("panel.cost"))}</th></tr>`;
  for (const part of p.parts || []) {
    html += `<tr data-slot="${esc(part.slot_key)}">
      <td><span class="sku">${esc(part.slot_key)}</span></td>
      <td>${esc(roleWord(part.role))}</td>
      <td class="num">${esc(String(part.qty))}</td>
      <td class="num">${part.length_mm ? esc(fmt(part.length_mm)) : ""}</td>
      <td><span class="sku">${esc(part.sku)}</span>${(part.eligible_skus || []).length > 1
        ? `<br><span class="meta">${sentence("panel.of_n_eligible",
            { n: part.eligible_skus.length })}</span>` : ""}</td>
      <td class="num">${esc(money(part.unit_price_cents))}</td>
      <td class="num">${esc(money(part.total_cents))}</td></tr>`;
  }
  html += `</table>
    <div id="panel-total">${sentence("panel.total", { total: money(p.total_cents) })}</div>`;
  return html + "</div>";
}

function unsuppliedHtml() {
  const lines = preview.unsupplied || [];
  if (!lines.length) return "";
  let html = `<div class="panel supply-problems" id="panel-unsupplied">
    <h3>${esc(t("panel.unsupplied_title"))}</h3>
    <div class="meta">${esc(t("panel.unsupplied_hint"))}</div>
    <table><tr><th>${esc(t("panel.slot"))}</th><th>${esc(t("panel.role"))}</th>
      <th>${esc(t("panel.qty"))}</th><th>${esc(tu("panel.length"))}</th></tr>`;
  for (const line of lines) {
    html += `<tr><td><span class="sku">${esc(line.slot_key)}</span></td>
      <td>${esc(roleWord(line.role))}</td>
      <td class="num">${esc(String(line.qty))}</td>
      <td class="num">${line.length_mm ? esc(fmt(line.length_mm)) : ""}</td></tr>`;
  }
  return html + "</table></div>";
}

/** How the panel goes together, when its model says so.
 *
 *  Absent for a model that states no order — which is not the same as a model
 *  that takes no steps, and showing an empty "how to build it" panel for the
 *  first would read as an answer rather than as silence.
 *
 *  `text_i18n` is EXPERT prose, not a UI string: it is whatever the author
 *  wrote, so it falls back across the languages they did write rather than
 *  through `t()`. Escaped like every other human sentence in the app. */
function assemblyHtml() {
  return assemblyPlanHtml(preview?.assembly);
}


export function assemblyPlanHtml(plan) {
  // `null` is "this line states no order"; a plan always has at least one step,
  // because it is built one-for-one from a non-empty `assembly`. The second half
  // of the old guard was dead and collapsed the two states the tri-state exists
  // to keep apart.
  if (!plan) return "";
  const said = (step) => step.text_i18n[currentLocale()]
    || step.text_i18n.en || Object.values(step.text_i18n)[0] || "";
  const rows = plan.steps.map((step, i) => `
    <li class="step" data-step="${esc(step.key)}" data-kind="${esc(step.kind)}">
      <div dir="auto">${esc(said(step))}</div>
      ${step.parts.length
        ? `<div class="meta">${step.parts.map((p) => `<span class="sku">${
            esc(p.slot_key)}</span> ×<span class="num">${fmt(p.qty)}</span>${
            p.length_mm == null ? "" : ` · ${esc(fmtLen(p.length_mm))}`}`).join(" · ")}</div>`
        : `<div class="meta">${esc(t("assembly.no_parts"))}</div>`}
    </li>`).join("");
  // a part no step fits is REPORTED: a sheet that omits it reads as a finished
  // panel to the person holding it
  const missed = plan.unplaced.length
    ? `<div class="warning">${esc(t("assembly.unplaced", {
        slots: plan.unplaced.map((p) => p.slot_key).join(", ") }))}</div>`
    : "";
  return `<div class="panel" id="panel-assembly">
    <h3>${esc(t("assembly.sheet_title"))}</h3>
    <div class="meta">${esc(t("assembly.sheet_hint"))}</div>
    ${missed}<ol class="steps">${rows}</ol></div>`;
}


function warningsHtml() {
  const list = preview.warnings || [];
  if (!list.length) return "";
  let html = `<div class="panel" id="panel-warnings"><h3>${esc(t("panel.warnings_title"))}</h3>`;
  // the preview's pegs are a synthetic span id — say "this panel" instead
  for (const w of list) html += warningRowHtml(w, { pegs: t("panel.this_panel") });
  return html + "</div>";
}

// ---------- the canvas aside's model row ----------

function renderModelRow() {
  const host = document.getElementById("model-row");
  if (!host) return;
  const choice = state.project?.fence_model;
  host.innerHTML = `<h3>${esc(t("panel.project_model"))}</h3>`
    + (choice
      ? `<div dir="auto">${defaultLineHtml()}</div>`
        + `<div class="meta"><bdi class="sku">${esc(choice.model_id)}</bdi></div>`
      : `<div class="meta">${esc(t("panel.default_none"))}</div>`)
    + `<div class="meta">${esc(t("panel.see_panel_tab"))}</div>`;
}
