"""The quoted-warning renderer (`js/doc-warnings.js`), in node.

The browser suite can only reach the demo document's four warnings on the happy
path. The cases that matter are the ones a fixture cannot arrange in a browser: a
Hebrew quotation on an English page and the reverse, a manufacturer's sentence
containing markup, a footnote printed 83 times, and an annexe that has to be
honest about what it is NOT showing.

The rule under test is a rule about restraint. Everything else in this app goes
through `t()`; this module carries somebody else's words and must leave them
alone, which is much easier to break than to write.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { readFileSync } from "node:fs";

globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  querySelector: () => null,
  createElement: () => ({ style: {}, classList: { add() {} }, appendChild() {} }),
  documentElement: {},
};
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { setLocale } from "./js/i18n.js";
import { annexeHtml, bucket, quotedGroupHtml, quotedWarningHtml }
  from "./js/doc-warnings.js";

const EN = JSON.parse(readFileSync("./i18n/en.json", "utf8"));
const HE = JSON.parse(readFileSync("./i18n/he.json", "utf8"));

const W = (over = {}) => ({
  text_raw: "CAUTION: set footings below the frost line.",
  lang: "en", severity_lexeme: "CAUTION",
  attaches_to: { kind: "document", ref: "" },
  cites: null, code: null, params: {}, ...over,
});
const placed = (w, where, ref = "", instances = 1) =>
  ({ warning: w, where, ref, instances });

const out = {};
await setLocale("en");

out.plain = quotedWarningHtml(placed(W(), "annexe"));
out.hebrew_quote = quotedWarningHtml(placed(W({
  lang: "he", text_raw: "אזהרה: אין לעמוד על הגדר." }), "annexe"));
out.markup = quotedWarningHtml(placed(W({
  text_raw: "<img src=x onerror=alert(1)> mind the gap" }), "annexe"));
out.lexemes = [
  // texts that do NOT lead with the publisher's word, so the badge is the only
  // place it can appear — see `out.leading` below for the case that does
  quotedWarningHtml(placed(W({ severity_lexeme: "CAUTION",
                               text_raw: "Set footings below the frost line." }),
                           "annexe")),
  quotedWarningHtml(placed(W({ severity_lexeme: "WARNING",
                               text_raw: "Do not load an uncured footing." }),
                           "annexe")),
  // the text itself carries no severity word either, so a badge invented from
  // nothing would be visible in the output rather than hidden in the sentence
  quotedWarningHtml(placed(W({ severity_lexeme: "",
                               text_raw: "Keep the bottom rail clear of grade." }),
                           "annexe")),
];
// the publisher leads its own sentence with its own word — both halves theirs
out.leading = quotedWarningHtml(placed(W({
  severity_lexeme: "WARNING",
  text_raw: "WARNING: This fence is not a pool barrier." }), "annexe"));
out.cited = quotedWarningHtml(placed(W({
  cites: { id: "SRC-7", belongs_to: "sha256:doc-a" } }), "annexe"));
out.repeated = quotedWarningHtml(placed(W(), "annexe", "", 83));
out.once = quotedWarningHtml(placed(W(), "annexe", "", 1));
// a publisher's own code rides along and never becomes the sentence
out.with_code = quotedWarningHtml(placed(W({
  code: "not_pool_rated", params: { standard: "IRC AG105.2" },
  text_raw: "Not rated as a pool barrier." }), "annexe"));

out.empty_group = quotedGroupHtml([], "annexe.on_step");
out.step_group = quotedGroupHtml(
  [placed(W({ attaches_to: { kind: "step", ref: "cure" } }), "step", "cure")],
  "annexe.on_step");

// The whole annexe, over a placement carrying one of everything.
const PLACEMENT = {
  placements: [
    placed(W(), "annexe", "", 83),
    placed(W({ attaches_to: { kind: "warranty", ref: "" },
               text_raw: "Warranty void on substitution." }), "annexe"),
    placed(W({ attaches_to: { kind: "step", ref: "cure" } }), "step", "cure"),
    placed(W({ attaches_to: { kind: "product", ref: "SLAT-V-150" } }),
           "product", "SLAT-V-150"),
    placed(W({ attaches_to: { kind: "procedure", ref: "PROC-1" } }),
           "unplaceable", "PROC-1"),
  ],
  not_in_plan: 4,
};
out.annexe = annexeHtml(PLACEMENT);
out.annexe_named = annexeHtml(PLACEMENT, { id: "structure-annexe" });
out.annexe_drawn = annexeHtml(PLACEMENT,
  { drawn: ["step", "procedure", "product", "model"] });
out.annexe_nothing = annexeHtml({ placements: [], not_in_plan: 0 });
out.annexe_only_elsewhere = annexeHtml({
  placements: [placed(W({ attaches_to: { kind: "step", ref: "cure" } }),
                      "step", "cure")],
  not_in_plan: 0,
});
out.buckets = {
  step: bucket(PLACEMENT, "step").length,
  step_named: bucket(PLACEMENT, "step", "cure").length,
  step_other: bucket(PLACEMENT, "step", "rails").length,
  annexe: bucket(PLACEMENT, "annexe").length,
  none: bucket(null, "annexe").length,
};

await setLocale("he");
out.he_furniture = annexeHtml(PLACEMENT);
out.he_quote_of_english = quotedWarningHtml(placed(W(), "annexe"));

out.keys = {
  quoted: EN["annexe.quoted"],
  unattributed: EN["annexe.unattributed"],
  instances_83: EN["annexe.instances"].replace("{n}", "83"),
  on_step: EN["annexe.on_step"],
  title: EN["annexe.title"],
  empty: EN["annexe.empty"],
  he_title: HE["annexe.title"],
  he_quoted: HE["annexe.quoted"],
  elsewhere_steps_1: EN["annexe.elsewhere_steps"].replace("{n}", "1"),
  elsewhere_lines_1: EN["annexe.elsewhere_lines"].replace("{n}", "1"),
  other_documents_4: EN["annexe.other_documents"].replace("{n}", "4"),
  unplaceable_1: EN["annexe.unplaceable"].replace("{n}", "1"),
};

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def rendered():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- the text ----------------------------------------------------------------

def test_the_text_is_rendered_verbatim(rendered):
    """Not localized, not normalised, not summarised. The one thing this module
    does with the sentence is escape it."""
    assert "CAUTION: set footings below the frost line." in rendered["plain"]


def test_a_quoted_sentence_says_that_it_is_quoted_and_untranslated(rendered):
    """The reader has to be able to tell "the manufacturer says" from "this
    system found". Without the note, an English sentence on a Hebrew page reads
    as an untranslated string the app forgot."""
    assert rendered["keys"]["quoted"] in rendered["plain"]


def test_a_manufacturers_sentence_is_data_and_never_markup(rendered):
    """It arrives from a document somebody else wrote, through a boundary nobody
    on this side controls. `esc()`, like every other human sentence in the app."""
    assert "<img src=x" not in rendered["markup"]
    assert "&lt;img src=x" in rendered["markup"]


def test_the_publishers_severity_word_is_printed_as_it_arrived(rendered):
    """CAUTION and WARNING are terms of art with different legal weight. Both
    appear unchanged, and a warning with no severity word gets no invented one."""
    caution, warning, none = rendered["lexemes"]
    assert ">CAUTION<" in caution and ">WARNING<" in warning
    assert "lexeme" not in none


def test_a_publishers_code_never_becomes_the_sentence(rendered):
    """`code` + `params` are an overlay for grouping. The text is what renders —
    and the code is not in our bundles, so a lookup would have fallen back to
    printing the code itself at the reader."""
    assert "Not rated as a pool barrier." in rendered["with_code"]
    assert "not_pool_rated" not in rendered["with_code"]
    assert "IRC AG105.2" not in rendered["with_code"]


# --- direction, which is the one thing inferred from `lang` -------------------

def test_the_direction_follows_the_quoted_language_not_the_page(rendered):
    """An English sentence in a Hebrew-first RTL page needs `dir="ltr"` on the
    element holding it, or its full stop walks to the wrong end of the line. The
    Hebrew quotation on the same page needs the opposite."""
    assert 'lang="en"' in rendered["plain"] and 'dir="ltr"' in rendered["plain"]
    assert 'lang="he"' in rendered["hebrew_quote"]
    assert 'dir="rtl"' in rendered["hebrew_quote"]


def test_the_furniture_is_localized_and_the_quotation_is_not(rendered):
    """The split, visible in one output: the annexe's own title follows the
    reader's language, and the sentence inside it stays in the language it was
    published in."""
    assert rendered["keys"]["he_title"] in rendered["he_furniture"]
    assert rendered["keys"]["he_quoted"] in rendered["he_quote_of_english"]
    assert "CAUTION: set footings below the frost line." \
        in rendered["he_quote_of_english"]
    assert 'dir="ltr"' in rendered["he_quote_of_english"]


# --- attribution -------------------------------------------------------------

def test_an_unattributed_warning_does_not_look_like_a_checkable_one(rendered):
    """A source reference proves where the system looked (§3.3.1). Its absence
    has to be as visible as its presence, or a sentence nobody can trace reads
    exactly like one an engineer confirmed against a drawing."""
    assert rendered["keys"]["unattributed"] in rendered["plain"]
    assert rendered["keys"]["unattributed"] not in rendered["cited"]
    assert "SRC-7" in rendered["cited"] and "sha256:doc-a" in rendered["cited"]


# --- the collapse ------------------------------------------------------------

def test_a_footnote_printed_83_times_says_so_and_appears_once(rendered):
    """The count is what makes "shown once" a decision the reader can see. Left
    out, one entry looks like all there was."""
    assert rendered["keys"]["instances_83"] in rendered["repeated"]
    assert rendered["keys"]["instances_83"] not in rendered["once"]
    assert "{n}" not in rendered["repeated"]


# --- the annexe --------------------------------------------------------------

def test_the_annexe_holds_the_job_wide_warnings_and_nothing_else(rendered):
    """Two entries — the footnote and the warranty condition — out of a placement
    that also carries a step warning, a product warning and a stranded one."""
    assert rendered["keys"]["title"] in rendered["annexe"]
    assert "Warranty void on substitution." in rendered["annexe"]
    assert rendered["annexe"].count('class="doc-warning"') == 2


def test_the_annexe_accounts_for_every_warning_it_is_not_showing(rendered):
    """A sheet that showed two notices while silently holding six more would be
    worse than one that showed none, because a reader would believe they had seen
    the warnings."""
    for key in ("elsewhere_steps_1", "elsewhere_lines_1", "other_documents_4"):
        assert rendered["keys"][key] in rendered["annexe"], key


def test_a_stranded_warning_reads_as_a_warning_and_not_as_a_footnote(rendered):
    """A warning with nowhere to go is a gap in this engine, not a note about the
    document. `procedures` are published (§1.2) and this engine models none, so
    the honest thing is to say so where a reader will see it."""
    assert rendered["keys"]["unplaceable_1"] in rendered["annexe"]
    assert '<div class="warning">' in rendered["annexe"]


def test_a_surface_that_draws_a_bucket_itself_is_not_told_to_look_elsewhere(rendered):
    """The Panel tab renders the step, procedure and product buckets on its own
    steps and rows, so pointing its reader at "the BOM line" — a surface that
    screen has not got — would be an instruction they cannot follow."""
    assert rendered["keys"]["elsewhere_steps_1"] not in rendered["annexe_drawn"]
    assert rendered["keys"]["elsewhere_lines_1"] not in rendered["annexe_drawn"]
    # what is NOT drawn by that caller is still accounted for
    assert rendered["keys"]["other_documents_4"] in rendered["annexe_drawn"]
    assert rendered["keys"]["unplaceable_1"] in rendered["annexe_drawn"]


def test_a_document_with_no_warnings_renders_no_annexe_at_all(rendered):
    """An empty panel headed "what the documents warn" reads as an answer. There
    is nothing to say, so nothing is said."""
    assert rendered["annexe_nothing"] == ""


def test_an_annexe_with_only_warnings_elsewhere_says_it_is_empty(rendered):
    """The other half of the same judgement: there IS something to say — four
    warnings exist and none of them belongs here — so the panel appears and says
    the annexe itself is empty rather than implying the document is silent."""
    assert rendered["keys"]["empty"] in rendered["annexe_only_elsewhere"]
    assert rendered["keys"]["elsewhere_steps_1"] in rendered["annexe_only_elsewhere"]


# --- the lookup --------------------------------------------------------------

def test_a_group_with_nothing_in_it_renders_nothing(rendered):
    """So every caller can concatenate it unconditionally — the contract
    `supplyProblemsHtml` already keeps."""
    assert rendered["empty_group"] == ""
    assert rendered["keys"]["on_step"] in rendered["step_group"]


def test_the_client_reads_the_buckets_and_never_recomputes_them(rendered):
    """`bucket` filters on `where`/`ref` — the placement the backend already
    decided. A client filtering on `attaches_to.kind` itself would be free to
    disagree with the plan about where the freeze-thaw footnote belongs."""
    b = rendered["buckets"]
    assert b["step"] == 1 and b["step_named"] == 1 and b["step_other"] == 0
    assert b["annexe"] == 2
    assert b["none"] == 0        # no placement at all is not a crash


def test_a_quoted_warning_is_not_one_of_this_engines_warnings(rendered):
    """It carries `.doc-warning` and never `.warning`, and the browser suite is
    what forced the distinction: a check counting `#tab-panel .warning` to prove a
    channelled panel reports NO GAP was counting a manufacturer's pool-barrier
    notice as a hole in this engine's own answer. Two kinds of thing, two
    selectors — which is item 8 in one class name.

    The exception is deliberate: a warning this engine cannot PLACE is our defect,
    so the annexe's unplaceable note IS a `.warning` and should be counted."""
    assert 'class="doc-warning"' in rendered["plain"]
    assert 'class="warning' not in rendered["plain"]
    assert '<div class="warning">' in rendered["annexe"]   # the unplaceable note


def test_the_caller_names_the_annexe_it_owns(rendered):
    """Both the Panel tab and the setting-out sheet render an annexe, and both are
    in the DOM at once. A hardcoded id here gave two elements the same one, so
    `getElementById` returned whichever came first and the panel sheet's check
    read the structure sheet's annexe — found by the browser suite, which is the
    only place both surfaces exist together. Each module owns and names its own
    subtree (CLAUDE.md)."""
    assert 'id=' not in rendered["annexe"]
    assert 'id="structure-annexe"' in rendered["annexe_named"]
    # the class is stable either way, so a caller can still find "an annexe"
    assert 'class="panel annexe"' in rendered["annexe"]


def test_a_word_the_quotation_already_leads_with_is_not_printed_twice(rendered):
    """The screenshot said it: "WARNING WARNING: This fence is not a pool
    barrier". The publisher leads its own sentence with its own word, and the
    badge repeated it.

    Suppressing the BADGE is not editing the quotation — the text goes out
    untouched either way. The reverse would be: trimming the word out of the
    sentence so the badge looked tidy is exactly the kind of tidying this module
    exists to refuse."""
    assert "WARNING: This fence is not a pool barrier." in rendered["leading"]
    assert rendered["leading"].count("WARNING") == 1
    assert "lexeme" not in rendered["leading"]
