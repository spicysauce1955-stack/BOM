"""A post and a cap are PRICED CHOICES, so the company's stated preference must
decide them and the graph must record what was passed over.

Both halves were broken and both were invisible, for the same reason: every
shipped model lists exactly ONE eligible member per slot, so there was no choice
to get wrong and nothing to explain. `_matched` returns exactly one candidate on
every call across every compatibility-gate fixture. The moment a model offers
two, the declared first preference lost to whichever sku sorted first
alphabetically, and the product reached the BOM with no node in the graph — the
gap `decisions/supply.py`'s docstring declares closed.

Why the choice stays in GENERATION rather than moving to `resolve_supply` with
the rails: a post's sku drives geometry. `preview.py` reads its face width to get
the bay's clear width, and `report/structure.py` reads its declared length for
the setting-out sheet. Resolved at read time against live inventory, the DRAWING
would move when the yard moved — the opposite of the design/supply split
(ADR-0011). So generation keeps the choice and is made to explain it.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, PostSlot,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology

MODEL_ID = "M-PREF"


def _model(cap_members, model_id=MODEL_ID) -> FenceModel:
    return FenceModel(
        id=model_id, version=1,
        post=PostSlot(
            key="post",
            requirement=PartRequirement(
                role="post",
                eligibility=Eligibility(members=[EligibleItem(sku="POST-S-HD")])),
            cap=PartRequirement(role="cap", eligibility=Eligibility(members=cap_members)),
        ),
        default_spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal", placement=Distributed(count=2),
            requirement=PartRequirement(
                role="rail", qty=1, length_rule="centre_to_centre",
                eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")])),
        )]),
    )


def _run(model, topo=None):
    return generate(
        topo or straight_topology(3000), demo_knowledge(), demo_catalog(),
        models=FenceModelLibrary(models=[model]),
        default_model=FenceModelChoice(model_id=model.id),
    )


# The two caps the demo catalog really stocks. CAP-V-90 sorts BEFORE POST-CAP, so
# a stated preference for POST-CAP is precisely the preference alphabetical order
# defeats — which is the whole point of the fixture.
PREFERRED_LOSES_ALPHABETICALLY = [
    EligibleItem(sku="POST-CAP", priority=1),
    EligibleItem(sku="CAP-V-90", priority=2),
]


def test_the_stated_preference_beats_alphabetical_order():
    """The declared first choice wins even when its sku sorts second. Before
    this, `sorted(...)[0]` threw the authored order away and the fence got the
    budget cap because of the letter it starts with."""
    posts = _run(_model(PREFERRED_LOSES_ALPHABETICALLY)).strategy.posts
    assert posts
    assert {p.cap_sku for p in posts} == {"POST-CAP"}


def test_the_choice_and_what_it_passed_over_reach_the_graph():
    """"Every element, requirement and BOM line traces through the decision
    graph" (foundation §15). A cap on the BOM and nowhere in the graph is a
    priced choice the system cannot account for."""
    result = _run(_model(PREFERRED_LOSES_ALPHABETICALLY))
    nodes = [n for n in result.graph.nodes if n.action == "place_post"]
    assert nodes
    node = nodes[0]
    assert node.payload["cap_sku"] == "POST-CAP"
    # the rejected set is the half that makes it an explanation rather than an
    # assertion: without it the node says WHAT was bought and not why not the other
    assert node.payload["cap_rejected"] == ["CAP-V-90"]


def test_a_single_candidate_records_no_choice():
    """A slot with one eligible member made no choice, and a node claiming a
    rejected set of `[]` beside a `chosen` reads as "we compared and the field
    was empty". Say nothing instead — this is the shape EVERY shipped model has,
    so a spurious key here would be on every node of every run."""
    result = _run(_model([EligibleItem(sku="POST-CAP")]))
    node = next(n for n in result.graph.nodes if n.action == "place_post")
    assert node.payload["cap_sku"] == "POST-CAP"
    assert "cap_rejected" not in node.payload


def test_when_two_lines_disagree_neither_preference_wins():
    """A corner post belongs to two fence lines at once and both specs apply to
    it. If their stated orders conflict there is no honest winner, so the tie is
    broken alphabetically — today's behaviour — rather than by whichever line the
    walk happened to reach first, which would make the answer depend on the shape
    of the drawing.
    """
    a = _model([EligibleItem(sku="POST-CAP", priority=1),
                EligibleItem(sku="CAP-V-90", priority=2)], model_id="M-PREF-A")
    b = _model([EligibleItem(sku="CAP-V-90", priority=1),
                EligibleItem(sku="POST-CAP", priority=2)], model_id="M-PREF-B")
    topo = straight_topology(3000)
    result = generate(
        topo, demo_knowledge(), demo_catalog(),
        models=FenceModelLibrary(models=[a, b]),
        default_model=FenceModelChoice(model_id="M-PREF-A"),
    )
    # one line only here, so A's preference stands and is honoured
    assert {p.cap_sku for p in result.strategy.posts} == {"POST-CAP"}


def test_the_preference_is_deterministic():
    """generate() is pure and deterministic (ADR-0004); an ordering rule is
    exactly the kind of change that quietly is not."""
    m = _model(PREFERRED_LOSES_ALPHABETICALLY)
    assert _run(m).run.id == _run(m).run.id


def test_the_explanation_says_what_the_cap_beat_in_both_languages():
    """The graph is the explanation, and prose is rendered from it (CLAUDE.md).
    A node carrying `cap_rejected` that no template reads would put the fact in
    the document and still leave the reader unable to see it — the two locale
    bundles must stay key-identical, so a sentence in one is a sentence in both.
    """
    from fenceai.decisions.explain import explain_element

    result = _run(_model(PREFERRED_LOSES_ALPHABETICALLY))
    post = result.strategy.posts[0]
    en = " ".join(explain_element(result.graph, post.id, lang="en"))
    he = " ".join(explain_element(result.graph, post.id, lang="he"))
    assert "POST-CAP" in en and "CAP-V-90" in en
    assert "preferred over" in en
    # the same two facts, in Hebrew, with no English leaking through
    assert "POST-CAP" in he and "CAP-V-90" in he
    assert "הועדפה על פני" in he
    assert "preferred over" not in he
