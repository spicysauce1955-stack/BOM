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

// THE TWO VOCABULARIES A SUBJECT CARRIES, AND WHY ONLY ONE OF THEM IS A KEY.
//
// `subject.kind` is CLOSED (`Literal["entity","param"]`, `core/gaps.py`) and is
// the locale-keyed discriminator: every value needs `gaps.subject.<value>` in
// both bundles, and `tests/web/test_locale_bundles.py` derives that set from the
// Literal so adding an arm without its Hebrew fails there.
//
// `subject.ref_kind` and `scope.kind` are `EntityRef.kind`, which v1.2 makes an
// OPEN registry — *"adding an entry is never a breaking change and never an
// amendment"*. A registry entry can therefore arrive from the other team with no
// release on this side, so `t("gaps.subject." + ref_kind)` would put the literal
// string `gaps.subject.fence_model` on screen the day they add a kind, in both
// languages, with nothing red anywhere. They are DATA here: carried, isolated as
// identifiers, never keys. Keeping the two apart is the whole point of v1.2
// splitting them into two fields.
//
// A CONDITION POINT IS NOT A SENTENCE FRAGMENT. `ParamRef.point` is a mapping
// (`{exposure_category: "D", hvhz: true}`) precisely so a renderer can build the
// phrase from its parts; the contract's own note says a pre-joined
// `"exposure_category=D, hvhz=True"` cannot be localised, and Hebrew is not a
// language this system renders English fragments into. So each dimension is
// looked up as a WORD and each value formatted by its type — a boolean becomes
// `כן`/`yes`, not `true`.

/** The word for a condition dimension, or `null` when this repo has none.
 *
 *  Condition dimensions are themselves a registry the other team extends without
 *  asking (CLAUDE.md: *"registry additions are not amendments"*), so this cannot
 *  be a bare `t()`: an unknown dimension must fall back to its raw name rendered
 *  AS a raw name, never to the literal key. The names it does know are the site
 *  fields this app already has words for (`site.hvhz`, `site.exposure_category`)
 *  — one answer per fact, rather than a second Hebrew for the same dimension.
 */
function dimensionWord(name) {
  const key = "site." + name;
  const word = t(key);
  return word === key ? null : word;
}

/** One value from a condition point, formatted by its type.
 *
 *  A boolean is a fact, not a token: `hvhz: true` reads `כן`, because `true` is
 *  neither Hebrew nor English and a reader deciding whether a row applies to
 *  their site should not have to know which. Strings arrive from published
 *  documents and routinely contain inch marks (`49" to 76"`), so they are
 *  escaped and `<bdi class="sku">`-isolated: an unescaped quote inside an
 *  attribute-adjacent template is an XSS hole, and an un-isolated one reorders
 *  the Hebrew sentence around it.
 */
function pointValueHtml(value) {
  if (typeof value === "boolean")
    return `<span class="gap-point-value">${esc(t(value ? "common.yes" : "common.no"))}</span>`;
  return `<bdi class="${typeof value === "number" ? "num" : "sku"}">${esc(value)}</bdi>`;
}

/** The cell in the table this gap is a hole in — dimension by dimension.
 *
 *  Sorted by dimension name so two renderings of the same point cannot differ
 *  by key order, which is the same reason `GapSubject.key()` sorts.
 */
function pointHtml(point) {
  const names = Object.keys(point || {}).sort();
  if (!names.length) return "";
  const cells = names.map((name) => {
    const word = dimensionWord(name);
    const label = word === null
      ? `<bdi class="sku">${esc(name)}</bdi>`
      : `<span class="gap-point-dim">${esc(word)}</span>`;
    return `<span class="gap-point-cell">${label} = ${pointValueHtml(point[name])}</span>`;
  });
  return `<span class="gap-point">${esc(t("gaps.subject.point"))} ${cells.join(", ")}</span>`;
}

/** WHICH product or assembly the parameter belongs to (`ParamRef.scope`).
 *
 *  Not decoration. The first real published snapshot carries `footing_depth_mm`
 *  under two different scopes, so a subject printed without it names two
 *  different holes at once and a curator closing "the footing_depth_mm gap"
 *  closes the wrong one. `scope.kind` is the open registry value and rides along
 *  as part of the identifier rather than as a key.
 */
function scopeHtml(scope) {
  if (!scope || !scope.id) return "";
  const shown = scope.kind ? `${scope.kind}/${scope.id}` : scope.id;
  return `<span class="gap-scope">${esc(t("gaps.subject.scope"))} `
    + `<bdi class="sku">${esc(shown)}</bdi></span>`;
}

/** What the gap is about, named the way the rest of the app names it.
 *
 *  An `entity` subject is a strategy element id, and the structure report knows
 *  its tag — so a gap about a gate reads "A/G1" rather than
 *  `gate@run1:2000-3000`, the same substitution `warnings.js` makes for element
 *  refs. A `param` ref has no tag and is printed verbatim — it is an identifier,
 *  so it gets `.sku` (which forces LTR) and `<bdi>` — and then says WHERE:
 *  its scope and the condition cell inside that scope's table.
 */
function subjectHtml(subject) {
  if (!subject || !subject.id) return "";
  const entity = subject.kind === "entity";
  const shown = entity ? (tagOf(subject.id) || subject.id) : subject.id;
  // The closed discriminator IS a key — but a stored run written before v1.2
  // retired `slot` still deserializes, and a bare `t()` would print
  // `gaps.subject.slot` at it. Same guard `gapRowHtml` gives `kind`.
  const kindWord = t("gaps.subject." + subject.kind);
  const label = kindWord === "gaps.subject." + subject.kind ? subject.kind : kindWord;
  const parts = [`${esc(label)} <bdi class="sku">${esc(shown)}</bdi>`];
  if (entity && subject.ref_kind)
    parts.push(`<span class="gap-ref-kind">${esc(t("gaps.subject.ref_kind"))} `
      + `<bdi class="sku">${esc(subject.ref_kind)}</bdi></span>`);
  if (!entity) {
    const scope = scopeHtml(subject.scope);
    const point = pointHtml(subject.point);
    if (scope) parts.push(scope);
    if (point) parts.push(point);
  }
  const refKindAttr = subject.ref_kind ? ` data-ref-kind="${esc(subject.ref_kind)}"` : "";
  return `<div class="gap-subject meta"${refKindAttr}>${parts.join(" ")}</div>`;
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
 *
 *  Each citation is now a `.evidence-link` button carrying the opaque id and
 *  `belongs_to` as data attributes — the shared, documented contract
 *  `js/evidence.js` alone interprets (its module header explains why this is
 *  not a cross-module DOM reach). This module still returns a pure HTML
 *  string and wires no listener itself.
 */
function citesHtml(cites) {
  const refs = (cites || []).filter((c) => c && (c.belongs_to || c.id));
  if (!refs.length) return "";
  return `<div class="gap-cites meta">${esc(t("gaps.cites"))} `
    + refs.map((c) => `<button type="button" class="evidence-link sku" `
        + `data-evidence-id="${esc(c.id)}" data-belongs-to="${esc(c.belongs_to || "")}">`
        + `<bdi>${esc(c.belongs_to || c.id)}</bdi></button>`).join(", ")
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
