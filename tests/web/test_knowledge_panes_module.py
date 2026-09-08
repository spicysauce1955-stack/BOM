"""The Knowledge tab's reorganization, and the properties that make it a fix.

The tab used to be one stacked page whose rules list drew a card for EVERY
version `GET /api/knowledge` returns — overwhelmingly `proposed` candidates the
Review tab already owns behind its own filtered endpoint — with `scope` and
`actions` rendered as two `JSON.stringify` dumps per card.

Four things here are load-bearing, and each of them is green-and-broken if only
the code is right:

  * the candidates are excluded AND counted. A filter that silently drops rows
    is indistinguishable from missing data, so the exclusion has to be stated.
  * every action kind the builder can WRITE has a sentence to be READ as. A
    kind with no phrasing renders a raw i18n key inside a Hebrew card, and key
    parity cannot see it because the key is computed.
  * both bundles' templates take the same placeholders. A translation that
    drops `{weight}` loses a number silently — the sentence still reads.
  * the phrasing has ONE owner. The review queue renders the same two fields on
    a candidate, so a second copy is how the two tabs come to describe one rule
    differently.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"
JS = STATIC / "js"


# --------------------------------------------------- the pane, actually drawn
#
# Four of the assertions below used to be regexes over the module's source, and
# a reviewer proved each of them blind: `if (v.status === "proposed") { proposed++;
# active.push(v); }` — a filter that excludes NOTHING, which is the entire point
# of the redesign — left `assert 'status === "proposed"' in src` green and the
# whole web suite passing. A source that mentions the right token is not a pane
# that drew the right cards.
#
# So the pane is RUN, in node, against a DOM stub and the real locale bundle:
# the same idiom `test_gaps_module.py` and `test_panel_inspector_module.py` use.
# What node cannot see is stated where it matters — `<details>` collapses in a
# browser and nowhere else — and points at the browser case that does
# (`_smoke_knowledge_panes` in tools/ui_smoke.py).

SCRIPT = r"""
import { readFileSync } from "node:fs";

// A DOM stub, not a DOM. This pane reaches for elements BY ID (it owns
// `#pane-k-rules`), so the stub carries a registry of exactly the six ids
// index.html gives it and THROWS on any other — which makes "the pane touches
// no DOM but its own" an assertion rather than a comment.
class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.style = {};
    this.className = "";
    this.hidden = false;
    this.open = false;
    this._text = "";
    this._html = "";
    this.parent = null;
    this.classList = {
      add: (c) => { this.className = `${this.className} ${c}`.trim(); },
      remove: () => {},
      contains: (c) => this.className.split(" ").includes(c),
    };
  }
  get options() { return this.children.filter((c) => c.tagName === "OPTION"); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this._text = String(v); this.children = []; }
  get innerHTML() { return this._html; }
  set innerHTML(v) { this._html = String(v); if (v === "") this.children = []; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  append(...cs) { for (const c of cs) if (c) this.appendChild(c); }
  remove() {
    const i = this.parent?.children.indexOf(this) ?? -1;
    if (i >= 0) this.parent.children.splice(i, 1);
  }
  addEventListener(ev, fn) { (this._on ??= {})[ev] = fn; }
  querySelector(sel) {
    // tag names only: the one lookup the pane makes inside a node it built is
    // <summary>. The retire button lives in an innerHTML string this stub does
    // not parse, and `?.` already makes that path a no-op.
    for (const c of this.children) {
      if (c.tagName === sel.toUpperCase()) return c;
      const found = c.querySelector(sel);
      if (found) return found;
    }
    return null;
  }
  querySelectorAll() { return []; }
  get value() { return this._value ?? ""; }
  set value(v) { this._value = v; }
}

globalThis.Option = class extends El {
  constructor(text, value) { super("option"); this._text = String(text); this.value = value; }
};

const byId = {};
const make = (id, tag) => (byId[id] = new El(tag));
function freshDom() {
  for (const k of Object.keys(byId)) delete byId[k];
  const sel = make("k-filter-type", "select");
  sel.appendChild(new Option("All types", ""));   // the literal index.html carries
  make("knowledge-list", "div");
  make("k-retired-list", "div");
  make("k-excluded-note", "div");
  make("k-filter-count", "span");
  make("k-retired-group", "details").appendChild(new El("summary"));
}

globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  createElement: (tag) => new El(tag),
  createElementNS: (_ns, tag) => new El(tag),
  getElementById: (id) => {
    if (!(id in byId)) throw new Error("the pane reached for an unknown id: " + id);
    return byId[id];
  },
  querySelectorAll: (sel) => {
    if (sel !== "#knowledge-list .rule-card")
      throw new Error("unexpected global selector: " + sel);
    return byId["knowledge-list"].children.filter((c) => c.classList.contains("rule-card"));
  },
  documentElement: new El("html"),
};

let versions = [];
globalThis.fetch = async (url) => {
  if (url === "/api/knowledge") return { ok: true, json: async () => versions };
  if (url === "/api/catalog") return { ok: true, json: async () => ({ products: {} }) };
  return { ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")) };
};

const { loadLocale, t } = await import("./js/i18n.js");
await loadLocale("en");
const { renderKnowledgeRules } = await import("./js/knowledge-rules.js");

const version = (object_id, status) => ({
  object_id, version: 1, status, type: "company_rule",
  title: object_id + " title", title_i18n: {},
  scope: { model: "Emblem" },
  actions: [{ kind: "set_param", param: "max_span_mm", value: 1800 }],
  attributed_to: "expert", derived_from: [],
});

async function draw(vs) {
  freshDom();
  versions = vs;
  await renderKnowledgeRules();
  const cards = (host) => byId[host].children.map((c) => ({
    id: (c.dataset.search || "").split(" ")[0], html: c.innerHTML,
  }));
  return {
    active: cards("knowledge-list"),
    retired: cards("k-retired-list"),
    note: byId["k-excluded-note"].innerHTML,
    note_hidden: byId["k-excluded-note"].hidden,
    summary: byId["k-retired-group"].querySelector("summary").textContent,
    group_hidden: byId["k-retired-group"].hidden,
    group_open: byId["k-retired-group"].open,
    count: byId["k-filter-count"].textContent,
  };
}

const out = {};
out.many = await draw([
  version("K-A", "active"), version("K-B", "active"),
  version("K-P1", "proposed"), version("K-P2", "proposed"), version("K-P3", "proposed"),
  version("K-R1", "retired"), version("K-R2", "retired"),
]);
out.one_each = await draw([
  version("K-A", "active"), version("K-P1", "proposed"), version("K-R1", "retired"),
]);
out.nothing_excluded = await draw([version("K-A", "active")]);
out.words = {
  excluded_one: t("knowledge.excluded_note_one"),
  excluded_n1: t("knowledge.excluded_note", { n: 1 }),
  excluded_n3: t("knowledge.excluded_note", { n: 3 }),
  retired_one: t("knowledge.retired_one"),
  retired_n1: t("knowledge.retired_n", { n: 1 }),
  retired_n2: t("knowledge.retired_n", { n: 2 }),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def drawn() -> dict:
    """`renderKnowledgeRules()` run three times over three version lists."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _bundles() -> tuple[dict, dict]:
    return (json.loads((STATIC / "i18n" / "en.json").read_text()),
            json.loads((STATIC / "i18n" / "he.json").read_text()))


def _action_kinds() -> list[str]:
    """`ACTION_KINDS` out of builder-ui.js — the closed list of kinds the rule
    builder offers, and therefore the list a phrasing must exist for."""
    src = (JS / "builder-ui.js").read_text()
    body = re.search(r"export const ACTION_KINDS = \[(.*?)\];", src, re.S)
    assert body, "ACTION_KINDS is no longer an exported const array in builder-ui.js"
    kinds = re.findall(r'"([a-z_]+)"', body.group(1))
    assert kinds, "ACTION_KINDS parsed empty — the scan below would pass vacuously"
    return kinds


# --------------------------------------------------------------- the phrasings


def test_every_action_kind_has_both_a_label_and_a_sentence():
    """The same rule the model editor's vocabularies follow: the builder's select
    reads `action.<kind>`, the rules list reads `action.sentence.<kind>`, and a
    kind carrying only one of the two renders either a raw key where a sentence
    belongs or a bare label pretending to be one."""
    en, he = _bundles()
    missing = []
    for kind in _action_kinds():
        for key in (f"action.{kind}", f"action.sentence.{kind}"):
            for lang, table in (("en", en), ("he", he)):
                if key not in table:
                    missing.append(f"{lang}:{key}")
    assert not missing, missing


# The two sentence keys that are not one-per-kind: an optional-SKU suffix, so
# that every kind keeps exactly one phrasing, and the degradation for a kind
# this bundle has never heard of. Neither is derivable from ACTION_KINDS, so
# deleting either passes the scan above and every parity check.
LITERAL_ACTION_SENTENCE_KEYS = [
    "action.sentence.with_sku",
    "action.sentence.unknown",
]


def test_the_literal_action_sentence_keys_exist():
    en, he = _bundles()
    missing = sorted(f"{lang}:{k}" for lang, table in (("en", en), ("he", he))
                     for k in LITERAL_ACTION_SENTENCE_KEYS if k not in table)
    assert not missing, missing


def test_both_bundles_take_the_same_sentence_placeholders():
    """A phrasing whose Hebrew drops `{weight}` still reads as a sentence — it
    just stops saying the number, in the language this app opens in."""
    en, he = _bundles()
    mismatched = {}
    for key, template in en.items():
        if not key.startswith("action.sentence."):
            continue
        ours = set(re.findall(r"\{(\w+)\}", str(template)))
        theirs = set(re.findall(r"\{(\w+)\}", str(he.get(key, ""))))
        if ours != theirs:
            mismatched[key] = {"en_only": sorted(ours - theirs),
                               "he_only": sorted(theirs - ours)}
    assert not mismatched, mismatched


def test_the_renderer_supplies_every_placeholder_its_templates_declare():
    """The other direction, which the two tests above cannot see: a template can
    declare a param the code never passes, and `sentence()` leaves `{sku}`
    sitting in the card rather than failing."""
    en, _ = _bundles()
    src = (JS / "builder-ui.js").read_text()
    body = src[src.index("export function actionSentence("):]
    body = body[:body.index("\nexport function scopeChips(")]

    unsupplied = {}
    for key, template in en.items():
        if not key.startswith("action.sentence."):
            continue
        declared = set(re.findall(r"\{(\w+)\}", str(template)))
        # the params the renderer hands this key, from the object literal that
        # follows the key in the source
        call = re.search(re.escape(f'"{key}"') + r",\s*\{(.*?)\}\)", body, re.S)
        assert call, f"{key} is in the bundles but no call site passes it"
        supplied = set(re.findall(r"(\w+):", call.group(1)))
        if declared - supplied:
            unsupplied[key] = sorted(declared - supplied)
    assert not unsupplied, unsupplied


# ------------------------------------------------------------- the single owner


def _sources() -> dict[str, str]:
    return {p.name: p.read_text() for p in [*JS.glob("*.js"), STATIC / "app.js"]}


def test_one_module_defines_the_rule_phrasing():
    """`actionSentence` and `scopeChips` answer "what does this rule say". A
    second DEFINITION is a second answer — but see the test below for the
    second answer this one cannot see."""
    sources = _sources()
    for fn in ("actionSentence", "scopeChips", "ACTION_KINDS"):
        pattern = re.compile(r"\b(?:function|const)\s+" + fn + r"\b")
        definers = [name for name, src in sources.items() if pattern.search(src)]
        assert definers == ["builder-ui.js"], (fn, definers)


def test_every_surface_that_shows_a_rule_uses_that_one_phrasing():
    """The test above justified itself by the review queue and then could not
    see it. A second answer does not have to be a second `function
    actionSentence` — tabs.js's was `esc(JSON.stringify(c.actions))`, no
    same-named definition anywhere, so the same rule read "Set max span to
    1800 mm" in the Knowledge tab and
    `{"kind":"set_param","param":"max_span_mm","value":1800}` in Review.

    Two properties, both about the SHAPE the second answer actually took:

      * nothing anywhere renders a `scope` or an `actions` as a JSON dump; and
      * every module that READS the two endpoints returning rule-shaped objects
        imports both renderers from builder-ui.js.

    The second is the one with teeth — a module that fetches candidates and
    does not import the phrasing has to be phrasing them itself.
    """
    dumps = {}
    for name, src in _sources().items():
        # whole-line comments stripped, the same way the JSON guard above does
        # it: builder-ui.js's own header NAMES the two dumps it replaced, and a
        # scan that read prose would forbid explaining the fix
        code = re.sub(r"^\s*//.*$", "", src, flags=re.M)
        hits = re.findall(r"JSON\.stringify\(\s*\w+\.(?:scope|actions)\b", code)
        if hits:
            dumps[name] = hits
    assert not dumps, (
        "a rule's scope or actions rendered as JSON — that is the second "
        "answer, whatever it is spelled", dumps)

    RULE_READS = ('apiGet("/api/knowledge")', 'apiGet("/api/candidates")')
    readers = {name for name, src in _sources().items()
               if any(call in src for call in RULE_READS)}
    assert readers == {"knowledge-rules.js", "tabs.js"}, (
        "a new surface reads the rule endpoints — it needs the same phrasing, "
        "and this list needs to say so", readers)
    for name in sorted(readers):
        src = (JS / name).read_text()
        imports = re.search(r"import \{(.*?)\} from \"\./builder-ui\.js\";",
                            src, re.S)
        assert imports, (name, "reads rules but imports nothing from builder-ui.js")
        named = set(re.findall(r"\w+", imports.group(1)))
        assert {"actionSentence", "scopeChips"} <= named, (
            name, "must describe a rule in the shared words", sorted(named))


def test_the_rules_list_no_longer_dumps_json_at_the_reader():
    """The complaint that started the redesign. `JSON.stringify` on a rule's
    scope or actions is the thing being removed, and it is one edit away from
    coming back the next time someone adds a field."""
    # comments stripped: this module's header NAMES the thing it stopped doing,
    # and a guard that reads prose would forbid explaining the fix
    src = re.sub(r"^\s*//.*$", "", (JS / "knowledge-rules.js").read_text(), flags=re.M)
    assert "JSON.stringify" not in src, (
        "the rules pane renders scope as chips and actions as sentences")
    assert "scopeChips(" in src and "actionSentence(" in src, (
        "...by calling the shared renderers, not by inlining its own")


# ------------------------------------------------------- excluded, and stated


def test_proposed_candidates_are_excluded_from_the_rules_pane(drawn):
    """Observed by DRAWING the pane, not by reading it. The regex this replaces
    (`assert 'status === "proposed"' in src`) survived the mutation that is the
    exact opposite of the pane's contract — a branch that counts a candidate and
    then pushes it into the active list anyway — because the token it looked for
    is still there in the mutant."""
    for case, expect_active in (("many", ["K-A", "K-B"]), ("one_each", ["K-A"])):
        d = drawn[case]
        assert [c["id"] for c in d["active"]] == [i.lower() for i in expect_active], case
        drawn_ids = " ".join(c["html"] for c in d["active"] + d["retired"])
        assert "K-P1" not in drawn_ids, (
            case, "a proposed candidate has a card in the rules pane")
        assert "K-P2" not in drawn_ids and "K-P3" not in drawn_ids, case


def test_the_exclusion_is_counted_and_shown(drawn):
    """A silent filter moves the confusion rather than fixing it: the reader
    cannot tell an excluded candidate from a rule that was never published.

    Read off the rendered note, so the NUMBER is checked and not merely the
    presence of a `proposed++` token: three excluded candidates must produce a
    note that says three, and none must produce no note at all."""
    words = drawn["words"]
    assert drawn["many"]["note"] == words["excluded_n3"]
    assert drawn["many"]["note_hidden"] is False
    assert "3" in drawn["many"]["note"]
    assert drawn["nothing_excluded"]["note_hidden"] is True, (
        "nothing was excluded, so nothing may claim anything was")
    assert drawn["nothing_excluded"]["note"] == ""
    en, he = _bundles()
    for table in (en, he):
        assert "{n}" in table["knowledge.excluded_note"], (
            "the note states a number, so its template must take one")


def test_retired_rules_go_to_their_own_group_and_start_closed(drawn):
    """Retired rules are history: kept reachable, not read first.

    The old assertion was `'id="k-retired-group"' in html and "<details" in
    html` — two independent facts about one file, and index.html carries
    another `<details>` (`#model-axes-box`), so replacing
    `<details id="k-retired-group">` with `<div id="k-retired-group">` passed.
    That swap silently breaks `group.open = ...`, which is a no-op on a div:
    every retired rule would then be listed open beside the rules in force.

    Two halves, and only one of them is observable here. Node can see the
    ROUTING — which host each version lands in, and that `open` is false and
    `hidden` true when there is nothing to show. Whether a closed `<details>`
    actually hides its children is a browser behaviour with no equivalent in a
    stub, so the element's TAG is asserted against index.html and the visible
    collapse is left to `_smoke_knowledge_panes` in tools/ui_smoke.py, which
    reads `#k-retired-group` out of a real page.
    """
    html = (STATIC / "index.html").read_text()
    assert re.search(r'<details\b[^>]*\bid="k-retired-group"', html), (
        "the retired group must BE a <details> — `group.open` is how the pane "
        "collapses it, and that property does nothing on any other element")

    many, one, none = drawn["many"], drawn["one_each"], drawn["nothing_excluded"]
    assert [c["id"] for c in many["retired"]] == ["k-r1", "k-r2"]
    assert "K-R1" not in " ".join(c["html"] for c in many["active"]), (
        "a retired rule must not sit among the rules in force")
    assert many["group_hidden"] is False and many["group_open"] is False, (
        "reachable, and closed until the reader asks")
    assert one["group_hidden"] is False
    assert none["group_hidden"] is True and none["retired"] == [], (
        "no retired rules, so no group")


# ------------------------------------------------------------ the strip itself


def test_every_subnav_button_has_a_pane_and_every_pane_a_button():
    """A button naming a missing pane is an inert tab; a pane with no button is
    a surface with no way to reach it."""
    html = (STATIC / "index.html").read_text()
    buttons = set(re.findall(r'data-kpane="(\w+)"', html))
    panes = set(re.findall(r'id="pane-k-(\w+)"', html))
    assert buttons == panes, {"button only": buttons - panes, "pane only": panes - buttons}
    assert buttons == {"rules", "author", "published"}, buttons


def test_one_path_moves_the_pane_active_class():
    """Same property `test_only_set_tab_moves_the_active_class` holds for the
    tab strip, one level down: two places deciding which pane shows is two
    answers, and the strip and the pane then disagree."""
    src = (JS / "tabs.js").read_text()
    assert re.search(r"^export function setKnowledgePane\(", src, re.M)
    body = src[src.index("export function setKnowledgePane("):]
    body = body[:body.index("\n}\n") + 1]
    assert body.count('classList.add("active")') == 2, (
        "setKnowledgePane activates exactly the button and its pane")
    assert re.search(r"if \(!btn \|\| !pane\) return;", body), (
        "an unknown pane name must be inert, like an unknown tab name")


def test_the_panes_do_not_reach_into_each_other():
    """The module-boundary rule from CLAUDE.md, checked on the one place this
    slice put three modules inside a single tab."""
    rules = (JS / "knowledge-rules.js").read_text()
    tabs = (JS / "tabs.js").read_text()
    # The Published pane's module is a CONCURRENT session's work and is not
    # committed on this branch. Reading it unconditionally made this file — the
    # one that asserts module boundaries — depend on a file outside the
    # repository, so the branch was red on a clean checkout and green only in a
    # working tree that happened to hold somebody else's untracked module.
    published_js = JS / "published-parts.js"
    published = published_js.read_text() if published_js.exists() else None

    assert "k-subnav" not in rules and "k-count" not in rules, (
        "the pane counts what it drew and emits it; the strip is not its DOM")
    assert 'emit("knowledge-counts"' in rules and 'on("knowledge-counts"' in tabs, (
        "...and the count travels by event, which is the only channel modules "
        "have to each other")
    assert "knowledge-list" not in tabs, (
        "the rules list belongs to knowledge-rules.js now")
    if published is not None:
        assert "knowledge-list" not in published and "k-filter" not in published


# --------------------------------------------------------------- the whole tab


def test_every_static_label_in_index_html_has_both_translations():
    """Not specific to this tab, and cheap: a `data-i18n` key with no entry
    renders as its own key. Every one of them passes today, so the guard costs
    nothing and catches the next one."""
    en, he = _bundles()
    html = (STATIC / "index.html").read_text()
    keys = set(re.findall(r'data-i18n(?:-title|-placeholder)?="([^"]+)"', html))
    assert keys, "the scan found no data-i18n attributes — has the idiom changed?"
    missing = sorted(f"{lang}:{k}" for lang, table in (("en", en), ("he", he))
                     for k in keys if k not in table)
    assert not missing, missing


def test_a_length_parameter_does_not_state_its_unit_twice():
    """`action.param.max_span_mm` is "max span ({u})" because the builder puts
    the unit in the form label, beside a bare number input. In a sentence the
    unit rides the value, so using the label as-is reads "Set max span (mm) to
    1200 mm" — which shipped, and is what the browser screenshot caught."""
    en, he = _bundles()
    src = (JS / "builder-ui.js").read_text()
    assert "function paramWord(" in src, (
        "the parameter word in a sentence is the label without its unit")
    body = src[src.index('case "set_param"'):]
    body = body[:body.index("break;")]
    assert "paramWord(" in body and "tu(" not in body, (
        "set_param must render the bare word, not the form label")
    # ...and the shape it strips is actually the shape both bundles use: a
    # trailing parenthetical. A bundle that moved the placeholder to the front
    # would make the strip a silent no-op.
    for lang, table in (("en", en), ("he", he)):
        for key, value in table.items():
            if key.startswith("action.param.") and "{u}" in str(value):
                assert str(value).rstrip().endswith("({u})"), (lang, key, value)


def test_counted_strings_render_their_singular_on_a_count_of_one(drawn):
    """"1 proposed candidates" — the plural the screenshot caught. This app
    already carries `_one` partners for every other counted string
    (`structure.height_one`, `strategy.warnings_count_one`).

    The old assertion was `"=== 1" in src`, which is FILE-GLOBAL: this module
    has two such comparisons, so deleting either singular branch left the other
    one satisfying the check and the test green. Here each string is read back
    off a render that has exactly one of the thing being counted, and compared
    against the two candidate phrasings — so a deleted branch shows up as the
    plural arriving where the singular belongs.
    """
    en, he = _bundles()
    for plural, singular in (("knowledge.excluded_note", "knowledge.excluded_note_one"),
                             ("knowledge.retired_n", "knowledge.retired_one")):
        for lang, table in (("en", en), ("he", he)):
            assert plural in table, f"{lang}:{plural}"
            assert singular in table, f"{lang}:{singular}"

    words, one, many = drawn["words"], drawn["one_each"], drawn["many"]
    # the fixture would be vacuous if the two phrasings coincided
    assert words["excluded_one"] != words["excluded_n1"]
    assert words["retired_one"] != words["retired_n1"]

    assert one["note"] == words["excluded_one"], "one candidate, one sentence"
    assert one["summary"] == words["retired_one"], "one retired rule, one summary"
    # ...and the plural is still chosen when there is more than one
    assert many["note"] == words["excluded_n3"]
    assert many["summary"] == words["retired_n2"]
