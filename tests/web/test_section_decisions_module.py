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
};

// the form appears only on the decision it was opened for
out.form_scoped = sectionHtml(BODY, new Map(), "d0007");
out.form_count = (out.form_scoped.match(/data-form=/g) || []).length;

await setLocale("he");
out.he = sectionHtml(BODY);

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
