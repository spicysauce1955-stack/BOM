"""The advice module, as source. Mirrors `tests/web/test_base_top_module.py`.

The rules here are the frontend contract's, and each has a defect behind it:
esc() on interpolated text, `t()` on every visible string, and a suggestion
that is added BESIDE what it concerns rather than replacing it.
"""
from __future__ import annotations

from pathlib import Path

MODULE = Path("src/fenceai/web/static/js/agent-advice.js")


def test_the_module_exists_and_owns_one_container():
    src = MODULE.read_text()
    assert "#agent-advice" in src or "agent-advice" in src
    assert "#choices" not in src, "no module touches another module's DOM subtree"


def test_every_interpolated_value_is_escaped():
    """Claim text and point labels are agent- and data-authored."""
    src = MODULE.read_text()
    assert "esc(" in src
    assert "${claim.text}" not in src, "unescaped agent text in innerHTML"


def test_no_literal_user_facing_string():
    """Every visible string goes through t(). A literal here is a string that
    exists in one language."""
    src = MODULE.read_text()
    for literal in ("Suggestion", "Nothing to suggest", "Could not check"):
        assert f'"{literal}"' not in src and f"'{literal}'" not in src


def test_not_evaluated_and_no_proposals_render_differently():
    """"I did not look" is never "nothing to report" — audit B01 in miniature."""
    src = MODULE.read_text()
    assert "agent.not_evaluated" in src
    assert "agent.none" in src


def test_the_module_never_writes_project_state():
    """Slice 1 advises and does not act. A keep/reverse path arrives in slice 2
    with the record that makes a refusal mean something."""
    src = MODULE.read_text()
    for mutator in ("saveTopology", "pushSnapshot", "method: \"PUT\"", "method: 'PUT'"):
        assert mutator not in src
