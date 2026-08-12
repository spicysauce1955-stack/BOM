// Fetch helpers + HTML escaping. No domain logic (ADR-0010).

import { t } from "./i18n.js";

export async function apiGet(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// `quiet`: report the failure by throwing only. A POST the USER pressed a button
// for owes them a dialog; a POST fired by a debounced field as they type (the
// panel preview) owes them silence — an alert per keystroke is not an error
// report, it is a trap. The console line is written either way.
export async function apiSend(method, url, body, { quiet = false } = {}) {
  const r = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text();
    // the user gets a localized sentence; the request line and the server's
    // English body are diagnostics and belong in the console, not in a dialog
    console.error(`${method} ${url} failed:\n${text}`);
    if (!quiet) alert(errorAlertText(text, r.status));
    throw new Error(text);
  }
  return r.json();
}

// Most refusals get the generic "request failed" sentence; a structured one the
// user can act on (a quote that can't be priced because a part has no supplier)
// gets its own — same idea as topology_changed on the read side
// (structure-data.js), but a POST/PUT must pre-empt the generic alert rather
// than replace it after the fact, since apiSend always shows one.
function errorAlertText(bodyText, status) {
  let detail = null;
  try {
    detail = JSON.parse(bodyText)?.detail ?? null;
  } catch {
    /* not JSON — generic message */
  }
  if (detail?.code === "unresolved_supply") {
    return t("quote.unresolved_supply", { n: (detail.unresolved || []).length });
  }
  // Any other refusal that names itself: `error.<code>` renders it with its own
  // params. This is the same contract the read routes use for ReadRefused —
  // without it a coded 422 (a fence model naming a SKU nobody stocks) still fell
  // through to the generic sentence, which is the shape wave H set out to remove.
  if (detail?.code) {
    const key = `error.${detail.code}`;
    const text = t(key, detail.params || {});
    if (text !== key) return text;
  }
  return t("api.request_failed", { status });
}

// verbatim user/expert text must never be interpreted as HTML
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
