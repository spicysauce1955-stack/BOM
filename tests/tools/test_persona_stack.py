"""A persona stack is fully isolated: its own port, its own throwaway DB,
its own Chrome. Two personas must never be able to see each other's work."""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def test_ports_never_collide_across_the_roster():
    from persona_lab import stack

    pairs = [stack.ports_for(i) for i in range(len(stack.PERSONAS))]
    flat = [p for pair in pairs for p in pair]
    assert len(set(flat)) == len(flat)


def test_roster_is_the_six_from_the_spec():
    from persona_lab import stack

    assert stack.PERSONAS == [
        "kablan-gderot", "estimator", "sales-rep",
        "procurement", "measurer", "export-engineer-en",
    ]


@pytest.fixture
def booted(tmp_path):
    from persona_lab import stack

    if not shutil.which("google-chrome"):
        pytest.skip("google-chrome not available")
    run_dir = tmp_path / "kablan-gderot"
    run_dir.mkdir()
    session = stack.start("kablan-gderot", 0, run_dir)
    yield stack, run_dir, session
    stack.stop(run_dir)


def test_stack_serves_the_app_and_records_its_session(booted):
    _stack, run_dir, session = booted

    body = urllib.request.urlopen(
        f"http://localhost:{session['port']}/api/health", timeout=5
    ).read()
    # /api/health answers {"ok": true, "interpreter": ...} — the plan's draft
    # asserted a "status" key this app has never served
    assert json.loads(body)["ok"] is True

    on_disk = json.loads((run_dir / "session.json").read_text())
    assert on_disk["ws_url"].startswith("ws://")
    assert on_disk["persona"] == "kablan-gderot"
    assert Path(on_disk["db"]).exists()


def test_stop_releases_the_port(booted):
    stack, run_dir, session = booted

    stack.stop(run_dir)
    with pytest.raises(Exception):
        urllib.request.urlopen(
            f"http://localhost:{session['port']}/api/health", timeout=2
        )
