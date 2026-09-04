// Lightweight i18n: JSON tables + data-i18n walker. No framework (spec §4).
// Task 1 ships the mechanism with English; Task 10 completes Hebrew + RTL default.

import { state, emit } from "./state.js";

const tables = {};  // locale -> {key: string}

export function currentLocale() {
  return state.locale;
}

// A salesperson is explicitly non-technical, so the same control needs
// different WORDS rather than a different control: "Height intent" is the same
// button as "How tall", and "⚙ Generate strategy" is "⚙ Work out the fence".
//
// So one optional layer, resolved here rather than at ~200 call sites: in sales
// mode `sales.<key>` wins if it exists, and every key without one falls straight
// through. That makes the sales vocabulary a short OVERRIDE LIST — only the
// words that are actually wrong for a salesperson — instead of a second full
// bundle that would drift from this one the first time anybody edited either.
//
// It reads `state.role` rather than importing role.js, which would be a cycle
// (role.js emits through state.js, and this module is imported by nearly
// everything). Same reason units.js reads `state.units`.
function lookup(table, key) {
  if (state.role === "sales") {
    const plain = table[`sales.${key}`];
    if (plain !== undefined) return plain;
  }
  return table[key];
}

export function t(key, params = {}) {
  const table = tables[state.locale] || {};
  let s = lookup(table, key) ?? lookup(tables.en || {}, key) ?? key;
  for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}

export async function loadLocale(locale) {
  if (tables[locale]) return;
  try {
    const r = await fetch(`i18n/${locale}.json`);
    tables[locale] = r.ok ? await r.json() : {};
  } catch {
    tables[locale] = {};
  }
}

export async function setLocale(locale) {
  await loadLocale(locale);
  state.locale = locale;
  localStorage.setItem("fenceai.locale", locale);
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === "he" ? "rtl" : "ltr";
  applyStatic();
  emit("locale-changed", locale);
}

export function applyStatic() {
  for (const node of document.querySelectorAll("[data-i18n]"))
    node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-placeholder]"))
    node.placeholder = t(node.dataset.i18nPlaceholder);
  for (const node of document.querySelectorAll("[data-i18n-title]"))
    node.title = t(node.dataset.i18nTitle);
}

export async function initI18n() {
  const stored = localStorage.getItem("fenceai.locale") || "he";  // Hebrew-first (spec §4)
  await loadLocale("en");
  await setLocale(stored);
}
