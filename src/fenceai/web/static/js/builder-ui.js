// The shared parts of a sentence-style row editor: the small DOM builders, the
// catalog cache the SKU picker reads, and the Advanced-JSON toggle.
//
// Two editors are built out of these — the knowledge rule builder (tabs.js) and
// the fence model editor (model-editor.js) — and they must not each own a copy.
// `skuSelect` is the reason: it is the ONE place that knows a product is shown
// as "SKU — localized name", so a second copy is how the model editor keeps
// showing English product names in Hebrew after the knowledge tab learned not
// to. The catalog cache is here for the same reason, one level down: two caches
// are two answers to "which products exist", and they diverge the moment one of
// them is populated before a catalog edit and the other after.
//
// No DOM of its own: every function here builds detached nodes, or acts on ids
// its CALLER owns. Same contract as fence-models.js.

import { apiGet } from "./api.js";
import { currentLocale, t } from "./i18n.js";
import { tu } from "./units.js";

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  node.append(...children);
  return node;
}

export function option(value, label, selected) {
  const o = el("option", { value, text: label });
  if (selected) o.selected = true;
  return o;
}

// small labelled field: <label><span class=meta>label</span> input</label>
export const field = (labelKey, input) =>
  el("label", { class: "builder-field" }, el("span", { class: "meta", text: tu(labelKey) }), input);

export function productLabel(products, sku) {
  const name = products[sku]?.name_i18n?.[currentLocale()] || products[sku]?.name;
  return name ? `${sku} — ${name}` : sku;
}

// SKU <select> from the cached catalog (localized names); optional adds a "none" entry
export function skuSelect(products, current, optional, onchange) {
  const sel = el("select", { title: t(optional ? "knowledge.builder.sku_optional" : "knowledge.builder.sku") });
  if (optional) sel.appendChild(option("", t("knowledge.builder.none"), !current));
  const skus = Object.keys(products).sort();
  for (const sku of skus) sel.appendChild(option(sku, productLabel(products, sku), current === sku));
  if (current && !skus.includes(current)) sel.appendChild(option(current, current, true));
  sel.addEventListener("change", () => onchange(sel.value || null));
  return sel;
}

// BomLine carries only the English `name`; localized names live on the catalog
// Product (`name_i18n`). Fetch the catalog once and map sku -> product.
//
// The PROMISE is cached, not the result: three surfaces warm this at load (the
// gate popover, the rule builder, the model editor) and caching the result
// alone lets two of them race into two fetches. A failure clears the cache so
// the next opener retries — a cached `{}` is a catalog that stays empty for the
// rest of the session because one request lost a network.
let catalogPromise = null;
export function loadCatalogProducts() {
  // `purchase_price_cents` rides alongside the products, derived by the server —
  // what ONE purchase unit costs, which for a rate-priced bar is a rounding the
  // catalog module calls THE rounding point for rate pricing. Folded onto each
  // product here so every consumer sees one shape and nobody is tempted to work
  // it out again in JavaScript.
  catalogPromise ??= apiGet("/api/catalog")
    .then((c) => Object.fromEntries(
      Object.entries(c.products || {}).map(([sku, p]) => [sku, {
        ...p, purchase_price_cents: c.purchase_price_cents?.[sku] ?? null,
      }])))
    .catch(() => { catalogPromise = null; return {}; });
  return catalogPromise;
}

// The PART library, cached exactly as the catalog above is and for the same two
// reasons: two caches are two answers to "which parts exist", and a cached empty
// list is a picker that stays empty for the rest of the session because one
// request lost a network. The promise is cached, not the result, so the two
// surfaces that warm it cannot race into two fetches.
//
// Read-only. Nothing here creates or edits a part — that is the arc that builds
// an editor for them — so there is no invalidation to get wrong yet.
let partsPromise = null;
export function loadParts() {
  partsPromise ??= apiGet("/api/parts")
    .then((body) => body.parts || [])
    .catch(() => { partsPromise = null; return []; });
  return partsPromise;
}

// The filing vocabulary the picker groups by. A separate request rather than a
// field derived in JS from the parts themselves: the LABEL is per-language and
// comes from the bundle the server reads, so deriving the list here would give
// the group headings raw keys in Hebrew.
let partTypesPromise = null;
export function loadPartTypes() {
  partTypesPromise ??= apiGet("/api/part-types")
    .then((body) => body.types || [])
    .catch(() => { partTypesPromise = null; return []; });
  return partTypesPromise;
}

// The vocabularies the schema accepts — the fixing bases, the length rules and
// the objective presets — from `GET /api/vocabularies`.
//
// Cached like the two above, and with ONE deliberate difference: a failed fetch
// resolves to NULL, never to `[]`. The other two degrade to an empty list
// because an empty picker is a truthful "nothing here yet"; this one cannot,
// because an empty vocabulary select does not read as "not loaded", it reads as
// "you have not chosen one" — and the alternative degradation, falling back to a
// list written into the JS, is exactly the second copy this route exists to
// delete. Null travels to `vocabulary()` and the control renders as unavailable.
let vocabulariesPromise = null;
export function loadVocabularies() {
  vocabulariesPromise ??= apiGet("/api/vocabularies")
    .catch(() => { vocabulariesPromise = null; return null; });
  return vocabulariesPromise;
}

// show/hide the structured editor vs. the raw-JSON textarea; the toggle button's
// data-i18n key is swapped so applyStatic keeps it correct across locale changes.
// `backKey` names the surface being returned to — the inventory tab has no rule
// builder, and labelling its button "back to the rule builder" misled a persona.
export function updateAdvancedUi(editorId, textareaId, btnId, open, backKey = "knowledge.builder.back") {
  document.getElementById(editorId).hidden = open;
  document.getElementById(textareaId).hidden = !open;
  const btn = document.getElementById(btnId);
  btn.dataset.i18n = open ? backKey : "knowledge.builder.advanced";
  btn.textContent = t(btn.dataset.i18n);
}
