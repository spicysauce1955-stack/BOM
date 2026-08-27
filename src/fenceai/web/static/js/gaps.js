// Rendering a `Gap` — what the run knows it does not know.
//
// A gap is not a warning with extra fields. A warning says something about the
// plan on screen; a gap says something about the SYSTEM, and it names the work
// item that would remove it. The contract makes two of its fields binding for
// exactly that reason, and both of them are about the reader:
//
//   * `would_close` — "a gap that only says something is missing sends a curator
//     hunting". So it is never behind a click here: it is on the row.
//   * `closes_by` — `knowledge` means a curator on the other side of the
//     boundary can close it; `planning` means it needs a schema change in this
//     repository and no curator can touch it. So the panel GROUPS by it rather
//     than printing it as a chip: a queue that mixes the two is a queue that
//     shows someone work they cannot do, which is the one property the contract
//     says it must not have.
//
// `severity` is the third axis and the smallest: `warns_line` affects a line in
// the plan (and is therefore also a warning row on the plan), `informational`
// does not. It changes the weight of a row, never its group — where the work
// goes is not a function of how loud it is.
//
// THE HONEST PROBLEM, stated on screen rather than papered over. `would_close`
// is generated ENGLISH prose with no code and no params, in a Hebrew-first
// product where every other user-visible string renders from a locale bundle.
// There is no translation layer for it and inventing one would be worse than
// the hole: a machine translation of a work item, presented as the sentence its
// author wrote, is the same defect the design forbids for a manufacturer's
// warning text ("verbatim and untranslated — never offer a translate
// affordance", frontend design §6). So it renders the way this app already
// renders every other piece of verbatim text written by someone else: quoted,
// `lang="en"` and `dir="ltr"` inside the RTL page, and labelled in the reader's
// own language as what it is — a note written for the knowledge curators. The
// long-term answer is a `close.<code>` registry beside the warning registry,
// which is a registry addition and needs no amendment.
//
// Everything here returns an HTML STRING and owns no DOM, exactly like
// `warnings.js`: the editor injects it under `#gaps`, the BOM tab into its own
// body, and neither reaches into the other's subtree.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { tagOf } from "./structure-data.js";
import { localizedByCode } from "./warnings.js";

// Grouping order, and it is not alphabetical: what a curator can do comes
// first, because that is the group whose items are actionable by the person
// most likely to be reading. `planning` is real work and is shown, never
// hidden — it is just not THEIR work.
const CLOSERS = ["knowledge", "planning"];

/** What the gap is about, named the way the rest of the app names it.
 *
 *  An `entity` subject is a strategy element id, and the structure report knows
 *  its tag — so a gap about a gate reads "A/G1" rather than
 *  `gate@run1:2000-3000`, the same substitution `warnings.js` makes for element
 *  refs. `slot` and `param` refs have no tag and are printed verbatim: they are
 *  identifiers, so they get `.sku` (which forces LTR) and `<bdi>`.
 */
function subjectHtml(subject) {
  if (!subject || !subject.id) return "";
  const shown = subject.kind === "entity" ? (tagOf(subject.id) || subject.id) : subject.id;
  return `<div class="gap-subject meta">${esc(t("gaps.subject." + subject.kind))} `
    + `<bdi class="sku">${esc(shown)}</bdi></div>`;
}

/** Evidence, where there is any.
 *
 *  A `SourceRef` is `{ id, belongs_to }` and the contract is explicit that `id`
 *  is OPAQUE to this side — do not parse it, do not infer a page from it. So the
 *  document hash is what is shown, because `belongs_to` is the only field this
 *  side may read and the only one that means anything to a curator holding the
 *  same snapshot; the opaque id rides along as the thing to quote back.
 *
 *  A run-produced gap usually cites nothing — the evidence for "no row covers
 *  this" is the absence itself — so the empty case is the normal one and must
 *  not render an empty "Evidence:" label.
 */
function citesHtml(cites) {
  const refs = (cites || []).filter((c) => c && (c.belongs_to || c.id));
  if (!refs.length) return "";
  return `<div class="gap-cites meta">${esc(t("gaps.cites"))} `
    + refs.map((c) => `<bdi class="sku">${esc(c.belongs_to || c.id)}</bdi>`).join(", ")
    + `</div>`;
}

/** One gap, as a row. Exported because the BOM tab attaches single gaps to the
 *  lines they warn, and a second spelling of a gap row is how the two surfaces
 *  come to disagree about what a gap looks like. */
export function gapRowHtml(gap) {
  const severity = gap.severity === "warns_line" ? "warns_line" : "informational";
  // the same sentence the paired StrategyWarning renders, from the same code and
  // the same params — one localizer, so a gap and its warning cannot drift
  const sentence = localizedByCode("warning", gap.because.code, gap.because.params);
  // A `Gap` has no `message` — `because` is its only rendering mechanism (§1.2.1) —
  // so a code neither bundle carries falls back to the bare code itself, not to an
  // English sentence. That is expected for a kind arriving under a code this repo
  // has never seen, and it must be MARKED as such rather than presented as a
  // localized sentence it is not: `t()` returning its own key is exactly that case.
  const localized = t("warning." + gap.because.code) !== "warning." + gap.because.code;
  const kindWord = t("gaps.kind." + gap.kind);
  // `on` belongs to `disputed` alone: WHICH of the two readings disagree. On any
  // other kind the field is absent, and printing a blank there would suggest the
  // gap is making a claim it is not.
  const on = gap.on ? ` <span class="tag">${esc(t("gaps.on." + gap.on))}</span>` : "";
  return `<div class="gap ${esc(severity)}" data-gap-code="${esc(gap.because.code)}"
       data-gap-kind="${esc(gap.kind)}" data-severity="${esc(severity)}"
       data-closes-by="${esc(gap.closes_by)}">
    <div class="gap-head">
      <span class="tag ${esc(severity)}">${esc(t("gaps.severity." + severity))}</span>
      <span class="gap-kind">${esc(kindWord === "gaps.kind." + gap.kind ? gap.kind : kindWord)}</span>${on}
      <span class="sku">${esc(gap.because.code)}</span>
    </div>
    <div class="gap-what"${localized ? "" : ' lang="en" dir="ltr"'}>${sentence}</div>
    ${subjectHtml(gap.subject)}
    <div class="gap-close">
      <span class="gap-close-label">${esc(t("gaps.would_close"))}</span>
      <q class="verbatim gap-verbatim" lang="en" dir="ltr"><bdi>${esc(gap.would_close || "")}</bdi></q>
      <div class="meta">${esc(t("gaps.would_close_note"))}</div>
    </div>
    ${citesHtml(gap.cites)}
  </div>`;
}

/** The whole surface: every gap this run produced, grouped by who can close it.
 *
 *  Empty string when there are none, so a caller concatenates it
 *  unconditionally — and `{ empty: true }` when the caller wants the panel to
 *  SAY there are none, which is a different claim from saying nothing and is
 *  worth making on a surface whose whole subject is absence.
 */
export function gapsPanelHtml(gaps, { empty = false } = {}) {
  const all = (gaps || []).filter(Boolean);
  if (!all.length && !empty) return "";
  let html = `<div class="panel gaps"><h3>${esc(t("gaps.title"))}</h3>`;
  if (!all.length) return html + `<div class="meta">${esc(t("gaps.none"))}</div></div>`;
  html += `<div class="meta">${esc(t("gaps.hint"))}</div>`;
  for (const closer of CLOSERS) {
    const of = all.filter((g) => g.closes_by === closer);
    if (!of.length) continue;
    // warns_line first inside a group: within one person's work, the items that
    // cost a line come before the ones that cost nothing yet.
    const ordered = [...of.filter((g) => g.severity === "warns_line"),
                     ...of.filter((g) => g.severity !== "warns_line")];
    html += `<div class="gap-group" data-closes-by="${esc(closer)}">
      <h4>${esc(t("gaps.group_" + closer))}
        <span class="num">${esc(String(ordered.length))}</span></h4>
      <div class="meta">${esc(t("gaps.group_" + closer + "_hint"))}</div>`;
    for (const gap of ordered) html += gapRowHtml(gap);
    html += `</div>`;
  }
  return html + `</div>`;
}

/** How many gaps warn a LINE — the number a summary line can say without
 *  implying that an informational note costs the plan something. */
export function warnsLineCount(gaps) {
  return (gaps || []).filter((g) => g && g.severity === "warns_line").length;
}
