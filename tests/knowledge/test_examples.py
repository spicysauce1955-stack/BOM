"""Rule example/counterexample runner (knowledge-system.md).

Every example stored on a knowledge version is executed here: editing a rule so it
breaks its own examples fails CI. This is the rule-regression suite no off-the-shelf
engine provides (Research B).
"""

from __future__ import annotations

import pytest

from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.evaluator import applicable_firings
from fenceai.knowledge.model import KnowledgeBase


def _cases():
    kb = demo_knowledge()
    for v in kb.versions:
        for i, ex in enumerate(v.examples):
            yield pytest.param(v, ex, id=f"{v.ref}-ex{i}")


@pytest.mark.parametrize("version,example", _cases())
def test_rule_examples(version, example):
    kb = KnowledgeBase(versions=[version])
    fired = any(f.version.ref == version.ref for f in applicable_firings(kb, example.ctx))
    assert fired == example.expect_applicable, (
        f"{version.ref} example '{example.description}': expected "
        f"applicable={example.expect_applicable}, got {fired}"
    )


def test_demo_kb_has_examples_for_conditional_rules():
    """Rules with conditions must ship examples AND counterexamples."""
    for v in demo_knowledge().versions:
        if v.condition is not None:
            outcomes = {ex.expect_applicable for ex in v.examples}
            assert outcomes == {True, False}, (
                f"{v.ref} has a condition but lacks example+counterexample coverage"
            )
