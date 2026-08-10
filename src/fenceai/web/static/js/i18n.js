// Lightweight i18n: JSON tables + data-i18n walker. No framework (spec §4).
// Task 1 ships the mechanism with English; Task 10 completes Hebrew + RTL default.

import { state, emit } from "./state.js";

const tables = {};  // locale -> {key: string}

export function currentLocale() {
  return state.locale;
}

export function t(key, params = {}) {
  const table = tables[state.locale] || {};
  let s = table[key] ?? (tables.en || {})[key] ?? key;
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
  const stored = localStorage.getItem("fenceai.locale") || "en";
  await loadLocale("en");
  await setLocale(stored);
}
