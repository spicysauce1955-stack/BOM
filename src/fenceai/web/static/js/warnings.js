// Rendering a backend warning — the one place that knows how `code + params`
// becomes a sentence.
//
// The backend never sends user-visible prose: it sends a code, a params bag and
// an English `message` that is a diagnostic fallback only. Three panels have to
// render that same shape (the editor's strategy warnings, the BOM tab's supply
// warnings, the structure sheet's), and before this module only the editor did
// — `Bom.warnings`, `StructureReport.warnings` and `StructureReport.unresolved`
// were computed by the API and read by no JS at all, so a bay whose part nothing
// can supply produced a BOM and a setting-out sheet that were silently short a
// line, and `warning.no_eligible_item` was an unreachable string in both bundles.
//
// Everything here returns an HTML STRING. It owns no DOM: each caller injects
// the result into its own subtree, so no module reaches into another's.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { tagOf } from "./structure-data.js";
import { fmtLen, unitParams } from "./units.js";

// Localize a warning/critique by code: t("<prefix>.<code>", params) with each
// param bidi-isolated (<bdi>); falls back to the server's English text when no
// key exists. Backend params are mm — unitParams converts every `*_mm` and
// supplies {u}.
export function localizedByCode(prefix, code, params, fallback) {
  const key = `${prefix}.${code}`;
  const template = t(key);  // no params: placeholders stay intact for wrapped interpolation
  if (template === key) return esc(fallback ?? code);
  let s = esc(template);
  for (const [k, v] of Object.entries(unitParams(params || {})))
    s = s.replaceAll(`{${k}}`, `<bdi>${esc(String(v))}</bdi>`);
  return s;
}

// An element id is the backend's only handle on "which bay" — it derives no
// tags, and `role` + `slot_key` alone name a KIND of part, so a 60-bay fence
// used to emit sixty identical warnings naming no bay between them. The
// structure report DOES carry a tag per element, so a warning reads "A/B3" the
// moment that report is loaded and falls back to the raw id when it is not —
// which is still an answer to "which one", where there was none.
const label = (elementId) => tagOf(elementId) || elementId;

function labelledParams(warning) {
  const refs = warning.element_refs || [];
  if (!refs.length) return warning.params;
  return { ...warning.params, pegs: refs.map(label).join(", ") };
}

export function warningRowHtml(warning) {
  const body = localizedByCode(
    "warning", warning.code, labelledParams(warning), warning.message);
  return `<div class="warning ${esc(warning.severity || "warning")}">`
    + `⚠ [<span class="sku">${esc(warning.code)}</span>] ${body}</div>`;
}

// The whole "this part has no supplier" story, as one panel: why, and which
// lines are consequently missing from the numbers beside it. Empty string when
// there is nothing to say, so a caller can concatenate it unconditionally.
export function supplyProblemsHtml(warnings, unresolved) {
  const list = warnings || [];
  const lines = unresolved || [];
  if (!list.length && !lines.length) return "";
  let html = `<div class="panel"><h3>${esc(t("supply.title"))}</h3>`
    + `<div class="meta">${esc(t("supply.hint"))}</div>`;
  for (const w of list) html += warningRowHtml(w);
  if (lines.length) {
    html += `<table><tr><th>${esc(t("supply.part"))}</th>`
      + `<th>${esc(t("supply.qty"))}</th><th>${esc(t("supply.needs"))}</th>`
      + `<th>${esc(t("supply.where"))}</th></tr>`;
    for (const line of lines) {
      html += `<tr><td>${esc(line.role)}`
        // the slot names WHICH rail of the panel this is; M-LEGACY has one, and
        // its key is the role, so printing both read "rail rail"
        + (line.slot_key && line.slot_key !== line.role
          ? ` <span class="meta">${esc(line.slot_key)}</span>` : "")
        + `</td><td class="num">${esc(String(line.engineering_qty))}</td>`
        + `<td class="num">${line.cut_length_mm ? esc(fmtLen(line.cut_length_mm)) : ""}</td>`
        + `<td><bdi class="meta">${esc((line.pegs || []).map(label).join(", "))}</bdi></td></tr>`;
    }
    html += `</table><div class="meta">${esc(t("supply.quote_blocked"))}</div>`;
  }
  return html + "</div>";
}
