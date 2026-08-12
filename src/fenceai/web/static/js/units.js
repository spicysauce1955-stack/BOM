// Display units (mm | cm) — a PRESENTATION preference only.
//
// Storage stays int millimetres everywhere (ADR-0002): this module converts on
// the way out (mm -> field value / label) and on the way in (field value -> mm),
// and nothing it returns is ever sent to the API un-converted. The raw JSON
// editors (knowledge actions, inventory JSON) deliberately keep showing mm —
// they are the storage representation, not a rendered field.

import { emit, state } from "./state.js";
import { t } from "./i18n.js";

export const UNITS = ["mm", "cm"];
const MM_PER_UNIT = { mm: 1, cm: 10 };

// mm -> display number. cm keeps one decimal, with the trailing ".0" trimmed so
// whole centimetres read "120", not "120.0" (Number division does the trimming).
export function toDisplayValue(mm, unit = state.units) {
  const n = Number(mm);
  if (!Number.isFinite(n)) return mm;
  const r = Math.round(n);
  return unit === "cm" ? r / 10 : r;
}

// display number -> int mm. The ONLY direction that touches stored data.
export function toMm(value, unit = state.units) {
  const n = typeof value === "number" ? value : parseFloat(value);
  if (!Number.isFinite(n)) return null;
  return Math.round(n * (MM_PER_UNIT[unit] ?? 1));
}

// A typed length from the draw tool -> int mm. An explicit trailing unit always
// wins ("250cm" -> 2500, "1.2m"/"1.2מ" -> 1200, "80mm" -> 80). A bare number is
// read in the ACTIVE unit, with one exception: in mm mode a value under 100 is
// metres ("4" -> 4000), because sub-100 mm entries are implausible while drawing.
// That shortcut does NOT apply in cm mode, where sub-100 values are the common
// case (anything under a metre).
export function parseTypedLength(buf, unit = state.units) {
  const m = /^(\d+(?:\.\d+)?|\.\d+)(mm|cm|m|מ)?$/.exec(buf);
  if (!m) return null;
  const v = parseFloat(m[1]);
  if (!(v > 0)) return null;
  const mm = m[2] === "mm" ? v : m[2] === "cm" ? v * 10 : m[2] ? v * 1000
    : unit === "mm" && v < 100 ? v * 1000 : toMm(v, unit);
  return Math.round(mm);
}

export function unitLabel(unit = state.units) {
  return t(`units.${unit}`);
}

// <input step> for a length field: 1 mm, or 0.1 cm (= the same 1 mm resolution)
export function inputStep(unit = state.units) {
  return unit === "cm" ? "0.1" : "1";
}

// <input step> for a field that snaps to `snapMm` (10 mm snap -> step 1 in cm)
export function snapStep(snapMm, unit = state.units) {
  return String(toDisplayValue(snapMm, unit));
}

export function fmt(mm) {          // number only (callers add their own .num span)
  return String(toDisplayValue(mm));
}

export function fmtLen(mm) {       // number + unit label
  return `${fmt(mm)} ${unitLabel()}`;
}

// Enum VALUES that are read as words inside a sentence (post kind, mounting,
// base surface, vertical mode, post orientation) — the same lexicon the backend
// applies to decision prose (decisions/explain.py _ENUM_WORDS). Ids, SKUs and
// knowledge refs are NOT in this set: they stay verbatim in every language.
const ENUM_PARAMS = new Set(["kind", "mounting", "surface", "surfaces", "vertical",
  "mode", "chosen"]);

export function enumWord(value) {
  const key = `enum.${value}`;
  const word = t(key);
  return word === key ? value : word;   // unknown value: show it raw, never blank
}

// What a requirement IS — post | cap | concrete | rail | screw | infill | spacer |
// gate_kit (`demand/derive.py:RequirementLine.role`). Its own lexicon rather than
// a few more `enum.*` keys, because the two vocabularies COLLIDE: `concrete` is a
// base surface AND a role, and "the slab it stands on" is not "the bag you pour".
// Same mechanism as enumWord, one namespace along.
export function roleWord(value) {
  const key = `role.${value}`;
  const word = t(key);
  return word === key ? value : word;   // unknown role: show it raw, never blank
}

// Display params for a template: every `*_mm` param converts to the display unit,
// enum params become words in the current language, and `{u}` carries the unit
// label — so a locale string writes "{width_mm} {u}" once and works in both units.
export function unitParams(params = {}) {
  const out = { u: unitLabel() };
  for (const [k, v] of Object.entries(params)) {
    if (k.endsWith("_mm")) out[k] = toDisplayValue(v);
    // supply warnings put the role in the middle of a Hebrew sentence, so a raw
    // "rail" there is untranslated English in a Hebrew-first UI
    else if (k === "role") out[k] = roleWord(v);
    else if (ENUM_PARAMS.has(k)) {
      // backend warning params arrive pre-joined ("soil, masonry_wall") — map each
      out[k] = Array.isArray(v) ? v.map(enumWord).join(", ")
        : typeof v === "string" ? v.split(", ").map(enumWord).join(", ") : v;
    } else out[k] = v;
  }
  return out;
}

export function tu(key, params = {}) {
  return t(key, unitParams(params));
}

export function currentUnit() {
  return state.units;
}

export function setUnits(unit) {
  if (!UNITS.includes(unit) || unit === state.units) return;
  state.units = unit;
  localStorage.setItem("fenceai.units", unit);
  updateUnitsButton();
  emit("units-changed", unit);
}

export function toggleUnits() {
  setUnits(state.units === "mm" ? "cm" : "mm");
}

export function updateUnitsButton() {
  const btn = document.getElementById("btn-units");
  if (!btn) return;
  btn.textContent = t("units.button", { u: unitLabel() });
  btn.title = t("units.toggle_title");
}

export function initUnits() {
  const stored = localStorage.getItem("fenceai.units");
  state.units = UNITS.includes(stored) ? stored : "mm";
  updateUnitsButton();
}
