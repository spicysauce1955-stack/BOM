// The Assembly tab: two synchronized viewports over one fence.
//
// MACRO — the run as it is set out: posts in their footings, panels docked
// between them, step-downs, gates, and the dimensions a person checks a layout
// against. MICRO — one panel as it is assembled: the same drawing the Panel and
// Structure tabs already show, for the bay the macro view has selected.
//
// They are one question at two scales, which is why they share a selection
// rather than living on two tabs: picking a bay up there assembles it down here,
// and picking a member down here lights up every bay that carries it.
//
// What this module does NOT do:
//   * it computes no geometry. The macro placement is `runview.js` (pure, node
//     tested) over the structure report; the micro drawing is `elevation.js`
//     over rectangles the SERVER placed. Two drawings of one fence that each did
//     their own maths would eventually disagree, and the one that disagrees with
//     the BOM is the one a person believes;
//   * it does not fetch the structure report. `structure-data.js` owns that
//     cache and its refusal branches, and a second GET here would race the one
//     in flight for the same run;
//   * it never generates. A dimension change that only a new layout could answer
//     marks the macro viewport stale and offers the button — the project rule is
//     that generation stays behind an explicit press, and a viewport that
//     silently re-ran it would spend money on the user's behalf.
//
// DOM ownership: `#assembly-bar`, `#assembly-macro`, `#assembly-micro` and
// `#assembly-drawer`. No other module writes those, and this module writes
// nothing else.

import { apiGet, apiSend, esc } from "./api.js";
import { loadCatalogProducts } from "./builder-ui.js";
import {
  elevationRects, gapLine, hasNominal, highlightSlot, renderElevation,
} from "./elevation.js";
import { el } from "./geom.js";
import { sectionPlacement, sectionsFor } from "./joint.js";
import { currentLocale, t } from "./i18n.js";
import { on, setSelection, state } from "./state.js";
import { drawerHtml, partOptions } from "./part-drawer.js";
import {
  footingShape, macroDimensions, macroModel, macroPlacement,
} from "./runview.js";
import {
  getReport, loadStructure, refusalKey, staleCode,
} from "./structure-data.js";
import {
  enumWord, inputStep, money, moneyDelta, toDisplayValue, toMm, tu, unitParams,
} from "./units.js";

const MODES = ["split", "macro", "micro"];
// Above this many drawn members the macro view stops drawing panels as their
// parts and draws them as blocks instead. A 60-bay fence of 20 slats is 1200
// rectangles that resolve to nothing legible at macro scale — the cost is real
// and the picture is not better for it. The view SAYS it simplified rather than
// quietly showing a different fence.
const MEMBER_BUDGET = 900;
// A typed dimension is a keystroke, not a decision: the same debounce the Panel
// tab and the model editor already use, so the three surfaces that re-price live
// re-price at one rhythm.
const PREVIEW_DEBOUNCE_MS = 250;

let mode = "split";
let annotations = true;
let macroSvg = null;
let microSvg = null;
let drawnBayId = null;       // the bay the micro view is showing
let microSlot = null;        // the member slot both views agree on
let faceWidths = {};         // sku -> declared post face width, from the catalog
let products = {};           // the catalog, for the drawer's names and materials
let inventory = null;        // this project's stock, for the drawer's availability
let preview = null;          // the current PanelPreview (as built, or the what-if)
let basePreview = null;      // the same bay at its OWN size, nothing pinned
let previewError = null;     // a locale KEY, never a server sentence
let previewTimer = null;
let previewSeq = 0;          // only the newest request may paint
let whatIf = null;           // { height_mm, width_mm, slot_skus } — null = as built
let drawerSlot = null;       // the slot the material drawer is open on
let runBom = null;           // this run's BOM total, in cents
let runAllocations = [];     // what this run already takes off the shelf

const assemblyTabActive = () =>
  !!document.getElementById("tab-assembly")?.classList.contains("active");

export function initAssembly() {
  mode = MODES.includes(localStorage.getItem("fenceai.assembly.mode"))
    ? localStorage.getItem("fenceai.assembly.mode") : "split";
  annotations = localStorage.getItem("fenceai.assembly.dims") !== "false";

  on("tab-changed", (tab) => { if (tab === "assembly") openTab(); });
  on("structure-loaded", () => { if (assemblyTabActive()) render(); });
  on("locale-changed", () => { if (assemblyTabActive()) render(); });
  on("units-changed", () => { if (assemblyTabActive()) render(); });
  // a new run is a new fence AND a new price: both viewports and the strip
  on("result-changed", async () => {
    clearWhatIf();
    basePreview = null;
    await loadRunBom();
    if (assemblyTabActive()) { render(); schedulePreview(0); }
  });
  // stock moved, so the drawer's availability column did too
  on("inventory-saved", async () => {
    await ensureInventory();
    if (assemblyTabActive()) renderDrawer();
  });
  // a selection made on the Structure tab or in the plan canvas lands here too:
  // switching tabs must not lose which bay the user was looking at
  on("selection-changed", () => { if (assemblyTabActive()) render(); });
}

async function openTab() {
  await Promise.all([ensureCatalog(), ensureInventory(), loadRunBom()]);
  await loadStructure();
  render();
  schedulePreview(0);
}

// The catalog is DATA this tab reads twice: post face widths for the macro
// drawing, and names, materials and prices for the drawer. Read through the
// shared cache rather than fetched here — the builder already holds the
// products, and a second copy is a second answer to "how wide is a POST-S".
async function ensureCatalog() {
  try {
    products = await loadCatalogProducts() || {};
  } catch {
    products = {};     // no catalog: every post draws at its nominal, and says so
  }
  faceWidths = Object.fromEntries(
    Object.entries(products)
      .map(([sku, p]) => [sku, p?.capabilities?.face_width_mm])
      .filter(([, w]) => Number.isFinite(w)));
}

// Stock is a property of a PROJECT, not of a model — which is why the drawer
// reads it here and the panel preview deliberately does not take it at all.
async function ensureInventory() {
  if (!state.projectId) { inventory = null; return; }
  try {
    inventory = await apiGet(`/api/projects/${state.projectId}/inventory`);
  } catch {
    inventory = null;
  }
}

// ------------------------------------------------------------------ the bar

function renderBar() {
  const host = document.getElementById("assembly-bar");
  if (!host) return;
  const button = (value) =>
    `<button data-mode="${value}" class="${mode === value ? "primary" : ""}">`
    + `${esc(t(`assembly.mode.${value}`))}</button>`;
  host.innerHTML = `<h3>${esc(t("assembly.title"))}</h3>
    <div class="meta">${esc(t("assembly.hint"))}</div>
    <div class="toolbar">
      <span class="meta">${esc(t("assembly.mode"))}</span>
      ${MODES.map(button).join("")}
      <label class="builder-field"><input type="checkbox" id="assembly-dims"
        ${annotations ? "checked" : ""}> <span class="meta">${
          esc(t("assembly.annotations"))}</span></label>
      ${dimensionFields()}
    </div>
    <div id="assembly-cost"></div>`;
  for (const btn of host.querySelectorAll("[data-mode]"))
    btn.addEventListener("click", () => {
      mode = btn.dataset.mode;
      localStorage.setItem("fenceai.assembly.mode", mode);
      render();
    });
  host.querySelector("#assembly-dims").addEventListener("change", (ev) => {
    annotations = ev.target.checked;
    localStorage.setItem("fenceai.assembly.dims", String(annotations));
    render();
  });
  wireDimensionFields(host);
}

/** Height and width for the SELECTED bay, seeded from what was generated.
 *
 * Typing in them does not edit the fence: it asks "what would this panel be if
 * it were this size", answered by the preview pipeline in a quarter of a second.
 * Editing the real fence is the canvas's height tool, and building it is the
 * Generate button — both one tab away, both unchanged by this. */
function dimensionFields() {
  const bay = bayToDraw(getReport());
  if (!bay) return "";
  const height = whatIf?.height_mm ?? bay.height_mm;
  const width = whatIf?.width_mm ?? bay.width_mm;
  const field = (id, key, value) =>
    `<label class="builder-field"><span class="meta">${esc(tu(key))}</span>
      <input id="${id}" type="number" step="${inputStep()}"
        value="${esc(String(toDisplayValue(value)))}"></label>`;
  return field("assembly-height", "panel.height", height)
    + field("assembly-width", "panel.width", width);
}

function wireDimensionFields(host) {
  for (const [id, key] of [["assembly-height", "height_mm"],
                           ["assembly-width", "width_mm"]]) {
    const field = host.querySelector(`#${id}`);
    if (!field) continue;
    field.addEventListener("input", () => {
      // a blank or unreadable field is NOT a panel of zero height: flag it and
      // keep the last good figure rather than previewing a fence of nothing
      const mm = toMm(field.value);
      const ok = mm !== null && mm > 0;
      field.classList.toggle("invalid", !ok);
      if (!ok) return;
      enterWhatIf({ [key]: mm });
      schedulePreview();
      renderCost();
    });
  }
}

// --------------------------------------------------------------- rendering

function render() {
  renderBar();
  const row = document.getElementById("assembly-row");
  if (row) row.dataset.mode = mode;
  renderMacro();
  renderMicro();
  renderCost();
  renderDrawer();
}

/** The refusal branches, from the module that OWNS the refusal state — not a
 *  second copy of the mapping, which is how two surfaces come to disagree about
 *  the same run (and which is a copy no test ever reached). */
function emptyMessage() {
  return `<div class="meta">${
    esc(t(refusalKey("assembly.no_run"), { code: staleCode() }))}</div>`;
}

function renderMacro() {
  const host = document.getElementById("assembly-macro");
  if (!host) return;
  macroSvg = null;
  const report = getReport();
  host.innerHTML = `<h3>${esc(t("assembly.macro_title"))}</h3>`;
  if (!report) { host.innerHTML += emptyMessage(); return; }

  const model = macroModel(report, { faceWidths });
  if (!model.posts.length) { host.innerHTML += emptyMessage(); return; }

  const svg = drawMacro(model);
  host.appendChild(svg);
  macroSvg = svg;

  const notes = [];
  if (model.posts.some((p) => !p.declared_face)) notes.push(t("assembly.nominal_post"));
  if (model.gates.some((g) => !g.declared_height)) notes.push(t("assembly.gate_height_unknown"));
  if (simplified(model)) notes.push(t("assembly.simplified"));
  host.insertAdjacentHTML("beforeend",
    `<div class="meta">${esc(t("assembly.macro_hint"))}</div>`
    + notes.map((n) => `<div class="meta elevation-note">${esc(n)}</div>`).join(""));
}

const simplified = (model) =>
  model.bays.reduce((n, b) => n + (b.elevation?.members?.length || 0), 0) > MEMBER_BUDGET;

function drawMacro(model) {
  const place = macroPlacement(model);
  const svg = el("svg", {
    viewBox: `0 0 ${r(place.viewBox.w)} ${r(place.viewBox.h)}`,
    class: "macro-svg",
    preserveAspectRatio: "xMidYMid meet",
  });
  const { px, pz } = place;

  // --- ground, and whatever is built on it ------------------------------
  for (const section of model.sections) {
    if (section.ground.length > 1) {
      const points = section.ground.map(([x, z]) => `${r(px(x))},${r(pz(z))}`).join(" ");
      el("polyline", { class: "macro-ground", points }, svg);
    }
    // a built base is a BAND between the ground and what the posts stand on,
    // toned by surface exactly as the plan canvas and the side view tone it
    const band = section.base
      .map(([x, z], i) => [x, z, section.ground[i]?.[1] ?? z])
      .filter(([, z, ground]) => z !== ground);
    if (band.length > 1) {
      const top = band.map(([x, z]) => `${r(px(x))},${r(pz(z))}`);
      const bottom = [...band].reverse().map(([x, , g]) => `${r(px(x))},${r(pz(g))}`);
      el("polygon", {
        class: `macro-base macro-base-${section.base_surface}`,
        points: [...top, ...bottom].join(" "),
      }, svg);
    }
  }

  // --- bays -------------------------------------------------------------
  const bayGroup = el("g", { class: "macro-bays" }, svg);
  const drawParts = !simplified(model);
  for (const bay of model.bays) drawBay(bayGroup, bay, place, drawParts);

  // --- gates ------------------------------------------------------------
  for (const gate of model.gates) drawGate(svg, gate, place);

  // --- posts, painted OVER the bays -------------------------------------
  // which is what "the panel docks into the post" looks like: the post face
  // covers the panel's end, and the panel is not drawn floating beside it
  const postGroup = el("g", { class: "macro-posts" }, svg);
  for (const post of model.posts) drawPost(postGroup, post, place);

  if (annotations) drawDimensions(svg, model, place);

  svg.addEventListener("click", (ev) => {
    const hit = ev.target.closest?.("[data-element]");
    if (!hit) return;
    setSelection({ runId: hit.dataset.run, elementId: hit.dataset.element });
  });
  return svg;
}

function drawBay(group, bay, { px, pz }, drawParts) {
  const g = el("g", {
    class: `macro-bay${bay.element_id === state.selection.elementId ? " selected" : ""}`,
    "data-element": bay.element_id, "data-run": bay.run_id,
  }, group);
  const outline = [
    [bay.x0_mm, bay.bottom_start_z_mm], [bay.x1_mm, bay.bottom_end_z_mm],
    [bay.x1_mm, bay.top_end_z_mm], [bay.x0_mm, bay.top_start_z_mm],
  ].map(([x, z]) => `${r(px(x))},${r(pz(z))}`).join(" ");
  el("polygon", { class: "macro-bay-face", points: outline }, g);
  // through tu() like every other length on this tab: a raw millimetre figure
  // in a tooltip stays in millimetres after the user switches to centimetres
  el("title", {}, g).textContent = `${bay.tag} · ${tu("assembly.bay_dims",
    { width_mm: bay.width_mm, height_mm: bay.height_mm })}`;

  if (!drawParts || !bay.elevation?.members?.length) return;
  // The panel's own members, mapped into the opening. A raked bay is a SHEAR,
  // not a rotation: its posts stay plumb and its top follows the grade, so the
  // members are placed by one matrix rather than re-laid-out per bay — the
  // rectangles are the server's, and this must not become a second fit.
  const w = bay.elevation.width_mm || 1;
  const h = bay.elevation.height_mm || 1;
  const x0 = px(bay.x0_mm);
  const kx = (px(bay.x1_mm) - x0) / w;
  const ky = (pz(bay.bottom_start_z_mm) - pz(bay.top_start_z_mm)) / h;
  const shear = (pz(bay.bottom_end_z_mm) - pz(bay.bottom_start_z_mm)) / w;
  const members = el("g", {
    class: "macro-members",
    transform: `translate(${r(x0)} ${r(pz(bay.top_start_z_mm))}) `
      + `matrix(${r6(kx)} ${r6(shear)} 0 ${r6(ky)} 0 0)`,
  }, g);
  for (const m of elevationRects(bay.elevation))
    el("rect", {
      // `elev-member` too, so a rail is the same colour in both viewports: the
      // role palette is a closed set in the stylesheet, and a macro view with
      // its own colours would make "the grey one" mean two different parts.
      // (Without it the role class alone matches nothing and SVG paints black.)
      class: `macro-member elev-member elev-${m.role || "other"}`,
      x: r6(m.x_mm), y: r6(m.y_mm),
      width: r6(Math.max(m.w_mm, 1)), height: r6(Math.max(m.h_mm, 1)),
      "data-slot": m.slot_key,
    }, members);
}

function drawPost(group, post, { px, pz }) {
  const g = el("g", {
    class: `macro-post${post.declared_face ? "" : " macro-nominal"}`
      + `${post.element_id === state.selection.elementId ? " selected" : ""}`,
    "data-element": post.element_id, "data-run": post.run_id,
  }, group);
  const footing = footingShape(post);
  if (footing)
    el("polygon", {
      class: "macro-footing",
      points: footing.map(([x, z]) => `${r(px(x))},${r(pz(z))}`).join(" "),
    }, g);
  // below the base line: the embedded length, drawn hatched because it is the
  // part nobody can see on site either
  if (post.embed_mm)
    el("rect", {
      class: "macro-embed",
      x: r(px(post.x_mm - post.face_mm / 2)), y: r(pz(post.base_z_mm)),
      width: r((px(post.x_mm + post.face_mm / 2)) - px(post.x_mm - post.face_mm / 2)),
      height: r(pz(post.base_z_mm - post.embed_mm) - pz(post.base_z_mm)),
    }, g);
  el("rect", {
    class: "macro-post-face",
    x: r(px(post.x_mm - post.face_mm / 2)), y: r(pz(post.top_z_mm)),
    width: r(px(post.x_mm + post.face_mm / 2) - px(post.x_mm - post.face_mm / 2)),
    height: r(Math.max(pz(post.base_z_mm) - pz(post.top_z_mm), 1)),
  }, g);
  el("title", {}, g).textContent = `${post.tag} · ${post.sku}`;
}

function drawGate(svg, gate, { px, pz }) {
  const g = el("g", {
    class: "macro-gate", "data-element": gate.element_id, "data-run": gate.run_id,
  }, svg);
  if (gate.height_mm !== null) {
    el("rect", {
      class: "macro-gate-leaf",
      x: r(px(gate.x0_mm)), y: r(pz(gate.bottom_z_mm + gate.height_mm)),
      width: r(px(gate.x1_mm) - px(gate.x0_mm)),
      height: r(pz(gate.bottom_z_mm) - pz(gate.bottom_z_mm + gate.height_mm)),
    }, g);
    // the swing, so a gate reads as a gate and not as a paler panel
    const x0 = px(gate.x0_mm);
    const y0 = pz(gate.bottom_z_mm);
    const radius = px(gate.x1_mm) - x0;
    el("path", {
      class: "macro-gate-swing",
      d: `M ${r(x0 + radius)} ${r(y0)} A ${r(radius)} ${r(radius)} 0 0 0 ${r(x0)} ${r(y0 - radius)}`,
    }, g);
  }
  el("title", {}, g).textContent =
    `${gate.tag}${gate.kit_sku ? ` · ${gate.kit_sku}` : ""}`;
}

// ----------------------------------------------------------- dimensions

function drawDimensions(svg, model, place) {
  const { px, pz } = place;
  const g = el("g", { class: "macro-dims" }, svg);
  const base = place.y0 + place.height;
  for (const dim of macroDimensions(model, {
    bays: true, heights: true, embed: true, steps: true, total: true,
  })) {
    if (dim.kind === "total") {
      line(g, px(dim.from_mm), base + 44, px(dim.to_mm), base + 44);
      label(g, (px(dim.from_mm) + px(dim.to_mm)) / 2, base + 39,
            tu("assembly.dim_total", { total_mm: dim.value_mm }));
    } else if (dim.axis === "x") {
      line(g, px(dim.from_mm), base + 24, px(dim.to_mm), base + 24);
      label(g, (px(dim.from_mm) + px(dim.to_mm)) / 2, base + 19,
            tu("elevation.length", { len_mm: dim.value_mm }));
    } else if (dim.kind === "height") {
      const x = px(dim.x_mm) - 16;
      line(g, x, pz(dim.from_mm), x, pz(dim.to_mm));
      rotated(g, x - 5, (pz(dim.from_mm) + pz(dim.to_mm)) / 2,
              tu("elevation.length", { len_mm: dim.value_mm }));
    } else {
      // embed and step both measure DOWN from something, and both are small:
      // the label goes beside the line rather than across it. At the far end it
      // goes on the INSIDE — the last post's embed label is the one that runs
      // off the sheet, and a clipped dimension is a wrong dimension.
      const inside = px(dim.x_mm) > place.x0 + place.width - 60;
      const x = px(dim.x_mm) + (inside ? -10 : 10);
      line(g, x, pz(dim.from_mm), x, pz(dim.to_mm));
      label(g, x + (inside ? -2 : 2), (pz(dim.from_mm) + pz(dim.to_mm)) / 2,
            tu("elevation.length", { len_mm: dim.value_mm }),
            inside ? "end" : "start");
    }
  }
}

const line = (g, x1, y1, x2, y2) =>
  el("line", { x1: r(x1), y1: r(y1), x2: r(x2), y2: r(y2) }, g);

function label(g, x, y, text, anchor = "middle") {
  // textContent, never innerHTML: a dimension label is a number and a unit word,
  // and neither becomes markup
  el("text", { class: "macro-dim-label", x: r(x), y: r(y), "text-anchor": anchor },
     g).textContent = text;
}

function rotated(g, x, y, text) {
  el("text", {
    class: "macro-dim-label", x: r(x), y: r(y), "text-anchor": "middle",
    transform: `rotate(-90 ${r(x)} ${r(y)})`,
  }, g).textContent = text;
}

// -------------------------------------------------------------- the micro

/** The bay the micro viewport assembles: the selection when it names one, else
 *  the last one drawn, else the first bay that has a drawing. Clicking a POST in
 *  the macro view therefore does not silently change which panel is open. */
function bayToDraw(report) {
  const bays = (report?.sections || []).flatMap((s) => s.bays).filter((b) => b.elevation);
  if (!bays.length) return null;
  return bays.find((b) => b.element_id === state.selection.elementId)
    || bays.find((b) => b.element_id === drawnBayId)
    || bays[0];
}

function renderMicro() {
  const host = document.getElementById("assembly-micro");
  if (!host) return;
  microSvg = null;
  const report = getReport();
  const bay = bayToDraw(report);
  host.innerHTML = `<h3>${esc(t("assembly.micro_title"))}</h3>`;
  if (!bay) {
    host.innerHTML += report
      ? `<div class="meta">${esc(t("elevation.none"))}</div>`
      : emptyMessage();
    return;
  }
  if (bay.element_id !== drawnBayId) {
    // Another bay is another panel, and everything held about the last one
    // belongs to the last one: a highlighted slot names nothing here, and the
    // preview is a different SIZE. Keeping it made the cost strip quote the
    // previous bay's panel under this bay's tag — which the browser suite found
    // and no unit test could, because both numbers are correct in isolation.
    microSlot = null;
    drawerSlot = null;
    whatIf = null;
    preview = null;
    basePreview = null;
    drawnBayId = bay.element_id;
    schedulePreview(0);
  }
  drawnBayId = bay.element_id;

  // WHICH panel is on screen, said before the drawing rather than after it: a
  // what-if and a bay that was really generated look identical, and the one
  // number on this tab that must never be mistaken for the other is a price.
  const drawn = whatIf && preview ? preview.elevation : bay.elevation;
  const gaps = gapLine(drawn);
  host.insertAdjacentHTML("beforeend",
    `<div class="summary-line"><b>${esc(t("elevation.bay_title", { tag: bay.tag }))}</b>`
    + `<span class="meta">${esc(tu("assembly.bay_dims",
        { width_mm: drawn.width_mm || bay.width_mm,
          height_mm: drawn.height_mm || bay.height_mm }))}</span>`
    + `<span class="meta">${esc(enumWord(bay.vertical))}</span>`
    + (whatIf
      ? `<span class="tag medium">${esc(t("assembly.what_if"))}</span>`
        + `<button id="btn-as-built">${esc(t("assembly.as_built"))}</button>`
      : `<span class="tag active">${esc(t("assembly.as_built_tag"))}</span>`)
    + `</div>`
    + `<div id="assembly-micro-draw"></div>`
    + `<div class="meta">${esc(t("assembly.micro_hint"))}${
        gaps ? ` · <bdi class="elev-gaps">${esc(gaps)}</bdi>` : ""}</div>`
    + (hasNominal(drawn)
      ? `<div class="elevation-note"><span class="elev-swatch"></span>${
          esc(t("elevation.nominal_note"))}</div>` : ""));
  host.querySelector("#btn-as-built")?.addEventListener("click", () => {
    clearWhatIf();
    schedulePreview(0);
    render();
  });

  const draw = host.querySelector("#assembly-micro-draw");
  // one dimension switch for both viewports: they are one drawing at two
  // scales, and a tab where half the annotations vanish is a tab that looks
  // broken rather than one that looks clean
  const svg = renderElevation(drawn, { onSelect: selectSlot, annotations });
  if (!svg) {
    draw.innerHTML = `<div class="meta">${esc(t("elevation.empty"))}</div>`;
    return;
  }
  draw.appendChild(svg);
  microSvg = svg;
  const sections = document.createElement("div");
  sections.id = "assembly-sections";
  host.appendChild(sections);
  applySlot();
}

// ------------------------------------------------------- the joint section
//
// A 15 mm engagement on an 1800 mm panel is eight thousandths of the drawing: at
// that scale a slat seated into a channel and a slat butted onto a rail are the
// same picture, and they are 135 mm apart on the cut list. So the joint gets its
// own view at its own scale, beside the panel — and only when a member with one
// is selected, because a section nobody asked for is a box of numbers.

/** Re-filled on every member click, not only on a full re-render.
 *
 * The bug this shape removes: `selectSlot` raises the member and opens the
 * drawer without redrawing the panel — which is right, the drawing has not
 * changed — so a section rendered inside the panel's own render ran exactly
 * once, while nothing was selected, and never again. The browser suite found
 * it; nothing else could, because the box was present and simply empty. */
function refreshSections() {
  const box = document.getElementById("assembly-sections");
  if (!box) return;
  const bay = bayToDraw(getReport());
  const elev = whatIf && preview ? preview.elevation : bay?.elevation;
  const sections = microSlot ? sectionsFor(elev, microSlot) : [];
  if (!sections.length) {
    // said, rather than left blank: "this member is not housed in anything" is
    // an answer, and an empty space where a detail was is not
    box.innerHTML = microSlot
      ? `<div class="meta">${esc(t("joint.none"))}</div>` : "";
    return;
  }
  box.innerHTML = `<h4>${esc(t("joint.title"))}</h4>`;
  const row = document.createElement("div");
  row.className = "joint-row";
  for (const section of sections) row.appendChild(sectionFigure(section));
  box.appendChild(row);
}

function sectionFigure(section) {
  const figure = document.createElement("div");
  figure.className = "joint-figure";
  figure.innerHTML = `<div class="meta">${esc(tu("joint.caption", {
    end: t(`joint.end.${section.end}`), kind: t(`joint.kind.${section.kind}`),
    frame: section.frame_slot,
  }))}</div>`;
  const place = sectionPlacement(section);
  const svg = el("svg", {
    viewBox: `0 0 ${r(place.viewBox.w)} ${r(place.viewBox.h)}`,
    class: "joint-svg", preserveAspectRatio: "xMidYMid meet",
  });
  const { px, py } = place;
  const across = place.across_mm;
  const half = (across - section.member_thickness_mm) / 2;

  // the housing: everything either side of the member, up to the mouth
  for (const [from, to] of [[0, half], [across - half, across]])
    el("rect", {
      class: "joint-frame",
      x: r(px(from)), y: r(py(section.bands.at(-1).from_mm)),
      width: r(Math.max((to - from) * place.scale, 0.5)),
      height: r(py(0) - py(section.bands.at(-1).from_mm)),
    }, svg);

  for (const band of section.bands) {
    if (band.role === "clearance") continue;    // a void is drawn by NOT drawing
    el("rect", {
      class: `joint-band joint-${band.role}${section.declared ? "" : " elev-nominal"}`,
      x: r(px(half)), y: r(py(band.to_mm)),
      width: r(Math.max(section.member_thickness_mm * place.scale, 0.5)),
      height: r(Math.max(py(band.from_mm) - py(band.to_mm), 0.5)),
    }, svg);
  }

  for (const [i, dim] of section.dims.entries()) {
    const x = px(0) - 8 - i * 13;
    el("line", { class: "joint-dim", x1: r(x), y1: r(py(dim.from_mm)),
                 x2: r(x), y2: r(py(dim.to_mm)) }, svg);
    const label = el("text", {
      class: "joint-dim-label", x: r(x - 3),
      y: r((py(dim.from_mm) + py(dim.to_mm)) / 2), "text-anchor": "middle",
      transform: `rotate(-90 ${r(x - 3)} ${r((py(dim.from_mm) + py(dim.to_mm)) / 2)})`,
    }, svg);
    label.textContent = tu(`joint.dim.${dim.kind}`, { len_mm: dim.value_mm });
  }
  figure.appendChild(svg);
  if (!section.declared)
    figure.insertAdjacentHTML("beforeend",
      `<div class="meta">${esc(t("joint.nominal_member"))}</div>`);
  return figure;
}

/** Clicking the same member twice clears it — a highlight with no way off is a
 *  highlight the user has to leave the tab to be rid of. It also opens (and
 *  closes) the drawer, because "which of these is the rail" and "what is that
 *  rail made of" are the same click in every CAD tool a person has used. */
function selectSlot(slotKey) {
  microSlot = microSlot === slotKey ? null : slotKey;
  drawerSlot = microSlot;
  applySlot();
  renderDrawer();
}

// ------------------------------------------------------- the panel preview
//
// The drawer needs the slot's ELIGIBILITY, and a stored run's structure report
// does not carry it — it reports what was bought, which is the point of a bill
// of materials. The eligible set lives on a panel preview, so the drawer asks
// for one: same model, same version, same bay size. It is not a second opinion
// about the fence — a preview at the bay's own dimensions resolves the panel the
// run resolved — and it is never stored, quoted or generated from.
//
// It is also what makes a material swap and a dimension change immediate: both
// re-run this one request, and both are explicitly labelled a what-if until
// somebody generates.

/** "M-SLAT@v1" -> { id: "M-SLAT", version: 1 }, or null.
 *
 * A run generated before fence models carries no model_ref at all, and a bay
 * from one gets no drawer rather than a drawer full of guesses. Kept as the test
 * of "can this bay be previewed at all"; the preview itself is asked of the RUN
 * (see below) and needs no model id from the client. */
export function modelRefParts(ref) {
  const m = /^(.+)@v(\d+)$/.exec(String(ref || ""));
  return m ? { id: m[1], version: Number(m[2]) } : null;
}

function schedulePreview(delay = PREVIEW_DEBOUNCE_MS) {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, delay);
}

async function runPreview() {
  const bay = bayToDraw(getReport());
  const runId = state.result?.run?.id;
  const ref = modelRefParts(bay?.elevation?.model_ref);
  if (!ref || !runId) {
    preview = null; previewError = null; renderCost(); renderDrawer(); return;
  }
  const seq = ++previewSeq;
  // Asked of the RUN, not of the model. The model-scoped route answers a
  // question about a model at a size — under the default preset, against
  // today's catalog, with none of the company-resolved quantities this bay was
  // laid out with — and reading that answer as THIS bay is how the drawer came
  // to mark one product "chosen" while the run had bought another, at half the
  // price, under a tag that said "as generated". Everything the run decided is
  // read off the run; the body carries only what a person is imagining.
  const body = {};
  if (whatIf) {
    body.height_mm = whatIf.height_mm;
    body.width_mm = whatIf.width_mm;
    body.slot_skus = whatIf.slot_skus || {};
  }
  try {
    const out = await apiSend(
      "POST", `/api/runs/${encodeURIComponent(runId)}`
        + `/bays/${encodeURIComponent(bay.element_id)}/panel-preview`,
      body, { quiet: true });
    if (seq !== previewSeq) return;      // a later request already answered
    preview = out;
    previewError = null;
    // the baseline the what-if is compared against: the bay at its OWN size,
    // with nothing pinned. Kept separately so a delta is always against what is
    // actually built, never against the previous what-if.
    if (!whatIf) basePreview = out;
  } catch (err) {
    if (seq !== previewSeq) return;
    preview = whatIf ? preview : null;   // keep the last good drawing on screen
    previewError = refusalCode(err);
  }
  renderCost();
  renderDrawer();
  if (whatIf) renderMicro();
}

/** The refusal's `code`, so a coded 422 can be said in the user's language.
 *  Same shape as `structure-data.js`'s — a panel is not a log viewer. */
function refusalCode(err) {
  try {
    const detail = JSON.parse(String(err?.message || ""))?.detail;
    // the PARAMS travel with the code, as they do everywhere else in this app:
    // `error.sku_not_eligible` is authored with {sku} and {slot_key}, and a
    // sentence rendered without them shows the reader its own braces
    if (detail?.code)
      return { key: `error.${detail.code}`, params: detail.params || {} };
  } catch { /* not JSON */ }
  return { key: "assembly.preview_failed", params: {} };
}

// a refusal, localized the way warnings.js localizes one: escape the template,
// then drop each param in bidi-isolated
function refusalText(refusal) {
  if (!refusal) return "";
  let s = esc(t(refusal.key));
  for (const [k, v] of Object.entries(unitParams(refusal.params || {})))
    s = s.replaceAll(`{${k}}`, `<bdi>${esc(String(v))}</bdi>`);
  return s;
}

function clearWhatIf() {
  whatIf = null;
  preview = basePreview;
}

function enterWhatIf(patch) {
  const bay = bayToDraw(getReport());
  whatIf = {
    height_mm: whatIf?.height_mm ?? bay?.height_mm ?? 0,
    width_mm: whatIf?.width_mm ?? bay?.width_mm ?? 0,
    slot_skus: { ...(whatIf?.slot_skus || {}) },
    ...patch,
  };
}

// ---------------------------------------------------------- the cost strip

/** What this tab currently costs, and WHICH of two questions that answers.
 *
 * A run's BOM and one panel's preview are different numbers with the same shape,
 * and a strip that silently switched between them would be the worst kind of
 * live figure. So it names both, every time. */
function renderCost() {
  const host = document.getElementById("assembly-cost");
  if (!host) return;
  const bits = [];
  if (runBom !== null)
    bits.push(`<span class="stat"><span class="meta">${esc(t("assembly.run_bom"))}</span> `
      + `<b class="num">${esc(money(runBom))}</b></span>`);
  if (previewError)
    bits.push(`<span class="stat meta">${refusalText(previewError)}</span>`);
  else if (preview)
    bits.push(`<span class="stat"><span class="meta">${esc(t("assembly.panel_cost"))}</span> `
      + `<b class="num">${esc(money(preview.total_cents))}</b></span>`);
  if (whatIf && preview && basePreview
      && preview.total_cents !== basePreview.total_cents)
    bits.push(`<span class="stat"><span class="meta">${esc(t("assembly.vs_as_built"))}</span> `
      + `<b class="num">${esc(moneyDelta(preview.total_cents - basePreview.total_cents))}</b></span>`);
  if (whatIf)
    bits.push(`<span class="stat meta">${esc(t("assembly.what_if_note"))}</span>`);
  host.innerHTML = `<div class="summary-line">${bits.join("")}</div>`;
}

async function loadRunBom() {
  const runId = state.result?.run?.id;
  if (!runId) { runBom = null; runAllocations = []; return; }
  try {
    const doc = await apiGet(`/api/runs/${runId}/bom`);
    runBom = doc?.bom?.total_cents ?? null;
    // the same response the total comes from: what this fence has already been
    // given off the shelf, which is what makes the drawer's "available" mean
    // available rather than "on the shelf before this job existed"
    runAllocations = doc?.bom?.allocations || [];
  } catch {
    // a stale run refuses its money views, and the two viewports already say so
    runBom = null;
    runAllocations = [];
  }
}

// -------------------------------------------------------------- the drawer

function renderDrawer() {
  const host = document.getElementById("assembly-drawer");
  if (!host) return;
  if (!drawerSlot) { host.innerHTML = ""; return; }
  if (!preview) {
    host.innerHTML = `<div class="panel meta">${
      previewError ? refusalText(previewError)
                   : esc(t("assembly.no_options_here"))}</div>`;
    return;
  }
  // the OPTIONS come from the unpinned baseline and the price from the current
  // preview: see partOptions — a pinned slot's own eligibility is the one
  // product that was pinned, which is right for pricing and useless as a list
  const model = partOptions(preview, drawerSlot, {
    products, inventory, catalogue: basePreview || preview,
    allocations: runAllocations,
  });
  if (!model) { host.innerHTML = ""; return; }
  host.innerHTML = drawerHtml(model, {
    locale: currentLocale(), pinned: whatIf?.slot_skus?.[drawerSlot] || null,
  });
  host.querySelector("#btn-drawer-close")?.addEventListener("click", () => {
    drawerSlot = null;
    renderDrawer();
  });
  // the drawer opens BELOW two viewports, so on a laptop it opens off-screen —
  // an inspector nobody can see reads as a click that did nothing
  host.querySelector("#assembly-drawer-panel")
    ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  for (const btn of host.querySelectorAll("[data-pick-sku]"))
    btn.addEventListener("click", () => {
      enterWhatIf({ slot_skus: { ...(whatIf?.slot_skus || {}),
                                 [drawerSlot]: btn.dataset.pickSku } });
      schedulePreview(0);
      render();
    });
}

// The two viewports agree about one slot: the micro drawing raises it, and the
// macro drawing lights up that member in EVERY bay that carries it — which is
// the macro question ("where else is this part?") that the micro view cannot
// answer on its own.
function applySlot() {
  highlightSlot(microSvg, microSlot);
  refreshSections();
  if (!macroSvg) return;
  for (const rect of macroSvg.querySelectorAll(".macro-member"))
    rect.classList.toggle("selected",
      microSlot !== null && rect.getAttribute("data-slot") === microSlot);
}

const r = (n) => Math.round(n * 10) / 10;
const r6 = (n) => Math.round(n * 1e6) / 1e6;
