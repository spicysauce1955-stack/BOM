// Rendering a warning QUOTED from a document — the one place that knows how not to.
//
// `warnings.js` is this module's mirror image, and the pair is the whole point.
// There, the backend sends a `code` and a params bag and the client owns the
// sentence: `t("warning." + code)`, both bundles, enforced by
// `tests/web/test_locale_bundles.py`. Here the backend sends somebody else's
// TEXT, and the client owns nothing about it — not the words, not the language,
// not the severity word in front of it.
//
// Three rules, and each one is a defect that has happened somewhere:
//
// 1. **The text is never localized and never translated.** Zero of the corpus's
//    81,794 elements are Hebrew. Translating a manufacturer's liability sentence
//    and publishing it as theirs manufactures a claim they never made, so there
//    is no translate affordance here and there must not be one added.
// 2. **The severity word is the publisher's.** `CAUTION` and `WARNING` are terms
//    of art with different legal weight in North American product literature.
//    They are printed as they arrived, not mapped onto our info/warning/error.
// 3. **`lang` sets the direction.** An English sentence in a Hebrew-first RTL
//    page needs `lang` and `dir` on the element that holds it, or the terminal
//    punctuation walks to the wrong end of the line. `<bdi>` isolates it from
//    the surrounding paragraph; the attributes tell the browser which way the
//    text inside runs.
//
// Everything here returns an HTML STRING and owns no DOM, exactly as
// `warnings.js` does: each caller injects the result into its own subtree.
//
// **`.doc-warning`, never `.warning`** — and the browser suite is what taught
// that lesson. A quoted warning first shipped as `class="warning quoted"`, and a
// smoke check counting `#tab-panel .warning` to prove a channelled panel reports
// NO GAP promptly failed: it was counting a manufacturer's pool-barrier notice as
// a hole in this engine's own answer. The two are different kinds of thing, which
// is the whole of item 8, and sharing a selector is how that difference gets lost
// in every future count. The one exception is deliberate and below: a warning
// this engine cannot PLACE is our defect, so it renders as `.warning` and SHOULD
// be counted.

import { esc } from "./api.js";
import { t } from "./i18n.js";

// Which way the quoted text runs. Only the direction is inferred from `lang` —
// the words never are. The list is deliberately short: everything not named here
// is left to the browser's own default for the tag, which is the honest answer
// for a language this UI has never been asked to show.
const RTL = new Set(["he", "ar", "fa", "ur"]);
const dirOf = (lang) => (RTL.has(String(lang || "").slice(0, 2)) ? "rtl" : "ltr");

// The publisher's severity word, isolated and unchanged. `.sku` is the existing
// class for a token that must not be reflowed or reinterpreted by the
// surrounding text direction — a sku, an id, and now a foreign term of art.
function lexeme(word, text) {
  if (!word) return "";
  // The publisher usually leads its own sentence with its own word — "WARNING:
  // this fence is not a pool barrier" — and both halves are theirs. Printing the
  // badge as well read "WARNING WARNING: this fence...". Suppressing the BADGE is
  // not editing the quotation: the text goes out untouched either way, and the
  // one thing that must never happen is the reverse, trimming the word out of
  // the sentence so the badge looks tidy.
  const lead = String(text || "").trimStart().toUpperCase();
  if (lead.startsWith(String(word).toUpperCase())) return "";
  return `<span class="sku lexeme" title="${esc(t("annexe.severity_title"))}">`
    + `${esc(word)}</span> `;
}

// Where this sentence came from, or the honest admission that nobody knows.
// An unattributed warning must not look like one that can be checked: the
// contract's own rule for the Frontend is that a source reference proves where
// the system looked, and its absence has to be as visible as its presence.
function attribution(cites) {
  if (!cites || !cites.id)
    return `<div class="meta">${esc(t("annexe.unattributed"))}</div>`;
  const ref = cites.belongs_to ? `${cites.id} · ${cites.belongs_to}` : cites.id;
  return `<div class="meta">`
    + esc(t("annexe.source")).replace("{ref}", `<bdi class="sku">${esc(ref)}</bdi>`)
    + `</div>`;
}

// One placed warning: the text, whose it is, and how many times the document
// said it. `instances > 1` is the freeze-thaw footnote — printed at the foot of
// fourteen pages, shown here once, and the count is what makes "once" a decision
// the reader can see rather than something that looks like all there was.
export function quotedWarningHtml(placed) {
  const w = placed.warning || placed;
  const n = placed.instances || 1;
  return `<div class="doc-warning" lang="${esc(w.lang || "")}" `
    + `dir="${dirOf(w.lang)}">`
    + `<bdi>${lexeme(w.severity_lexeme, w.text_raw)}${esc(w.text_raw || "")}</bdi>`
    + `<div class="meta">${esc(t("annexe.quoted"))}</div>`
    + attribution(w.cites)
    + (n > 1
      ? `<div class="meta">${esc(t("annexe.instances")).replace("{n}", esc(String(n)))}</div>`
      : "")
    + `</div>`;
}

// A labelled run of them, for a step, a procedure head or a BOM line. Empty
// string when there is nothing to say, so a caller can concatenate it
// unconditionally — the same contract `supplyProblemsHtml` keeps.
export function quotedGroupHtml(placedList, labelKey) {
  const list = placedList || [];
  if (!list.length) return "";
  return `<div class="doc-warnings">`
    + (labelKey ? `<div class="meta">${esc(t(labelKey))}</div>` : "")
    + list.map(quotedWarningHtml).join("")
    + `</div>`;
}

// Read one bucket out of a `WarningPlacement`. The backend already decided where
// every warning goes (`report/annexe.py`); this is a lookup and NOT a second
// placement rule — a client that filtered on `attaches_to.kind` itself would be
// free to disagree with the plan about where the freeze-thaw footnote belongs,
// which is the one thing that whole read model exists to prevent.
export function bucket(placement, where, ref = null) {
  return (placement?.placements || []).filter(
    (p) => p.where === where && (ref === null || p.ref === ref));
}

// The annexe itself: every job-wide warning, once each, plus an honest account of
// what is NOT here. The counts matter as much as the entries — a sheet that
// showed three notices while silently holding four more would be worse than one
// that showed none, because a reader would believe they had seen the warnings.
export function annexeHtml(placement, { title = true, drawn = [], id = "" } = {}) {
  const entries = bucket(placement, "annexe");
  // "N more warnings are shown on the panel sheet" is only true where the reader
  // can actually get to that sheet. `drawn` is the caller saying which buckets it
  // renders ITSELF, so the note is replaced by the thing it was pointing at
  // rather than sending a reader to a surface this screen does not have.
  const elsewhere = (where) =>
    (drawn.includes(where) ? 0 : bucket(placement, where).length);
  const steps = elsewhere("step");
  const lines = elsewhere("product") + elsewhere("model");
  const stranded = bucket(placement, "unplaceable").length;
  const other = placement?.not_in_plan || 0;
  if (!entries.length && !steps && !lines && !stranded && !other) return "";

  const note = (key, n) => (n
    ? `<div class="meta">${esc(t(key)).replace("{n}", esc(String(n)))}</div>` : "");
  // `id` comes from the CALLER, and it has to. Both the Panel tab and the
  // structure sheet render an annexe, and they are in the DOM at the same time:
  // hardcoding one id here gave two elements the same one, so
  // `getElementById` returned whichever came first and the panel sheet's own
  // check read the setting-out sheet's annexe instead. Each module owns its own
  // subtree (CLAUDE.md), and that includes naming it.
  return `<div class="panel annexe"${id ? ` id="${esc(id)}"` : ""}>`
    + (title ? `<h3>${esc(t("annexe.title"))}</h3>` : "")
    + `<div class="meta">${esc(t("annexe.hint"))}</div>`
    + (entries.length
      ? entries.map(quotedWarningHtml).join("")
      : `<div class="meta">${esc(t("annexe.empty"))}</div>`)
    + note("annexe.elsewhere_steps", steps)
    + note("annexe.elsewhere_lines", lines)
    + note("annexe.other_documents", other)
    // Not a `meta` line: a warning with nowhere to go is a gap in this engine,
    // not a note about the document. It reads as a warning because it is one.
    + (stranded
      ? `<div class="warning">`
        + esc(t("annexe.unplaceable")).replace("{n}", esc(String(stranded)))
        + `</div>`
      : "")
    + `</div>`;
}
