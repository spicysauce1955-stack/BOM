"""Two sentences, because a default and a decision are different facts.

*"Three equal bays because nobody has chosen"* and *"because you chose them"*
must not render as one sentence, or the graph asserts a decision that may never
have happened. That is the whole reason a choice set is a fifth kind and not an
`override_applied` (spec §3).

The losing layout rides in the node PAYLOAD, not on a `defeated` edge.
`GraphBuilder.add(defeated=[...])` calls `_knowledge_node(ref)` on every string
and materialises an `input_fact` node for it — so a width list there would invent
a knowledge fact, against that method's own comment that *"nothing new is
invented in the graph"*.
"""

from __future__ import annotations

import re

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.decisions.explain import TEMPLATES, explain_node
from fenceai.knowledge.demo import demo_knowledge
from fenceai.project.model import Selection
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def _run(**kw):
    return generate(straight_topology(5000), demo_knowledge(), demo_catalog(), **kw)


@pytest.mark.parametrize("key", ["resolve_choice_set", "resolve_choice_set_default"])
def test_both_bundles_carry_both_sentences(key):
    assert key in TEMPLATES["en"]
    assert key in TEMPLATES["he"]


@pytest.mark.parametrize("key", ["resolve_choice_set", "resolve_choice_set_default"])
def test_the_two_languages_interpolate_the_same_params(key):
    """Key parity is guarded by `tests/web/test_locale_bundles.py`; PARAM parity
    is not, and nothing else can see it. A template interpolating a param its
    sibling does not supply renders a literal `{widths}` to a reader."""
    en = set(re.findall(r"\{(\w+)\}", TEMPLATES["en"][key]))
    he = set(re.findall(r"\{(\w+)\}", TEMPLATES["he"][key]))
    assert en == he, (key, en ^ he)


def test_a_default_never_renders_as_a_decision():
    """The chooser's name appears in one sentence and cannot appear in the
    other, because in the other there is nobody to name."""
    assert "{chosen_by}" in TEMPLATES["en"]["resolve_choice_set"]
    assert "{chosen_by}" not in TEMPLATES["en"]["resolve_choice_set_default"]


def test_an_unanswered_question_gets_a_node_saying_nobody_chose():
    """The node the first draft never emitted: it recorded a choice only when
    somebody had made one, so a plan built on the usual answer explained itself
    as though the question did not exist."""
    out = _run()
    node = next(n for n in out.graph.nodes
                if n.action == "resolve_choice_set_default")
    assert node.kind == "choice"
    assert node.payload["widths"] == [1667, 1667, 1666]
    assert node.payload["alternatives"] == [[1800, 1800, 1400]]
    assert "chosen_by" not in node.payload


def test_an_answered_question_names_the_chooser_and_what_was_displaced():
    out = _run(choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                                   widths=[1800, 1800, 1400], author="bob")])
    node = next(n for n in out.graph.nodes if n.action == "resolve_choice_set")
    assert node.payload["chosen_by"] == "bob"
    assert node.payload["widths"] == [1800, 1800, 1400]
    assert node.payload["displaced"] == [1667, 1667, 1666]


@pytest.mark.parametrize("lang", ["en", "he"])
def test_both_sentences_render_with_nothing_left_uninterpolated(lang):
    """The failure this catches reaches a reader as a literal brace. Rendered in
    BOTH languages, because a Hebrew template with an English param name is
    invisible to a key-set test and to an English-only render."""
    out = _run()
    graph = out.graph
    node = next(n for n in graph.nodes
                if n.action == "resolve_choice_set_default")
    text = explain_node(graph, node, lang=lang)
    assert "{" not in text and "}" not in text
    assert "1667" in text


@pytest.mark.parametrize("lang", ["en", "he"])
def test_the_chosen_sentence_renders_in_both_languages(lang):
    out = _run(choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                                   widths=[1800, 1800, 1400], author="bob")])
    node = next(n for n in out.graph.nodes if n.action == "resolve_choice_set")
    text = explain_node(out.graph, node, lang=lang)
    assert "{" not in text and "}" not in text
    assert "bob" in text


def test_no_width_list_is_ever_put_on_a_defeated_edge():
    """`defeated=` materialises a knowledge node per ref. A layout point has no
    knowledge version behind it, so its loser belongs in the payload — and this
    asserts the graph holds no invented fact."""
    out = _run()
    refs = [n.payload.get("knowledge_ref") for n in out.graph.nodes
            if n.kind == "input_fact"]
    assert not any(r and "1800" in str(r) for r in refs)
