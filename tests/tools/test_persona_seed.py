"""A portfolio, not one project.

The knowledge owner asks "would this rule change break work I already did?"
and the approver asks "what moved since I accepted?". Both questions are
empty against a single project, which is why run 1 could not test either.
"""

from __future__ import annotations

import shutil
import sys
import urllib.request
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    from persona_lab import seed, stack

    if not shutil.which("google-chrome"):
        pytest.skip("google-chrome not available")
    run_dir = tmp_path_factory.mktemp("seed") / "expert"
    session = stack.start("expert", 0, run_dir)
    made = seed.seed(session["port"])
    yield session, made
    stack.stop(run_dir)


def test_every_portfolio_project_generates_and_is_quoted(seeded):
    session, made = seeded

    assert len(made) == len(seed_portfolio())
    for entry in made:
        assert entry["run_id"]
    # only the delivered jobs carry an accepted quote — that distinction is
    # the whole point for the knowledge owner
    assert [e["name"] for e in made if e.get("quote_id")] == [
        "גדר שדרות הדקל", "גדר מגרש 12 — גבעת האלה"]


def test_the_briefs_named_jobs_exist(seeded):
    """The briefs name jobs by street. If the portfolio does not contain them,
    a persona hunts for something absent and we record a fake dead end."""
    _session, made = seeded
    names = {e["name"] for e in made}

    assert "גדר רחוב הזית 3" in names
    assert "גדר שדרות הדקל" in names


def test_the_portfolio_is_visible_to_the_app(seeded):
    session, made = seeded

    listed = json.load(urllib.request.urlopen(
        f"http://localhost:{session['port']}/api/projects", timeout=10))
    names = {p["name"] for p in listed}

    for entry in made:
        assert entry["name"] in names


def test_accepted_quotes_give_a_baseline_to_diff_against(seeded):
    session, made = seeded

    delivered = next(e for e in made if e.get("quote_id"))
    quotes = json.load(urllib.request.urlopen(
        f"http://localhost:{session['port']}/api/projects/{delivered['project_id']}/quotes",
        timeout=10))

    assert any(q["status"] == "accepted" for q in quotes)


def seed_portfolio():
    from persona_lab import seed

    return seed.PORTFOLIO
