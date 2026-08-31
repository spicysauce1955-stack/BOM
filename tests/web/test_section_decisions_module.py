"""The section-decisions panel (static/js/section-decisions.js), run in node.

The browser suite can see that the panel appears and that a comment round-trips.
What only node can check is the part that would be wrong SILENTLY: that expert
prose is escaped rather than interpolated, that a decision with no conversation
still offers to start one, and that the panel says something rather than nothing
when a section has no decisions.

It renders against the REAL locale bundle, so what node produces is what the
browser produces.
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
  documentElement: {},
};
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { setLocale } from "./js/i18n.js";
import { commentHtml, sectionHtml } from "./js/section-decisions.js";

// Assert against the BUNDLE, never against the copy. A wording change is not a
// regression, and a test that spells the sentence out reddens on a copy edit
// while passing if the wrong key were rendered with matching text.
const EN = JSON.parse(readFileSync("./i18n/en.json", "utf8"));
const HE = JSON.parse(readFileSync("./i18n/he.json", "utf8"));

const out = {};
const BODY = {
  section_id: "run1",
  decisions: [
    { node_id: "d0001", ordinal: 1, kind: "input_fact", action: "run_geometry",
      elements: [], sentence: "Section run1 is 6000 mm long.",
      governed_by: [], defeated: [] },
    { node_id: "d0007", ordinal: 7, kind: "structural", action: "layout_spans",
      elements: ["span@run1:0-1500"], sentence: "Four bays of 1500 mm.",
      governed_by: ["K-MAXSPAN@v1"], defeated: [] },
  ],
};

await setLocale("en");
out.empty_section = sectionHtml({ section_id: "run9", decisions: [] });
out.plain = sectionHtml(BODY);
out.governed = out.plain.includes("K-MAXSPAN@v1");

// a decision with a conversation offers to ADD, one without offers to START
const threads = new Map([["d0007", [
  { comment: "the closing bay should be the odd one", author: "dana",
    created_at: "2026-08-19T21:30:00+00:00" },
]]]);
out.with_thread = sectionHtml(BODY, threads);
out.shows_comment = out.with_thread.includes("the closing bay should be the odd one");
out.author = out.with_thread.includes("dana");

// THE escaping rule: expert prose is data, never markup
const nasty = { comment: '<img src=x onerror="alert(1)">', author: "<b>x</b>",
                created_at: "2026-08-19T21:30:00+00:00" };
out.escaped = commentHtml(nasty);

// a comment is keyed to the decision it is ABOUT: the d0001 block must be clean
const chunk = (html, node) => {
  const parts = html.split('data-node="');
  const hit = parts.find((p) => p.startsWith(node));
  return hit || "";
};
out.d0001_comments = (chunk(out.with_thread, "d0001").match(/class="verbatim"/g) || []).length;
out.d0007_comments = (chunk(out.with_thread, "d0007").match(/class="verbatim"/g) || []).length;

// human prose and an author name are direction-isolated (CLAUDE.md)
out.isolated = commentHtml({ comment: "שלום world", author: "dana",
                             created_at: "2026-08-19T21:30:00+00:00" });

// a conversation from an earlier run is NAMED rather than silently absent
out.earlier = sectionHtml(BODY, new Map(), null, 3);

out.keys = {
  start: EN["decisions.start_conversation"], add: EN["decisions.add_comment"],
  none: EN["decisions.none_here"], note: EN["decisions.comment_note"],
  he_start: HE["decisions.start_conversation"],
  he_hint: HE["decisions.hint"], he_earlier: HE["decisions.earlier"],
};

// the form appears only on the decision it was opened for
out.form_scoped = sectionHtml(BODY, new Map(), "d0007");
out.form_count = (out.form_scoped.match(/data-form=/g) || []).length;

await setLocale("he");
out.he = sectionHtml(BODY);

// The panel's own sentences carry latin parameters INTO Hebrew prose: a run id
// mid-sentence followed by a comma, and a count opening one. The convention is
// escape the template, then drop each parameter in wrapped in <bdi>
// (warnings.js localizedByCode, panel.js sentence) — escaping the whole
// rendered sentence instead leaves the parameter without its own direction and
// the id reorders against the punctuation beside it.
out.he_earlier = sectionHtml(BODY, new Map(), null, 3);
// escape-then-isolate, not isolate-then-inject-raw: the parameter is machine
// data here, but the shape has to stay the safe one
out.he_hostile = sectionHtml(
  { section_id: '<img src=x onerror="alert(1)">', decisions: [] });

// -- §1.4 `admitted_by`: what backed a number, beside the fact that decided it
await setLocale("en");
const JUDGED = {
  ...BODY,
  admitted: {
    "K-MAXSPAN@v1": {
      rank: 40, source_class: "manufacturer_installation_instruction",
      curation_level: 2, version_status: "unknown",
    },
  },
};
out.judged = sectionHtml(JUDGED);
// an ABSENT verdict renders nothing rather than an "unverified" claim: an
// authored rule has no document behind it to have checked
out.unjudged = sectionHtml(BODY);

// an OPEN-registry class we have no word for must read as its own name, never
// as a raw locale key
out.unknown_class = sectionHtml({
  ...BODY,
  admitted: { "K-MAXSPAN@v1": {
    rank: 1, source_class: "future_class_we_have_no_word_for",
    curation_level: 0, version_status: "active" } },
});

// a hostile class name is data, not markup
out.hostile_class = sectionHtml({
  ...BODY,
  admitted: { "K-MAXSPAN@v1": {
    rank: 1, source_class: '<img src=x onerror="alert(1)">',
    curation_level: 0, version_status: "active" } },
});

await setLocale("he");
out.he_judged = sectionHtml(JUDGED);
out.he_keys = { admitted: HE["decisions.admitted_by"],
                level: HE["decisions.curation_level"] };

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def rendered():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_section_with_no_decisions_says_so(rendered):
    """Silence reads as broken. A section nothing was decided about is a real
    state and gets a sentence."""
    assert rendered["keys"]["none"] in rendered["empty_section"]


def test_each_decision_shows_its_sentence_and_what_governed_it(rendered):
    assert "Four bays of 1500 mm." in rendered["plain"]
    assert "Section run1 is 6000 mm long." in rendered["plain"]
    assert rendered["governed"], "the rule that governed a decision belongs beside it"


def test_a_decision_with_nothing_said_offers_to_START_a_conversation(rendered):
    """The roadmap's word. A button reading "add a comment" on an empty thread
    invites you to add to nothing."""
    assert rendered["keys"]["start"] in rendered["plain"]
    assert rendered["keys"]["add"] not in rendered["plain"]


def test_a_decision_that_has_been_discussed_shows_the_conversation(rendered):
    assert rendered["shows_comment"]
    assert rendered["author"]
    assert rendered["keys"]["add"] in rendered["with_thread"]


def test_the_boundary_is_stated_where_the_conversation_IS(rendered):
    """It used to live only inside the comment form, so it vanished the moment
    you commented — the reader saw the promise while typing and never again. A
    thread that exists is exactly where "this changed nothing on its own" has to
    keep being true."""
    assert rendered["keys"]["note"] in rendered["with_thread"]
    assert rendered["keys"]["note"] not in rendered["plain"], \
        "an empty decision has no conversation to qualify"


def test_expert_prose_is_escaped_rather_than_interpolated(rendered):
    """Any user or expert text reaching `innerHTML` goes through `esc()`
    (CLAUDE.md). A comment is the most obviously attacker-controlled string in
    the app: it is typed by a person and rendered to everyone who opens the
    project."""
    html = rendered["escaped"]
    # the payload must not survive as MARKUP. `onerror` appearing as escaped
    # TEXT is harmless and asserting on it would be testing the payload's
    # spelling rather than the escaping — what matters is that no `<` from the
    # comment reached the document as a tag.
    assert '<img src=x' not in html
    assert "&lt;img src=x onerror=" in html
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


def test_only_the_decision_asked_about_opens_a_comment_box(rendered):
    """One form at a time: a box under every decision is a wall of inputs on a
    section with twenty of them."""
    assert rendered["form_count"] == 1
    assert 'data-form="d0007"' in rendered["form_scoped"]


def test_a_comment_is_shown_under_the_decision_it_is_ABOUT(rendered):
    """Keying, not merely presence. Rendering every comment under every decision
    passed a test that only asked whether the text appeared somewhere — and it
    is the failure that would make the panel actively misleading, attributing an
    argument to a decision nobody made it about."""
    assert rendered["d0007_comments"] == 1
    assert rendered["d0001_comments"] == 0


def test_a_comment_is_direction_isolated(rendered):
    """Hebrew prose beside a latin author name and an ISO timestamp: without
    `dir="auto"` and `<bdi>` the punctuation migrates across the line. CLAUDE.md
    requires both for user text."""
    assert 'dir="auto"' in rendered["isolated"]
    assert "<bdi>" in rendered["isolated"]


def test_a_conversation_from_an_earlier_run_is_named_not_hidden(rendered):
    """A decision is numbered per generation, so older comments cannot be matched
    to the decisions below — but going silent would offer to "start" a
    conversation two people already had. Counted and named at the PANEL, which
    is the finest grain at which the statement is true."""
    assert "3" in rendered["earlier"]
    assert rendered["earlier"] != rendered["plain"]


def test_the_panel_speaks_the_readers_language(rendered):
    assert rendered["keys"]["he_start"] in rendered["he"]
    assert rendered["keys"]["start"] not in rendered["he"]


def test_a_run_id_inside_a_hebrew_sentence_is_direction_isolated(rendered):
    """Hebrew is the locale the app opens in, and `decisions.hint` puts a latin
    run id in the middle of the sentence with a comma right after it. Without
    `<bdi>` the id and that punctuation swap sides on screen — the classic bidi
    run reversal. Asserted against the BUNDLE with only the parameter slot
    filled, so this pins the isolation without spelling the copy out."""
    expected = rendered["keys"]["he_hint"].replace("{section}", "<bdi>run1</bdi>")
    assert expected in rendered["he"]


def test_a_count_inside_a_hebrew_sentence_is_direction_isolated(rendered):
    """Same sentence shape, opening figure: `decisions.earlier` leads with the
    count and continues in Hebrew."""
    expected = rendered["keys"]["he_earlier"].replace("{count}", "<bdi>3</bdi>")
    assert expected in rendered["he_earlier"]


def test_an_isolated_parameter_is_still_escaped(rendered):
    """Escape-then-isolate, never isolate-then-inject-raw. The parameter is a
    run id — machine data — but the ONE convention this codebase has escapes
    both the template and every value it drops into it, and a pattern that is
    safe only because of what happens to flow through it today is not safe."""
    html = rendered["he_hostile"]
    assert "<bdi>&lt;img src=x onerror=" in html
    assert "<img src=x" not in html


# -- §1.4's verdict, shown where the fact that decided the number is shown ------

def test_what_backed_a_number_is_shown_beside_the_fact_that_decided_it(rendered):
    """Obligation §3.3.2: show curation level and source class wherever a value
    appears. Until now the panel named the fact (`K-MAXSPAN@v1`) and said nothing
    about whether anyone had checked the document behind it."""
    assert "manufacturer_installation_instruction" in rendered["judged"]
    assert rendered["he_keys"]["admitted"] in rendered["he_judged"]
    assert rendered["he_keys"]["level"].replace("{level}", "") .strip() \
        in rendered["he_judged"].replace("<span class=\"num\">2</span>", "")


def test_an_unjudged_fact_shows_no_verdict_rather_than_a_failing_one(rendered):
    """The distinction the whole slice turns on. An authored company rule has no
    document behind it, so there is nothing to have checked — and rendering
    "unverified" there would be a claim about provenance that does not apply,
    while rendering nothing is the honest reading: this is our rule.

    A judged pass and an unjudged fact must therefore look different on screen,
    which is why absence is rendered as absence and never defaulted."""
    assert "admitted" not in rendered["unjudged"]
    assert "K-MAXSPAN@v1" in rendered["unjudged"], "the fact is still named"


def test_an_unregistered_source_class_reads_as_itself_not_as_a_locale_key(rendered):
    """`SourceClass` is an OPEN registry — the other side adds entries without a
    release here (§2). So it is rendered as DATA and never concatenated into a
    locale key, or the day they register one we have no word for it appears on
    screen as `decisions.source_class.future_thing` in both languages."""
    assert "future_class_we_have_no_word_for" in rendered["unknown_class"]
    assert "decisions.source_class" not in rendered["unknown_class"]


def test_a_hostile_source_class_is_escaped(rendered):
    """It arrives over the boundary, so it is untrusted text like any other.

    Asserted on the ANGLE BRACKET rather than on `onerror=`: the escaped string
    still contains that substring as text, and a test forbidding it would pass
    only by accident of wording. What makes it inert is that no element is
    created, so `<img` must not survive and the quote must be escaped."""
    html = rendered["hostile_class"]
    assert "<img" not in html
    assert "&lt;img" in html
    assert 'onerror="alert' not in html, "the quote must be escaped, not raw"
