// The inspector: one selected thing on the panel canvas, in the words a person
// who builds fences uses.
//
// The vocabularies underneath are unchanged and still typed — `basis`,
// `justification`, `length_rule` are read by resolution and fulfillment code
// that has to know what each value means, so adding one stays a code change
// with tests. What became data is the PHRASING: each value renders through
// `model.<vocab>.sentence.<v>` out of the locale bundles, correctable without a
// release, and `test_locale_bundles.py` pins both halves in both languages.
//
// Detached DOM only. `renderInspector` fills the host it is handed and reaches
// for no global id, which is what let the controls be mounted beside the old
// row list first and swapped onto the canvas afterwards — the same contract
// `renderElevation` has, and the reason neither is a second owner of #tab-models.
//
// Every edit goes through `onChange`, which is the caller's "the document
// moved". Nothing here saves, prices, or knows what a session is: a draft the
// author never asked to store is still a row in a versioned library, and the
// library has no delete.
//
// `data-f="<field>"` rides on every input, as it did on the rows. That attribute
// is not decoration: the controls are generated, so a test (or a person reading
// the DOM) has no other stable way to name "the length rule of the selected
// slot", and positional selectors are exactly the kind that keep passing after
// a field moves.
//
// Two things here are load-bearing and easy to "tidy" into defects:
//
//   * `gap_after_mm` MAY BE NEGATIVE. A negative gap is an overlap, and an
//     overlap is what board-on-board and shadowbox ARE. The control hides the
//     SIGN — a checkbox plus a positive amount — and puts no `min` on the
//     amount: the bound that is real is the member's net advance, which
//     `validate_model` and `gapFromDrag` both hold.
//   * a `swatch` ends up in a CSS/SVG colour, where esc() is not enough. It is
//     validated `^#[0-9a-fA-F]{6}$` at model load, and the field refuses
//     anything else here rather than leaning on that check alone.

import { el, field, option, skuSelect } from "./builder-ui.js";
import { currentLocale, t } from "./i18n.js";
import { gapForOverlap, overlapOf } from "./panel-canvas-geom.js";
import {
  APPROVALS, AXIS_KINDS, BASES, COUNT_PARAMS, EXCESS, JUSTIFICATIONS,
  LENGTH_RULES, PLACEMENT_KINDS, ROLES, SWATCH_RE, defaultEligibleMember,
  defaultPlacement,
} from "./panel-model.js";
import { inputStep, roleWord, toDisplayValue, toMm, tu } from "./units.js";

/** Nothing on the drawing is selected: the panel itself is. */
export const SELECTION_NONE = { kind: "panel", key: null };

// The caller's "the document moved", set for the duration of one render so the
// small field builders below need not each be handed it. Set once per render,
// never read outside one — an inspector rendered without a host has no edits to
// report.
let notify = () => {};
// ... and "the thing being edited is now called something else", which is a
// different event: the selection is BY KEY, so a rename with nobody told leaves
// the inspector pointed at a name nothing has — reporting that the element you
// are looking at is gone.
let rename = () => {};

// --- field builders ----------------------------------------------------------

// `length` means the value is millimetres at rest and shown in the display
// unit. The conversion happens here and nowhere else, so a width typed in cm is
// stored as mm and reads back as the same width.
export function num(obj, key, labelKey, { length = false, min = null, onCommit = null } = {}) {
  const raw = obj[key] ?? "";
  const attrs = { type: "number", "data-f": key, step: length ? inputStep() : "1",
                  value: raw === "" || !length ? raw : toDisplayValue(raw) };
  // `min` is a number in the FIELD, so on a length it crosses the same boundary
  // the value does — a raw `min="1"` means 1 mm in mm and 10 mm in cm.
  if (min !== null) attrs.min = length ? toDisplayValue(min) : min;
  const i = el("input", attrs);
  i.addEventListener("change", () => {
    obj[key] = length ? (toMm(i.value) ?? 0) : Math.round(i.valueAsNumber || 0);
    (onCommit || notify)();
  });
  return field(labelKey, i);
}

export function text(obj, key, labelKey, { size = 16, ltr = false, nullable = false } = {}) {
  const i = el("input", { type: "text", "data-f": key, dir: ltr ? "ltr" : "auto", size,
                          class: ltr ? "sku" : null, value: obj[key] ?? "" });
  i.addEventListener("input", () => {
    const v = i.value.trim();
    obj[key] = nullable && !v ? null : i.value;
    notify();
  });
  return field(labelKey, i);
}

export function choice(obj, key, values, labelFor, labelKey,
                       { rerender = false, nullKey = null } = {}) {
  const s = el("select", { "data-f": key });
  if (nullKey) s.appendChild(option("", t(nullKey), obj[key] === null || obj[key] === undefined));
  for (const v of values) s.appendChild(option(v, labelFor(v), obj[key] === v));
  // a value the resolver does not honour is never OFFERED, but a document that
  // already carries one must not be silently rewritten by opening the editor
  if (obj[key] && !values.includes(obj[key]))
    s.appendChild(option(obj[key], obj[key], true));
  s.addEventListener("change", () => {
    obj[key] = s.value === "" ? null : s.value;
    notify({ rerender });
  });
  return field(labelKey, s);
}

/** A select over a closed vocabulary, rendered as a SENTENCE.
 *
 * The same values `choice()` offers, with the phrasing key instead of the label
 * key — so "Screws at: where every board meets every rail" is one control over
 * an enum that has not moved. */
function sentenceChoice(obj, key, values, prefix, labelKey, opts = {}) {
  return choice(obj, key, values, (v) => t(`${prefix}sentence.${v}`), labelKey, opts);
}

/** The element's own key.
 *
 * Not `text(obj, "key", …)`: a rename has to travel, because the selection is
 * by key and everything holding one — the chips, the drawing's `data-slot`, the
 * inspector itself — would otherwise still be pointing at the old name one
 * keystroke later. */
function keyField(obj, kind, spec) {
  const i = el("input", { type: "text", "data-f": "key", dir: "ltr", class: "sku",
                          size: 10, value: obj.key ?? "" });
  i.addEventListener("input", () => {
    const was = obj.key;
    obj.key = i.value;
    // A board names the rails it starts and stops at BY KEY. Renaming a rail
    // and leaving those behind authors a document the gate refuses with English
    // authoring text, for an edit that looked like a rename — so the references
    // move with it.
    if (kind === "frame") reref(spec, was, obj.key);
    rename({ kind, key: obj.key });
    notify();
  });
  return field("model.key", i);
}

function reref(spec, was, now) {
  for (const member of spec?.infill?.pattern || []) {
    if (member.base_ref === was) member.base_ref = now;
    if (member.top_ref === was) member.top_ref = now;
  }
}

function removeButton(onclick) {
  const b = el("button", { type: "button", class: "remove-row",
                           title: t("common.remove"), text: "✕" });
  b.addEventListener("click", onclick);
  return b;
}

function group(titleKey, ...children) {
  return el("div", { class: "inspect-group" },
    el("b", { class: "inspect-head", text: t(titleKey) }), ...children);
}

function row(...children) {
  return el("div", { class: "builder-row" }, ...children);
}

// --- the overlap control -----------------------------------------------------

/** "Overlaps the next board", plus a positive amount.
 *
 * `gap_after_mm` MAY BE NEGATIVE and that is the whole point — a negative gap is
 * an overlap, and board-on-board and shadowbox ARE that. The sign is what the
 * author previously had to remember, from a hint under the field; this control
 * remembers it instead. No `min` reaches the amount either: the bound that is
 * real lives on the member's net advance, in `validate_model` and in
 * `gapFromDrag`, and a `min="0"` here would delete two product families from
 * what the tool can express. */
export function gapControl(member) {
  const state = overlapOf(member);
  const box = el("input", { type: "checkbox", "data-f": "overlaps" });
  box.checked = state.overlaps;
  const amount = el("input", {
    type: "number", "data-f": "gap_after_mm", step: inputStep(),
    value: String(toDisplayValue(state.amount_mm)),
  });
  const commit = ({ rerender = false } = {}) => {
    member.gap_after_mm = gapForOverlap(box.checked, toMm(amount.value) ?? 0);
    notify({ rerender });
  };
  box.addEventListener("change", () => commit({ rerender: true }));  // the label changes
  amount.addEventListener("change", () => commit());
  return row(
    el("label", { class: "builder-field" },
      box, el("span", { class: "meta", text: t("model.overlaps_next") })),
    field(box.checked ? "model.overlap_amount" : "model.gap_amount", amount));
}

// --- a requirement and the products that may answer it -----------------------

function requirementRows(req, { products, model, spec }, kind) {
  const box = el("div", { class: "builder-sub" });
  if (!req) return box;
  req.eligibility ??= { members: [] };
  req.eligibility.members ??= [];

  const first = row();
  first.appendChild(choice(req, "role", ROLES, roleWord, "model.role"));
  first.appendChild(num(req, "qty", "model.qty", { min: 0 }));
  // `between_frame` is the one rule that reads a member's base/top refs, and a
  // FRAME slot has none — the schema refuses it there, so it is not offered
  // there. Same principle as the narrowed `excess` list: offering a value the
  // gate then refuses invites an author into a document they can only fix by
  // undoing the choice the editor invited.
  const rules = kind === "frame"
    ? LENGTH_RULES.filter((r) => r !== "between_frame") : LENGTH_RULES;
  first.appendChild(sentenceChoice(req, "length_rule", rules,
    "model.length_rule.", "model.length_rule",
    { rerender: true, nullKey: "model.length_rule.none" }));
  if (req.length_rule === "overlap")
    first.appendChild(num(req, "overlap_mm", "model.overlap_mm", { length: true }));
  const axes = (model.option_axes || []).map((a) => a.key);
  first.appendChild(choice(req, "option_axis", axes, (k) => k, "model.option_axis",
    { rerender: true, nullKey: "model.option_axis.none" }));
  box.appendChild(first);
  box.appendChild(eligibilityList(req, { products }));

  // A slot binds to AT MOST ONE axis, and then names a SKU per axis value. The
  // SKU must be one of the eligible members — anything else is a product the
  // slot was never allowed to use, and `validate_model` says so.
  if (req.option_axis) {
    const axis = (model.option_axes || []).find((a) => a.key === req.option_axis);
    req.sku_by_option ??= {};
    for (const value of axis?.values || []) {
      const vrow = row(el("span", { class: "meta",
        text: t("model.sku_for_option", { option: valueLabel(value) }) }));
      const skus = req.eligibility.members.map((m) => m.sku).filter(Boolean);
      const sel = el("select");
      sel.appendChild(option("", t("model.ref_none"), !req.sku_by_option[value.key]));
      for (const sku of skus)
        sel.appendChild(option(sku, sku, req.sku_by_option[value.key] === sku));
      sel.addEventListener("change", () => {
        if (sel.value) req.sku_by_option[value.key] = sel.value;
        else delete req.sku_by_option[value.key];
        notify();
      });
      vrow.appendChild(sel);
      box.appendChild(vrow);
    }
  }
  return box;
}

/** "In preference order" — the eligibility, dragged rather than numbered.
 *
 * `priority` is the company's stated preference and the ORDER it is read in IS
 * part of the answer, so the list is the priority: every drop renumbers the
 * whole list from 1, which is the only arrangement where the two can never
 * disagree. The numbers still exist in the document; they have simply stopped
 * being something a person types. */
function eligibilityList(req, { products }) {
  const box = el("div", { class: "pref-box" });
  box.appendChild(row(
    el("span", { class: "meta", text: t("model.prefer_order") }),
    addProductButton(req, products)));
  const members = req.eligibility.members;
  if (!members.length) {
    box.appendChild(el("div", { class: "meta",
      text: t(req.eligibility.predicate ? "model.prefer_predicate"
                                        : "model.prefer_none") }));
    return box;
  }
  const list = el("ul", { class: "pref-list" });
  members.forEach((member, idx) => {
    member.kind ??= "catalog_item";
    const item = el("li", { class: "pref-item", draggable: "true",
                            "data-eligible-row": String(idx) });
    item.appendChild(el("span", { class: "pref-grip", text: "⠿",
                                  title: t("model.prefer_hint") }));
    item.appendChild(swatchChip(products[member.sku]));
    const picker = skuSelect(products, member.sku, false,
      (v) => { member.sku = v; notify({ rerender: true }); });
    picker.dataset.f = "sku";
    item.appendChild(picker);

    // "let the system substitute automatically" — `approval` as a decision the
    // author makes about the product, not as a word they pick off a list
    const auto = el("input", { type: "checkbox", "data-f": "approval" });
    auto.checked = (member.approval ?? "auto") === "auto";
    auto.addEventListener("change", () => {
      member.approval = auto.checked ? APPROVALS[0] : APPROVALS[1];
      notify();
    });
    item.appendChild(el("label", { class: "builder-field" }, auto,
      el("span", { class: "meta", text: t("model.approval.sentence.auto") })));
    item.appendChild(removeButton(() => {
      members.splice(idx, 1);
      renumber(members);
      notify({ rerender: true });
    }));

    item.addEventListener("dragstart", (ev) => {
      ev.dataTransfer.setData("text/plain", String(idx));
      ev.dataTransfer.effectAllowed = "move";
      item.classList.add("dragging");
    });
    item.addEventListener("dragend", () => item.classList.remove("dragging"));
    item.addEventListener("dragover", (ev) => { ev.preventDefault(); });
    item.addEventListener("drop", (ev) => {
      ev.preventDefault();
      const from = Number(ev.dataTransfer.getData("text/plain"));
      if (!Number.isInteger(from) || from === idx) return;
      const [moved] = members.splice(from, 1);
      members.splice(idx, 0, moved);
      renumber(members);
      notify({ rerender: true });
    });
    list.appendChild(item);
  });
  box.appendChild(list);
  box.appendChild(el("div", { class: "meta", text: t("model.prefer_hint") }));
  return box;
}

// The order IS the priority, so the numbers are written from the order and
// never the other way round — two authorities over one preference is how a list
// reading top-to-bottom comes to be resolved bottom-to-top.
const renumber = (members) => members.forEach((m, i) => { m.priority = i + 1; });

function addProductButton(req, products) {
  const b = el("button", { type: "button", "data-act": "add-eligible",
                           text: t("model.add_eligible") });
  // an eligibility that declares a PREDICATE may not also name members — the
  // loader refuses the pair — so the button that would author that combination
  // is offered as refused rather than as available
  if (req.eligibility.predicate) {
    b.disabled = true;
    b.title = t("model.prefer_predicate");
    return b;
  }
  b.addEventListener("click", () => {
    req.eligibility.members.push(defaultEligibleMember(
      Object.keys(products).sort()[0], req.eligibility.members.length + 1));
    notify({ rerender: true });
  });
  return b;
}

/** The product's own colour, when the catalog declares one that is a colour.
 *
 * A swatch reaches a CSS colour, which is a STYLE context: esc() would not make
 * a bad value safe there. The catalog validates `^#[0-9a-fA-F]{6}$` at load and
 * that check is NOT weakened — only a string that matched the pattern here is
 * ever assigned, so a product carrying anything else simply has no chip. */
function swatchChip(product) {
  const chip = el("span", { class: "swatch-chip" });
  const colour = product?.attrs?.colour;
  chip.style.background = SWATCH_RE.test(colour || "") ? colour : "transparent";
  return chip;
}

const valueLabel = (value) =>
  value.label_i18n?.[currentLocale()] || value.label_i18n?.en || value.key;

// --- the basis diagrams ------------------------------------------------------

/** A three-board, two-rail sketch with this basis's fasteners on it.
 *
 * An illustration of the VOCABULARY, never of this panel: a model with twenty
 * boards still shows three, because the question the picture answers is "what
 * does per-gap mean" and not "where are my screws" — the drawing next to it
 * answers that one, with the resolver's own places.
 *
 * Built as elements rather than as an HTML string: nothing here is user text,
 * and keeping it that way means it cannot become the exception. */
const DIAGRAM_DOTS = {
  per_panel: [[30, 20]],
  per_frame_member: [[30, 8], [30, 32]],
  per_member: [[10, 20], [30, 20], [50, 20]],
  per_end_member: [[10, 20], [50, 20]],
  per_gap: [[20, 20], [40, 20]],
  per_member_crossing: [[10, 8], [30, 8], [50, 8], [10, 32], [30, 32], [50, 32]],
};

function basisDiagram(basis) {
  const svg = el("svg", { class: "basis-diagram", viewBox: "0 0 60 40",
                          "aria-hidden": "true" });
  for (const y of [5, 29])
    svg.appendChild(el("rect", { class: "basis-rail", x: "2", y: String(y),
                                 width: "56", height: "6" }));
  for (const x of [6, 26, 46])
    svg.appendChild(el("rect", { class: "basis-board", x: String(x), y: "2",
                                 width: "8", height: "36" }));
  for (const [cx, cy] of DIAGRAM_DOTS[basis] || [])
    svg.appendChild(el("circle", { class: "basis-dot", cx: String(cx),
                                   cy: String(cy), r: "3" }));
  return svg;
}

// --- the swatch field (option axis values) -----------------------------------

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
    notify();
  });
  paint();
  wrap.append(el("span", { class: "meta", text: t("model.swatch") }), i, chip);
  return wrap;
}

function i18nLabelField(obj, labelKey) {
  const i = el("input", { type: "text", dir: "auto", size: 16,
                          value: obj.label_i18n?.[currentLocale()] || "" });
  i.addEventListener("input", () => {
    obj.label_i18n = { ...obj.label_i18n, [currentLocale()]: i.value };
    notify();
  });
  return field(labelKey, i);
}

// --- option axes -------------------------------------------------------------

/** The model's option axes — colour, finish, whatever a line varies on.
 *
 * Not a selection: an axis is a property of the MODEL, not of anything on the
 * drawing, so it has its own entry point. It lives here rather than in the
 * editor because it is built out of the same field builders, and `notify` is an
 * internal detail with exactly two doors — this one and `renderInspector`. */
export function renderAxisEditor(host, { model, onChange = () => {} } = {}) {
  if (!host) return;
  notify = onChange;
  // an axis is not a selection, so nothing here renames one — but leaving the
  // last inspector render's callback installed is a loaded gun in module state
  rename = () => {};
  host.innerHTML = "";
  model.option_axes ??= [];
  const axes = model.option_axes;
  const head = el("div", { class: "builder-head" },
    el("b", { text: t("model.axes") }));
  const addAxis = el("button", { type: "button", id: "btn-model-add-axis",
                                 text: t("model.add_axis") });
  addAxis.addEventListener("click", () => {
    axes.push({ key: `axis${axes.length + 1}`, label_i18n: {}, kind: "enum",
                values: [], available_when: null });
    notify({ rerender: true });
  });
  head.appendChild(addAxis);
  host.appendChild(head);

  axes.forEach((axis, idx) => {
    const arow = el("div", { class: "builder-row", "data-axis-row": String(idx) });
    arow.appendChild(text(axis, "key", "model.key", { size: 12, ltr: true }));
    arow.appendChild(i18nLabelField(axis, "model.label"));
    arow.appendChild(choice(axis, "kind", AXIS_KINDS,
      (k) => t("model.axis_kind." + k), "model.axis_kind"));
    const addValue = el("button", { type: "button", "data-act": "add-axis-value",
                                    text: t("model.add_axis_value") });
    addValue.addEventListener("click", () => {
      axis.values ??= [];
      axis.values.push({ key: `v${axis.values.length + 1}`, label_i18n: {}, swatch: null });
      notify({ rerender: true });
    });
    arow.appendChild(addValue);
    arow.appendChild(removeButton(() => {
      axes.splice(idx, 1);
      notify({ rerender: true });
    }));
    host.appendChild(arow);
    for (const [vIdx, value] of (axis.values || []).entries()) {
      const vrow = el("div", { class: "builder-row", "data-axis-value-row": String(vIdx) });
      vrow.appendChild(text(value, "key", "model.key", { size: 10, ltr: true }));
      vrow.appendChild(i18nLabelField(value, "model.label"));
      vrow.appendChild(swatchField(value));
      vrow.appendChild(removeButton(() => {
        axis.values.splice(vIdx, 1);
        notify({ rerender: true });
      }));
      host.appendChild(vrow);
    }
  });
}

// --- the inspector itself ----------------------------------------------------

/** Render the controls for `selection` into `host`.
 *
 * `onChange({rerender})` fires after every committed edit — the caller decides
 * what that means (re-price, mark dirty, repaint). `onRemove(selection)` fires
 * when the selected thing is deleted, so the caller can drop the selection with
 * it rather than leaving the inspector pointed at nothing. */
export function renderInspector(host, {
  selection = SELECTION_NONE, spec, model, products = {}, elevation = null,
  onChange = () => {}, onRemove = () => {}, onRename = () => {},
} = {}) {
  if (!host) return;
  notify = onChange;
  rename = onRename;
  host.innerHTML = "";
  if (!spec || !model) return;
  const ctx = { products, model, spec, elevation, onRemove };
  switch (selection?.kind) {
    case "frame": return frameInspector(host, selection.key, ctx);
    case "infill": return infillInspector(host, selection.key, ctx);
    case "fixing": return fixingInspector(host, selection.key, ctx);
    default: return panelInspector(host, ctx);
  }
}

function missing(host, key) {
  host.appendChild(el("div", { class: "meta", text: t(key) }));
}

function frameInspector(host, key, ctx) {
  const slot = (ctx.spec.frame || []).find((s) => s.key === key);
  if (!slot) return missing(host, "model.inspect.gone");
  const title = el("div", { class: "inspect-title" },
    el("b", { text: t("model.inspect.rail") }),
    el("bdi", { class: "sku", text: slot.key }),
    removeButton(() => {
      ctx.spec.frame.splice(ctx.spec.frame.indexOf(slot), 1);
      ctx.onRemove({ kind: "frame", key });
    }));
  host.appendChild(title);

  const place = row(
    keyField(slot, "frame", ctx.spec),
    sentenceChoice(slot, "orientation", ["horizontal", "vertical"],
      "model.orientation.", "model.orientation", { rerender: true }));
  const kindSel = el("select", { class: "builder-kind", "data-f": "placement" });
  for (const k of PLACEMENT_KINDS)
    kindSel.appendChild(option(k, t(`model.placement.sentence.${k}`),
                               slot.placement?.kind === k));
  kindSel.addEventListener("change", () => {
    slot.placement = defaultPlacement(kindSel.value);
    notify({ rerender: true });
  });
  place.appendChild(field("model.placement", kindSel));

  const p = slot.placement || {};
  if (p.kind === "distributed") {
    place.appendChild(num(p, "count", "model.count", { min: 0 }));
    // a knowledge PARAM, not an authored integer: rail count ladders with height
    // and a company rule must still be able to win it
    place.appendChild(choice(p, "count_param", COUNT_PARAMS,
      (v) => tu("action.param." + v), "model.count_param",
      { nullKey: "model.count_param_none" }));
    place.appendChild(num(p, "bottom_inset_mm", "model.bottom_inset_mm", { length: true }));
    place.appendChild(num(p, "top_inset_mm", "model.top_inset_mm", { length: true }));
  } else if (p.kind === "fraction") {
    place.appendChild(num(p, "permille", "model.permille", { min: 0 }));
  } else if (p.kind) {
    place.appendChild(num(p, "offset_mm", "model.offset_mm", { length: true }));
  }
  host.appendChild(group("model.inspect.where", place));
  // the sentence the missing handle owes the author: an interior rail of a
  // distributed slot has no authored position of its own to drag
  if (p.kind === "distributed" && (p.count || 0) > 2)
    host.appendChild(el("div", { class: "meta",
      text: t("model.inspect.interior_not_placeable") }));
  host.appendChild(group("model.inspect.made_of",
    requirementRows(slot.requirement, ctx, "frame")));
}

function infillInspector(host, key, ctx) {
  // the whole pane rebuilds on a rule change, because "starts at"/"ends at"
  // appear and disappear with it
  const infill = ctx.spec.infill;
  const member = (infill?.pattern || []).find((m) => m.key === key);
  if (!member) return missing(host, "model.inspect.gone");
  host.appendChild(el("div", { class: "inspect-title" },
    el("b", { text: t("model.inspect.board") }),
    el("bdi", { class: "sku", text: member.key }),
    removeButton(() => {
      infill.pattern.splice(infill.pattern.indexOf(member), 1);
      ctx.onRemove({ kind: "infill", key });
    })));

  host.appendChild(group("model.inspect.all_boards",
    row(sentenceChoice(infill, "orientation", ["vertical", "horizontal"],
          "model.orientation.", "model.orientation", { rerender: true }),
        sentenceChoice(infill, "justification", JUSTIFICATIONS,
          "model.justification.", "model.justification"),
        sentenceChoice(infill, "excess", EXCESS, "model.excess.", "model.excess"),
        num(infill, "edge_margin_mm", "model.edge_margin_mm", { length: true }))));

  const frameKeys = (ctx.spec.frame || []).map((s) => s.key);
  const sizes = row(
    num(member, "face_offset_mm", "model.face_offset_mm", { length: true }),
    num(member, "thickness_mm", "model.thickness_mm", { length: true, min: 0 }));
  // "starts at" / "ends at" are read by ONE length rule, and the schema refuses
  // a member that sets them under any other — so they are offered under that
  // one. The rule itself lives a group down, where the board's products are.
  if (member.requirement?.length_rule === "between_frame") {
    sizes.appendChild(choice(member, "base_ref", frameKeys, (k) => k, "model.base_ref",
      { nullKey: "model.ref_none" }));
    sizes.appendChild(choice(member, "top_ref", frameKeys, (k) => k, "model.top_ref",
      { nullKey: "model.ref_none" }));
  }
  host.appendChild(group("model.inspect.this_board",
    row(keyField(member, "infill", ctx.spec),
        num(member, "width_mm", "model.width_mm", { length: true, min: 1 })),
    gapControl(member),
    sizes));
  host.appendChild(group("model.inspect.made_of",
    requirementRows(member.requirement, ctx, "infill")));
}

function fixingInspector(host, key, ctx) {
  const fix = (ctx.spec.fixings || []).find((f) => f.key === key);
  if (!fix) return missing(host, "model.inspect.gone");
  host.appendChild(el("div", { class: "inspect-title" },
    el("b", { text: t("model.inspect.screws") }),
    el("bdi", { class: "sku", text: fix.key }),
    removeButton(() => {
      ctx.spec.fixings.splice(ctx.spec.fixings.indexOf(fix), 1);
      ctx.onRemove({ kind: "fixing", key });
    })));
  host.appendChild(group("model.inspect.where",
    row(keyField(fix, "fixing", ctx.spec),
        sentenceChoice(fix, "basis", BASES, "model.basis.", "model.basis",
          { rerender: true })),
    basisDiagram(fix.basis),
    unplacedNote(fix.key, ctx.elevation),
    row(num(fix, "qty_per_basis", "model.qty_per_basis", { min: 0 }),
        choice(fix, "qty_param", COUNT_PARAMS, (v) => tu("action.param." + v),
          "model.qty_param", { nullKey: "model.count_param_none" }))));
  host.appendChild(group("model.inspect.made_of",
    requirementRows(fix.requirement, ctx, "fixing")));
}

/** "12 of these are not drawn", when the drawing could not place them all.
 *
 * `per_member_crossing` is counted as members x frame members, so a panel with
 * members that never cross — stiles beside slats — buys fasteners for crossings
 * that are nowhere on the drawing. The read model reports the leftover rather
 * than thickening the dots that ARE there, and this is where an author asking
 * "where do my screws go" finds out that some of them have no answer. */
function unplacedNote(key, elevation) {
  const left = (elevation?.fixings_unplaced || []).find((u) => u.slot_key === key);
  return el("div", { class: "meta inspect-unplaced" },
    ...(left ? [el("span", { text: t("model.fixings_unplaced", { n: left.qty }) })]
             : []));
}

function panelInspector(host, ctx) {
  host.appendChild(el("div", { class: "inspect-title" },
    el("b", { text: t("model.inspect.panel") })));
  host.appendChild(el("div", { class: "meta", text: t("model.inspect.select_hint") }));
  // textContent, not innerHTML: nothing here needs markup, and a surface that
  // never reaches for innerHTML cannot grow an exception to esc() later
  host.appendChild(el("div", { class: "meta", text: t("model.inspect.counts", {
    rails: (ctx.spec.frame || []).length,
    boards: (ctx.spec.infill?.pattern || []).length,
    fixings: (ctx.spec.fixings || []).length,
  }) }));
}
