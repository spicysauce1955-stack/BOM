// The material & inventory drawer: what one part of a panel IS, and what else
// it could be.
//
// A drawing where every rectangle is inert answers "what does this look like".
// The question an estimator actually has is "what is that rail made of, what
// else fits there, and do we have any" — which is three documents (the resolved
// panel, the catalog, the project's inventory) joined on one SKU.
//
// The join is the whole module, and it is PURE (`partOptions`): three documents
// in, one list of rows out, no DOM and no fetch. That is what makes the two
// claims a drawer must not get wrong testable in node —
//
//   * an alternative is offered ONLY if the slot's own eligibility names it. A
//     drawer that offered the catalog would let someone pick a gate kit for a
//     screw slot, and the API would refuse it after the click;
//   * "in stock" means stock of THAT sku for THIS project, counted the way the
//     cut planner counts it: whole units and reusable remnants are different
//     things, and adding them together would promise a 300 mm offcut as a post.
//
// DOM ownership: none. `assembly.js` owns `#assembly-drawer` and writes it; this
// module is a pure producer of the HTML that goes in it and of the join behind
// that HTML. (An earlier version of this header claimed the node, which would
// have made two modules its owner — the one rule the frontend has no room to be
// vague about.)

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { money, moneyDelta, roleWord, tu } from "./units.js";

/** The rows for one slot: the chosen product first, then its alternatives.
 *
 * `preview` is the PanelPreview whose price and choice are being SHOWN;
 * `catalogue` is the preview the option LIST comes from, and they are different
 * documents on purpose. Pinning a sku narrows that slot's eligibility — which is
 * correct, and is what makes the price honest — but `eligible_skus` on the
 * narrowed preview then contains exactly the pinned product, so building the
 * comparison table from it collapsed the table to one row on the first click and
 * left no way back to the other candidates. The list is a property of the slot,
 * not of the choice.
 *
 * `products` the catalog map, `inventory` the project's items.
 *
 * Returns null when the preview has no such slot — which happens legitimately:
 * a fitted pattern can place none of a member, and a slot with no placed member
 * is not a part of this bay. */
export function partOptions(preview, slotKey, products = {}, inventory = null,
                            catalogue = null) {
  const find = (doc) => (doc?.parts || []).concat(doc?.unsupplied || [])
    .find((p) => p.slot_key === slotKey);
  const part = find(preview);
  if (!part) return null;
  // the unnarrowed candidate set, when the caller has one to offer
  const offered = find(catalogue)?.eligible_skus;
  const stock = stockBySku(inventory);
  const chosenPrice = unitPrice(products, part.sku);
  return {
    slot_key: part.slot_key,
    role: part.role,
    qty: part.qty,
    length_mm: part.length_mm ?? null,
    unit: part.unit || "",
    total_cents: part.total_cents || 0,
    unsupplied: (preview?.unsupplied || []).some((p) => p.slot_key === slotKey),
    options: (offered?.length ? offered : part.eligible_skus || []).map((sku) => {
      const product = products[sku] || null;
      const price = unitPrice(products, sku);
      return {
        sku,
        chosen: sku === part.sku,
        name: product?.name_i18n || null,
        fallback_name: product?.name || sku,
        material: product?.attrs?.material || null,
        finish: product?.attrs?.finish || null,
        colour: swatch(product?.attrs?.colour),
        price_cents: price,
        // the difference PER PURCHASE UNIT, which is the only comparison two
        // products can honestly be given before one of them is planned: how
        // many bars a bay needs depends on cutting, and cutting is not additive
        delta_cents: price === null || chosenPrice === null
          ? null : price - chosenPrice,
        bought_as: product?.consumption?.kind || null,
        on_hand: stock.get(sku)?.units || 0,
        remnants: stock.get(sku)?.remnants || [],
      };
    }),
  };
}

/** Whole units and reusable remnants, counted separately and never summed.
 *
 * `full_stock` and `opened_package` are units you can issue; a `remnant` is a
 * length, and a 300 mm offcut is not "one post in stock". The cut planner
 * already treats them as different bins — this is the same distinction, shown. */
export function stockBySku(inventory) {
  const out = new Map();
  for (const item of inventory?.items || []) {
    if (!out.has(item.sku)) out.set(item.sku, { units: 0, remnants: [] });
    const row = out.get(item.sku);
    if (item.kind === "remnant") {
      if (item.length_mm) row.remnants.push(item.length_mm);
    } else {
      row.units += item.qty ?? 1;
    }
  }
  for (const row of out.values()) row.remnants.sort((a, b) => a - b);
  return out;
}

/** A colour attr is only paintable if it is a plain hex triple.
 *
 * The catalog validates this at load, and this is the second gate: the value
 * reaches a `background` — a STYLE context, where `esc()` guarantees nothing —
 * and a client that trusted the server here would be one bad row away from
 * painting arbitrary CSS. */
export function swatch(value) {
  return typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value) ? value : null;
}

function unitPrice(products, sku) {
  const product = products[sku];
  if (!product) return null;
  if (product.pricing?.kind === "linear") {
    // the rate is authored per metre; ONE purchase unit is a whole bar, and the
    // backend rounds that once (`purchase_price_cents`). Mirrored here rather
    // than shown as a rate, so the column compares like with like.
    const length = product.consumption?.purchase_length_mm || 0;
    return Math.floor((product.pricing.cents_per_m * length + 500) / 1000);
  }
  return product.price_cents ?? 0;
}

// ------------------------------------------------------------------- render

/** The drawer, as HTML. `locale` picks the product's own localized name.
 *
 * Every server string goes through `esc()`; the only value that reaches a style
 * context is the swatch, which `swatch()` has already proved is a hex triple. */
export function drawerHtml(model, { locale = "en", pinned = null } = {}) {
  if (!model) return "";
  const head = `<div class="summary-line">
      <b>${esc(roleWord(model.role))}</b>
      <span class="sku">${esc(model.slot_key)}</span>
      <span class="meta"><span class="num">${esc(String(model.qty))}</span>×</span>
      ${model.length_mm
        ? `<span class="meta">${esc(tu("structure.cut", { cut_mm: model.length_mm }))}</span>`
        : ""}
      ${model.unsupplied
        ? `<span class="tag rejected">${esc(t("drawer.unsupplied"))}</span>` : ""}
    </div>`;
  const rows = model.options.map((option) => optionRow(option, locale, pinned)).join("");
  return `<div class="panel" id="assembly-drawer-panel">
      <h3>${esc(t("drawer.title"))}</h3>
      ${head}
      <div class="meta">${esc(t("drawer.hint"))}</div>
      ${model.options.length
        ? `<table class="drawer-table"><tr>
             <th>${esc(t("drawer.product"))}</th>
             <th>${esc(t("drawer.material"))}</th>
             <th>${esc(t("drawer.bought_as"))}</th>
             <th>${esc(tu("drawer.unit_price"))}</th>
             <th>${esc(t("drawer.in_stock"))}</th>
             <th></th></tr>${rows}</table>`
        : `<div class="meta">${esc(t("drawer.no_options"))}</div>`}
      <div class="meta">${esc(t("drawer.stock_scope"))}</div>
      <button id="btn-drawer-close">${esc(t("common.close"))}</button>
    </div>`;
}

function optionRow(option, locale, pinned) {
  const name = option.name?.[locale] || option.name?.en || option.fallback_name;
  // A catalog is editable through the API, so its vocabulary is open while the
  // bundle's is not: `t()` returns the KEY when it has no entry, and a product
  // made of bamboo would read "material.bamboo". Fall back to the attr itself.
  const word = (prefix, value) => {
    if (!value) return null;
    const key = `${prefix}.${value}`;
    const said = t(key);
    return said === key ? value : said;
  };
  const material = [word("material", option.material),
                    word("finish", option.finish)].filter(Boolean).join(" · ");
  const stock = option.on_hand
    ? `<span class="num">${esc(String(option.on_hand))}</span>`
    : `<span class="meta">${esc(t("drawer.none_on_hand"))}</span>`;
  const remnants = option.remnants.length
    ? ` <span class="meta">${esc(tu("drawer.remnants",
        { n: option.remnants.length, longest_mm: option.remnants.at(-1) }))}</span>`
    : "";
  return `<tr class="${option.chosen ? "selected" : ""}${
      option.sku === pinned ? " pinned" : ""}">
    <td><span class="sku">${esc(option.sku)}</span>
      <br><span class="meta" dir="auto">${esc(name)}</span></td>
    <td>${option.colour
        ? `<span class="drawer-swatch" style="background:${esc(option.colour)}"></span>`
        : ""}<span dir="auto">${esc(material) || `<span class="meta">—</span>`}</span></td>
    <td class="meta">${option.bought_as
        ? esc(t(`consumption.${option.bought_as}`)) : "—"}</td>
    <td class="num">${option.price_cents === null ? "—" : esc(money(option.price_cents))}
      ${option.delta_cents ? `<br><span class="meta">${
          esc(moneyDelta(option.delta_cents))}</span>` : ""}</td>
    <td>${stock}${remnants}</td>
    <td>${option.chosen
        ? `<span class="tag active">${esc(t("drawer.chosen"))}</span>`
        : `<button data-pick-sku="${esc(option.sku)}">${esc(t("drawer.use"))}</button>`}</td>
  </tr>`;
}
