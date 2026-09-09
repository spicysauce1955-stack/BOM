// Read-only public definitions. This module owns #published-parts only.
import { apiGet, esc } from "./api.js";
import { currentLocale, t } from "./i18n.js";
import { on, state } from "./state.js";

let receipt = null;
let request = 0;

// Public quantities have finer precision than private integer-mm geometry.
// Render milli-units without the geometry editor's integer rounding.
export function quantityText(value, units = state.units) {
  if (!value || !Number.isSafeInteger(value.amount_milli)) return value?.key ?? "";
  const cm = value.unit === "mm" && units === "cm";
  const places = cm ? 4 : 3;
  const amount = BigInt(value.amount_milli);
  const digits = (amount < 0n ? -amount : amount).toString().padStart(places + 1, "0");
  const fraction = digits.slice(-places).replace(/0+$/, "");
  return `${amount < 0n ? "-" : ""}${digits.slice(0, -places)}${fraction ? "." + fraction : ""} ${cm ? "cm" : value.unit}`;
}

function render() {
  if (!receipt) return;
  const status = document.getElementById("published-parts-status");
  const list = document.getElementById("published-parts-list");
  if (!receipt.loaded) {
    status.textContent = t("published.empty"); list.replaceChildren(); return;
  }
  const query = document.getElementById("published-parts-search").value.trim().toLowerCase();
  const parts = receipt.definitions.filter((p) =>
    `${p.id} ${Object.values(p.name_i18n).join(" ")}`.toLowerCase().includes(query));
  status.textContent = t("published.count", { n: parts.length, id: receipt.snapshot_id });
  list.innerHTML = parts.map((p) => {
    const hashes = new Set([...p.contributing_sources, ...p.cites.map((c) => c.belongs_to),
      ...p.spec.flatMap((s) => (s.provenance.cites || []).map((c) => c.belongs_to))]);
    const sources = receipt.source_docs.filter((d) => hashes.has(d.content_hash));
    return `<article class="card">
      <h4 dir="auto">${esc(p.name_i18n[currentLocale()] || p.name_i18n.en || p.id)}</h4>
      <p>${esc(t(`published.${p.status}`))} · <bdi class="sku">${esc(p.id)}</bdi></p>
      <ul>${p.spec.map((s) => `<li><bdi>${esc(s.key)}</bdi> <bdi>${esc(s.agree)}</bdi> <bdi class="num">${esc(quantityText(s.value))}</bdi>
        <bdi>${esc((s.value?.value_raw || []).join("; "))}</bdi></li>`).join("")}</ul>
      <details><summary>${esc(t("published.evidence"))}</summary>
        <pre dir="ltr">${esc(JSON.stringify({ part: p, source_docs: sources }, null, 2))}</pre>
      </details>
    </article>`;
  }).join("");
}

async function refresh() {
  const ticket = ++request;
  document.getElementById("published-parts-status").textContent = t("published.loading");
  try {
    const data = await apiGet("/api/knowledge/parts");
    if (ticket !== request) return;
    receipt = data;
    render();
  } catch {
    if (ticket !== request) return;
    receipt = null;
    document.getElementById("published-parts-list").replaceChildren();
    document.getElementById("published-parts-status").textContent = t("published.error");
  }
}

export function initPublishedParts() {
  document.getElementById("published-parts-search").addEventListener("input", render);
  document.getElementById("published-parts-refresh").addEventListener("click", refresh);
  on("tab-changed", (name) => { if (name === "knowledge") refresh(); });
  on("locale-changed", render);
  on("units-changed", render);
}
