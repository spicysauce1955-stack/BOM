"""Which of four shapes a slot is — asked once, in Python, where a test can reach it.

The editor renders a different pane per shape. Inferring that in JavaScript by
checking three fields in order would put the rule where no test here could see it,
and the next reader of the model would have to derive it again.
"""

from fenceai.fencemodel.demo import demo_models
from fenceai.fencemodel.model import Eligibility, EligibleItem, PartRequirement
from fenceai.knowledge.ast import Cmp, FieldRef, Lit
from fenceai.parts.resolve import part_requirements


def test_a_slot_naming_a_part_says_so():
    assert PartRequirement(part_id="rail-38").eligibility_source == "part"


def test_authored_members_when_no_part():
    req = PartRequirement(
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]))
    assert req.eligibility_source == "authored_members"


def test_authored_predicate_when_no_part():
    req = PartRequirement(eligibility=Eligibility(
        predicate=Cmp(cmp="==", left=FieldRef(path="item.material"),
                      right=Lit(value="vinyl"))))
    assert req.eligibility_source == "authored_predicate"


def test_nothing_yet_is_unspecified():
    assert PartRequirement().eligibility_source == "unspecified"


def test_the_part_wins_over_anything_riding_along():
    """Resolution fills `predicate` on a part-named slot, so a resolved document
    would report `authored_predicate` if the part were not checked first — and the
    editor would offer to edit a rule the author never wrote."""
    # model_construct bypasses validation to simulate post-resolution state,
    # where both part_id and predicate exist (validator forbids this on authored docs)
    req = PartRequirement.model_construct(part_id="rail-38", eligibility=Eligibility(
        predicate=Cmp(cmp="==", left=FieldRef(path="item.material"),
                      right=Lit(value="vinyl"))))
    assert req.eligibility_source == "part"


def test_the_real_demo_models_cover_three_of_the_four_shapes():
    """Over the shipped models, not fixtures: a change to demo data that made every
    slot one shape would leave the fixtures passing and the editor untested."""
    found = {req.eligibility_source
             for model in demo_models().values()
             for _key, req in part_requirements(model)}
    assert found == {"part", "authored_members", "authored_predicate"}


def test_the_knowledge_sourced_slots_report_what_they_are_on_paper():
    """M-LEGACY's rail and screw have their members REPLACED per run from
    `demand_skus`. That is a generation-time behaviour with no trace on the authored
    document, so the property reports `authored_members` — what they are on paper —
    and the editor must not claim to know otherwise."""
    legacy = demo_models()["M-LEGACY"]
    sources = {key: req.eligibility_source for key, req in part_requirements(legacy)}
    assert sources["rail"] == "authored_members"
    assert sources["screw"] == "authored_members"
