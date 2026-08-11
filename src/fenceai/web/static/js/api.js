// Fetch helpers + HTML escaping. No domain logic (ADR-0010).

import { t } from "./i18n.js";

export async function apiGet(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function apiSend(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    const body = await r.text();
    // the user gets a localized sentence; the request line and the server's
    // English body are diagnostics and belong in the console, not in a dialog
    console.error(`${method} ${url} failed:\n${body}`);
    alert(t("api.request_failed", { status: r.status }));
    throw new Error(body);
  }
  return r.json();
}

// verbatim user/expert text must never be interpreted as HTML
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
