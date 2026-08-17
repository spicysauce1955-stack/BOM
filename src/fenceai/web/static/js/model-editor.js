// The Models tab: authoring a fence model, and seeing the panel it builds.
//
// What it answers, in the user's own words: "what if the user wants to edit,
// change or add a panel? variant?" Models became persisted, versioned,
// selectable data with a working preview in W1–W3, and the only way to author
// one was a JSON POST — so the structure that decides every material, size and
// price in the fence was editable by everyone except the expert who owns it.
//
// Shape copied from the knowledge rule builder (tabs.js), deliberately:
// sentence-style rows over the LIVE data structure, plus an Advanced-JSON
// escape hatch whose exit is NEVER gated on the JSON being valid. That last
// rule is not a preference — the rule editor once trapped users behind a stray
// comma, with no way back but a page reload.
//
// Two things here are load-bearing and easy to "tidy" into defects:
//
//   * `gap_after_mm` MAY BE NEGATIVE. A negative gap is an overlap, and an
//     overlap is what board-on-board and shadowbox ARE. A `min="0"` on that
//     field would delete two whole product families from what the tool can
//     express. `validate_model` bounds the member's net ADVANCE instead.
//   * a `swatch` ends up in a CSS/SVG colour, where esc() is not enough. It is
//     validated `^#[0-9a-fA-F]{6}$` at model load, and the field refuses
//     anything else here rather than leaning on that check alone.
//
// DOM ownership: everything under `#tab-models`. No other module writes it, and
// this module writes nothing else — the library it changed is announced with a
// `fence-models-changed` event, which the Panel tab listens for.

import { apiGet, apiSend, esc } from "./api.js";
import {
  el, field, loadCatalogProducts, option, updateAdvancedUi,
} from "./builder-ui.js";
import {
  CONDITION_CMPS, CONDITION_FIELDS, readSentence, writeSentence,
} from "./condition-sentence.js";
import { renderElevation } from "./elevation.js";
import { loadModelListing, refreshModelListing } from "./fence-models.js";
import { currentLocale, t } from "./i18n.js";
import { renderImpactReport } from "./impact.js";
import { isDragging, renderCanvas } from "./panel-canvas.js";
import {
  renderAxisEditor, renderInspector, SELECTION_NONE,
} from "./panel-inspector.js";
import { TEMPLATES } from "./panel-templates.js";
import {
  GRADES, blankModel, canChooseId, defaultFixing, defaultInfill, defaultMember,
  defaultSlot, defaultVariant, draftCopyOf, duplicateOf, freeId, idCollision,
  specOf,
} from "./panel-model.js";
import { on } from "./state.js";
import {
  fmt, inputStep, money, roleWord, toDisplayValue, toMm, tu, unitParams,
} from "./units.js";

const PREVIEW_DEBOUNCE_MS = 250;
const DEFAULT_HEIGHT_MM = 1800;
const DEFAULT_WIDTH_MM = 2500;

// --- module state ------------------------------------------------------------

let listing = [];
let session = null;      // { model, version | null, invalid, saveError, published }
let specIndex = -1;      // -1 = default_spec, else variants[specIndex].spec
let advancedOpen = false;
// which thing on the panel the inspector is editing — a chip on the element
// list today, a rectangle on the drawing once the canvas lands
let selection = SELECTION_NONE;
let heightMm = DEFAULT_HEIGHT_MM;
let widthMm = DEFAULT_WIDTH_MM;
let preview = null;
let previewError = null;
let publishError = null;  // {code, params, errors} from the 422 — the gate's answer
let notice = null;        // [key, params] — the last thing that happened
let previewPending = null;
let inFlightSave = null;  // a save already issued; publish must not overtake it
let saveSeq = 0;
let previewSeq = 0;

const modelsTabActive = () =>
  !!document.getElementById("tab-models")?.classList.contains("active");

// A locale sentence whose params are ids, refs or dimensions: escape the
// template first, then drop each param in bidi-isolated. Same shape (and same
// reason) as panel.js's — a model ref inside a Hebrew sentence needs its own
// direction, and an author's model id is text they typed.
function sentence(key, params = {}) {
  let s = esc(t(key));
  for (const [k, v] of Object.entries(unitParams(params)))
    s = s.replaceAll(`{${k}}`, `<bdi>${esc(String(v))}</bdi>`);
  return s;
}

// --- wiring ------------------------------------------------------------------

export function initModelEditor() {
  document.getElementById("btn-model-new").addEventListener("click", openGallery);
  document.getElementById("btn-model-save").addEventListener("click", async () => {
    if (!session || !commitAdvanced()) return;   // an invalid JSON box must not save silently
    const saved = await saveDraft();
    session.dirty = !saved;
    notice = saved ? ["model.saved", { ref: sessionRef() }] : null;
    renderAll();
  });
  document.getElementById("btn-model-impact").addEventListener("click", async () => {
    if (!session || !commitAdvanced()) return;
    const out = document.getElementById("model-impact-out");
    out.innerHTML = `<em>${esc(t("impact.computing"))}</em>`;
    try {
      renderImpactReport(out, await apiSend(
        "POST", `/api/fence-models/${encodeURIComponent(session.model.id)}/preview-impact`,
        session.model));
    } catch {
      out.innerHTML = `<div class="meta">${esc(t("model.impact_failed"))}</div>`;
    }
  });
  document.getElementById("btn-model-publish").addEventListener("click", publish);
  document.getElementById("btn-model-close").addEventListener("click", () => {
    session = null; advancedOpen = false; preview = null; previewError = null;
    publishError = null; notice = null;
    closeGallery();
    renderAll();
  });
  document.getElementById("btn-model-advanced").addEventListener("click", toggleAdvanced);

  on("tab-changed", (tab) => { if (tab === "models") openModelsTab(); });
  const relocalize = () => { if (modelsTabActive()) renderAll(); };
  on("locale-changed", relocalize);
  on("units-changed", relocalize);   // same fields, different numbers
}

// Entering the tab repaints EVERYTHING, not just the library. The display unit
// and the language can both have changed while this tab was hidden, and a form
// left rendering millimetres under a "(cm)" label does not merely look stale:
// `num()` converts on commit with the LIVE unit, so editing a field that reads
// 100 would store 1000 mm.
async function openModelsTab() {
  await readListing();
  renderAll();
}

// `fence-models.js` owns the listing; this reads it rather than keeping a
// second copy, so the editor and every picker cannot disagree about which
// models exist.
async function readListing() {
  listing = await loadModelListing();
  return listing;
}

// One write happened: re-read, announce, repaint the library.
async function announceLibraryChange() {
  listing = await refreshModelListing();
  renderList();
}

// `panel-model.js` owns the rule and takes the rows it judges against — this is
// the one place that knows WHICH rows, so the rule stays testable without a
// library and every call site here still means "free in the library I hold".
const freeLibraryId = (base) => freeId(base, listing);

function sessionRef() {
  return session ? `${session.model.id}@v${session.version ?? "?"}` : "";
}

// `isNew` is the session's INTENT, and it is not derivable from `version`:
// "New", "Duplicate" and "Edit a published version" all start without one, but
// only the first two mean to create a model id that does not exist yet.
function openSession(model, version, { isNew = false } = {}) {
  session = { model, version, isNew, invalid: null, saveError: null, dirty: false };
  specIndex = -1;
  selection = SELECTION_NONE;
  advancedOpen = false;
  preview = null;
  previewError = null;
  publishError = null;
  notice = null;
  updateAdvancedUi("model-editor", "model-json", "btn-model-advanced", false, "model.back");
  renderAll();
  refreshPreview();   // an unsaved document prices exactly as a stored one does
}

// A version that cannot be fetched is nothing to open, and a rejected click
// handler reports that to nobody — so every entry point catches its own load.
async function loadVersion(modelId, version) {
  try {
    return await apiGet(`/api/fence-models/${encodeURIComponent(modelId)}/${version}`);
  } catch {
    return null;
  }
}

async function openForEdit(row) {
  // A draft is reopened where it was left; a published model is COPIED, and the
  // copy has no version until it is saved — which is what stops "Edit" from
  // rewriting a version some accepted quote was priced against.
  const version = row.draft_version ?? row.active_version
    ?? (row.versions.length ? row.versions[row.versions.length - 1] : null);
  if (version === null || version === undefined) return;
  const doc = await loadVersion(row.id, version);
  if (!doc) return;
  const isDraft = row.draft_version === version;
  openSession(isDraft ? doc : draftCopyOf(doc), isDraft ? version : null);
}

async function openForDuplicate(row, version) {
  const doc = await loadVersion(row.id, version);
  if (doc) openSession(duplicateOf(doc, freeLibraryId(`${row.id}-COPY`)), null,
                       { isNew: true });
}

// --- starting a new panel: the gallery ---------------------------------------
//
// "New model" opens a handful of curated starters rather than an empty
// document, because an empty panel is the one shape from which nothing on the
// canvas can be clicked. Each card is a REAL preview of the panel it would
// open — priced through the same `/preview` route the editor uses, so a card
// cannot show a panel the editor then disagrees with — and picking one lands an
// ordinary independent draft, exactly as "Duplicate" already did.

async function openGallery() {
  const host = document.getElementById("model-gallery");
  if (!host) return;
  host.hidden = false;
  host.innerHTML = `<h3>${esc(t("model.gallery_title"))}</h3>
    <div class="meta">${esc(t("model.gallery_hint"))}</div>
    <div class="template-cards"></div>`;
  const cards = host.querySelector(".template-cards");
  for (const template of TEMPLATES)
    cards.appendChild(await templateCard(template));
  cards.appendChild(blankCard());
}

function closeGallery() {
  const host = document.getElementById("model-gallery");
  if (host) { host.hidden = true; host.innerHTML = ""; }
}

async function templateCard(template) {
  const card = el("button", { type: "button", class: "template-card",
                              "data-template": template.key });
  card.appendChild(el("b", { text: t(`model.template.${template.key}.name`) }));
  const draw = el("div", { class: "template-draw" });
  card.appendChild(draw);
  card.appendChild(el("span", { class: "meta",
                                text: t(`model.template.${template.key}.desc`) }));
  card.addEventListener("click", () => {
    closeGallery();
    openSession(template.build(freeLibraryId(template.id_base)), null, { isNew: true });
  });
  // the card's picture comes from the same route the editor prices with; a card
  // that failed to price simply shows its words, rather than a broken box
  try {
    const out = await apiSend("POST", "/api/fence-models/preview", {
      model: template.build(template.id_base),
      bay: { height_mm: heightMm, width_mm: widthMm },
    }, { quiet: true });
    const svg = renderElevation(out.elevation, { annotations: false, joints: false });
    if (svg) draw.appendChild(svg);
  } catch { /* the words are the card; the drawing is the bonus */ }
  return card;
}

function blankCard() {
  const card = el("button", { type: "button", class: "template-card",
                              "data-template": "blank" });
  card.appendChild(el("b", { text: t("model.template.blank.name") }));
  card.appendChild(el("div", { class: "template-draw" }));
  card.appendChild(el("span", { class: "meta", text: t("model.template.blank.desc") }));
  card.addEventListener("click", () => {
    closeGallery();
    openSession(blankModel(freeLibraryId("M-NEW")), null, { isNew: true });
  });
  return card;
}

// --- saving, publishing, retiring -------------------------------------------

// An edit re-prices, and that is ALL it does. Nothing is written until the
// author asks — see `refreshPreview`, which prices the document in memory.
function scheduleRepreview() {
  clearTimeout(previewPending);
  previewPending = setTimeout(refreshPreview, PREVIEW_DEBOUNCE_MS);
}

// The id the live session would collide with, or null — the rule itself lives
// in `panel-model.js`, judged against the library this module holds.
const idTaken = () => idCollision(session, listing);

async function saveDraft({ quiet = false } = {}) {
  if (!session) return false;
  if (idTaken()) {
    // POST routes by the id in the body and mints the NEXT VERSION of whatever
    // it names, so saving under a taken id would not create this model — it
    // would attach a half-built document to a shipped one as its next draft,
    // which is then what "Edit" opens for everybody. There is no delete route
    // to undo it.
    session.saveError = "model.id_taken";
    return false;
  }
  const mySeq = ++saveSeq;
  const before = session.version;
  const request = session.version === null
    ? apiSend("POST", "/api/fence-models", session.model, { quiet })
    : apiSend("PUT", `/api/fence-models/${encodeURIComponent(session.model.id)}/draft`,
              session.model, { quiet });
  inFlightSave = request.catch(() => null);   // publish waits on this, not on a timer
  try {
    const out = await request;
    if (mySeq !== saveSeq) return true;    // a later save already answered
    session.version = out.model.version;
    session.model.version = out.model.version;
    session.model.status = out.model.status;
    session.invalid = out.invalid;
    session.saveError = null;
    if (before !== session.version) {
      // a NEW version row appeared: every picker in the app is now stale
      await announceLibraryChange();
      renderForm();   // the id is fixed from here — the field must show it
    }
    return true;
  } catch {
    if (mySeq !== saveSeq) return false;
    session.saveError = "model.save_failed";
    return false;
  }
}

async function publish() {
  if (!session || !commitAdvanced()) return;
  // A save ALREADY ISSUED cannot be cancelled, only waited for: if one landed
  // after the publish it would find no draft and mint a fresh draft version of
  // the model just frozen. `clearTimeout` alone never closed that — it stops a
  // timer, not a request in flight.
  await inFlightSave;
  publishError = null;
  notice = null;
  if (!await saveDraft()) return renderAll();
  try {
    // quiet: the 422 carries the reasons this model cannot be published, and
    // they belong on the page beside the fields that caused them — api.js's
    // generic alert would render `error.fence_model_invalid`, whose sentence
    // ("No strategy was generated…") is about GENERATION, not about publishing.
    const out = await apiSend(
      "POST",
      `/api/fence-models/${encodeURIComponent(session.model.id)}/${session.version}/publish`,
      undefined, { quiet: true });
    session.model = out;
    session.invalid = null;
    session.dirty = false;
    notice = ["model.published", { ref: `${out.id}@v${out.version}` }];
  } catch (err) {
    publishError = parseRefusal(err) || { code: "fence_model_invalid", params: {}, errors: [] };
  }
  await announceLibraryChange();
  // the whole surface, not just the library: the gate's answer — published, or
  // refused and why — is the point of having pressed the button
  renderAll();
}

async function retire(row, version) {
  try {
    await apiSend(
      "POST",
      `/api/fence-models/${encodeURIComponent(row.id)}/${version}/status?status=retired`);
  } catch {
    return;   // apiSend already told the user; a rejected handler tells nobody
  }
  notice = ["model.retired", { ref: `${row.id}@v${version}` }];
  await announceLibraryChange();
  renderAll();
}

// The refusal body as the server sends it: {detail: {code, params, errors}}.
// Read structurally, never by parsing the English sentence.
function parseRefusal(err) {
  try {
    const detail = JSON.parse(String(err?.message || ""))?.detail;
    return detail?.code ? detail : null;
  } catch {
    return null;
  }
}

// --- the Advanced (JSON) escape hatch ---------------------------------------

function toggleAdvanced() {
  if (!session) return;
  const ta = document.getElementById("model-json");
  if (!advancedOpen) {
    ta.value = JSON.stringify(session.model, null, 2);
    advancedOpen = true;
  } else {
    // NEVER gate the way out on the thing that is broken (tabs.js:93-95). The
    // exit is offered either way; only the edits are discarded.
    const parsed = parseModel(ta.value);
    if (parsed) session.model = parsed;
    else if (!confirm(t("model.json_discard"))) return;
    advancedOpen = false;
    if (specIndex >= (session.model.variants || []).length) specIndex = -1;
    session.dirty = true;
    renderAll();
    scheduleRepreview();
  }
  updateAdvancedUi("model-editor", "model-json", "btn-model-advanced", advancedOpen, "model.back");
}

// The raw-JSON box stays in MILLIMETRES, like the knowledge and inventory ones:
// it is the storage representation, not a rendered field.
function parseModel(text) {
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" && typeof parsed.id === "string"
      ? parsed : null;
  } catch { return null; }
}

// Save/publish/impact must act on what the user is LOOKING at. Returns false
// when the open JSON box cannot become a model — the one case where a broken
// box blocks an action, because there is nothing coherent to send.
function commitAdvanced() {
  if (!advancedOpen) return true;
  const parsed = parseModel(document.getElementById("model-json").value);
  if (!parsed) { alert(t("model.json_invalid")); return false; }
  session.model = parsed;
  return true;
}

// --- rendering ---------------------------------------------------------------

function renderAll() {
  renderList();
  renderForm();
  renderStatus();
  renderPreviewControls();
  renderPreview();
}

function renderList() {
  const host = document.getElementById("model-list");
  if (!host) return;
  if (!listing.length) {
    host.innerHTML = `<div class="meta">${esc(t("model.no_models"))}</div>`;
    return;
  }
  let html = "";
  for (const row of listing) {
    const name = row.name_i18n?.[currentLocale()] || row.name_i18n?.en || row.id;
    html += `<div class="card model-row" data-model="${esc(row.id)}">
      <span class="tag ${esc(row.status)}">${esc(t("status." + row.status))}</span>
      <b dir="auto">${esc(name)}</b> <bdi class="sku">${esc(row.id)}</bdi>
      <div class="meta">${row.active_version === null ? esc(t("model.no_published_version"))
        : sentence("model.active_is", { version: row.active_version })}
        ${row.draft_version !== null && row.draft_version !== undefined
          ? " · " + sentence("model.draft_is", { version: row.draft_version }) : ""}</div>
      <button data-act="edit">${esc(t("model.edit"))}</button>
      <button data-act="duplicate">${esc(t("model.duplicate"))}</button>
      <select data-f="version" title="${esc(t("model.duplicate_from"))}">${
        row.versions.map((v) => `<option value="${v}">v${v}</option>`).join("")}</select>
      ${row.active_version !== null
        ? `<button data-act="retire" title="${
            esc(t("model.retire_version", { version: row.active_version }))}">${
            esc(t("model.retire"))}</button>` : ""}
    </div>`;
  }
  host.innerHTML = html;
  for (const card of host.querySelectorAll("[data-model]")) {
    const row = listing.find((r) => r.id === card.dataset.model);
    const version = () => Number(card.querySelector('[data-f="version"]').value);
    card.querySelector('[data-act="edit"]').addEventListener("click", () => openForEdit(row));
    card.querySelector('[data-act="duplicate"]')
      .addEventListener("click", () => openForDuplicate(row, version()));
    card.querySelector('[data-act="retire"]')
      ?.addEventListener("click", () => retire(row, row.active_version));
  }
}

function renderStatus() {
  const host = document.getElementById("model-status");
  if (!host) return;
  if (!session) { host.innerHTML = ""; return; }
  let html = session.version === null
    ? `<span class="meta">${esc(t("model.unsaved"))}</span>`
    : sentence("model.draft_ref", { ref: sessionRef() });
  // Nothing is written until Save is pressed, so the editor has to SAY that
  // there is something unwritten — an editor that silently holds your work is
  // the other half of the trap an editor that silently stores it would be.
  if (session.dirty)
    html += ` <span class="tag medium">${esc(t("model.unsaved_changes"))}</span>`;
  const taken = idTaken();
  if (taken)
    html += ` <span class="tag rejected">${sentence("model.id_taken", { id: taken })}</span>`;
  if (session.saveError && !taken)
    html += ` <span class="tag rejected">${esc(t(session.saveError))}</span>`;
  if (notice) html += ` <span class="tag active">${sentence(notice[0], notice[1])}</span>`;
  host.innerHTML = html;
  renderProblems();
}

// Everything standing between this draft and a published version. `invalid` is
// what a save reports; `publishError` is what the gate refused with. Both carry
// code + params, and both carry `errors[]` — English authoring text by design
// (`model.py::validate_model`), shown under a localized heading that says so.
function renderProblems() {
  const host = document.getElementById("model-errors");
  if (!host) return;
  const problem = publishError || session?.invalid;
  if (!problem) { host.innerHTML = ""; return; }
  const key = `model.invalid.${problem.code}`;
  const headline = t(key, problem.params || {});
  host.innerHTML = `<div class="panel supply-problems">
    <h3>${esc(publishError ? t("model.publish_refused") : t("model.draft_invalid"))}</h3>
    <div>${esc(headline === key ? t("model.invalid.fence_model_invalid", problem.params || {}) : headline)}</div>
    <div class="meta">${esc(t("model.errors_are_authoring_text"))}</div>
    <ul dir="ltr">${(problem.errors || []).map((e) => `<li>${esc(e)}</li>`).join("")}</ul>
  </div>`;
}

function renderForm() {
  const form = document.getElementById("model-form");
  if (!form) return;
  form.hidden = !session;
  if (!session) return;
  renderHead();
  renderSpecPicker();
  renderElements();
  renderCanvasPane();
  renderInspectorPane();
  renderAxisPane();
}

// An edit changes the document and re-prices it. It does NOT save: a draft the
// author never asked to store is still a row in a versioned library, and the
// library has no delete.
function touch({ rerender = false } = {}) {
  if (rerender) { renderForm(); renderStatus(); }
  if (session) session.dirty = true;
  scheduleRepreview();
  renderStatus();
}

function removeButton(onclick) {
  const b = el("button", { type: "button", class: "remove-row",
                           title: t("common.remove"), text: "✕" });
  b.addEventListener("click", onclick);
  return b;
}

// --- the model head: id, name, grade ----------------------------------------

function renderHead() {
  const host = document.getElementById("model-head");
  host.innerHTML = "";
  const row = el("div", { class: "builder-row" });

  // The id is editable only while this session means to CREATE a model. Editing
  // an existing one — draft or published copy — must keep its id, because that
  // is what makes the save land as the next version OF that model rather than
  // forking a second one under a new name.
  //
  // The id is a SAVE KEY, which is also why nothing here writes as you type. A
  // save routes by it and mints a draft under whatever it names: when editing
  // still auto-saved, typing "M-SLAT" one character at a time left `M@v1`,
  // `M-@v1`, `M-S@v1` … behind as real library rows and landed the half-built
  // document as `M-SLAT@v2` — a new draft version of the shipped model, and no
  // delete route to undo any of it. Saving is explicit now, and a NEW model
  // still refuses an id the library holds, because one deliberate Save under a
  // taken id does the same damage.
  const idInput = el("input", { type: "text", "data-f": "id", dir: "ltr",
                                class: "sku", size: 16, value: session.model.id });
  if (!canChooseId(session)) idInput.disabled = true;
  idInput.addEventListener("input", () => {
    session.model.id = idInput.value.trim();
    idInput.classList.toggle("invalid", !!idTaken());
    renderStatus();
  });
  row.appendChild(field("model.id", idInput));

  // The name is per-language; the field edits the ACTIVE language and leaves the
  // other alone, so flipping the toggle is how a bilingual name is written.
  const nameInput = el("input", { type: "text", "data-f": "name", dir: "auto", size: 26,
                                  value: session.model.name_i18n?.[currentLocale()] || "" });
  nameInput.addEventListener("input", () => {
    session.model.name_i18n = { ...session.model.name_i18n, [currentLocale()]: nameInput.value };
    touch();
  });
  row.appendChild(field("model.name", nameInput));

  // The grade is written here rather than through the inspector's `choice`,
  // small as it is: those builders report their edits through a `notify` the
  // inspector sets per render, and a caller outside that render would be
  // reporting into whatever the last one happened to leave behind.
  const grade = el("select", { "data-f": "grade" });
  for (const g of GRADES)
    grade.appendChild(option(g, t("model.grade." + g), session.model.grade === g));
  grade.addEventListener("change", () => {
    session.model.grade = grade.value;
    touch();
  });
  row.appendChild(field("model.grade", grade));
  host.appendChild(row);
}

// --- which spec the row editors edit: the default panel, or a variant --------

function renderSpecPicker() {
  const host = document.getElementById("model-spec-picker");
  host.innerHTML = "";
  const variants = session.model.variants || [];
  const row = el("div", { class: "builder-row" });
  const sel = el("select", { class: "builder-kind" });
  sel.appendChild(option("-1", t("model.spec.default"), specIndex === -1));
  variants.forEach((_, i) =>
    sel.appendChild(option(String(i), t("model.spec.variant", { n: i + 1 }), specIndex === i)));
  sel.addEventListener("change", () => { specIndex = Number(sel.value); renderForm(); });
  row.appendChild(field("model.spec", sel));

  const add = el("button", { type: "button", text: t("model.add_variant") });
  add.addEventListener("click", () => {
    variants.push(defaultVariant());
    session.model.variants = variants;
    specIndex = variants.length - 1;
    touch({ rerender: true });
  });
  row.appendChild(add);
  if (specIndex >= 0) {
    row.appendChild(removeButton(() => {
      variants.splice(specIndex, 1);
      specIndex = -1;
      touch({ rerender: true });
    }));
  }
  host.appendChild(row);

  // A variant's condition is an `Expr` AST. The ONE shape every shipped model
  // uses — a field compared to a literal — is a sentence; everything else keeps
  // the JSON box, which is not a fallback to be designed away but the parity
  // guarantee itself: a condition the sentence cannot say is left alone rather
  // than rewritten into one it can.
  if (specIndex >= 0) {
    const variant = variants[specIndex];
    host.appendChild(conditionSentence(variant));
    const advanced = el("details", { class: "condition-advanced" },
      el("summary", { text: t("model.condition_advanced") }));
    const hint = el("div", { class: "meta", text: t("model.variant_conditions_hint") });
    const ta = el("textarea", { id: "model-variant-condition", dir: "ltr", rows: 3, cols: 60 });
    ta.value = JSON.stringify(variant.condition ?? null, null, 2);
    ta.addEventListener("change", () => {
      try {
        variant.condition = JSON.parse(ta.value);
        ta.classList.remove("invalid");
        touch({ rerender: true });   // the sentence above may now be able to say it
      } catch {
        // the box keeps the user's text; nothing is saved from it until it parses
        ta.classList.add("invalid");
      }
    });
    advanced.append(hint, ta);
    host.appendChild(advanced);
  }
}

/** "Applies when panel height is at least 1800 mm" — three controls over the
 *  same `Expr` the JSON box below holds.
 *
 *  A condition the sentence cannot read renders as a line saying so, with the
 *  box beneath it in charge. Nothing is rewritten on the way past: opening the
 *  editor on a document must not narrow it. */
function conditionSentence(variant) {
  const said = readSentence(variant.condition);
  const wrap = el("div", { class: "builder-row condition-sentence" });
  if (!said) {
    wrap.appendChild(el("span", { class: "meta", text: t("model.condition_only_json") }));
    return wrap;
  }
  const isLength = said.path.endsWith("_mm");
  const write = () => {
    variant.condition = writeSentence({
      path: fieldSel.value, cmp: cmpSel.value,
      // a length crosses the display-unit boundary here, like every other
      // length field — a height typed as 180 in cm is 1800 mm in the condition
      value: isLength ? (toMm(valueInput.value) ?? 0)
                      : Math.round(valueInput.valueAsNumber || 0),
    });
    touch();
  };
  wrap.appendChild(el("span", { class: "meta", text: t("model.condition_applies_when") }));
  const fieldSel = el("select", { "data-f": "condition_field" });
  for (const path of CONDITION_FIELDS)
    fieldSel.appendChild(option(path, t(`model.condition.field.${path}`), said.path === path));
  if (!CONDITION_FIELDS.includes(said.path))
    fieldSel.appendChild(option(said.path, said.path, true));
  fieldSel.addEventListener("change", write);
  wrap.appendChild(fieldSel);

  const cmpSel = el("select", { "data-f": "condition_cmp" });
  for (const cmp of CONDITION_CMPS)
    cmpSel.appendChild(option(cmp, t(`model.condition.cmp.${cmp}`), said.cmp === cmp));
  cmpSel.addEventListener("change", write);
  wrap.appendChild(cmpSel);

  const valueInput = el("input", {
    type: "number", "data-f": "condition_value", step: isLength ? inputStep() : "1",
    value: String(isLength ? toDisplayValue(said.value) : said.value),
  });
  valueInput.addEventListener("change", write);
  wrap.appendChild(isLength ? field("model.condition_value_mm", valueInput)
                            : field("model.condition_value", valueInput));
  return wrap;
}

// --- what the panel is made of: the elements, and the one being edited -------
//
// The list is the SELECTOR the drawing became: every rail, board and set of
// screws as a chip, plus the buttons that add one. It stays beside the canvas
// rather than being replaced by it, because two of the three cannot always be
// clicked on the drawing — a set of screws with no fasteners placed yet has no
// dot, and a panel being started has no rectangles at all.

const ELEMENT_KINDS = ["frame", "infill", "fixing"];

/** Every element of the live spec, in the order the panel is read in. */
function elementsOf(spec) {
  if (!spec) return [];
  return [
    ...(spec.frame || []).map((s) => ({ kind: "frame", key: s.key })),
    ...(spec.infill?.pattern || []).map((m) => ({ kind: "infill", key: m.key })),
    ...(spec.fixings || []).map((f) => ({ kind: "fixing", key: f.key })),
  ];
}

const selectionEquals = (a, b) => a?.kind === b?.kind && a?.key === b?.key;

function selectElement(next) {
  selection = selectionEquals(selection, next) ? SELECTION_NONE : next;
  renderElements();
  renderCanvasPane();
  renderInspectorPane();
}

// The drawing, with everything a pointer can do to it. A commit writes ONE
// authored number and then re-prices, which is the same `touch()` every field
// in the inspector goes through — a drag is an edit like any other, and in
// particular it does not save.
function renderCanvasPane() {
  const host = document.getElementById("model-canvas");
  if (!host) return;
  renderCanvas(host, {
    elev: preview?.elevation,
    spec: specOf(session.model, specIndex),
    selection,
  }, { onSelect: selectElement, onCommit: commitDrag });
}

function commitDrag(handle, value) {
  const spec = specOf(session.model, specIndex);
  if (!spec) return;
  switch (value.kind) {
    case "placement": {
      const slot = (spec.frame || []).find((s) => s.key === handle.slot_key);
      if (slot) slot.placement = value.placement;
      break;
    }
    case "width": {
      const member = (spec.infill?.pattern || []).find((m) => m.key === handle.slot_key);
      if (member) member.width_mm = value.width_mm;
      break;
    }
    case "gap": {
      const member = (spec.infill?.pattern || []).find((m) => m.key === handle.slot_key);
      if (member) member.gap_after_mm = value.gap_after_mm;
      break;
    }
    case "margin":
      if (spec.infill) spec.infill.edge_margin_mm = value.edge_margin_mm;
      break;
    default:
      return;
  }
  // the inspector's number fields are live readouts of the drag, so they are
  // rebuilt with it — the drawing waits for the re-price, which is the server's
  // answer about where the board actually ended up
  touch({ rerender: true });
}

function renderElements() {
  const host = document.getElementById("model-elements");
  if (!host) return;
  host.innerHTML = "";
  const spec = specOf(session.model, specIndex);
  if (!spec) return;
  host.appendChild(addBar(spec));
  const chips = el("div", { class: "element-chips" });
  for (const item of elementsOf(spec)) {
    const chip = el("button", {
      type: "button", class: `element-chip element-${item.kind}`,
      "data-element": `${item.kind}:${item.key}`,
    }, el("span", { class: "meta", text: t(`model.inspect.${ELEMENT_WORD[item.kind]}`) }),
       el("bdi", { class: "sku", text: item.key }));
    if (selectionEquals(selection, item)) chip.classList.add("selected");
    chip.addEventListener("click", () => selectElement(item));
    chips.appendChild(chip);
  }
  if (!elementsOf(spec).length)
    chips.appendChild(el("span", { class: "meta", text: t("canvas.empty_hint") }));
  host.appendChild(chips);
}

const ELEMENT_WORD = { frame: "rail", infill: "board", fixing: "screws" };

// The add buttons keep the ids they had as row-list subheads: they are the same
// actions, and the browser suite addresses them by name.
function addBar(spec) {
  const bar = el("div", { class: "canvas-toolbar" });
  const button = (id, key, onClick) => {
    const b = el("button", { type: "button", id, text: t(key) });
    b.addEventListener("click", onClick);
    return b;
  };
  bar.appendChild(button("btn-model-add-slot", "model.add_slot", () => {
    spec.frame ??= [];
    const slot = defaultSlot(`slot${spec.frame.length + 1}`);
    spec.frame.push(slot);
    selection = { kind: "frame", key: slot.key };
    touch({ rerender: true });
  }));
  bar.appendChild(button("btn-model-toggle-infill",
    spec.infill ? "model.remove_infill" : "model.add_infill", () => {
      spec.infill = spec.infill ? null : defaultInfill();
      selection = spec.infill
        ? { kind: "infill", key: spec.infill.pattern[0].key } : SELECTION_NONE;
      touch({ rerender: true });
    }));
  if (spec.infill) {
    bar.appendChild(button("btn-model-add-member", "model.add_member", () => {
      const member = defaultMember(`member${spec.infill.pattern.length + 1}`);
      spec.infill.pattern.push(member);
      selection = { kind: "infill", key: member.key };
      touch({ rerender: true });
    }));
  }
  bar.appendChild(button("btn-model-add-fixing", "model.add_fixing", () => {
    spec.fixings ??= [];
    const fixing = defaultFixing(`fix${spec.fixings.length + 1}`);
    spec.fixings.push(fixing);
    selection = { kind: "fixing", key: fixing.key };
    touch({ rerender: true });
  }));
  return bar;
}

// The catalog is awaited BEFORE the host is written, so two renders racing each
// other rebuild the pane rather than leaving a half-built one behind.
async function renderInspectorPane() {
  const products = await loadCatalogProducts();
  const host = document.getElementById("model-inspector");
  if (!host || !session) return;
  renderInspector(host, {
    selection, products,
    spec: specOf(session.model, specIndex),
    model: session.model,
    onChange: touch,
    onRemove: () => { selection = SELECTION_NONE; touch({ rerender: true }); },
    // a rename moves the selection with it: everything that holds one holds a
    // KEY, so without this the next repaint reports the element being edited as
    // no longer there
    onRename: (next) => { selection = next; renderElements(); },
  });
}

function renderAxisPane() {
  renderAxisEditor(document.getElementById("model-axes"),
                   { model: session.model, onChange: touch });
}

// --- the live preview, beside the editor -------------------------------------

// Prices the document IN MEMORY, saved or not. `POST /api/fence-models/preview`
// takes the whole model in its body, so seeing the effect of an edit costs
// nothing but a request — the editor writes only when the author asks it to.
// `quiet`: a half-built panel is expected to fail, and an alert per keystroke is
// not an error report, it is a trap.
async function refreshPreview() {
  if (!session) return;
  const seq = ++previewSeq;
  try {
    const out = await apiSend("POST", "/api/fence-models/preview", {
      model: session.model,
      bay: { height_mm: heightMm, width_mm: widthMm },
    }, { quiet: true });
    if (seq !== previewSeq) return;
    preview = out;
    previewError = null;
  } catch {
    if (seq !== previewSeq) return;
    preview = null;
    previewError = "model.preview_failed";
  }
  renderPreview();
}

// The bay the preview is imagined into. Rendered ONLY when the session, the
// language or the display unit changes — never on a re-price. A re-price fires
// on every keystroke in these very fields, and rebuilding them from inside that
// handler takes the caret out of the field the user is still typing in.
function renderPreviewControls() {
  const host = document.getElementById("model-preview-controls");
  if (!host) return;
  if (!session) { host.innerHTML = ""; host.hidden = true; return; }
  host.hidden = false;
  host.innerHTML = `<h3>${esc(t("model.preview_title"))}</h3>
    <div class="meta">${esc(t("model.preview_hint"))}</div>
    <div class="toolbar">
      <label class="builder-field"><span class="meta">${esc(tu("panel.height"))}</span>
        <input id="model-preview-height" type="number" step="${inputStep()}"
          value="${esc(String(toDisplayValue(heightMm)))}"></label>
      <label class="builder-field"><span class="meta">${esc(tu("panel.width"))}</span>
        <input id="model-preview-width" type="number" step="${inputStep()}"
          value="${esc(String(toDisplayValue(widthMm)))}"></label>
    </div>`;
  for (const [id, set] of [["model-preview-height", (mm) => { heightMm = mm; }],
                           ["model-preview-width", (mm) => { widthMm = mm; }]]) {
    const input = host.querySelector(`#${id}`);
    input.addEventListener("input", () => {
      // a blank field is NOT a panel of zero height: flag it and keep the last
      // good figure rather than previewing a fence of nothing
      const mm = toMm(input.value);
      const ok = mm !== null && mm > 0;
      input.classList.toggle("invalid", !ok);
      if (!ok) return;
      set(mm);
      refreshPreview();
    });
  }
}

function renderPreview() {
  const body = document.getElementById("model-preview-body");
  if (!body) return;
  body.innerHTML = session ? previewBodyHtml() : "";
  // A re-price landing mid-drag would rebuild the SVG the pointer is captured
  // on, and the capture would go with it — the board would stop following the
  // hand. The commit re-renders; until then the handle moves locally.
  if (session && !isDragging()) renderCanvasPane();
}

function previewBodyHtml() {
  if (previewError)
    return `<div class="panel meta">${esc(t(previewError))}</div>`;
  if (!preview) return `<div class="panel meta">${esc(t("panel.computing"))}</div>`;
  let html = `<div class="panel" id="model-parts">
    <h3>${esc(t("panel.parts_title"))} — <bdi class="sku">${esc(preview.model_ref)}</bdi></h3>
    <div class="meta">${sentence("panel.bay_line",
      { width_mm: preview.width_mm, height_mm: preview.height_mm })}</div>
    <div class="meta">${esc(t("panel.not_a_quote"))}</div>
    <table><tr><th>${esc(t("panel.slot"))}</th><th>${esc(t("panel.role"))}</th>
      <th>${esc(t("panel.qty"))}</th><th>${esc(tu("panel.length"))}</th>
      <th>${esc(t("panel.item"))}</th><th>${esc(t("panel.cost"))}</th></tr>`;
  for (const part of preview.parts || []) {
    html += `<tr data-slot="${esc(part.slot_key)}">
      <td><span class="sku">${esc(part.slot_key)}</span></td>
      <td>${esc(roleWord(part.role))}</td>
      <td class="num">${esc(String(part.qty))}</td>
      <td class="num">${part.length_mm ? esc(fmt(part.length_mm)) : ""}</td>
      <td><span class="sku">${esc(part.sku)}</span></td>
      <td class="num">${esc(money(part.total_cents))}</td></tr>`;
  }
  html += `</table><div id="model-preview-total">${
    sentence("panel.total", { total: money(preview.total_cents) })}</div></div>`;
  if ((preview.unsupplied || []).length) {
    // ABOVE nothing and BELOW the table on purpose: it is a gap in what was just
    // priced, and a panel one part short must not read as complete
    html += `<div class="panel supply-problems" id="model-unsupplied">
      <h3>${esc(t("panel.unsupplied_title"))}</h3>
      <div class="meta">${esc(t("panel.unsupplied_hint"))}</div>
      <ul>${preview.unsupplied.map((line) =>
        `<li><span class="sku">${esc(line.slot_key)}</span> — ${esc(roleWord(line.role))}</li>`)
        .join("")}</ul></div>`;
  }
  return html;
}
