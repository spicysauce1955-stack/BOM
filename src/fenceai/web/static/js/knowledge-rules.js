// The Rules pane of the Knowledge tab: the rules this engine actually applies.
//
// Split out of tabs.js because the list it renders was the whole complaint the
// redesign started from. `GET /api/knowledge` returns EVERY version, and the
// old renderer drew a card for each one — so the tab opened with hundreds of
// cards, the overwhelming majority of them `proposed` candidates that the
// Review tab already owns behind its own filtered endpoint. A reader looking
// for the rules in force had to find them among the ones nobody had decided on
// yet.
//
// Three things follow from that, and they are the pane's whole contract:
//
//   * `proposed` versions are EXCLUDED, not merely sorted downward. They are
//     still counted, and the count is stated with a pointer to Review — a
//     silent filter would just move the confusion.
//   * retired versions collapse into a <details>. They are history, and history
//     is worth keeping reachable and not worth reading first.
//   * `scope` and `actions` render as chips and sentences via builder-ui.js,
//     not as `JSON.stringify`. See the note on `actionSentence` there for why
//     the phrasing lives beside the builder that writes it.
//
// Owns `#pane-k-rules` and nothing else. The sub-navigation above it belongs to
// tabs.js (the module whose job is already "switch between panels"), and gets
// its badge numbers through the `knowledge-counts` event rather than by reading
// anything in here.

import { apiGet, apiSend, esc } from "./api.js";
import { actionSentence, loadCatalogProducts, scopeChips } from "./builder-ui.js";
import { currentLocale, t } from "./i18n.js";
import { emit } from "./state.js";

// The filter state is module-local rather than in state.js on purpose: nothing
// outside this pane can act on it, and a project reload must not reset it.
const filters = { type: "", q: "", showRetired: false };

const TYPES = ["hard_constraint", "company_rule", "preference", "heuristic", "fact"];

export function initKnowledgeRules() {
  const type = document.getElementById("k-filter-type");
  type.addEventListener("change", () => {
    filters.type = type.value;
    applyFilters();
  });

  const search = document.getElementById("k-filter-search");
  search.addEventListener("input", () => {
    filters.q = search.value.trim().toLowerCase();
    applyFilters();
  });

  const retired = document.getElementById("k-filter-retired");
  retired.addEventListener("change", () => {
    filters.showRetired = retired.checked;
    document.getElementById("k-retired-group").open = retired.checked;
  });
}

/** Re-fetch and redraw. Named for what it draws, not for the tab it sits in —
 *  every caller that used to say `renderKnowledge()` means this. */
export async function renderKnowledgeRules() {
  const versions = await apiGet("/api/knowledge");
  const products = await loadCatalogProducts();
  renderTypeOptions();

  // one pass, three buckets: what is in force, what was retired, and what has
  // not been decided on at all
  const active = [], retired = [];
  let proposed = 0;
  for (const v of versions) {
    if (v.status === "proposed") proposed++;
    else if (v.status === "retired") retired.push(v);
    else active.push(v);
  }

  const host = document.getElementById("knowledge-list");
  host.innerHTML = "";
  for (const v of active) host.appendChild(card(v, products, false));

  const retiredHost = document.getElementById("k-retired-list");
  retiredHost.innerHTML = "";
  for (const v of retired) retiredHost.appendChild(card(v, products, true));

  const group = document.getElementById("k-retired-group");
  group.hidden = !retired.length;
  group.open = filters.showRetired;
  group.querySelector("summary").textContent = retired.length === 1
    ? t("knowledge.retired_one")
    : t("knowledge.retired_n", { n: retired.length });

  // the excluded candidates are stated, never silently dropped
  const note = document.getElementById("k-excluded-note");
  note.hidden = !proposed;
  if (proposed)
    note.innerHTML = proposed === 1
      ? esc(t("knowledge.excluded_note_one"))
      : esc(t("knowledge.excluded_note", { n: proposed }));

  applyFilters();
  emit("knowledge-counts", { rules: active.length, proposed });
}

/** The type options, rebuilt on every render rather than wired once at init.
 *
 *  They carry localized labels, and `new Option(...)` leaves no `data-i18n` for
 *  the walker to find — so a select built once at startup keeps its English
 *  words after the user switches to Hebrew. The "All types" entry is a literal
 *  in index.html and localizes itself; only the five type words are built here.
 */
function renderTypeOptions() {
  const sel = document.getElementById("k-filter-type");
  const chosen = filters.type;
  for (const stale of [...sel.options].slice(1)) stale.remove();
  for (const ty of TYPES) sel.appendChild(new Option(t("type." + ty), ty));
  sel.value = chosen;
}

/** Hide what the filter bar excludes, and say how many are left.
 *
 *  A filter that HIDES rather than re-renders is deliberate: re-fetching on
 *  every keystroke would put the list behind the network, and the retire
 *  buttons already wired on each card would be rebuilt under the user's cursor.
 */
function applyFilters() {
  let shown = 0;
  for (const el of document.querySelectorAll("#knowledge-list .rule-card")) {
    const ok = (!filters.type || el.dataset.type === filters.type)
      && (!filters.q || el.dataset.search.includes(filters.q));
    el.hidden = !ok;
    if (ok) shown++;
  }
  document.getElementById("k-filter-count").textContent =
    t("knowledge.n_in_force", { n: shown });
}

function card(v, products, isRetired) {
  const div = document.createElement("div");
  div.className = "card rule-card" + (isRetired ? " is-retired" : "");
  div.dataset.type = v.type;
  const title = v.title_i18n?.[currentLocale()] || v.title || "";
  // searched lowercase and unescaped: this is a dataset value compared against
  // the query, never interpolated into the document
  div.dataset.search = `${v.object_id} ${title}`.toLowerCase();

  let html = `<div class="rule-row1">
      <span class="tag ${v.type}">${t("type." + v.type)}</span>
      ${isRetired ? `<span class="tag retired">${t("status.retired")}</span>` : ""}
      <b class="rule-id"><bdi>${esc(v.object_id)}@v${v.version}</bdi></b>
      <span class="rule-title" dir="auto">${esc(title)}</span>
    </div>
    <div class="rule-scope">${scopeChips(v.scope)}</div>
    <ul class="actions-list">${
      (v.actions || []).map((a) => `<li>${actionSentence(a, products)}</li>`).join("")
    }</ul>`;
  if (v.source_text) html += `<div class="verbatim" dir="auto">“${esc(v.source_text)}”</div>`;
  html += `<div class="rule-footer">
      <span class="meta"><bdi>${esc(v.attributed_to)}</bdi>${
        v.derived_from?.length
          ? ` · ${t("knowledge.derived_from")} <bdi>${esc(v.derived_from.join(", "))}</bdi>`
          : ""
      }</span>
      ${isRetired ? "" : `<button data-retire="1">${t("knowledge.retire")}</button>`}
    </div>`;
  div.innerHTML = html;

  div.querySelector("[data-retire]")?.addEventListener("click", async () => {
    await apiSend("POST", `/api/knowledge/${v.object_id}/${v.version}/retire`);
    renderKnowledgeRules();
  });
  return div;
}
