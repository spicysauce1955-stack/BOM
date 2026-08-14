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

import { esc } from "./api.js";
import { loadCatalogProducts } from "./builder-ui.js";
import {
  elevationRects, gapLine, hasNominal, highlightSlot, renderElevation,
} from "./elevation.js";
import { el } from "./geom.js";
import { t } from "./i18n.js";
import { on, setSelection, state } from "./state.js";
import {
  footingShape, macroDimensions, macroModel, macroPlacement,
} from "./runview.js";
import {
  getReport, isStale, loadStructure, staleCode, staleKind,
} from "./structure-data.js";
import { enumWord, tu } from "./units.js";

const MODES = ["split", "macro", "micro"];
// Above this many drawn members the macro view stops drawing panels as their
// parts and draws them as blocks instead. A 60-bay fence of 20 slats is 1200
// rectangles that resolve to nothing legible at macro scale — the cost is real
// and the picture is not better for it. The view SAYS it simplified rather than
// quietly showing a different fence.
const MEMBER_BUDGET = 900;

let mode = "split";
let annotations = true;
let macroSvg = null;
let microSvg = null;
let drawnBayId = null;       // the bay the micro view is showing
let microSlot = null;        // the member slot both views agree on
let faceWidths = {};         // sku -> declared post face width, from the catalog

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
  // a selection made on the Structure tab or in the plan canvas lands here too:
  // switching tabs must not lose which bay the user was looking at
  on("selection-changed", () => { if (assemblyTabActive()) render(); });
}

async function openTab() {
  await ensureFaceWidths();
  await loadStructure();
  render();
}

// Post face widths are catalog DATA (`attrs.face_width_mm`). Read through the
// shared cache rather than fetched here: the builder already holds the products,
// and a second copy is a second answer to "how wide is a POST-S".
async function ensureFaceWidths() {
  try {
    const products = await loadCatalogProducts();
    faceWidths = Object.fromEntries(
      Object.entries(products || {})
        .map(([sku, p]) => [sku, p?.attrs?.face_width_mm])
        .filter(([, w]) => Number.isFinite(w)));
  } catch {
    faceWidths = {};   // no catalog: every post draws at its nominal, and says so
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
    </div>`;
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
}

// --------------------------------------------------------------- rendering

function render() {
  renderBar();
  const row = document.getElementById("assembly-row");
  if (row) row.dataset.mode = mode;
  renderMacro();
  renderMicro();
}

/** The refusal branches, borrowed WHOLE from the Structure tab.
 *
 * "No structure yet" is true for exactly one state — no run. Every other branch
 * is a run that exists and cannot be laid out, and telling the user to generate
 * a strategy about one of those is a lie they cannot act on. */
function emptyMessage() {
  const key = !isStale() ? "assembly.no_run"
    : staleKind() === "catalog" ? "structure.catalog_changed"
    : staleKind() === "predates" ? "error.run_predates_fence_model"
    : staleKind() === "unknown" ? "structure.unreadable"
    : "structure.stale";
  return `<div class="meta">${esc(t(key, { code: staleCode() }))}</div>`;
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
  el("title", {}, g).textContent =
    `${bay.tag} · ${bay.width_mm} × ${bay.height_mm}`;

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
  if (bay.element_id !== drawnBayId) microSlot = null;
  drawnBayId = bay.element_id;

  const gaps = gapLine(bay.elevation);
  host.insertAdjacentHTML("beforeend",
    `<div class="summary-line"><b>${esc(t("elevation.bay_title", { tag: bay.tag }))}</b>`
    + `<span class="meta">${esc(tu("assembly.bay_dims",
        { width_mm: bay.width_mm, height_mm: bay.height_mm }))}</span>`
    + `<span class="meta">${esc(enumWord(bay.vertical))}</span></div>`
    + `<div id="assembly-micro-draw"></div>`
    + `<div class="meta">${esc(t("assembly.micro_hint"))}${
        gaps ? ` · <bdi class="elev-gaps">${esc(gaps)}</bdi>` : ""}</div>`
    + (hasNominal(bay.elevation)
      ? `<div class="elevation-note"><span class="elev-swatch"></span>${
          esc(t("elevation.nominal_note"))}</div>` : ""));

  const draw = host.querySelector("#assembly-micro-draw");
  const svg = renderElevation(bay.elevation, { onSelect: selectSlot });
  if (!svg) {
    draw.innerHTML = `<div class="meta">${esc(t("elevation.empty"))}</div>`;
    return;
  }
  draw.appendChild(svg);
  microSvg = svg;
  applySlot();
}

/** Clicking the same member twice clears it — a highlight with no way off is a
 *  highlight the user has to leave the tab to be rid of. */
function selectSlot(slotKey) {
  microSlot = microSlot === slotKey ? null : slotKey;
  applySlot();
}

// The two viewports agree about one slot: the micro drawing raises it, and the
// macro drawing lights up that member in EVERY bay that carries it — which is
// the macro question ("where else is this part?") that the micro view cannot
// answer on its own.
function applySlot() {
  highlightSlot(microSvg, microSlot);
  if (!macroSvg) return;
  for (const rect of macroSvg.querySelectorAll(".macro-member"))
    rect.classList.toggle("selected",
      microSlot !== null && rect.getAttribute("data-slot") === microSlot);
}

const r = (n) => Math.round(n * 10) / 10;
const r6 = (n) => Math.round(n * 1e6) / 1e6;
