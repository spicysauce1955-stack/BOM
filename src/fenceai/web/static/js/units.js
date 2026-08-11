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

// Template params in the display unit: every `*_mm` param converts, and `{u}`
// carries the unit label, so a locale string writes "{width_mm} {u}" once and
// works in both units.
export function unitParams(params = {}) {
  const out = { u: unitLabel() };
  for (const [k, v] of Object.entries(params))
    out[k] = k.endsWith("_mm") ? toDisplayValue(v) : v;
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
