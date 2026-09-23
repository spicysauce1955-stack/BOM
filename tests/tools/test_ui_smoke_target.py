"""Where the browser suite points, and who owns the server it talks to.

Read at CALL time, not at import — `tools/persona_lab/stack.py:ports_for`
records what the other way costs: a module-level constant froze at its default
before any fixture ran, and the override silently did nothing while looking
like it worked.
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def test_it_starts_its_own_server_by_default(monkeypatch):
    import ui_smoke

    monkeypatch.delenv("FENCEAI_SMOKE_BASE_URL", raising=False)
    assert ui_smoke.target_base_url() == f"http://localhost:{ui_smoke.PORT}"
    assert ui_smoke.attached() is False


def test_it_attaches_to_a_base_url_when_given_one(monkeypatch):
    import ui_smoke

    monkeypatch.setenv("FENCEAI_SMOKE_BASE_URL", "http://localhost:8080")
    assert ui_smoke.target_base_url() == "http://localhost:8080"
    assert ui_smoke.attached() is True


def test_a_trailing_slash_does_not_become_a_double_one(monkeypatch):
    """Every call site appends a path, so `…8080//api/health` is one typo away
    and a 404 from it would read as a broken server."""
    import ui_smoke

    monkeypatch.setenv("FENCEAI_SMOKE_BASE_URL", "http://localhost:8080/")
    assert ui_smoke.target_base_url() == "http://localhost:8080"


def test_a_blank_value_is_not_an_attachment(monkeypatch):
    """`FENCEAI_SMOKE_BASE_URL=` exported empty must behave as unset, or a
    stale export in a shell profile silently disables the server launch and the
    run fails with nothing listening."""
    import ui_smoke

    monkeypatch.setenv("FENCEAI_SMOKE_BASE_URL", "   ")
    assert ui_smoke.attached() is False
    assert ui_smoke.target_base_url() == f"http://localhost:{ui_smoke.PORT}"
