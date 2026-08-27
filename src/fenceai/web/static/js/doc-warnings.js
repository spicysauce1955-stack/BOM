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
  const refs = (cites || []).filter((c) => c && c.id);
  if (!refs.length)
    return `<div class="meta">${esc(t("annexe.unattributed"))}</div>`;
  // `belongs_to` first: §1.1 says `id` is opaque to this side in every respect
  // except `belongs_to`, so `belongs_to` is the field that means anything to a
  // reader and `id` rides along as the opaque thing to quote back — the same
  // rule `gaps.js`'s `citesHtml` follows.
  const shown = refs
    .map((c) => (c.belongs_to ? `${c.belongs_to} · ${c.id}` : c.id))
    .map((ref) => `<bdi class="sku">${esc(ref)}</bdi>`)
    .join(", ");
  return `<div class="meta">${fill(t("annexe.source"), "ref", shown)}</div>`;
}

// Put already-escaped fragments into placeholders in a localized string, one
// (name, html) pair at a time.
//
// FUNCTION replacements, not string ones, and that is the whole reason this
// helper exists: `String.replace(x, str)` treats `$&`, `$'` and friends in the
// REPLACEMENT as patterns, and a `SourceRef.id` is opaque publisher text that may
// contain them (§1.1 — do not parse it, do not assume its shape). The output
// garbled rather than escaped wrongly, but a citation a reader cannot read is a
// citation they cannot check.
function fill(template, ...pairs) {
  let out = esc(template);
  for (let i = 0; i < pairs.length; i += 2)
    out = out.replace(`{${pairs[i]}}`, () => pairs[i + 1]);
  return out;
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
      ? `<div class="meta">${fill(t("annexe.instances"), "n", esc(String(n)))}</div>`
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

// One row for whatever a document says about a line's product, once per line
// group. Shared by the BOM tab and the panel preview: the test review found
// the two had drifted into near-identical closures, one of them reachable only
// through the browser smoke suite, which is how a mutant that broke it stayed
// green. `seenSku` is the caller's — two callers must not share a set, and one
// call site (the panel) needs it for real, where two slots are routinely
// supplied by one product.
export function productWarningRowHtml(placement, sku, seenSku) {
  if (!sku || seenSku.has(sku)) return "";
  seenSku.add(sku);
  const list = bucket(placement, "product", sku);
  return list.length
    ? `<tr class="doc-warning-row"><td colspan="7">${
        quotedGroupHtml(list, "annexe.on_product")}</td></tr>`
    : "";
}

// Every model-scoped warning, grouped and labelled by which model it is about.
// A run can carry more than one product line (a two-section run, a boundary
// post between them), and putting both under one unlabeled "this product line"
// header is the misattribution obligation 10 exists to prevent, arrived at from
// a surface that reads several models at once instead of one.
export function modelWarningsHtml(placement) {
  const entries = bucket(placement, "model");
  const refs = [...new Set(entries.map((p) => p.ref))];
  return refs.map((ref) => {
    const label = `<div class="meta">${fill(t("annexe.on_target"), "ref",
      `<bdi class="sku">${esc(ref)}</bdi>`)}</div>`;
    const group = entries.filter((p) => p.ref === ref).map(quotedWarningHtml).join("");
    return `<div class="doc-warnings">${label}${group}</div>`;
  }).join("");
}

// The annexe itself: every job-wide warning, once each, plus an honest account of
// what is NOT here. The counts matter as much as the entries — a sheet that
// showed three notices while silently holding four more would be worse than one
// that showed none, because a reader would believe they had seen the warnings.
export function annexeHtml(
  placement, { title = true, drawn = [], inline = [], id = "" } = {},
) {
  const entries = bucket(placement, "annexe");
  // "N more warnings are shown on the panel sheet" is only true where the reader
  // can actually get to that sheet. `drawn` is the caller saying which buckets it
  // renders ITSELF, so the note is replaced by the thing it was pointing at
  // rather than sending a reader to a surface this screen does not have.
  //
  // `inline` is the sharper version of the same problem, and the architecture
  // review found it: the print stylesheet emits only the canvas and structure
  // tabs, so the PRINTED plan contains neither the panel sheet nor the BOM tab —
  // and the setting-out sheet was telling the reader that a "do not load an
  // uncured footing" warning was on one of them. A sheet that goes to site
  // carries every warning or says so; it does not cite an absent page. So the
  // print surface asks for those buckets to be drawn HERE, labelled with what
  // they attach to.
  const shown = [...drawn, ...inline];
  const elsewhere = (where) =>
    (shown.includes(where) ? 0 : bucket(placement, where).length);
  const steps = elsewhere("step");
  const lines = elsewhere("product") + elsewhere("model");
  // `procedure` had no term here at all, which is how a procedure-scoped warning
  // on a document with no assembly steps came to render nowhere while the
  // backend reported it placed and the invariant balanced.
  const procedures = elsewhere("procedure");
  const stranded = bucket(placement, "unplaceable").length;
  const other = placement?.not_in_plan || 0;
  const unreadable = placement?.documents_unreadable || 0;

  const attached = inline.flatMap((where) => bucket(placement, where));
  if (!entries.length && !attached.length && !steps && !lines && !procedures
      && !stranded && !other && !unreadable) return "";

  const note = (key, n) => (n
    ? `<div class="meta">${fill(t(key), "n", esc(String(n)))}</div>` : "");
  // An inline entry says what it is attached to, because on this sheet it is no
  // longer sitting on the thing it is about. `owner` disambiguates a run built
  // to more than one document: `rails`, `cure` and `frame` are generic step
  // keys (see `PlacedWarning.owner`), so two manufacturers' warnings on their
  // own `rails` step would otherwise render as identical, unlabeled blocks.
  const attachedHtml = attached.map((p) => {
    const label = p.owner
      ? (p.ref
          ? `<div class="meta">${fill(t("annexe.on_target_of_model"),
              "ref", `<bdi class="sku">${esc(p.ref)}</bdi>`,
              "model", `<bdi class="sku">${esc(p.owner)}</bdi>`)}</div>`
          : `<div class="meta">${fill(t("annexe.on_procedure_of_model"),
              "model", `<bdi class="sku">${esc(p.owner)}</bdi>`)}</div>`)
      : (p.ref
          ? `<div class="meta">${fill(t("annexe.on_target"), "ref",
              `<bdi class="sku">${esc(p.ref)}</bdi>`)}</div>`
          : `<div class="meta">${esc(t("annexe.on_procedure"))}</div>`);
    return `<div class="doc-warnings">${label}${quotedWarningHtml(p)}</div>`;
  }).join("");

  return `<div class="panel annexe"${id ? ` id="${esc(id)}"` : ""}>`
    + (title ? `<h3>${esc(t("annexe.title"))}</h3>` : "")
    + `<div class="meta">${esc(t("annexe.hint"))}</div>`
    + (entries.length
      ? entries.map(quotedWarningHtml).join("")
      : `<div class="meta">${esc(t("annexe.empty"))}</div>`)
    + attachedHtml
    + note("annexe.elsewhere_steps", steps)
    + note("annexe.elsewhere_procedure", procedures)
    + note("annexe.elsewhere_lines", lines)
    + note("annexe.other_documents", other)
    // Not `meta` lines: a warning with nowhere to go, and a document that cannot
    // be read back, are gaps in THIS engine rather than notes about a document.
    // They read as warnings because they are ours.
    + (stranded
      ? `<div class="warning">`
        + fill(t("annexe.unplaceable"), "n", esc(String(stranded)))
        + `</div>`
      : "")
    + (unreadable
      ? `<div class="warning">`
        + fill(t("annexe.documents_unreadable"), "n", esc(String(unreadable)))
        + `</div>`
      : "")
    + `</div>`;
}
