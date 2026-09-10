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

import { apiGet, esc } from "./api.js";
import { currentLocale, t } from "./i18n.js";
import { fmtLen, sentence, tu } from "./units.js";

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

// ---------- read-only phrasing of what the builder above writes ----------
//
// The rules list used to render `JSON.stringify(v.actions)` and
// `JSON.stringify(v.scope)`, which is why the Knowledge tab was unreadable: a
// rule's actual content was two raw dumps per card, in a language the reader
// does not necessarily write. These two turn the same data into the sentence
// the builder already composes from its selects.
//
// They live HERE, beside the editor they mirror, for the reason the file header
// gives: the review queue renders the same two fields on a candidate, and a
// second copy of the phrasing is how the two tabs come to describe one rule
// differently. Both return HTML — every interpolated value goes through
// `sentence()`, which escapes the template and bidi-isolates each param, so a
// Latin SKU inside a Hebrew phrase does not reorder on screen.

// The action kinds the builder offers, and therefore the kinds a phrasing must
// exist for. Closed on purpose: adding one is a release either way, and
// `tests/web/test_knowledge_panes_module.py` fails until both bundles carry its
// sentence.
export const ACTION_KINDS = [
  "set_param", "default_component", "require_mounting", "require_post_reinforcement",
  "prefer_equal_spans", "prefer_min_span_width", "prefer_span_width", "prefer_vertical",
  "add_note", "flag_for_review",
];

/** One action as a sentence, e.g. "Set max span to 1800 mm".
 *
 *  `products` is the catalog cache, so a SKU reads as the builder shows it.
 *  An unknown kind degrades to its own token — never to a raw i18n key, for
 *  the reason `vocabWord` exists in the inspector: a backend newer than these
 *  bundles must not put `action.sentence.set_gizmo` inside a Hebrew card.
 */
export function actionSentence(action, products = {}) {
  const kind = action?.kind;
  if (!ACTION_KINDS.includes(kind))
    return sentence("action.sentence.unknown", { kind: kind || "?" });

  // a `*_mm` action field is a length and follows the display unit; a weight or
  // a count is a plain number in every unit. Same split the builder's `num()`
  // makes, and for the same reason.
  const len = (mm) => fmtLen(mm ?? 0);

  let html;
  switch (kind) {
    case "set_param": {
      const isLength = String(action.param || "").endsWith("_mm");
      const key = "action.param." + action.param;
      const known = t(key) !== key;
      html = sentence("action.sentence.set_param", {
        // an unregistered parameter is shown verbatim — it is a real, saveable
        // value of this field (the builder's "other…" box writes one)
        param: known ? paramWord(key) : action.param,
        value: isLength ? len(action.value) : action.value,
      });
      break;
    }
    case "default_component":
      html = sentence("action.sentence.default_component", {
        role: t("action.role." + action.role),
        sku: productLabel(products, action.sku),
      });
      break;
    case "require_mounting":
      html = sentence("action.sentence.require_mounting", {
        mounting: t("action.mounting." + action.mounting),
        surface: t("surface." + action.surface),
      });
      break;
    case "require_post_reinforcement":
      html = sentence("action.sentence.require_post_reinforcement", {
        context: t("action.context." + action.context),
      });
      break;
    case "prefer_equal_spans":
      html = sentence("action.sentence.prefer_equal_spans", { weight: action.weight ?? 1 });
      break;
    case "prefer_min_span_width":
      html = sentence("action.sentence.prefer_min_span_width",
        { min: len(action.min_mm), weight: action.weight ?? 1 });
      break;
    case "prefer_span_width":
      html = sentence("action.sentence.prefer_span_width",
        { width: len(action.width_mm), weight: action.weight ?? 1 });
      break;
    case "prefer_vertical":
      html = sentence("action.sentence.prefer_vertical",
        { mode: t("action.mode." + action.mode), weight: action.weight ?? 1 });
      break;
    case "add_note":
      html = sentence("action.sentence.add_note", { text: action.text || "" });
      break;
    default:  // flag_for_review
      html = sentence("action.sentence.flag_for_review", { reason: action.reason || "" });
  }

  // the optional SKU on the two actions that take one: a suffix rather than a
  // second template per kind, so every kind keeps exactly one phrasing
  if ((kind === "require_mounting" || kind === "require_post_reinforcement") && action.sku)
    html += " " + sentence("action.sentence.with_sku",
      { sku: productLabel(products, action.sku) });
  return html;
}

/** A length parameter's label without its unit.
 *
 *  `action.param.max_span_mm` is "max span ({u})", which is right for the
 *  builder — the unit belongs in a form label, beside a bare number input. In a
 *  sentence the unit rides the VALUE, so the form's label reads "Set max span
 *  (mm) to 1200 mm" and says it twice. The trailing parenthetical is dropped
 *  rather than a second bundle key added: two labels per parameter is two
 *  things to keep in step, and this shape holds in both languages because both
 *  bundles put the placeholder in the same place.
 */
function paramWord(key) {
  return tu(key).replace(/\s*\([^)]*\)\s*$/, "");
}

/** A rule's scope as chips — `{model: "Emblem"}` reads as "model: Emblem".
 *
 *  Dimension names stay verbatim: condition dimensions are a registry that
 *  grows without a contract amendment, so a scope key can legitimately be one
 *  no bundle has a word for, and inventing one here would be worse than
 *  showing the publisher's own token.
 */
export function scopeChips(scope) {
  const keys = Object.keys(scope || {});
  if (!keys.length)
    return `<span class="chip empty">${esc(t("knowledge.scope_any"))}</span>`;
  return keys.sort().map((k) =>
    `<span class="chip"><b><bdi>${esc(k)}</bdi></b>: <bdi>${esc(String(scope[k]))}</bdi></span>`
  ).join("");
}
