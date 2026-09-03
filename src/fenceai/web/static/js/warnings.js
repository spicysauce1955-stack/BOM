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
import { CONSUMABLE_ROLES, tagOf } from "./structure-data.js";
import { fmtLen, roleWord, unitParams } from "./units.js";

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
    s = s.replaceAll(`{${k}}`, `<bdi>${esc(paramText(v))}</bdi>`);
  return s;
}

// A param value as text. Contract §1.2.1 puts no ceiling on what a `because`
// param IS, and v1.2's `ParamRef.point` is a MAPPING — `{exposure_category: "D",
// hvhz: true}` — which the first real snapshot sends on all 16 of its
// uncovered-condition gaps. Through a bare `String(v)` that renders
// `[object Object]` in both languages, which is the silent version of the
// failure the flattened-English-string it replaced was the loud version of.
//
// A boolean is rendered as a word rather than as `true`: `true` is not a value a
// reader of either language recognises, and Hebrew has no reason to display an
// English literal.
function paramText(v) {
  if (typeof v === "boolean") return t(v ? "common.yes" : "common.no");
  // A list renders as its members, separated. The publisher sends one where a
  // gap names the several shapes it could not choose between, and `String(v)`
  // on an array happens to produce comma-joined output with no spaces — close
  // enough to look intentional and wrong enough to read as a bug.
  if (Array.isArray(v)) return v.map(paramText).join(", ");
  if (v && typeof v === "object") {
    // sorted, matching the backend's own `GapSubject.key()` ordering, so the
    // same point reads the same way everywhere it appears
    return Object.keys(v).sort()
      .map((k) => `${dimensionText(k)} = ${paramText(v[k])}`).join(", ");
  }
  return String(v);
}

// A condition dimension's own word, where one exists. Dimension names are an
// OPEN registry, so a miss returns the raw name rather than a locale key: the
// day the other side registers a dimension we have no word for, it must read as
// its own name and not as `site.frost_line`.
function dimensionText(name) {
  const word = t(`site.${name}`);
  return word === `site.${name}` ? name : word;
}

// An element id is the backend's only handle on "which bay" — it derives no
// tags, and `role` + `slot_key` alone name a KIND of part, so a 60-bay fence
// used to emit sixty identical warnings naming no bay between them. The
// structure report DOES carry a tag per element, so a warning reads "A/B3" the
// moment that report is loaded and falls back to the raw id when it is not —
// which is still an answer to "which one", where there was none.
const label = (elementId) => tagOf(elementId) || elementId;

// `pegs`: what to call the place the warning is about, when the caller knows
// better than the element ids do. A panel PREVIEW is computed over a synthetic
// one-bay strategy (`fencemodel/preview.py` PREVIEW_SPAN_ID), so its warnings
// carry `span@preview:0-0` — a made-up id, printed at the reader as if it named
// something on their drawing. The caller substitutes "this panel"; every other
// caller keeps the real pegs.
function labelledParams(warning, pegs) {
  const p = { ...(warning.params || {}) };
  const refs = warning.element_refs || [];
  if (pegs) p.pegs = pegs;
  else if (refs.length) p.pegs = refs.map(label).join(", ");
  if ("slot_key" in p) {
    // The slot says WHICH rail of the panel this is, which is worth saying when
    // a panel has a top and a bottom one — and is noise when it does not.
    // M-LEGACY has a single rail slot whose key IS the role, so the sentence
    // read "rail in rail". The suffix is a locale string, not punctuation glued
    // on here, so a language that brackets differently still can.
    p.slot = p.slot_key && p.slot_key !== p.role
      ? t("supply.slot_suffix", { slot_key: p.slot_key }) : "";
  }
  return p;
}

export function warningRowHtml(warning, { pegs = null } = {}) {
  const body = localizedByCode(
    "warning", warning.code, labelledParams(warning, pegs), warning.message);
  return `<div class="warning ${esc(warning.severity || "warning")}">`
    + `⚠ [<span class="sku">${esc(warning.code)}</span>] ${body}</div>`;
}

const isConsumable = (role) => CONSUMABLE_ROLES.has(role);

// The whole "this part has no supplier" story, as one panel: why, and which
// lines are consequently missing from the numbers beside it. Empty string when
// there is nothing to say, so a caller can concatenate it unconditionally.
//
// `customer: true` follows the customer sheet's rule rather than opting out of
// it: fixings and concrete are DESCRIBED, never itemised, so an unsuppliable
// screw becomes "some fixings cannot be supplied" instead of "screw · 96" on a
// proposal. The customer is still told; they are not told the screw count.
export function supplyProblemsHtml(warnings, unresolved, { customer = false } = {}) {
  const all = warnings || [];
  const allLines = unresolved || [];
  if (!all.length && !allLines.length) return "";

  const list = customer ? all.filter((w) => !isConsumable(w.params?.role)) : all;
  const lines = customer ? allLines.filter((l) => !isConsumable(l.role)) : allLines;
  const hiddenConsumables = customer
    && (all.length !== list.length || allLines.length !== lines.length);

  let html = `<div class="panel supply-problems"><h3>${esc(t("supply.title"))}</h3>`
    + `<div class="meta">${esc(t("supply.hint"))}</div>`;
  for (const w of list) html += warningRowHtml(w);
  if (hiddenConsumables)
    html += `<div class="warning">${esc(t("supply.consumables_unsupplied"))}</div>`;
  if (lines.length) {
    html += `<table><tr><th>${esc(t("supply.part"))}</th>`
      + `<th>${esc(t("supply.qty"))}</th><th>${esc(t("supply.needs"))}</th>`
      + `<th>${esc(t("supply.where"))}</th></tr>`;
    for (const line of lines) {
      html += `<tr><td>${esc(roleWord(line.role))}`
        // the slot names WHICH rail of the panel this is; M-LEGACY has one, and
        // its key is the role, so printing both read "rail rail"
        + (line.slot_key && line.slot_key !== line.role
          ? ` <span class="meta">${esc(line.slot_key)}</span>` : "")
        + `</td><td class="num">${esc(String(line.engineering_qty))}</td>`
        + `<td class="num">${line.cut_length_mm ? esc(fmtLen(line.cut_length_mm)) : ""}</td>`
        + `<td><bdi class="meta">${esc((line.pegs || []).map(label).join(", "))}</bdi></td></tr>`;
    }
    html += `</table>`;
  }
  if (!customer) html += `<div class="meta">${esc(t("supply.quote_blocked"))}</div>`;
  return html + "</div>";
}
