// "This change would affect N of your projects" — an ImpactReport, rendered.
//
// THREE surfaces ask that question now: the review queue (a candidate rule), the
// knowledge form (a rule being written) and the model editor's publish gate (a
// fence model being changed). Foundation §11 requires the answer BEFORE the
// change is made, and one renderer answers all three the same way — a second
// copy is how the model editor would come to say something different about a
// failed hypothetical generation than the knowledge tab says about the same
// failure.
//
// It writes into a container its CALLER owns and reads nothing global, which is
// what lets three modules share it without touching each other's DOM.

import { esc } from "./api.js";
import { t } from "./i18n.js";

export function renderImpactReport(container, report) {
  let html = `<div class="impact"><b>${t("impact.summary",
    { affected: report.projects_affected, checked: report.projects_checked })}</b>`;
  for (const i of report.impacts) {
    if (!i.changed) continue;
    html += `<div class="impact-row"><bdi>${esc(i.project_name || i.project_id)}</bdi>: `;
    if (i.generation_failure) {
      // code + params, localized; the engine's English sentence stays a tooltip
      const f = i.generation_failure;
      html += `<span class="tag rejected">${t("impact.generation_fails")}</span>
        <span class="meta" title="${esc(f.message)}">${esc(t("impact.failure." + f.code, f.params || {}))}</span>`;
    } else {
      const delta = (i.bom_delta_cents / 100).toFixed(2);
      const sign = i.bom_delta_cents > 0 ? "+" : "";
      html += `${t("impact.spans", { before: i.spans_before, after: i.spans_after })} · `
        + `${t("impact.posts", { added: i.posts_added, removed: i.posts_removed, modified: i.posts_modified })} · `
        + `<span class="num">${sign}${delta}€</span>`;
      if (i.vs_accepted_delta_cents !== null && i.vs_accepted_delta_cents !== undefined) {
        const vs = (i.vs_accepted_delta_cents / 100).toFixed(2);
        const vsSign = i.vs_accepted_delta_cents > 0 ? "+" : "";
        html += ` · ${t("impact.vs_accepted", { delta: `${vsSign}${vs}` })}`;
      }
    }
    html += "</div>";
  }
  if (!report.projects_affected) html += `<div class="meta">${t("impact.none")}</div>`;
  html += "</div>";
  container.innerHTML = html;
}
