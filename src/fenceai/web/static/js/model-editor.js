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
  el, field, loadCatalogProducts, option, skuSelect, updateAdvancedUi,
} from "./builder-ui.js";
import { loadModelListing, refreshModelListing } from "./fence-models.js";
import { currentLocale, t } from "./i18n.js";
import { renderImpactReport } from "./impact.js";
import { emit, on } from "./state.js";
import { fmt, inputStep, roleWord, toDisplayValue, toMm, tu, unitParams } from "./units.js";

// --- the closed vocabularies, read from fencemodel/model.py -------------------
const ROLES = ["post", "cap", "concrete", "rail", "screw", "infill", "spacer"];
const LENGTH_RULES = ["clear_between_posts", "centre_to_centre", "overlap", "panel_height",
  // the one rule that reads the "starts at" / "ends at" selects below; under any
  // other rule the schema now refuses a member that sets them
  "between_frame"];
const PLACEMENT_KINDS = ["distributed", "from_bottom", "from_top", "fraction"];
const JUSTIFICATIONS = ["start", "end", "center", "spread_to_fit"];
// `trim_last` and `extension_clip` are schema-expressible and NOT built
// (`model.py::_unsupported_features`: fit_pattern treats both exactly as
// `truncate`, which is a different BOM). Offering them would author a model the
// publish gate then refuses, so the editor offers what the resolver honours —
// and an existing document carrying one still shows it, rather than being
// silently rewritten to something it does not say.
const EXCESS = ["truncate", "space"];
const BASES = [
  "per_member_crossing", "per_member", "per_end_member",
  "per_gap", "per_frame_member", "per_panel",
];
const APPROVALS = ["auto", "suggest_only"];
const GRADES = ["residential", "commercial", "industrial"];
// `numeric` is schema-expressible and unbuilt, for the same reason `trim_last`
// is: nothing reads `Axis.kind`, and resolution answers every axis out of its
// declared `values`. W4 added the `_unsupported_features` entry that refuses it
// — this list is the other half of that change.
const AXIS_KINDS = ["enum"];
// Knowledge params a count may defer to. The point of `count_param` is that
// rail count stays DEFEASIBLE knowledge — a company rule may still win it — so
// the field is offered as a param name and not as an authored integer.
const COUNT_PARAMS = ["rails_per_span", "screws_per_span"];

export const SWATCH_RE = /^#[0-9a-fA-F]{6}$/;

const PREVIEW_DEBOUNCE_MS = 250;
const DEFAULT_HEIGHT_MM = 1800;
const DEFAULT_WIDTH_MM = 2500;

// --- pure shapes (no DOM, no state): what a fresh row of each kind is --------

export function blankModel(id) {
  return {
    id, version: 1, name_i18n: {}, grade: "residential", status: "draft",
    height_support: { kind: "continuous", min_mm: 0, max_mm: 10000 },
    layout_policy: [], option_axes: [],
    default_spec: { frame: [], infill: null, fixings: [] },
    variants: [],
  };
}

export function defaultEligibility() {
  return { members: [] };
}

// The ONE place a member is built, called by the "+ Add product" button and by
// the test that judges its shape — a second literal in either would let them
// agree with each other while disagreeing with the schema.
//
// `kind` is not decoration: `Eligibility.members` is a discriminated union, so
// a member without it is a 422 `union_tag_not_found` on the whole document, and
// the author is told only "the action failed".
export function defaultEligibleMember(sku, priority = 1) {
  return { kind: "catalog_item", sku: sku || "", priority, approval: "auto" };
}

export function defaultRequirement(role) {
  return {
    role, qty: 1, length_rule: null, overlap_mm: 0,
    option_axis: null, sku_by_option: {}, eligibility: defaultEligibility(),
  };
}

export function defaultPlacement(kind) {
  switch (kind) {
    case "from_bottom": return { kind, offset_mm: 0 };
    case "from_top": return { kind, offset_mm: 0 };
    case "fraction": return { kind, permille: 500 };
    default:
      return { kind: "distributed", count: 2, count_param: null,
               bottom_inset_mm: 0, top_inset_mm: 0 };
  }
}

export function defaultSlot(key) {
  return {
    key, orientation: "horizontal", placement: defaultPlacement("distributed"),
    requirement: defaultRequirement("rail"),
  };
}

export function defaultMember(key) {
  return {
    key, width_mm: 100, thickness_mm: 0, face_offset_mm: 0, gap_after_mm: 20,
    base_ref: null, top_ref: null,
    requirement: { ...defaultRequirement("infill"), length_rule: "panel_height" },
  };
}

export function defaultInfill() {
  return {
    orientation: "vertical", pattern: [defaultMember("slat")],
    justification: "spread_to_fit", excess: "space", edge_margin_mm: 0,
    supply: "components",
  };
}

export function defaultFixing(key) {
  return {
    key, basis: "per_panel", qty_per_basis: 1, qty_param: null,
    requirement: defaultRequirement("screw"),
  };
}

export function defaultAxis(key) {
  return { key, label_i18n: {}, kind: "enum", values: [], available_when: null };
}

// A NEW variant starts from a condition that is already valid AST and already
// says something ("panels 1800 and taller"), because the alternative — an empty
// box — makes the first thing an author meets a 422 about a discriminator.
export function defaultVariant() {
  return {
    condition: {
      op: "cmp", cmp: ">=",
      left: { op: "field", path: "panel.height_mm" },
      right: { op: "lit", value: 1800 },
    },
    spec: { frame: [], infill: null, fixings: [] },
  };
}

// A published version is NEVER mutated: editing one opens a COPY, and the
// session that holds it carries no version, so the first save POSTs and the
// SERVER assigns the next free one. The copy keeps the source's `version`
// field — it is what the document said, the editor does not get to invent a
// number, and nothing sends this one anywhere as an instruction.
//
// DEEP, and that is the load-bearing half: a shallow copy shares `default_spec`
// with the document the library handed over, so the first keystroke would
// rewrite the panel an accepted quote was priced against — in memory, where
// nothing reports it.
export function draftCopyOf(model) {
  return { ...structuredClone(model), status: "draft" };
}

export function duplicateOf(model, newId) {
  return { ...structuredClone(model), id: newId, version: 1, status: "draft" };
}

// The spec the row editors are pointed at: the default panel, or one variant's.
export function specOf(model, index) {
  return index < 0 ? model.default_spec : model.variants[index]?.spec;
}

// --- module state ------------------------------------------------------------

let listing = [];
let session = null;      // { model, version | null, invalid, saveError, published }
let specIndex = -1;      // -1 = default_spec, else variants[specIndex].spec
let advancedOpen = false;
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

const money = (cents) => `€${((cents || 0) / 100).toFixed(2)}`;

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
  document.getElementById("btn-model-new").addEventListener("click", () => {
    openSession(blankModel(freeId("M-NEW")), null, { isNew: true });
  });
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

// Ids are identifiers, never prose — no locale key. Uniqueness is not cosmetic:
// a POST reusing an existing id does not create a model, it opens the NEXT
// VERSION of that one, so duplicating twice would quietly turn the second copy
// into v2 of the first. Takes the listing rather than reading it, so the rule
// can be tested without a library.
export function freeId(base, rows = listing) {
  const taken = new Set((rows || []).map((r) => r.id));
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

function sessionRef() {
  return session ? `${session.model.id}@v${session.version ?? "?"}` : "";
}

// `isNew` is the session's INTENT, and it is not derivable from `version`:
// "New", "Duplicate" and "Edit a published version" all start without one, but
// only the first two mean to create a model id that does not exist yet.
function openSession(model, version, { isNew = false } = {}) {
  session = { model, version, isNew, invalid: null, saveError: null, dirty: false };
  specIndex = -1;
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
  if (doc) openSession(duplicateOf(doc, freeId(`${row.id}-COPY`)), null,
                       { isNew: true });
}

// --- saving, publishing, retiring -------------------------------------------

// An edit re-prices, and that is ALL it does. Nothing is written until the
// author asks — see `refreshPreview`, which prices the document in memory.
function scheduleRepreview() {
  clearTimeout(previewPending);
  previewPending = setTimeout(refreshPreview, PREVIEW_DEBOUNCE_MS);
}

// The id already in the library, if the one being typed collides with it.
//
// Only a session that means to create a NEW model can collide. A draft copy of
// a published version also carries no version number, and its id is the
// existing model's ON PURPOSE — that is what makes the save land as that
// model's next version. Reading "no version yet" as "must be new" refuses
// exactly the save that "Edit" exists to make.
// True only while this session could still choose its id: it means to create a
// model AND has not yet been saved under one. After the first save the id is
// the model's own, so it is in the listing BY DEFINITION and asking again would
// refuse every later save of the thing just created.
export const canChooseId = (s) => !!s?.isNew && s.version === null;

// The id a save would collide with, or null. Pure, and exported, because the
// four session kinds are easy to collapse into a wrong rule: "no version yet"
// reads like "new", and a draft copy of a published version has no version
// either — refusing THAT is refusing the save "Edit" exists to make.
export function idCollision(session, rows) {
  if (!canChooseId(session)) return null;
  const id = (session.model?.id || "").trim();
  return (rows || []).some((row) => row.id === id) ? id : null;
}

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
  renderFrame();
  renderInfill();
  renderFixings();
  renderAxes();
}

// --- field builders (shared by every row list below) -------------------------
//
// Each writes ONE field of the live document and then debounces a save, and
// each carries `data-f="<field name>"`. That attribute is not decoration: the
// row lists are generated, so a test (or a person reading the DOM) has no other
// stable way to name "the length rule of the first frame slot" — and positional
// selectors are exactly the kind that keep passing after a field moves.

// `length` means the value is millimetres at rest and shown in the display
// unit. The conversion happens here and nowhere else, so a width typed in cm is
// stored as mm and reads back as the same width.
function num(obj, key, labelKey, { length = false, min = null, onCommit = null } = {}) {
  const raw = obj[key] ?? "";
  const attrs = { type: "number", "data-f": key, step: length ? inputStep() : "1",
                  value: raw === "" || !length ? raw : toDisplayValue(raw) };
  // `min` is a number in the FIELD, so on a length it crosses the same boundary
  // the value does — a raw `min="1"` means 1 mm in mm and 10 mm in cm.
  if (min !== null) attrs.min = length ? toDisplayValue(min) : min;
  const i = el("input", attrs);
  i.addEventListener("change", () => {
    obj[key] = length ? (toMm(i.value) ?? 0) : Math.round(i.valueAsNumber || 0);
    (onCommit || touch)();
  });
  return field(labelKey, i);
}

function text(obj, key, labelKey, { size = 16, ltr = false, nullable = false } = {}) {
  const i = el("input", { type: "text", "data-f": key, dir: ltr ? "ltr" : "auto", size,
                          class: ltr ? "sku" : null, value: obj[key] ?? "" });
  i.addEventListener("input", () => {
    const v = i.value.trim();
    obj[key] = nullable && !v ? null : i.value;
    touch();
  });
  return field(labelKey, i);
}

function choice(obj, key, values, labelFor, labelKey, { rerender = false, nullKey = null } = {}) {
  const s = el("select", { "data-f": key });
  if (nullKey) s.appendChild(option("", t(nullKey), obj[key] === null || obj[key] === undefined));
  for (const v of values) s.appendChild(option(v, labelFor(v), obj[key] === v));
  // a value the resolver does not honour is never OFFERED, but a document that
  // already carries one must not be silently rewritten by opening the editor
  if (obj[key] && !values.includes(obj[key]))
    s.appendChild(option(obj[key], obj[key], true));
  s.addEventListener("change", () => {
    obj[key] = s.value === "" ? null : s.value;
    touch({ rerender });
  });
  return field(labelKey, s);
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

function subhead(titleKey, addKey, onAdd, addId = null) {
  const head = el("div", { class: "builder-head" },
    el("b", { text: t(titleKey) }));
  if (addKey) {
    const b = el("button", { type: "button", id: addId, text: t(addKey) });
    b.addEventListener("click", onAdd);
    head.appendChild(b);
  }
  return head;
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
  if (!canChooseId()) idInput.disabled = true;
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

  row.appendChild(choice(session.model, "grade", GRADES,
    (g) => t("model.grade." + g), "model.grade"));
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

  // A variant's condition is an `Expr` AST. A general AST editor is its own
  // design round, and half of one is worse than none — so it gets exactly what
  // the knowledge tab gives rule conditions: a JSON box and a hint that says so.
  if (specIndex >= 0) {
    const variant = variants[specIndex];
    const hint = el("div", { class: "meta", text: t("model.variant_conditions_hint") });
    const ta = el("textarea", { id: "model-variant-condition", dir: "ltr", rows: 3, cols: 60 });
    ta.value = JSON.stringify(variant.condition ?? null, null, 2);
    ta.addEventListener("change", () => {
      try {
        variant.condition = JSON.parse(ta.value);
        ta.classList.remove("invalid");
        touch();
      } catch {
        // the box keeps the user's text; nothing is saved from it until it parses
        ta.classList.add("invalid");
      }
    });
    host.append(hint, ta);
  }
}

// --- frame slots -------------------------------------------------------------

async function renderFrame() {
  // the catalog is awaited BEFORE the host is cleared, so two renders racing
  // each other rebuild the list rather than appending a second copy of it
  const products = await loadCatalogProducts();
  const host = document.getElementById("model-frame");
  const spec = specOf(session?.model, specIndex);
  host.innerHTML = "";
  if (!spec) return;
  spec.frame ??= [];
  host.appendChild(subhead("model.frame", "model.add_slot", () => {
    spec.frame.push(defaultSlot(`slot${spec.frame.length + 1}`));
    touch({ rerender: true });
  }, "btn-model-add-slot"));
  spec.frame.forEach((slot, idx) => {
    // the slot and the requirement it carries are ONE thing to read and to
    // address, so they share a group rather than sitting as loose siblings
    const group = el("div", { class: "builder-group", "data-slot-row": String(idx) });
    const row = el("div", { class: "builder-row" });
    row.appendChild(text(slot, "key", "model.key", { size: 10, ltr: true }));
    row.appendChild(choice(slot, "orientation", ["horizontal", "vertical"],
      (v) => t("model.orientation." + v), "model.orientation"));

    const kindSel = el("select", { class: "builder-kind" });
    for (const k of PLACEMENT_KINDS)
      kindSel.appendChild(option(k, t("model.placement." + k), slot.placement?.kind === k));
    kindSel.addEventListener("change", () => {
      slot.placement = defaultPlacement(kindSel.value);
      touch({ rerender: true });
    });
    row.appendChild(field("model.placement", kindSel));

    const p = slot.placement || {};
    if (p.kind === "distributed") {
      row.appendChild(num(p, "count", "model.count", { min: 0 }));
      // a knowledge PARAM, not an authored integer: rail count ladders with
      // height and a company rule must still be able to win it
      row.appendChild(choice(p, "count_param", COUNT_PARAMS,
        (v) => tu("action.param." + v), "model.count_param",
        { nullKey: "model.count_param_none" }));
      row.appendChild(num(p, "bottom_inset_mm", "model.bottom_inset_mm", { length: true }));
      row.appendChild(num(p, "top_inset_mm", "model.top_inset_mm", { length: true }));
    } else if (p.kind === "fraction") {
      row.appendChild(num(p, "permille", "model.permille", { min: 0 }));
    } else if (p.kind) {
      row.appendChild(num(p, "offset_mm", "model.offset_mm", { length: true }));
    }
    row.appendChild(removeButton(() => {
      spec.frame.splice(idx, 1);
      touch({ rerender: true });
    }));
    group.append(row, requirementRows(slot.requirement, products));
    host.appendChild(group);
  });
}

// --- infill ------------------------------------------------------------------

async function renderInfill() {
  const products = await loadCatalogProducts();
  const host = document.getElementById("model-infill");
  const spec = specOf(session?.model, specIndex);
  host.innerHTML = "";
  if (!spec) return;
  const has = !!spec.infill;
  const head = subhead("model.infill", null);
  const toggle = el("button", { type: "button", id: "btn-model-toggle-infill",
                                text: t(has ? "model.remove_infill" : "model.add_infill") });
  toggle.addEventListener("click", () => {
    spec.infill = has ? null : defaultInfill();
    touch({ rerender: true });
  });
  head.appendChild(toggle);
  host.appendChild(head);
  if (!has) return;

  const infill = spec.infill;
  const row = el("div", { class: "builder-row" });
  row.appendChild(choice(infill, "orientation", ["vertical", "horizontal"],
    (v) => t("model.orientation." + v), "model.orientation"));
  row.appendChild(choice(infill, "justification", JUSTIFICATIONS,
    (v) => t("model.justification." + v), "model.justification"));
  row.appendChild(choice(infill, "excess", EXCESS,
    (v) => t("model.excess." + v), "model.excess"));
  row.appendChild(num(infill, "edge_margin_mm", "model.edge_margin_mm", { length: true }));
  host.appendChild(row);

  infill.pattern ??= [];
  host.appendChild(subhead("model.pattern", "model.add_member", () => {
    infill.pattern.push(defaultMember(`member${infill.pattern.length + 1}`));
    touch({ rerender: true });
  }, "btn-model-add-member"));
  const frameKeys = (spec.frame || []).map((s) => s.key);
  infill.pattern.forEach((member, idx) => {
    const group = el("div", { class: "builder-group", "data-member-row": String(idx) });
    const mrow = el("div", { class: "builder-row" });
    mrow.appendChild(text(member, "key", "model.key", { size: 10, ltr: true }));
    mrow.appendChild(num(member, "width_mm", "model.width_mm", { length: true, min: 1 }));
    // NO min: a negative gap is an OVERLAP, and board-on-board and shadowbox are
    // exactly that. `validate_model` bounds width + gap (the member's net
    // advance) instead, which is the quantity that must stay positive.
    mrow.appendChild(num(member, "gap_after_mm", "model.gap_after_mm", { length: true }));
    mrow.appendChild(num(member, "face_offset_mm", "model.face_offset_mm", { length: true }));
    mrow.appendChild(num(member, "thickness_mm", "model.thickness_mm", { length: true, min: 0 }));
    mrow.appendChild(choice(member, "base_ref", frameKeys, (k) => k, "model.base_ref",
      { nullKey: "model.ref_none" }));
    mrow.appendChild(choice(member, "top_ref", frameKeys, (k) => k, "model.top_ref",
      { nullKey: "model.ref_none" }));
    mrow.appendChild(removeButton(() => {
      infill.pattern.splice(idx, 1);
      touch({ rerender: true });
    }));
    group.append(mrow,
      el("div", { class: "meta", text: t("model.gap_after_hint") }),
      requirementRows(member.requirement, products));
    host.appendChild(group);
  });
}

// --- fixings -----------------------------------------------------------------

async function renderFixings() {
  const products = await loadCatalogProducts();
  const host = document.getElementById("model-fixings");
  const spec = specOf(session?.model, specIndex);
  host.innerHTML = "";
  if (!spec) return;
  spec.fixings ??= [];
  host.appendChild(subhead("model.fixings", "model.add_fixing", () => {
    spec.fixings.push(defaultFixing(`fix${spec.fixings.length + 1}`));
    touch({ rerender: true });
  }, "btn-model-add-fixing"));
  spec.fixings.forEach((fix, idx) => {
    const group = el("div", { class: "builder-group", "data-fixing-row": String(idx) });
    const row = el("div", { class: "builder-row" });
    row.appendChild(text(fix, "key", "model.key", { size: 10, ltr: true }));
    row.appendChild(choice(fix, "basis", BASES, (b) => t("model.basis." + b), "model.basis"));
    row.appendChild(num(fix, "qty_per_basis", "model.qty_per_basis", { min: 0 }));
    row.appendChild(choice(fix, "qty_param", COUNT_PARAMS,
      (v) => tu("action.param." + v), "model.qty_param", { nullKey: "model.count_param_none" }));
    row.appendChild(removeButton(() => {
      spec.fixings.splice(idx, 1);
      touch({ rerender: true });
    }));
    group.append(row, requirementRows(fix.requirement, products));
    host.appendChild(group);
  });
}

// --- a requirement + its eligibility -----------------------------------------

function requirementRows(req, products) {
  const box = el("div", { class: "builder-sub" });
  if (!req) return box;
  req.eligibility ??= defaultEligibility();
  req.eligibility.members ??= [];

  const row = el("div", { class: "builder-row" });
  row.appendChild(choice(req, "role", ROLES, roleWord, "model.role"));
  row.appendChild(num(req, "qty", "model.qty", { min: 0 }));
  row.appendChild(choice(req, "length_rule", LENGTH_RULES,
    (r) => t("model.length_rule." + r), "model.length_rule",
    { rerender: true, nullKey: "model.length_rule.none" }));
  if (req.length_rule === "overlap")
    row.appendChild(num(req, "overlap_mm", "model.overlap_mm", { length: true }));
  const axes = (session.model.option_axes || []).map((a) => a.key);
  row.appendChild(choice(req, "option_axis", axes, (k) => k, "model.option_axis",
    { rerender: true, nullKey: "model.option_axis.none" }));
  box.appendChild(row);

  // eligibility: an ORDERED list, because `priority` is the company's stated
  // preference and the order it is read in is part of the answer
  const eligibility = el("div", { class: "builder-row" });
  eligibility.appendChild(el("span", { class: "meta", text: t("model.eligibility") }));
  const add = el("button", { type: "button", "data-act": "add-eligible",
                             text: t("model.add_eligible") });
  add.addEventListener("click", () => {
    req.eligibility.members.push(defaultEligibleMember(
      Object.keys(products).sort()[0], req.eligibility.members.length + 1));
    touch({ rerender: true });
  });
  eligibility.appendChild(add);
  box.appendChild(eligibility);

  req.eligibility.members.forEach((member, idx) => {
    const mrow = el("div", { class: "builder-row", "data-eligible-row": String(idx) });
    member.kind ??= "catalog_item";
    const picker = skuSelect(products, member.sku, false,
      (v) => { member.sku = v; touch({ rerender: true }); });
    picker.dataset.f = "sku";
    mrow.appendChild(field("knowledge.builder.sku", picker));
    mrow.appendChild(num(member, "priority", "model.priority", { min: 1 }));
    mrow.appendChild(choice(member, "approval", APPROVALS,
      (a) => t("model.approval." + a), "model.approval"));
    mrow.appendChild(removeButton(() => {
      req.eligibility.members.splice(idx, 1);
      touch({ rerender: true });
    }));
    box.appendChild(mrow);
  });

  // A slot binds to AT MOST ONE axis, and then names a SKU per axis value. The
  // SKU must be one of the eligible members — anything else is a product the
  // slot was never allowed to use, and `validate_model` says so.
  if (req.option_axis) {
    const axis = (session.model.option_axes || []).find((a) => a.key === req.option_axis);
    req.sku_by_option ??= {};
    for (const value of axis?.values || []) {
      const vrow = el("div", { class: "builder-row" });
      vrow.appendChild(el("span", { class: "meta",
        text: t("model.sku_for_option", { option: valueLabel(value) }) }));
      const skus = req.eligibility.members.map((m) => m.sku).filter(Boolean);
      const sel = el("select");
      sel.appendChild(option("", t("model.ref_none"), !req.sku_by_option[value.key]));
      for (const sku of skus)
        sel.appendChild(option(sku, sku, req.sku_by_option[value.key] === sku));
      sel.addEventListener("change", () => {
        if (sel.value) req.sku_by_option[value.key] = sel.value;
        else delete req.sku_by_option[value.key];
        touch();
      });
      vrow.appendChild(sel);
      box.appendChild(vrow);
    }
  }
  return box;
}

const valueLabel = (value) =>
  value.label_i18n?.[currentLocale()] || value.label_i18n?.en || value.key;

// --- option axes -------------------------------------------------------------

function renderAxes() {
  const host = document.getElementById("model-axes");
  host.innerHTML = "";
  session.model.option_axes ??= [];
  const axes = session.model.option_axes;
  host.appendChild(subhead("model.axes", "model.add_axis", () => {
    axes.push(defaultAxis(`axis${axes.length + 1}`));
    touch({ rerender: true });
  }, "btn-model-add-axis"));
  axes.forEach((axis, idx) => {
    const row = el("div", { class: "builder-row", "data-axis-row": String(idx) });
    row.appendChild(text(axis, "key", "model.key", { size: 12, ltr: true }));
    row.appendChild(i18nLabelField(axis, "model.label"));
    row.appendChild(choice(axis, "kind", AXIS_KINDS,
      (k) => t("model.axis_kind." + k), "model.axis_kind"));
    const add = el("button", { type: "button", "data-act": "add-axis-value",
                               text: t("model.add_axis_value") });
    add.addEventListener("click", () => {
      axis.values ??= [];
      axis.values.push({ key: `v${axis.values.length + 1}`, label_i18n: {}, swatch: null });
      touch({ rerender: true });
    });
    row.appendChild(add);
    row.appendChild(removeButton(() => {
      axes.splice(idx, 1);
      touch({ rerender: true });
    }));
    host.appendChild(row);
    for (const [vIdx, value] of (axis.values || []).entries()) {
      const vrow = el("div", { class: "builder-row", "data-axis-value-row": String(vIdx) });
      vrow.appendChild(text(value, "key", "model.key", { size: 10, ltr: true }));
      vrow.appendChild(i18nLabelField(value, "model.label"));
      vrow.appendChild(swatchField(value));
      vrow.appendChild(removeButton(() => {
        axis.values.splice(vIdx, 1);
        touch({ rerender: true });
      }));
      host.appendChild(vrow);
    }
  });
}

function i18nLabelField(obj, labelKey) {
  const i = el("input", { type: "text", dir: "auto", size: 16,
                          value: obj.label_i18n?.[currentLocale()] || "" });
  i.addEventListener("input", () => {
    obj.label_i18n = { ...obj.label_i18n, [currentLocale()]: i.value };
    touch();
  });
  return field(labelKey, i);
}

// A swatch reaches a CSS colour, which is a STYLE context: esc() would not make
// a bad value safe there. The backend validates `^#[0-9a-fA-F]{6}$` at model
// load and that check is NOT weakened — the field simply refuses anything else,
// so the author is told at the keystroke rather than at the publish gate.
function swatchField(value) {
  const wrap = el("span", { class: "builder-field" });
  const chip = el("span", { class: "swatch-chip" });
  const i = el("input", { type: "text", dir: "ltr", class: "sku", size: 9,
                          placeholder: "#rrggbb", value: value.swatch || "" });
  const paint = () => {
    // only ever a string that MATCHED the pattern reaches the style property
    chip.style.background = SWATCH_RE.test(value.swatch || "") ? value.swatch : "transparent";
  };
  i.addEventListener("input", () => {
    const v = i.value.trim();
    const ok = v === "" || SWATCH_RE.test(v);
    i.classList.toggle("invalid", !ok);
    if (!ok) return;                 // a half-typed "#ab" is not a colour yet
    value.swatch = v === "" ? null : v;
    paint();
    touch();
  });
  paint();
  wrap.append(el("span", { class: "meta", text: t("model.swatch") }), i, chip);
  return wrap;
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
