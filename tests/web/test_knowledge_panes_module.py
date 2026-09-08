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
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"
JS = STATIC / "js"


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


def test_one_module_owns_the_rule_phrasing():
    """`actionSentence` and `scopeChips` answer "what does this rule say" for
    the rules list, and the review queue renders the same two fields on a
    candidate. A second definition is a second answer."""
    sources = {p.name: p.read_text() for p in [*JS.glob("*.js"), STATIC / "app.js"]}
    for fn in ("actionSentence", "scopeChips", "ACTION_KINDS"):
        pattern = re.compile(r"\b(?:function|const)\s+" + fn + r"\b")
        definers = [name for name, src in sources.items() if pattern.search(src)]
        assert definers == ["builder-ui.js"], (fn, definers)


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


def test_proposed_candidates_are_excluded_from_the_rules_pane():
    src = (JS / "knowledge-rules.js").read_text()
    assert 'status === "proposed"' in src, (
        "the pane must exclude review-pending candidates — they are the 90% "
        "that made this tab unreadable")


def test_the_exclusion_is_counted_and_shown():
    """A silent filter moves the confusion rather than fixing it: the reader
    cannot tell an excluded candidate from a rule that was never published."""
    src = (JS / "knowledge-rules.js").read_text()
    assert "proposed++" in src, "the excluded candidates must be counted"
    assert "k-excluded-note" in src, "...and the count must reach the screen"
    en, he = _bundles()
    for table in (en, he):
        assert "{n}" in table["knowledge.excluded_note"], (
            "the note states a number, so its template must take one")


def test_retired_rules_are_reachable_but_collapsed():
    src = (JS / "knowledge-rules.js").read_text()
    html = (STATIC / "index.html").read_text()
    assert 'status === "retired"' in src
    assert 'id="k-retired-group"' in html and "<details" in html, (
        "retired rules are history: kept reachable, not read first")


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
    published = (JS / "published-parts.js").read_text()

    assert "k-subnav" not in rules and "k-count" not in rules, (
        "the pane counts what it drew and emits it; the strip is not its DOM")
    assert 'emit("knowledge-counts"' in rules and 'on("knowledge-counts"' in tabs, (
        "...and the count travels by event, which is the only channel modules "
        "have to each other")
    assert "knowledge-list" not in tabs, (
        "the rules list belongs to knowledge-rules.js now")
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


def test_counted_strings_have_a_singular():
    """"1 proposed candidates" — the plural the screenshot caught. This app
    already carries `_one` partners for every other counted string
    (`structure.height_one`, `strategy.warnings_count_one`)."""
    en, he = _bundles()
    src = (JS / "knowledge-rules.js").read_text()
    for plural, singular in (("knowledge.excluded_note", "knowledge.excluded_note_one"),
                             ("knowledge.retired_n", "knowledge.retired_one")):
        for lang, table in (("en", en), ("he", he)):
            assert plural in table, f"{lang}:{plural}"
            assert singular in table, f"{lang}:{singular}"
        assert singular in src, f"{singular} exists but nothing renders it"
        assert "=== 1" in src, "the singular must be selected on a count of one"
