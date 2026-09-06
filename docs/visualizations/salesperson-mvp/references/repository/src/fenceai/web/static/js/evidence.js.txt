// The evidence viewer — resolves a `SourceRef` (core/gaps.py: `{ id, belongs_to }`)
// into a page crop, the quoted text beside it, and an honest provenance label.
// Frontend design §3.
//
// THE ONE THING THIS MODULE MUST NEVER DO is let a crop imply a verification it
// has not had. A source reference proves where the system looked; it does not
// prove the source says what was written down (source-refs-design.md §6). So
// every record renders a provenance STATE — `extracted`, `checked`, or
// `derived` today, with `verified` reserved as a named seam for a review field
// no Discovery response carries yet — and the state comes from what the record
// actually says, never from the mere presence of a picture.
//
// FIXTURE-BACKED, deliberately. `POST /api/source-refs:batch` resolves against
// a vendored copy of fence-rag's design fixture, not a live Discovery API
// (`fenceai/knowledge/discovery_stub.py`), and that fixture-backed API has no
// pixel service behind it — poppler-windowed crop rendering is Discovery's own
// work (source-refs-design.md §4), not built in this repository. So
// `image.status: "available"` here still means "no picture rendered by this
// build" rather than "here is a picture" — an honest degrade, not an error,
// and never a broken `<img>` tag guessing at a URL this backend cannot serve.
//
// DOM ownership: this module owns `#evidence-viewer` alone, exactly like
// `assembly.js` owns `#assembly-drawer`. It reads `.evidence-link[data-evidence-id]`
// attributes anywhere in the document — a shared, documented contract any
// renderer may emit (the same relationship `data-i18n` has to `i18n.js`), not a
// reach into another module's owned subtree — so that opening one citation can
// resolve every citation currently on screen in ONE batch call rather than one
// request per click (frontend design §3: "ask for the batch call now, not
// later").
//
// Everything document-derived that reaches `innerHTML` — quotes, titles,
// manufacturer names, reasons, ids — goes through `esc()`. Document content is
// untrusted data by contract, and that now includes everything the Knowledge
// Platform sends.

import { apiSend, esc } from "./api.js";
import { t } from "./i18n.js";
import { localizedByCode } from "./warnings.js";

const HASH_PREFIX = "evidence=";

// id -> resolved record, or `null` for a confirmed miss (not yet resolved ids
// are simply absent from the map).
const cache = new Map();

/** Every citation link currently rendered anywhere on the page. Read-only scan
 *  for a shared attribute contract, not a lookup into any one module's state —
 *  see the module header. Exported so the node suite can prove the "one batch
 *  call" behavior against a synthetic DOM without exercising the rest of the
 *  module's real `document` use. */
export function idsOnScreen() {
  const ids = new Set();
  for (const el of document.querySelectorAll(".evidence-link[data-evidence-id]"))
    if (el.dataset.evidenceId) ids.add(el.dataset.evidenceId);
  return [...ids];
}

/** Resolve every id not already cached, in ONE batch call — frontend design
 *  §3: "ask for the batch call now, not later". Failures degrade to an honest
 *  "not found" per id rather than losing the whole batch, the same shape the
 *  backend already returns for an id outside the fixture. Exported: pure
 *  aside from `fetch` (via `apiSend`), so the node suite can count calls
 *  directly without a DOM at all. Returns the ids actually fetched, so a
 *  caller — or a test — can tell a cache hit from a real request. */
export async function resolveIds(ids) {
  const missing = [...new Set(ids)].filter((id) => !cache.has(id));
  if (!missing.length) return [];
  try {
    const body = await apiSend(
      "POST", "/api/source-refs:batch", { ids: missing }, { quiet: true },
    );
    for (const rec of body.resolved) cache.set(rec.source_ref_id, rec);
    for (const id of body.not_found) cache.set(id, null);
  } catch {
    for (const id of missing) if (!cache.has(id)) cache.set(id, null);
  }
  return missing;
}

// ---------------------------------------------------------------------------
// Provenance — the honesty channel §3 exists for.
// ---------------------------------------------------------------------------

/** `extracted` | `checked` | `verified` | `derived`. `verified` is a named
 *  seam, not dead code: nothing in today's Discovery response can produce it
 *  (source-refs-design.md's own note on record #4 — "there is not one human
 *  reading in this corpus"), and inventing a path to it here would be exactly
 *  the false confidence §3 forbids. The vocabulary exists in both locale
 *  bundles so a future review field needs no new translation work, only a
 *  new branch below. */
function provenanceState(rec) {
  if (rec.kind === "derived") return "derived";
  if (rec.kind === "visual_reading" && rec.reading?.reader_kind === "human") return "checked";
  return "extracted";
}

function provenanceHtml(rec) {
  const state = provenanceState(rec);
  return `<div class="evidence-provenance">
    <span class="tag evidence-state-${esc(state)}">${esc(t("evidence.provenance." + state))}</span>
    <div class="meta">${esc(t("evidence.provenance_hint"))}</div>
  </div>`;
}

// ---------------------------------------------------------------------------
// The image — a picture, or an honest reason there is not one.
// ---------------------------------------------------------------------------

function imageHtml(rec) {
  const img = rec.image || {};
  if (img.status === "not_applicable") {
    return `<div class="evidence-no-image meta">${esc(t("evidence.image_not_applicable"))}`
      + (img.reason ? ` — ${esc(img.reason)}` : "") + `</div>`;
  }
  if (img.status === "source_not_fetched" || img.status === "failed") {
    return `<div class="evidence-no-image warning">${esc(t("evidence.image_" + img.status))}`
      + (img.reason ? ` — ${esc(img.reason)}` : "") + `</div>`;
  }
  // status === "available": the record HAS a picture on the Discovery side;
  // this build simply does not serve pixels yet. Say so plainly, and still
  // surface the real metadata the fixture carries — dimensions and dpi are
  // exactly what a component built against this file should get right
  // (source-refs-design.md §4.1's dpi trap).
  const target = img.crop || img.page;
  const dims = target
    ? `<div class="meta num">${esc(target.width_px)}×${esc(target.height_px)}px @ ${esc(target.dpi)}dpi</div>`
    : "";
  const located = img.crop && img.crop.bbox_px
    ? "" : `<div class="meta">${esc(t("evidence.no_located_region"))}</div>`;
  return `<div class="evidence-crop-placeholder">
    <div class="evidence-crop-box" aria-hidden="true"></div>
    <div class="meta">${esc(t("evidence.image_unavailable_stub"))}</div>
    ${dims}${located}
  </div>`;
}

// ---------------------------------------------------------------------------
// The quoted text, or an honest reason there is none.
// ---------------------------------------------------------------------------

function textHtml(rec) {
  const txt = rec.text || {};
  if (txt.quote) {
    const source = txt.text_source
      ? `<div class="meta">${esc(t("evidence.text_source"))} <bdi class="sku">${esc(txt.text_source)}</bdi>`
        + (txt.ocr_confidence != null ? ` (<bdi class="num">${esc(txt.ocr_confidence)}%</bdi>)` : "") + `</div>`
      : "";
    return `<div class="evidence-quote">
      <q class="verbatim" lang="en" dir="ltr"><bdi>${esc(txt.quote)}</bdi></q>
      ${source}
    </div>`;
  }
  return `<div class="evidence-no-quote meta">${esc(t("evidence.no_quote"))}`
    + (txt.quote_absent_reason ? ` — ${esc(txt.quote_absent_reason)}` : "") + `</div>`;
}

// ---------------------------------------------------------------------------
// A visual reading — a named reader, not a quote. Must not look like one.
// ---------------------------------------------------------------------------

function readingHtml(rec) {
  const r = rec.reading;
  if (!r) return "";
  const box = r.cell_bbox_px
    ? ""
    : `<div class="meta">${esc(t("evidence.no_cell_box"))}`
      + (r.cell_bbox_absent_reason ? ` — ${esc(r.cell_bbox_absent_reason)}` : "") + `</div>`;
  return `<div class="evidence-reading">
    <div class="meta">${esc(t("evidence.read_by"))} <bdi class="sku">${esc(r.reader)}</bdi>
      (${esc(t("evidence.reader_kind." + (r.reader_kind || "agent")))})</div>
    <div class="evidence-reading-value">
      <span class="meta">${esc(r.row_label || "")} / ${esc(r.col_label || "")}</span>
      <bdi class="num">${esc(r.value_raw || "")}</bdi>
    </div>
    ${box}
  </div>`;
}

// ---------------------------------------------------------------------------
// The document — or, for `derived`, the honest absence of one.
// ---------------------------------------------------------------------------

function statusHtml(status) {
  if (!status) return "";
  const superseded = (status.superseded_by || []).length
    ? `<div class="meta">${esc(t("evidence.superseded_by_count", { n: status.superseded_by.length }))}</div>`
    : "";
  return `<div class="evidence-status">
    <span class="tag evidence-status-${esc(status.version_status)}">${
      esc(t("evidence.status." + status.version_status))}</span>
    ${status.version_status_basis ? `<div class="meta">${esc(status.version_status_basis)}</div>` : ""}
    ${status.expiration_date ? `<div class="meta">${esc(t("evidence.expires"))} <bdi class="num">${esc(status.expiration_date)}</bdi></div>` : ""}
    ${superseded}
  </div>`;
}

function documentHtml(rec) {
  const doc = rec.document;
  if (!doc) {
    const d = rec.derived_from;
    return `<div class="evidence-document meta">${esc(t("evidence.no_document"))}`
      + (d ? `<div><bdi class="sku">${esc(d.dataset_path)}</bdi></div>` : "") + `</div>`;
  }
  // `doc_type` is Discovery's own enum word (`cut_sheet`, `hvhz_noa`, ...), not
  // yet in either locale bundle — shown as an identifier (`.sku` + `<bdi>`),
  // the same treatment an untranslated SKU or opaque id gets, rather than
  // inventing a translation for a vocabulary this side does not own.
  return `<div class="evidence-document">
    <div class="evidence-doc-title">${esc(doc.title)}</div>
    <div class="meta">${esc(doc.manufacturer)} · <bdi class="sku">${esc(doc.doc_type)}</bdi></div>
    <div class="meta"><bdi class="sku">${esc(doc.source_path)}</bdi></div>
    ${statusHtml(doc.status)}
  </div>`;
}

// ---------------------------------------------------------------------------
// Warnings — a code + params the Discovery side authors, parameterised and
// therefore translatable (source-refs-design.md §3.2), unlike a quoted
// document warning. Reuses `warnings.js`'s localizer under its own prefix so
// an unmapped code falls back to itself rather than to invented English.
// ---------------------------------------------------------------------------

function warningsHtml(rec) {
  const list = rec.warnings || [];
  if (!list.length) return "";
  return `<div class="evidence-warnings">`
    + list.map((w) => `<div class="meta">${localizedByCode("sourcewarning", w.code, w.params, w.code)}</div>`).join("")
    + `</div>`;
}

// ---------------------------------------------------------------------------
// Assembly + the modal shell.
// ---------------------------------------------------------------------------

/** One resolved record's body. Exported and pure — no DOM, no fetch — so the
 *  node suite can render every fixture kind directly, the same way
 *  `gaps.js`'s `gapRowHtml` and `doc-warnings.js`'s `quotedWarningHtml` are
 *  tested. */
export function recordHtml(rec) {
  return `<div class="evidence-body">
    ${provenanceHtml(rec)}
    ${imageHtml(rec)}
    ${textHtml(rec)}
    ${readingHtml(rec)}
    ${documentHtml(rec)}
    ${warningsHtml(rec)}
  </div>`;
}

/** The three states a lookup can be in — pending, resolved, or a confirmed
 *  miss — as the one piece of markup that goes inside the modal shell. `entry`
 *  is exactly what `cache.get(id)` returns: `undefined` (not yet resolved),
 *  `null` (the backend said `not_found`), or a resolved record. Exported and
 *  pure for the same reason as `recordHtml`. */
export function viewerInnerHtml(entry) {
  if (entry === undefined) return `<div class="meta">${esc(t("evidence.loading"))}</div>`;
  if (entry === null) return `<div class="meta">${esc(t("evidence.not_found"))}</div>`;
  return recordHtml(entry);
}

/** The modal chrome around one citation's content, including the shareable
 *  deep link (frontend design §3). Exported and pure given a `loc` object
 *  shaped like `window.location` — a real `location` in the browser, an
 *  explicit stub in the node suite. */
export function shellHtml(id, inner, loc = location) {
  const link = `${loc.origin}${loc.pathname}#${HASH_PREFIX}${encodeURIComponent(id)}`;
  return `<div class="evidence-overlay" data-evidence-overlay>
    <div class="panel evidence-panel" role="dialog" aria-label="${esc(t("evidence.title"))}">
      <div class="evidence-head">
        <h3>${esc(t("evidence.title"))}</h3>
        <button type="button" class="evidence-close" data-evidence-close>${esc(t("common.close"))}</button>
      </div>
      <div class="meta"><bdi class="sku">${esc(id)}</bdi></div>
      <div class="meta evidence-link-line"><bdi class="num" dir="ltr">${esc(link)}</bdi></div>
      ${inner}
    </div>
  </div>`;
}

// The only DOM-mutating step in this module: everything above it is a pure
// string producer, exactly like `gaps.js` and `doc-warnings.js`; this is the
// one function that writes `#evidence-viewer`, the subtree this module alone
// owns (CLAUDE.md). Covered by the browser smoke suite, not the node suite —
// there is no DOM in node here and the repo takes on no jsdom dependency to
// manufacture one (no build step, per CLAUDE.md).
function render(id) {
  const root = document.getElementById("evidence-viewer");
  if (!root) return;
  root.innerHTML = shellHtml(id, viewerInnerHtml(cache.get(id)));
  const overlay = root.querySelector("[data-evidence-overlay]");
  overlay.querySelector("[data-evidence-close]").addEventListener("click", closeEvidenceViewer);
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay) closeEvidenceViewer();
  });
}

/** Open the viewer for one citation, resolving every citation currently
 *  rendered on the page in the same batch call. Exported so `gaps.js` and
 *  `doc-warnings.js` never need to — their citations stay pure HTML strings
 *  carrying `.evidence-link` + `data-evidence-id`; this module is the only one
 *  that turns a click into a fetch. */
export async function openEvidenceViewer(id) {
  if (!id) return;
  location.hash = HASH_PREFIX + encodeURIComponent(id);
  const ids = idsOnScreen();
  if (!ids.includes(id)) ids.unshift(id);
  render(id);  // show "loading" immediately rather than a frozen click
  await resolveIds(ids);
  render(id);
}

export function closeEvidenceViewer() {
  const root = document.getElementById("evidence-viewer");
  if (root) root.innerHTML = "";
  if (location.hash.startsWith("#" + HASH_PREFIX)) {
    history.replaceState(null, "", location.pathname + location.search);
  }
}

function idFromHash() {
  const h = location.hash;
  if (!h.startsWith("#" + HASH_PREFIX)) return null;
  return decodeURIComponent(h.slice(1 + HASH_PREFIX.length));
}

/** Wires the one document-level delegated click listener that turns any
 *  `.evidence-link` — wherever it was rendered — into an open viewer, and
 *  restores a deep link on load / back-forward navigation. */
export function initEvidence() {
  document.addEventListener("click", (ev) => {
    const link = ev.target.closest && ev.target.closest(".evidence-link[data-evidence-id]");
    if (!link) return;
    ev.preventDefault();
    openEvidenceViewer(link.dataset.evidenceId);
  });
  window.addEventListener("hashchange", () => {
    const id = idFromHash();
    if (id) openEvidenceViewer(id); else closeEvidenceViewer();
  });
  const initial = idFromHash();
  if (initial) openEvidenceViewer(initial);
}
