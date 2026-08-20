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
// WHAT THIS PANE IS ALLOWED TO ASK. Describing one board took eighteen controls,
// and the trade describes a panel with about six. The four rules that keep it
// there, each of which is easy to undo one "just one more field" at a time:
//
//   * NOTHING NAMES AN ELEMENT. A board is "Board 2", built from its position in
//     the pattern; the schema `key` is generated and renamed behind a
//     double-click on the chip (model-editor.js), never as a field. `applyRename`
//     below is that rename, and it still carries `base_ref`/`top_ref` — a rail
//     renamed without them authors a document the publish gate refuses, for an
//     edit that looked like a rename.
//   * ONE SPACING CONTROL, not a four-by-two matrix. `spacingMode` reads the
//     (justification, excess) pair the document carries and says which segment
//     it is — and a pair that is NEITHER segment renders as itself under
//     Advanced and is left alone. Opening the editor on a document must never
//     narrow it: all eight pairs stay reachable, three of them only there.
//   * A ZERO IS NOT AN ANSWER. `derivedNum` shows what the panel above actually
//     did, with the reason, dashed — and the moment the author types, the figure
//     is theirs. The derived value is NEVER written to the document by being
//     displayed; only a keystroke writes.
//   * EVERYTHING ELSE IS DEFERRED, NEVER REMOVED. `advancedBox` holds the
//     length rule, option axis, offsets, refs, the preference list and the raw
//     spacing pair, and its summary carries a count when any of them is set —
//     an author who cannot see what they set has lost it.
//     ROLE IS THE ONE EXCEPTION, and it is not a deferral: the part a slot names
//     says what the piece IS, `PartRequirement` refuses a document that says
//     both, so the control did not move behind a disclosure — it left, because
//     what it wrote could no longer be saved.
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
// the SVG builder (createElementNS). `builder-ui`'s `el` is createElement, and
// `document.createElement("svg")` is an HTMLUnknownElement: it takes its CSS,
// reports a computed width, holds its children — and paints nothing at all,
// which is a defect no assertion about the DOM can see.
import { el as svgEl } from "./geom.js";
import { currentLocale, t } from "./i18n.js";
import { gapForOverlap, overlapOf } from "./panel-canvas-geom.js";
import {
  APPROVALS, AXIS_KINDS, BASES, COUNT_PARAMS, EXCESS, JUSTIFICATIONS,
  LENGTH_RULES, PART_DIMENSIONS, PLACEMENT_KINDS, SWATCH_RE,
  defaultEligibility, defaultEligibleMember, defaultPlacement, defaultRequirement,
  eligibilitySource, partSummary, partsByType,
} from "./panel-model.js";
import { fmt, inputStep, toDisplayValue, toMm, tu } from "./units.js";

/** Nothing on the drawing is selected: the panel itself is. */
export const SELECTION_NONE = { kind: "panel", key: null };

// The caller's "the document moved", set for the duration of one render so the
// small field builders below need not each be handed it. Set once per render,
// never read outside one — an inspector rendered without a host has no edits to
// report.
let notify = () => {};
// Whether the Advanced disclosure is open, ACROSS renders. The pane is rebuilt
// on every committed edit and again when the re-price lands, and a `<details>`
// rebuilt closed is a disclosure that shuts itself the moment the author edits
// something inside it — which is the one place they cannot afford to lose their
// place, because it is the place things are hidden.
let advancedOpen = false;

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

/** A number the panel has already answered, shown with the reason it has.
 *
 * A field reading `0` for an edge margin teaches nothing: the fit spread the
 * leftover and the boards actually stand 37 mm off the post, and the one number
 * on screen said none of that. So the DRAWN figure is shown — dashed, with the
 * sentence that explains where it came from — and the field stays editable:
 * typing over it makes the number the author's own, and until they do, nothing
 * is written. Displaying a derived value must never author it, or opening the
 * editor on a document rewrites it.
 *
 * `derived.overrides` is the second case, and it is not the same one: a count
 * deferred to a knowledge param is NOT the authored integer beside it, so the
 * authored number would be a lie however it is styled. */
function derivedNum(obj, key, labelKey, { length = false, min = null, derived = null } = {}) {
  const wrap = el("div", { class: "derived-field" });
  const f = num(obj, key, labelKey, { length, min });
  wrap.appendChild(f);
  if (!derived) return wrap;
  const input = f.querySelector("input");
  if (derived.overrides || !obj[key]) {
    input.value = String(length ? toDisplayValue(derived.value) : derived.value);
    input.classList.add("derived");
    input.dataset.derived = "1";
  }
  wrap.appendChild(el("span", { class: "meta derived-why", text: derived.why }));
  return wrap;
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

// --- what an element is CALLED -----------------------------------------------
//
// Nothing in the trade names a board. A fence is specified as a style, a height,
// a board width, a gap, a rail count and a post spacing — six numbers, none of
// which is an identifier — and the editor asked for a `key` before it asked for
// any of them. So the name is built from what the element IS and where it sits:
// "Rail", "Board", "Board 2", "Fixings". The schema key still exists, is still
// unique, and is still what `base_ref`, `data-slot` and every drag handle hold —
// it has simply stopped being something a person types.

const KIND_WORD = { frame: "rail", infill: "board", fixing: "screws" };

/** Every key of one kind, in document order — which is where the number in
 *  "Board 2" comes from. */
export function keysOfKind(spec, kind) {
  if (kind === "frame") return (spec?.frame || []).map((s) => s.key);
  if (kind === "infill") return (spec?.infill?.pattern || []).map((m) => m.key);
  if (kind === "fixing") return (spec?.fixings || []).map((f) => f.key);
  return [];
}

/** "Rail", "Board 2", "Fixings" — what this element is called on screen.
 *
 * The FIRST of a kind is the bare word: a panel with one set of boards should
 * not have to read "Board 1" to learn there is only one. */
export function elementLabel(spec, kind, key) {
  const word = t(`model.inspect.${KIND_WORD[kind] || "board"}`);
  const idx = keysOfKind(spec, kind).indexOf(key);
  return idx <= 0 ? word : t("model.element_n", { name: word, n: idx + 1 });
}

function rowOf(spec, kind, key) {
  if (kind === "frame") return (spec?.frame || []).find((s) => s.key === key);
  if (kind === "infill") return (spec?.infill?.pattern || []).find((m) => m.key === key);
  if (kind === "fixing") return (spec?.fixings || []).find((f) => f.key === key);
  return null;
}

/** Give an element a new key, and carry everything that points at the old one.
 *
 * This is what `keyField` did while the key was a field, and it is the half
 * that must not be lost with it: a board names the rails it starts and stops at
 * BY KEY, so renaming a rail and leaving those behind authors a document the
 * publish gate refuses with English authoring text — for an edit that looked
 * like a rename. The caller (model-editor.js) owns uniqueness, because it is
 * the one that holds the whole spec's key set; this owns the references. */
export function applyRename(spec, kind, was, now) {
  const target = rowOf(spec, kind, was);
  if (!target || !now || now === was) return was;
  target.key = now;
  if (kind === "frame") reref(spec, was, now);
  return now;
}

function reref(spec, was, now) {
  for (const member of spec?.infill?.pattern || []) {
    if (member.base_ref === was) member.base_ref = now;
    if (member.top_ref === was) member.top_ref = now;
  }
}

// --- what the drawing already answered ---------------------------------------
//
// Read off the server's `PanelElevation` and NEVER recomputed: the fit that
// decides where a board sits has a justification x excess matrix behind it, and
// a JS copy of it would eventually disagree with the cut list the same numbers
// produced. These are readouts of what happened, which is exactly why they are
// allowed to be shown beside the number that did not happen.

const drawnOfKind = (elev, kind, key) => (elev?.members || [])
  .filter((m) => m.kind === kind && (!key || m.slot_key === key));

/** The margin the fit actually left against the first post.
 *
 * `_infill` starts its walk at `fit.edge_margin_start_mm`, so the first drawn
 * rectangle's coordinate along the spread axis IS that margin. */
function drawnMargin(elev, infill) {
  const drawn = drawnOfKind(elev, "infill");
  if (!drawn.length) return null;
  const across = infill?.orientation !== "horizontal";
  return Math.max(0, Math.min(...drawn.map((m) => (across ? m.x_mm : m.y_mm))));
}

/** Where the outermost members of a distributed slot actually sit.
 *
 * `_positions` spreads INCLUSIVE of both ends between `bottom_inset_mm` and
 * `span - top_inset_mm`, and `_frame` centres each member on its position — so
 * the centre of the lowest one is the bottom inset, measured rather than
 * assumed. */
function drawnInsets(elev, slot, key) {
  const drawn = drawnOfKind(elev, "frame", key);
  if (!drawn.length || !elev) return null;
  const along = slot.orientation === "vertical";
  const span = along ? elev.width_mm : elev.height_mm;
  const centres = drawn.map((m) => (along ? m.x_mm + m.w_mm / 2 : m.y_mm + m.h_mm / 2));
  return { bottom_inset_mm: Math.round(Math.min(...centres)),
           top_inset_mm: Math.round(span - Math.max(...centres)) };
}

const paramWord = (p) => tu("action.param." + p);

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

// --- the spacing control -----------------------------------------------------
//
// `justification` x `excess` is eight combinations for ONE decision, and the
// decision a person actually makes is Figma's: spread them out, or keep the
// spacing exact and put the slack somewhere. So two segments say it, and the
// pairs neither segment can say are left ALONE and shown as themselves under
// Advanced — the same rule the variant condition sentence follows. A value the
// editor cannot show is a document it would silently rewrite.

// the three places a leftover can be put once the gaps are exact; `spread_to_fit`
// is not one of them, because spreading IS the other segment
const REMAINDERS = ["start", "end", "center"];

/** Which segment this document's (justification, excess) pair is, or null when
 *  it is one of the pairs only Advanced can say. Pure, and exported, because
 *  the badge that warns "you have set something you cannot see" is computed from
 *  the same answer. */
export function spacingMode(infill) {
  const j = infill?.justification;
  const x = infill?.excess;
  if (j === "spread_to_fit" && x === "space") return "even";
  if (x === "truncate" && REMAINDERS.includes(j)) return "exact";
  return null;
}

function spacingControl(infill, ctx) {
  const mode = spacingMode(infill);
  const box = el("div", { class: "spacing-control" });
  const seg = el("div", { class: "segmented", "data-f": "spacing" });
  const segment = (value, labelKey) => {
    const b = el("button", { type: "button", class: "segment",
                             "data-spacing": value, text: t(labelKey) });
    if (mode === value) b.classList.add("selected");
    b.setAttribute("aria-pressed", mode === value ? "true" : "false");
    b.addEventListener("click", () => {
      if (value === "even") {
        infill.justification = "spread_to_fit";
        infill.excess = "space";
      } else {
        infill.excess = "truncate";
        if (!REMAINDERS.includes(infill.justification)) infill.justification = "center";
      }
      notify({ rerender: true });
    });
    return b;
  };
  seg.append(segment("even", "model.spacing.even"),
             segment("exact", "model.spacing.exact"));
  box.appendChild(el("div", { class: "builder-field" },
    el("span", { class: "meta", text: t("model.spacing") }), seg));

  if (mode === null) {
    // neither segment says this pair, so nothing here pretends one does
    box.appendChild(el("div", { class: "meta", text: t("model.spacing.custom") }));
    return box;
  }
  box.appendChild(el("div", { class: "meta",
    text: t(mode === "even" ? "model.spacing.even_why" : "model.spacing.exact_why") }));

  // The margin is read by the fit under BOTH segments (it is `start`/`end`
  // before any residual is placed), so it is shown under both — hiding a number
  // that still moves the boards is the defect this pane is being cured of. It is
  // the figure "Exactly" turns from a readout into an authored one.
  const drawn = drawnMargin(ctx.elevation, infill);
  box.appendChild(derivedNum(infill, "edge_margin_mm", "model.edge_margin_mm", {
    length: true,
    derived: drawn === null ? null
      : { value: drawn, why: tu("model.derived.margin", { n_mm: drawn }) },
  }));
  if (mode === "exact")
    box.appendChild(choice(infill, "justification", REMAINDERS,
      (v) => t(`model.justification.sentence.${v}`), "model.spacing.remainder"));
  return box;
}

// --- what supplies a slot: the PART it names ---------------------------------
//
// A slot used to be authored as a sku, and this pane picked one. It no longer
// is: the slot names a PART, the part owns the eligibility and the role, and
// `PartRequirement` refuses a document that says both — which is why this pane
// spent an arc showing "no product" on every slot in the demo library and then
// refusing the save that would have fixed it. What the author picks here is a
// name out of the part library; what the pane SHOWS beside it is what that name
// means, so choosing one is not choosing blind.
//
// Four shapes, and the pane branches on them before it renders anything, because
// three of them have no part to pick and a picker offered there authors exactly
// the pair the loader refuses:
//
//   * `part`               — the picker, the part's facts, and what can fill it.
//   * `authored_predicate` — M-VINYL's post and cap: their rule agrees with a
//                            fact about the BAY, which no part can declare. Said
//                            plainly, and the rule itself stays under Advanced.
//   * `authored_members`   — M-LEGACY's rail and screw: a sku list, still edited
//                            under Advanced, because those two are rebuilt per
//                            run from company knowledge and a part would outrank
//                            the rule silently.
//   * `unspecified`        — a slot the "+ Add" button just made. Ask for a part.

/** The part library as a grouped `<select>` — the one control that writes here.
 *
 * It writes `part_id` and, when it writes one, CLEARS in the same act everything
 * the part is now the authority on: `role`, the authored eligibility, and the
 * holder's own dimensions. Not tidiness — three validators refuse those pairs.
 * `_part_or_authored` refuses a slot that names a part and says what the piece
 * is, so leaving the `role` the "+ Add slot" button wrote is a 422 on a field the
 * author cannot see; `_refuse_authored_dimensions` refuses the same slot carrying
 * a `width_mm`, so leaving the 100 mm `defaultMember` wrote is the SAME defect one
 * level up. One place does all of it, so the set can never be half-applied. */
function partSelect(req, ctx, summary, { holder = null, dims = [] } = {}) {
  const sel = el("select", { "data-f": "part" });
  // the empty entry is the prompt, not a value — an author who lands on a fresh
  // slot must read "choose a part", never a part they did not choose
  sel.appendChild(option("", t("model.slot.choose_part"), !req.part_id));
  const labels = new Map((ctx.partTypes || []).map((ty) => [ty.key, ty]));
  for (const { type, parts } of partsByType(ctx.parts)) {
    const ty = labels.get(type);
    const group = el("optgroup",
      { label: ty?.label_i18n?.[currentLocale()] || ty?.label_i18n?.en || type });
    for (const part of parts)
      group.appendChild(option(part.id, partWord(part), req.part_id === part.id));
    sel.appendChild(group);
  }
  // a part the library does not have is still what the document says, and an
  // editor that silently dropped it would rewrite the slot by being opened
  if (summary.missing)
    sel.appendChild(option(req.part_id, req.part_id, true));
  sel.addEventListener("change", () => {
    req.part_id = sel.value;
    if (req.part_id) {
      req.role = "";
      req.eligibility = defaultEligibility();
      // 0 is what an UNDECLARED dimension is here — the elevation renders it
      // `declared=False` rather than drawing a nominal band — so this hands the
      // number to the part rather than inventing one
      for (const dim of dims) if (holder) holder[dim] = 0;
    }
    notify({ rerender: true });
  });
  return field("model.part", sel);
}

/** A part as a person reads it: its localized name, or its id when it has none. */
const partWord = (part) =>
  part.name_i18n?.[currentLocale()] || part.name_i18n?.en || part.id;

/** One declared fact of the part, as an isolated chip.
 *
 * `specChips` hands over `{key, agree, value, unit}` and no prose — it is the
 * import-free module — so the sentence is assembled HERE, out of the bundle.
 * `!=`, `>=`, `<=` and `covers` share `model.chip.other`, which renders the
 * agreement as the symbol the author typed: no demo part exercises them, and an
 * invented phrasing for an untested case is a worse answer than an honest one.
 *
 * A UNIT-BEARING fact goes through the same length path as every other length in
 * this app — a `_len` template carrying `{…_mm}` + `{u}`, rendered with `tu()` —
 * so a part declaring 38 mm reads "3.8 cm" for an author working in centimetres
 * instead of a bare `38` that means nothing until you know which editor wrote it.
 *
 * DIRECTION. Every chip but `supplies` begins with the part's own `key` — a Latin
 * identifier a catalog author typed — followed by a value, and that pair reorders
 * on screen in an RTL page. So those render as `<bdi class="num">`: isolated, and
 * ltr inside, which is the same treatment a SKU and every other figure gets.
 * `supplies` is the one chip that is PROSE ("cut from stock" / "נחתך ממלאי") and
 * it keeps the page's own direction, because forcing ltr on Hebrew is the defect
 * this rule exists to prevent, mirrored.
 *
 * Every field of the chip is DATA a catalog author typed, and it reaches the DOM
 * through `textContent` — `el`'s `text` attribute — so there is no interpolation
 * into markup for `esc()` to guard. That is the stronger half of the rule this
 * pane has kept from the beginning: a surface that never reaches for innerHTML
 * cannot grow an exception to it later. */
function chipText(chip) {
  // `supplies` first, and out: it is the only agreement carrying no value, so its
  // `unit: "mm"` — which the schema REQUIRES — is not a measurement to convert.
  // It means "the bay resolves the length", never "the length is zero mm".
  if (chip.agree === "supplies") return t("model.chip.supplies");
  const len = chip.unit === "mm";
  const key = chip.key;
  const list = Array.isArray(chip.value)
    ? chip.value.map((v) => (len ? toDisplayValue(v) : v)).join(", ") : "";
  switch (chip.agree) {
    case "among":
      return len ? tu("model.chip.among_len", { key, value: list })
                 : t("model.chip.among", { key, value: list });
    case "between":
      return len
        ? tu("model.chip.between_len",
             { key, low_mm: chip.value?.[0], high_mm: chip.value?.[1] })
        : t("model.chip.between",
            { key, low: chip.value?.[0], high: chip.value?.[1] });
    case "==":
      return len ? tu("model.chip.eq_len", { key, value_mm: chip.value })
                 : t("model.chip.eq", { key, value: chip.value });
    default:
      return len
        ? tu("model.chip.other_len",
             { key, agree: chip.agree, value_mm: chip.value })
        : t("model.chip.other", { key, agree: chip.agree, value: chip.value });
  }
}

/** The chip itself. `data-chip` carries the agreement, so a check can find the
 *  chips and say WHICH fact it found without parsing a localized sentence. */
function chipNode(chip) {
  const prose = chip.agree === "supplies";
  return el(prose ? "span" : "bdi", {
    class: `part-chip agree-${chip.agree}${prose ? "" : " num"}`,
    "data-chip": chip.agree, text: chipText(chip),
  });
}

/** "N products can fill this", and which ones.
 *
 * Shut by default and counted on the summary: the count is the fact an author
 * needs at a glance ("is this part supplied at all?"), and the skus are the
 * answer to the question that follows. Both come off the preview the editor
 * already fetched — no request of its own, because the candidate set is already
 * on the wire.
 *
 * The chosen one is marked with a ✓ rather than with a word: it needs no
 * translation, and it survives being read in either direction.
 *
 * `null` when the preview never answered for this slot (`summary.counted`), and
 * that is the honest answer rather than a tidy one: `preview_panel` emits rows for
 * frame, infill and fixings only, so M-VINYL's post and cap — the two slots the
 * rule-authored pane is designed FOR — would otherwise read "0 products can fill
 * this" about a supply nobody measured. A zero is a measurement; silence is not,
 * and the count is only worth printing where it was taken. */
function candidateList(summary) {
  if (!summary.counted) return null;
  const box = el("details", { class: "part-candidates" });
  // `data-candidates` carries the number as well as marking the element, so a
  // check reads the count without parsing a sentence that exists in two languages
  box.appendChild(el("summary", { "data-candidates": String(summary.candidates),
    text: t("model.part.can_fill", { n: summary.candidates }) }));
  const list = el("ul", { class: "part-candidate-list" });
  for (const sku of summary.eligibleSkus) {
    const chosen = sku === summary.chosen;
    const item = el("li", { class: chosen ? "chosen" : null },
      el("bdi", { class: "sku", text: sku }));
    if (chosen) item.appendChild(el("span", { class: "chosen-mark", text: "✓" }));
    list.appendChild(item);
  }
  box.appendChild(list);
  return box;
}

/** The dimensions the PART owns, standing where the fields for them used to be.
 *
 * A width field on a member whose part declares the width is the `role` control
 * one level up: `_refuse_authored_dimensions` refuses that pair too, so typing
 * there produced exactly the unexplainable 422 this arc exists to remove. The
 * CONTROL is gone; the NUMBER must not be. An author still has to see how wide
 * the board is, and see it where they looked for it, or the pane has answered a
 * question by deleting it.
 *
 * Read off the part's own spec — the `unit=mm, agree===, int` fields, which is
 * `Part.dimensions` in Python and the same three-way test `is_dimension` makes.
 * A part declaring none shows a dash: undeclared is what the document then means,
 * and a 0 would read as a measured zero. */
function partDimensions(part, dims) {
  const box = el("div", { class: "part-dims" });
  for (const dim of dims) {
    const declared = (part?.spec || []).find(
      (f) => f.key === dim && f.agree === "==" && f.unit === "mm");
    box.appendChild(row(
      field(`model.${dim}`, el("bdi", { class: "num", "data-dim": dim,
        text: declared ? fmt(declared.value) : "—" })),
      el("span", { class: "meta", text: t("model.dim.from_part") })));
  }
  return box;
}

/** Appends a node that a renderer may decline to build. `appendChild(null)` throws
 *  and `append(null)` writes the word "null" onto the page, so the check is here
 *  once rather than at each call. */
const addIf = (box, node) => { if (node) box.appendChild(node); };

/** What supplies this slot — the pane, branching on which of the four it is.
 *
 *  It READS the requirement and never writes to it. An earlier draft defaulted
 *  `eligibility` here, which made drawing the pane a document edit: opening a slot
 *  dirtied the model, and a shape a render invented is a shape no author chose.
 *  `eligibilitySource` and `partSummary` already answer over an absent field. */
function partField(req, ctx, { slotKey = "", holder = null, dims = [] } = {}) {
  const summary = partSummary(req, {
    parts: ctx.parts, preview: ctx.preview, slotKey });
  const box = el("div", { class: "part-field" });

  if (summary.source === "authored_predicate") {
    box.appendChild(el("div", { class: "meta", text: t("model.slot.by_rule") }));
    addIf(box, candidateList(summary));
    return box;
  }
  if (summary.source === "authored_members") {
    const first = req.eligibility.members[0]?.sku || "";
    box.appendChild(el("div", { class: "meta" },
      el("span", { text: t("model.slot.by_listed_product") }),
      el("bdi", { class: "sku", text: first })));
    addIf(box, candidateList(summary));
    return box;
  }

  box.appendChild(row(partSelect(req, ctx, summary, { holder, dims })));
  if (summary.source === "unspecified") {
    box.appendChild(el("div", { class: "meta", text: t("model.slot.choose_part") }));
    return box;
  }
  if (summary.missing) {
    // named, and not there. Reported as the id it names — an empty select would
    // read as "you never chose one", and the repair is a different one.
    box.appendChild(el("div", { class: "meta" },
      el("bdi", { class: "sku", text: req.part_id }),
      el("span", { text: ` — ${t("model.part.not_in_library")}` })));
    return box;
  }

  const chips = el("div", { class: "part-chips" });
  for (const chip of summary.chips) chips.appendChild(chipNode(chip));
  box.appendChild(chips);
  if (dims.length) box.appendChild(partDimensions(summary.part, dims));
  addIf(box, candidateList(summary));
  // the id and the version, as TEXT. Not a link: there is no Parts tab in this
  // arc, and a link that goes nowhere is worse than a readout that does not
  // pretend to.
  const ref = el("div", { class: "meta part-ref" },
    el("bdi", { class: "sku", text: `${summary.part.id}@v${summary.part.version}` }));
  if (summary.part.status !== "active")
    ref.appendChild(el("span", { text: ` — ${t("model.part.not_published")}` }));
  box.appendChild(ref);
  return box;
}

// --- a requirement and the products that may answer it -----------------------

/** The part of a requirement a person meets first: what supplies it, how many.
 *
 * `slotKey` is the slot's own key, and it is what joins this pane to the preview
 * row: `PreviewPart.eligible_skus` is keyed by it, so a pane rendered without it
 * says "0 products can fill this" about a slot the server just supplied.
 *
 * `holder` and `dims` are the row the requirement BELONGS to and the dimensions
 * that row authors — `PART_DIMENSIONS`. They travel together because naming a
 * part is one act that has to reach both objects: the requirement loses its role
 * and its eligibility, and the holder loses the width the part now states. */
function requirementRows(req, ctx, opts = {}) {
  const box = el("div", { class: "builder-sub" });
  if (!req) return box;
  box.appendChild(partField(req, ctx, opts));
  box.appendChild(row(num(req, "qty", "model.qty", { min: 0 })));
  return box;
}

/** ... and the part it meets when it needs to: cut length, option axis, and the
 *  preference order for the slots that still author one.
 *
 *  ROLE IS NOT HERE, and its absence is the point. The part is the one authority
 *  on what a piece is — `resolve_model_parts` fills `role` from the part's type,
 *  and `PartRequirement` refuses a slot that names a part and says a role too.
 *  Offering the control anyway is what turned "set the role" into a save the
 *  server rejected, on a field the author had every reason to think was theirs.
 *  The word did not leave the system: `ResolvedSlot.role` is still required and
 *  the BOM still reads it. It left AUTHORING. */
function requirementAdvanced(req, ctx, kind) {
  const box = el("div", { class: "builder-sub" });
  if (!req) return box;
  const first = row();
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
  const axes = (ctx.model.option_axes || []).map((a) => a.key);
  first.appendChild(choice(req, "option_axis", axes, (k) => k, "model.option_axis",
    { rerender: true, nullKey: "model.option_axis.none" }));
  box.appendChild(first);
  // The preference list belongs to the slots that GENUINELY author a sku list.
  // On a slot that names a part it is the pair the loader refuses, and on one
  // that declares a predicate it is a list with nothing to order — offering it
  // on either is offering the author a document they can only fix by undoing
  // the edit the editor invited.
  if (eligibilitySource(req) === "authored_members")
    box.appendChild(eligibilityList(req, ctx));

  // A slot binds to AT MOST ONE axis, and then names a SKU per axis value. The
  // SKU must be one of the eligible members — anything else is a product the
  // slot was never allowed to use, and `validate_model` says so.
  if (req.option_axis) {
    const axis = (ctx.model.option_axes || []).find((a) => a.key === req.option_axis);
    req.sku_by_option ??= {};
    for (const value of axis?.values || []) {
      const vrow = row(el("span", { class: "meta",
        text: t("model.sku_for_option", { option: valueLabel(value) }) }));
      const skus = (req.eligibility?.members || []).map((m) => m.sku).filter(Boolean);
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
      // Remove, then insert at the TARGET'S index: the dragged row takes the
      // slot of the row it was dropped on, in both directions. Reviewed as an
      // off-by-one on downward drags; it is not. Removing first does shift the
      // later indices, and that shift is exactly what makes "insert at idx"
      // land on the target's slot rather than after it.
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

// --- Advanced: deferred, never removed ---------------------------------------

// What each kind's requirement looks like when nobody has touched it. Read
// against `panel-model.js`'s `defaultRequirement`/`defaultMember` — the badge is
// a claim about what the AUTHOR set, so a field sitting at the value the "+ Add"
// button gave it is not something they set.
//
// Role is not among them any more, because it is no longer BEHIND the
// disclosure: the part says what a piece is, the control is gone, and a badge
// counting a field nobody can see is the exact lie the count exists to prevent.
const REQUIREMENT_DEFAULTS = {
  frame: { length_rule: null },
  infill: { length_rule: "panel_height" },
  fixing: { length_rule: null },
};

/** How many things behind the disclosure are NOT at their default.
 *
 * The whole risk of deferring a field is that an author sets it, forgets, and
 * then reads a panel that does not match the five controls in front of them. So
 * the summary counts. */
function advancedCount(kind, { req = null, member = null, infill = null,
                               placement = null, fixing = null } = {}) {
  const base = REQUIREMENT_DEFAULTS[kind] || {};
  let n = 0;
  if (req) {
    if ((req.length_rule ?? null) !== (base.length_rule ?? null)) n += 1;
    if (req.overlap_mm) n += 1;
    if (req.option_axis) n += 1;
    if ((req.eligibility?.members || []).length > 1) n += 1;
  }
  if (member) {
    if (member.face_offset_mm) n += 1;
    // not counted when the part owns it: the control is not behind the
    // disclosure at all then, and a badge counting what nobody can see is the
    // lie this count exists to prevent
    if (!req?.part_id && member.thickness_mm) n += 1;
    if (member.base_ref) n += 1;
    if (member.top_ref) n += 1;
  }
  // a pair no segment can say is, by definition, only visible in here
  if (infill && spacingMode(infill) === null) n += 1;
  if (placement?.count_param) n += 1;
  if (fixing?.qty_param) n += 1;
  return n;
}

function advancedBox(count, ...children) {
  const summary = el("summary", {},
    el("span", { text: t("model.advanced") }));
  if (count > 0)
    summary.appendChild(el("span", { class: "tag medium advanced-badge",
                                     text: t("model.advanced_set", { n: count }) }));
  const box = el("details", { class: "inspect-advanced",
                              "data-advanced-set": String(count) },
    summary,
    el("div", { class: "meta", text: t("model.advanced_hint") }),
    ...children);
  box.open = advancedOpen;
  box.addEventListener("toggle", () => { advancedOpen = box.open; });
  return box;
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
  const svg = svgEl("svg", { class: "basis-diagram", viewBox: "0 0 60 40",
                             width: "90", height: "60", "aria-hidden": "true" });
  for (const y of [5, 29])
    svgEl("rect", { class: "basis-rail", x: "2", y: String(y),
                    width: "56", height: "6" }, svg);
  for (const x of [6, 26, 46])
    svgEl("rect", { class: "basis-board", x: String(x), y: "2",
                    width: "8", height: "36" }, svg);
  for (const [cx, cy] of DIAGRAM_DOTS[basis] || [])
    svgEl("circle", { class: "basis-dot", cx: String(cx), cy: String(cy),
                      r: "3" }, svg);
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
 * internal detail with exactly two doors — this one and `renderInspector`.
 *
 * An axis key IS typed, and that is not the `key` field this pane deleted: an
 * axis is referred to by name in `option_axis` and `sku_by_option`, has no
 * position to be numbered from, and is authored once per model rather than once
 * per board. */
export function renderAxisEditor(host, { model, onChange = () => {} } = {}) {
  if (!host) return;
  notify = onChange;
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
  selection = SELECTION_NONE, spec, model, products = {}, parts = [],
  partTypes = [], elevation = null, preview = null,
  onChange = () => {}, onRemove = () => {}, onSelect = () => {},
} = {}) {
  if (!host) return;
  notify = onChange;
  host.innerHTML = "";
  if (!spec || !model) return;
  // `elevation` AND `preview`: the elevation is the drawing (what could not be
  // placed), the preview's `parts` rows are the SUPPLY (which products can fill
  // each slot). They are two different readouts of the same response and the
  // pane needs both — handed the drawing alone, the part picker counts every
  // candidate set as empty and tells the author nothing can supply anything.
  const ctx = { products, parts, partTypes, model, spec, elevation, preview,
                onRemove, onSelect };
  switch (selection?.kind) {
    case "frame": return frameInspector(host, selection.key, ctx);
    case "infill": return infillInspector(host, selection.key, ctx);
    case "fixing": return fixingInspector(host, selection.key, ctx);
    case "post": case "cap": return postInspector(host, selection.kind, ctx);
    default: return panelInspector(host, ctx);
  }
}

function missing(host, key) {
  host.appendChild(el("div", { class: "meta", text: t(key) }));
}

/** The name of the thing being edited, and the one destructive action on it.
 *
 * The name is generated, so this is a readout and not a field. The rename lives
 * on the chip in the element list, behind a double-click — the title says so
 * rather than leaving it undiscoverable. */
function titleBar(ctx, kind, key, onRemove) {
  return el("div", { class: "inspect-title", "data-element": `${kind}:${key}` },
    el("b", { text: elementLabel(ctx.spec, kind, key) }),
    el("span", { class: "meta rename-hint", text: t("model.rename_hint") }),
    removeButton(onRemove));
}

function frameInspector(host, key, ctx) {
  const slot = (ctx.spec.frame || []).find((s) => s.key === key);
  if (!slot) return missing(host, "model.inspect.gone");
  host.appendChild(titleBar(ctx, "frame", key, () => {
    ctx.spec.frame.splice(ctx.spec.frame.indexOf(slot), 1);
    ctx.onRemove({ kind: "frame", key });
  }));

  const place = row(
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
  const where = group("model.inspect.where", place);
  if (p.kind === "distributed") {
    const drawn = drawnOfKind(ctx.elevation, "frame", key).length;
    // a knowledge PARAM, not an authored integer: rail count ladders with height
    // and a company rule must still be able to win it — so when one is named,
    // the count on screen is the rule's answer and says whose it is
    const why = p.count_param
      ? { value: drawn || p.count, overrides: true,
          why: t("model.derived.from_param", { param: paramWord(p.count_param) }) }
      : drawn
        ? { value: drawn, why: t("model.derived.rails", { n: drawn }) }
        : null;
    where.appendChild(derivedNum(p, "count", "model.count", { min: 0, derived: why }));
    const insets = drawnInsets(ctx.elevation, slot, key);
    for (const side of ["bottom_inset_mm", "top_inset_mm"])
      where.appendChild(derivedNum(p, side, `model.${side}`, {
        length: true,
        derived: insets === null ? null
          : { value: insets[side], why: tu("model.derived.at", { n_mm: insets[side] }) },
      }));
  } else if (p.kind === "fraction") {
    where.appendChild(num(p, "permille", "model.permille", { min: 0 }));
  } else if (p.kind) {
    where.appendChild(num(p, "offset_mm", "model.offset_mm", { length: true }));
  }
  host.appendChild(where);
  // the sentence the missing handle owes the author: an interior rail of a
  // distributed slot has no authored position of its own to drag
  if (p.kind === "distributed" && (p.count || 0) > 2)
    host.appendChild(el("div", { class: "meta",
      text: t("model.inspect.interior_not_placeable") }));
  host.appendChild(group("model.inspect.made_of",
    requirementRows(slot.requirement, ctx,
      { slotKey: key, holder: slot, dims: PART_DIMENSIONS.frame })));
  host.appendChild(advancedBox(
    advancedCount("frame", { req: slot.requirement, placement: p }),
    p.kind === "distributed"
      ? row(choice(p, "count_param", COUNT_PARAMS, paramWord, "model.count_param",
          { rerender: true, nullKey: "model.count_param_none" }))
      : el("span"),
    requirementAdvanced(slot.requirement, ctx, "frame")));
}

function infillInspector(host, key, ctx) {
  // the whole pane rebuilds on a rule change, because "starts at"/"ends at"
  // appear and disappear with it
  const infill = ctx.spec.infill;
  const member = (infill?.pattern || []).find((m) => m.key === key);
  if (!member) return missing(host, "model.inspect.gone");
  host.appendChild(titleBar(ctx, "infill", key, () => {
    infill.pattern.splice(infill.pattern.indexOf(member), 1);
    ctx.onRemove({ kind: "infill", key });
  }));

  // The width is the PART's when the member names one — `partDimensions` shows it
  // a few lines down, read-only. Offering the field as well is the `role` defect
  // one level up: `_refuse_authored_dimensions` refuses the pair, so a number
  // typed here is a 422 the author cannot connect to anything they did.
  const ownsSize = !member.requirement?.part_id;
  host.appendChild(group("model.inspect.this_board",
    ownsSize
      ? row(num(member, "width_mm", "model.width_mm", { length: true, min: 1 }))
      : el("span"),
    gapControl(member),
    requirementRows(member.requirement, ctx,
      { slotKey: key, holder: member, dims: PART_DIMENSIONS.infill })));

  host.appendChild(group("model.inspect.all_boards",
    row(sentenceChoice(infill, "orientation", ["vertical", "horizontal"],
      "model.orientation.", "model.orientation", { rerender: true })),
    spacingControl(infill, ctx)));

  const frameKeys = (ctx.spec.frame || []).map((s) => s.key);
  // `face_offset_mm` is the member's own — where it sits on the face, which is a
  // fact about this PANEL and not about the piece — so it stays whoever supplies
  // it. `thickness_mm` is the part's, on the same terms as the width above.
  const sizes = row(
    num(member, "face_offset_mm", "model.face_offset_mm", { length: true }),
    ...(ownsSize
      ? [num(member, "thickness_mm", "model.thickness_mm",
             { length: true, min: 0 })]
      : []));
  // "starts at" / "ends at" are read by ONE length rule, and the schema refuses
  // a member that sets them under any other — so they are offered under that
  // one. The rule itself is one row up, in the same disclosure.
  if (member.requirement?.length_rule === "between_frame") {
    sizes.appendChild(choice(member, "base_ref", frameKeys, (k) => k, "model.base_ref",
      { nullKey: "model.ref_none" }));
    sizes.appendChild(choice(member, "top_ref", frameKeys, (k) => k, "model.top_ref",
      { nullKey: "model.ref_none" }));
  }
  host.appendChild(advancedBox(
    advancedCount("infill", { req: member.requirement, member, infill }),
    requirementAdvanced(member.requirement, ctx, "infill"),
    sizes,
    // the raw pair, always offered: three of the eight (justification, excess)
    // combinations are sayable nowhere else, and a document carrying one must be
    // editable rather than merely preserved
    row(sentenceChoice(infill, "justification", JUSTIFICATIONS,
          "model.justification.", "model.justification", { rerender: true }),
        sentenceChoice(infill, "excess", EXCESS, "model.excess.", "model.excess",
          { rerender: true }))));
}

function fixingInspector(host, key, ctx) {
  const fix = (ctx.spec.fixings || []).find((f) => f.key === key);
  if (!fix) return missing(host, "model.inspect.gone");
  host.appendChild(titleBar(ctx, "fixing", key, () => {
    ctx.spec.fixings.splice(ctx.spec.fixings.indexOf(fix), 1);
    ctx.onRemove({ kind: "fixing", key });
  }));
  host.appendChild(group("model.inspect.where",
    row(sentenceChoice(fix, "basis", BASES, "model.basis.", "model.basis",
      { rerender: true })),
    basisDiagram(fix.basis),
    unplacedNote(fix.key, ctx.elevation),
    derivedNum(fix, "qty_per_basis", "model.qty_per_basis", {
      min: 0,
      derived: fix.qty_param
        ? { value: fix.qty_per_basis || 1, overrides: true,
            why: t("model.derived.from_param", { param: paramWord(fix.qty_param) }) }
        : null,
    })));
  host.appendChild(group("model.inspect.made_of",
    requirementRows(fix.requirement, ctx, { slotKey: key })));
  host.appendChild(advancedBox(
    advancedCount("fixing", { req: fix.requirement, fixing: fix }),
    row(choice(fix, "qty_param", COUNT_PARAMS, paramWord, "model.qty_param",
      { rerender: true, nullKey: "model.count_param_none" })),
    requirementAdvanced(fix.requirement, ctx, "fixing")));
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

/** The post the bay stands between, and the cap on top of it.
 *
 * The two parts of a fence that had NO editor at all until now — `model.post`
 * and `model.post.cap` were reachable only through the raw JSON box, and they
 * are not on the panel spec, so no chip and no rectangle led to them.
 *
 * A post is chosen by WHERE IT STANDS as much as by what it is: end, line and
 * corner posts are routed on different faces and are different products. That
 * is a rule over the catalog rather than a list of skus, which is why a post's
 * eligibility is so often a predicate — and why this pane says so plainly
 * instead of showing an empty product list.
 */
function postInspector(host, kind, ctx) {
  const post = ctx.model.post;
  if (!post) {
    host.appendChild(el("div", { class: "inspect-title" },
      el("b", { text: t("model.inspect.posts") })));
    host.appendChild(el("div", { class: "meta", text: t("model.post_none") }));
    const add = el("button", { type: "button", "data-act": "add-post",
                               text: t("model.add_post") });
    add.addEventListener("click", () => {
      ctx.model.post = { key: "post", requirement: defaultRequirement("post"),
                         cap: null };
      notify({ rerender: true });
    });
    host.appendChild(add);
    return;
  }

  host.appendChild(el("div", { class: "inspect-title" },
    el("b", { text: t("model.inspect.posts") }),
    el("bdi", { class: "sku", text: drawnPostSku(ctx.elevation) }),
    removeButton(() => {
      ctx.model.post = null;
      ctx.onRemove({ kind: "post", key: "post" });
    })));

  host.appendChild(group("model.inspect.the_post",
    requirementRows(post.requirement, ctx,
      { slotKey: post.key || "post" })));

  // The cap NESTS in the post, and reads the post it caps — so it is offered
  // after it, never beside it. That ordering is the model's, not a layout
  // choice: a cap's predicate is only answerable because the post is chosen.
  const capRow = row();
  const toggle = el("button", { type: "button", "data-act": "toggle-cap",
    text: t(post.cap ? "model.remove_cap" : "model.add_cap") });
  toggle.addEventListener("click", () => {
    post.cap = post.cap ? null : defaultRequirement("cap");
    notify({ rerender: true });
  });
  capRow.appendChild(toggle);
  if (post.cap && drawnCapSku(ctx.elevation))
    capRow.appendChild(el("bdi", { class: "sku", text: drawnCapSku(ctx.elevation) }));
  const capGroup = group("model.inspect.the_cap", capRow);
  if (post.cap)
    capGroup.appendChild(requirementRows(post.cap, ctx, { slotKey: "cap" }));
  host.appendChild(capGroup);
}

// what the SERVER resolved for this bay — a readout, never a second answer
const drawnPostSku = (elev) => (elev?.posts || [])[0]?.sku || "";
const drawnCapSku = (elev) => (elev?.posts || [])[0]?.cap_sku || "";

function panelInspector(host, ctx) {
  host.appendChild(el("div", { class: "inspect-title" },
    el("b", { text: t("model.inspect.panel") })));
  host.appendChild(el("div", { class: "meta", text: t("model.inspect.select_hint") }));
  // the one part of the fence with no rectangle of its own when a model has not
  // declared it — so the panel pane is where it has to be reachable from
  const posts = el("button", { type: "button", "data-act": "edit-posts",
                               text: t("model.inspect.posts") });
  posts.addEventListener("click", () => ctx.onSelect({ kind: "post", key: "post" }));
  host.appendChild(posts);
  // textContent, not innerHTML: nothing here needs markup, and a surface that
  // never reaches for innerHTML cannot grow an exception to esc() later
  host.appendChild(el("div", { class: "meta", text: t("model.inspect.counts", {
    rails: (ctx.spec.frame || []).length,
    boards: (ctx.spec.infill?.pattern || []).length,
    fixings: (ctx.spec.fixings || []).length,
  }) }));
}
