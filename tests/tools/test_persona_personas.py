"""The roster is evidence-based, not invented: five Hebrew trade roles plus one
English control that separates RTL bugs from real usability bugs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
LAB = TOOLS / "persona_lab"

REQUIRED = {"id", "role_he", "locale", "tech_literacy", "context", "goal",
            "vocabulary", "fallback_today", "quit_triggers", "success"}


def personas():
    from persona_lab import stack
    return stack.PERSONAS


@pytest.mark.parametrize("pid", personas())
def test_persona_file_exists_and_has_every_required_key(pid):
    data = json.loads((LAB / "personas" / f"{pid}.json").read_text(encoding="utf-8"))

    assert REQUIRED <= set(data)
    assert data["id"] == pid
    assert data["vocabulary"] and data["quit_triggers"]


@pytest.mark.parametrize("pid", personas())
def test_every_persona_has_a_scenario_brief(pid):
    brief = LAB / "scenarios" / f"{pid}.md"

    assert brief.exists()
    assert len(brief.read_text(encoding="utf-8")) > 200


def test_five_hebrew_one_english_control():
    locales = [json.loads((LAB / "personas" / f"{p}.json").read_text(encoding="utf-8"))["locale"]
               for p in personas()]

    assert locales.count("he") == 5
    assert locales.count("en") == 1


def test_tech_literacy_is_never_high():
    """The whole point is a non-technical reader. A 'high' persona would
    quietly restore the developer's-eye view we spent the driver removing."""
    for p in personas():
        data = json.loads((LAB / "personas" / f"{p}.json").read_text(encoding="utf-8"))
        assert data["tech_literacy"] in {"low", "medium"}
