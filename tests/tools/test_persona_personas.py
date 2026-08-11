"""The roster comes from the architecture, not from market research: five
Hebrew roles, each mapped to golden scenarios that exist, with the expert who
corrects proposals in context (foundation §9) at the centre.

The briefs are job tickets — site data with real numbers. They must not tell
the persona what to inspect: run 1 handed each persona "your central checks"
and then reported the prompt back as findings.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
LAB = TOOLS / "persona_lab"

REQUIRED = {"id", "role_he", "locale", "tech_literacy", "context", "goal",
            "vocabulary", "fallback_today", "quit_triggers", "success"}

ROSTER = ["expert", "knowledge-owner", "topology-author", "fulfillment", "approver"]

# a number followed by a trade unit — "6.00 מ'", "30 ס\"מ", "3 מ\"מ", "90 מעלות"
DIMENSION = re.compile(r"\d+(?:[.,]\d+)?\s*(?:מ'|מטר|ס\"מ|מ\"מ|מעלות)")

# leading language: anything that hands the persona a checklist of things to
# inspect. A real user arrives with a job, not with a list of the product's
# likely weaknesses.
CHECKLIST_MARKERS = ["בדוק אם", "בדוק ש", "תבדוק", "האם יש", "האם אפשר",
                     "ודא ש", "שים לב אם", "נסה למצוא"]


def personas():
    from persona_lab import stack
    return stack.PERSONAS


def _persona(pid: str) -> dict:
    return json.loads((LAB / "personas" / f"{pid}.json").read_text(encoding="utf-8"))


def _brief(pid: str) -> str:
    return (LAB / "scenarios" / f"{pid}.md").read_text(encoding="utf-8")


def test_roster_is_the_five_roles_from_the_architecture():
    assert personas() == ROSTER


def test_the_retired_run_one_roster_is_gone():
    """Its files must not linger — the sales rep graded the product against
    selling, which no golden scenario covers."""
    for stale in ("kablan-gderot", "estimator", "sales-rep",
                  "procurement", "measurer", "export-engineer-en"):
        assert not (LAB / "personas" / f"{stale}.json").exists()
        assert not (LAB / "scenarios" / f"{stale}.md").exists()


@pytest.mark.parametrize("pid", personas())
def test_persona_file_exists_and_has_every_required_key(pid):
    data = _persona(pid)

    assert REQUIRED <= set(data)
    assert data["id"] == pid
    assert data["vocabulary"] and data["quit_triggers"]


def test_every_persona_reads_hebrew():
    """The English control is retired: its question — is language the
    blocker? — was answered, and the budget belongs to the loop §9 describes."""
    assert [_persona(p)["locale"] for p in personas()] == ["he"] * 5


def test_tech_literacy_is_never_high():
    """The whole point is a non-technical reader. A 'high' persona would
    quietly restore the developer's-eye view we spent the driver removing."""
    for p in personas():
        assert _persona(p)["tech_literacy"] in {"low", "medium"}


@pytest.mark.parametrize("pid", personas())
def test_brief_is_a_job_ticket_not_a_paragraph(pid):
    brief = LAB / "scenarios" / f"{pid}.md"

    assert brief.exists()
    assert len(brief.read_text(encoding="utf-8")) > 400


@pytest.mark.parametrize("pid", personas())
def test_brief_carries_real_site_measurements(pid):
    """Prose to invent from produces invented sites. Every ticket arrives the
    way a measurement sheet does: with numbers."""
    found = DIMENSION.findall(_brief(pid))

    assert len(found) >= 2, f"{pid}: only {found} reads as a site dimension"


@pytest.mark.parametrize("pid", personas())
def test_brief_describes_two_sites(pid):
    """Run 1 measured a first-ever session. The second site is the
    measurement that matters; the first is training."""
    brief = _brief(pid)

    assert "ראשון" in brief or "ראשונה" in brief
    assert "שני" in brief or "שנייה" in brief


@pytest.mark.parametrize("pid", personas())
def test_brief_never_leads_the_witness(pid):
    """No checklist of things to inspect, and no naming of product surfaces —
    those come back as findings that are only the prompt reflected."""
    brief = _brief(pid)

    for marker in CHECKLIST_MARKERS:
        assert marker not in brief, f"{pid}: brief hands over a checklist ({marker!r})"


@pytest.mark.parametrize("pid", personas())
def test_brief_defines_done_and_never_rewards_quitting(pid):
    """An agent told that giving up is a deliverable will give up; run 1's
    unanimous 0/6 is not trustworthy. The instruction is to finish the job."""
    brief = _brief(pid)

    assert "מה נחשב גמור" in brief
    for marker in ("מתי אתה מוותר", "תגיד את זה בקול רם ותסיים"):
        assert marker not in brief
