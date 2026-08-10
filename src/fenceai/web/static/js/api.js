// Fetch helpers + HTML escaping. No domain logic (ADR-0010).

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
    const t = await r.text();
    alert(`${method} ${url} failed:\n${t}`);
    throw new Error(t);
  }
  return r.json();
}

// verbatim user/expert text must never be interpreted as HTML
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
