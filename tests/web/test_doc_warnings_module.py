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
import { setUnits } from "./js/units.js";
import { annexeHtml, bucket, quotedGroupHtml, quotedWarningHtml }
  from "./js/doc-warnings.js";
// The CALL SITES, not only the renderer. Every one of these was reachable only
// through the browser, and the test review proved it: a mutant emptying the
// withheld-step list, one dropping the per-sku dedup and one making the BOM's
// warning row return "" all survived the entire pytest suite.
import { assemblyPlanHtml } from "./js/panel.js";
import { bomHtml } from "./js/tabs.js";

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
  cites: [{ id: "SRC-7", belongs_to: "sha256:doc-a" }] }), "annexe"));
out.repeated = quotedWarningHtml(placed(W(), "annexe", "", 83));
out.once = quotedWarningHtml(placed(W(), "annexe", "", 1));
// a publisher's own code rides along and never becomes the sentence
out.with_code = quotedWarningHtml(placed(W({
  code: "not_pool_rated", params: { standard: "IRC AG105.2" },
  text_raw: "Not rated as a pool barrier." }), "annexe"));
// ...and the case where localizing is OBSERVABLE: a publisher's code that
// collides with one of OUR platform codes. `not_pool_rated` is correctly absent
// from both bundles, so a renderer that looked the code up would fall back to
// the text and hide the mutation. This one has a sentence in en.json, so a
// lookup would print OUR words over THEIRS.
out.colliding_code = quotedWarningHtml(placed(W({
  code: "sliver_span",
  text_raw: "Trim the last board to suit; do not stretch the spacing." }),
  "annexe"));

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
    // a `model`-bucket entry, because without one the mutant that drops the
    // `model` term from the annexe's own accounting survived: the fixture simply
    // never had anything in that bucket to lose
    placed(W({ attaches_to: { kind: "model", ref: "M-VINYL@v1" },
               text_raw: "This line is discontinued." }), "model", "M-VINYL@v1"),
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

// --- the call sites ---------------------------------------------------------
// A plan whose `cure` step is SITE-scoped, so the panel sheet withholds the step
// (obligation 12) and must still show the warning hanging off it.
const STEP_PLAN = {
  model_ref: "M-X@v1",
  steps: [
    { key: "rails", kind: "assembly", scope: "panel", stage: 0,
      text_i18n: { en: "Slide the rails through." }, parts: [] },
    { key: "cure", kind: "installation", scope: "site", stage: 1,
      text_i18n: { en: "Let the footings cure." }, parts: [] },
  ],
  order: { stages: [["rails"], ["cure"]], unique: true, basis: "requires",
           cycle: [], exclusive: [], concurrent: [] },
  unplaced: [], unplaced_bay: [],
};
const STEP_PLACEMENT = {
  placements: [
    placed(W({ text_raw: "WARNING: do not load an uncured footing.",
               attaches_to: { kind: "step", ref: "cure" } }), "step", "cure"),
    placed(W({ text_raw: "Slide, do not force.",
               attaches_to: { kind: "step", ref: "rails" } }), "step", "rails"),
    placed(W({ text_raw: "Read the whole guide first.",
               attaches_to: { kind: "procedure", ref: "" } }), "procedure"),
  ],
  not_in_plan: 0,
};
out.sheet = assemblyPlanHtml(STEP_PLAN, STEP_PLACEMENT);
out.sheet_no_quoted = assemblyPlanHtml(STEP_PLAN, null);

// The BOM: one product notice, on the line for its own sku, once — even when two
// lines somehow share a sku.
const BOM = {
  total_cents: 1000,
  lines: [
    { sku: "RAIL-3000", purchase_qty: 4, purchase_unit: "bar", engineering_qty: 4,
      engineering_unit: "each", overage_qty: 0, unit_price_cents: 100,
      total_cents: 400, notes: [] },
    { sku: "RAIL-3000", purchase_qty: 1, purchase_unit: "bar", engineering_qty: 1,
      engineering_unit: "each", overage_qty: 0, unit_price_cents: 100,
      total_cents: 100, notes: [] },
    { sku: "SLAT-100", purchase_qty: 9, purchase_unit: "each", engineering_qty: 9,
      engineering_unit: "each", overage_qty: 0, unit_price_cents: 50,
      total_cents: 450, notes: [] },
  ],
  cut_plans: {},
};
const BOM_PLACEMENT = {
  placements: [
    placed(W({ text_raw: "Pre-drill before screwing.",
               attaches_to: { kind: "product", ref: "RAIL-3000" } }),
           "product", "RAIL-3000"),
    placed(W({ text_raw: "This line is discontinued.",
               attaches_to: { kind: "model", ref: "M-X@v1" } }), "model", "M-X@v1"),
    placed(W(), "annexe", "", 3),
  ],
  not_in_plan: 0,
};
setUnits("mm");
out.bom = bomHtml(BOM, [], { quoted: BOM_PLACEMENT });
out.bom_frozen = bomHtml(BOM, [], {});   // the quote path passes no placement

// The annexe as the PRINTED sheet asks for it: the other buckets drawn here,
// because the printout contains neither the panel sheet nor the BOM tab.
out.annexe_inline = annexeHtml(BOM_PLACEMENT,
  { id: "structure-annexe", inline: ["step", "procedure", "product", "model"] });
out.annexe_unreadable = annexeHtml(
  { placements: [], not_in_plan: 0, documents_unreadable: 2 });
out.annexe_procedure_note = annexeHtml(STEP_PLACEMENT);

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
  our_sentence_for_a_colliding_code: EN["warning.sliver_span"],
  elsewhere_steps_1: EN["annexe.elsewhere_steps"].replace("{n}", "1"),
  elsewhere_lines_1: EN["annexe.elsewhere_lines"].replace("{n}", "1"),
  other_documents_4: EN["annexe.other_documents"].replace("{n}", "4"),
  elsewhere_lines_2: EN["annexe.elsewhere_lines"].replace("{n}", "2"),
  unplaceable_1: EN["annexe.unplaceable"].replace("{n}", "1"),
  on_withheld: EN["annexe.on_withheld_step"],
  on_procedure: EN["annexe.on_procedure"],
  on_target: EN["annexe.on_target"].split("{ref}")[0],
  elsewhere_procedure_1: EN["annexe.elsewhere_procedure"].replace("{n}", "1"),
  unreadable_2: EN["annexe.documents_unreadable"].replace("{n}", "2"),
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
    # `elsewhere_lines` counts the product AND model buckets together — one of
    # each here, so 2. The fixture had no `model` entry until the test review
    # showed a mutant dropping that term surviving for want of anything to lose.
    for key in ("elsewhere_steps_1", "elsewhere_lines_2", "other_documents_4"):
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


# --- the call sites, which were browser-only ---------------------------------

def test_a_warning_on_a_withheld_step_reaches_the_sheet(rendered):
    """The browser found this defect and the browser was then its only guard: a
    mutant emptying `heldWarnings` survived the whole pytest suite and put the
    defect straight back. `cure` is site-scoped, so obligation 12 withholds the
    STEP from a panel sheet — and the warning hanging off it is the document's
    most safety-relevant sentence, so it is shown with the withheld note instead.

    Both halves asserted: the step is genuinely not drawn, and its warning is on
    the sheet anyway."""
    sheet = rendered["sheet"]
    assert 'data-step="cure"' not in sheet          # the step is withheld
    assert "Let the footings cure." not in sheet
    assert "WARNING: do not load an uncured footing." in sheet
    assert rendered["keys"]["on_withheld"] in sheet


def test_a_step_warning_lands_on_its_own_step_and_no_other(rendered):
    """The drawn half of the same wiring. `rails` is a panel step, so its warning
    is inside its own `<li>` — not in the withheld group with `cure`'s."""
    sheet = rendered["sheet"]
    li = sheet[sheet.index('data-step="rails"'):]
    li = li[:li.index("</li>")]
    assert "Slide, do not force." in li
    assert "WARNING: do not load an uncured footing." not in li


def test_the_procedure_head_is_above_the_steps(rendered):
    """A "read the whole guide first" warning is about the procedure, not about
    any step in it, so it renders at the head — above the numbered list."""
    sheet = rendered["sheet"]
    assert "Read the whole guide first." in sheet
    assert sheet.index("Read the whole guide first.") < sheet.index("<ol")
    assert rendered["keys"]["on_procedure"] in sheet


def test_a_sheet_handed_no_placement_still_renders(rendered):
    """Every quoted-warning call site has to tolerate a payload from before the
    field existed — a stored run re-read, a saved quote — so `null` is a
    supported argument and not a crash."""
    assert 'data-step="rails"' in rendered["sheet_no_quoted"]
    assert "doc-warning" not in rendered["sheet_no_quoted"]


def test_the_bom_carries_a_product_notice_once_per_line_group(rendered):
    """"Once per line group" (§3.3.5). The fixture gives two lines the same sku —
    which `Bom.lines` should never do, and which is exactly why the dedup is
    there — and the notice appears once. A mutant dropping `seenSku` survived the
    whole suite."""
    bom = rendered["bom"]
    assert bom.count("Pre-drill before screwing.") == 1
    assert bom.count('class="doc-warning-row"') == 1


def test_the_bom_notice_sits_under_the_line_it_is_about(rendered):
    """Not merely present: on the right row. A notice about RAIL-3000 under the
    SLAT-100 line is worse than no notice."""
    bom = rendered["bom"]
    row = bom.index('class="doc-warning-row"')
    assert bom.rindex("RAIL-3000", 0, row) > bom.rfind("SLAT-100", 0, row)


def test_a_model_scoped_notice_is_drawn_once_above_the_table(rendered):
    """`model` is the whole product line, so it is one notice for the bill and not
    one per row. Its own label, because "this product" and "this product line"
    are different claims."""
    bom = rendered["bom"]
    assert bom.count("This line is discontinued.") == 1
    assert bom.index("This line is discontinued.") < bom.index("<table")


def test_the_bom_does_not_carry_the_annexe(rendered):
    """The annexe belongs to the PLAN and renders on the setting-out sheet.
    Printing it here as well is the same notice twice, which is how a reader
    learns to skip both."""
    assert "panel annexe" not in rendered["bom"]


def test_a_frozen_quote_carries_no_live_notices(rendered):
    """`bomHtml` renders saved quotes too, and the quote path deliberately passes
    no placement: a `Quote` is an immutable commercial document, and annotating a
    historical one with what its manufacturer says TODAY prints text on a page
    nobody accepted. Untested anywhere before — a regression here was silent."""
    assert "doc-warning" not in rendered["bom_frozen"]
    assert "Pre-drill before screwing." not in rendered["bom_frozen"]


# --- the printed plan --------------------------------------------------------

def test_the_printed_annexe_carries_the_warnings_the_printout_cannot_cite(rendered):
    """The print stylesheet emits only the canvas and structure tabs, so a
    setting-out sheet that said "shown on the panel sheet" was citing a page the
    printout does not contain — and a "do not load an uncured footing" warning
    reached site nowhere. `inline` draws them here instead, each labelled with
    what it attaches to."""
    out = rendered["annexe_inline"]
    assert "Pre-drill before screwing." in out          # a product notice...
    assert rendered["keys"]["on_target"] in out         # ...labelled with its sku
    assert "RAIL-3000" in out
    # ...and no note sending the reader to a surface the printout has not got
    assert rendered["keys"]["elsewhere_lines_1"] not in out


def test_a_procedure_warning_is_accounted_for_when_it_is_not_drawn(rendered):
    """`procedure` had no term in the annexe's accounting at all, which is how a
    procedure-scoped warning on a document with no assembly steps came to render
    nowhere while the backend reported it placed and the invariant balanced."""
    assert rendered["keys"]["elsewhere_procedure_1"] in rendered["annexe_procedure_note"]


def test_a_document_that_could_not_be_read_is_said_out_loud(rendered):
    """Skipping an unreadable document is the right trade — a missing annexe is
    not a reason to take a working BOM away — but skipping in SILENCE means a
    plan built to a document carrying a safety notice prints with no annexe and
    no reason. It reads as a warning because it is ours, not the document's."""
    out = rendered["annexe_unreadable"]
    assert rendered["keys"]["unreadable_2"] in out
    assert '<div class="warning">' in out


def test_a_publishers_code_that_collides_with_ours_still_renders_their_words(rendered):
    """The case that makes "never localizes" testable rather than merely grepped.

    The source-text guard in `test_locale_bundles.py` was evaded in one line by
    the test review, and the reason it could not be caught behaviourally is that
    no fixture used a code with an entry in a bundle — `not_pool_rated` is
    correctly absent, so a renderer that looked it up would fall back to the text
    and hide the mutation.

    `sliver_span` IS one of our platform codes with a sentence in both bundles. A
    publisher sending it means what the publisher means, and their text is what
    renders. Ours must not appear."""
    out = rendered["colliding_code"]
    assert "Trim the last board to suit; do not stretch the spacing." in out
    assert rendered["keys"]["our_sentence_for_a_colliding_code"] not in out
    assert "sliver_span" not in out
