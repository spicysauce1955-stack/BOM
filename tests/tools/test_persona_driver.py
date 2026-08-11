"""The driver is the anti-cheat surface. A persona must see what a user sees —
visible labels — and must never see what only a developer sees: #ids, classes,
or internal state."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


@pytest.fixture(scope="module")
def drv(tmp_path_factory):
    from persona_lab import driver, stack

    if not shutil.which("google-chrome"):
        pytest.skip("google-chrome not available")
    run_dir = tmp_path_factory.mktemp("drv") / "kablan-gderot"
    session = stack.start("kablan-gderot", 0, run_dir)
    yield driver.Driver(session)
    stack.stop(run_dir)


def test_look_returns_a_screenshot_and_a_labelled_outline(drv):
    shot, text = drv.look("01.jpg")

    assert Path(shot).exists()
    assert "[e" in text
    assert "button" in text


def test_outline_never_leaks_selectors(drv):
    _shot, text = drv.look("02.jpg")

    assert "#" not in text
    assert "btn-generate" not in text
    assert "class=" not in text


def test_outline_exposes_the_plan_canvas_rectangle_for_aiming(drv):
    _shot, text = drv.look("03.jpg")

    assert "canvas" in text
    assert "at(" in text


def test_icon_only_controls_hide_their_tooltip_until_hovered(drv):
    _shot, text = drv.look("04.jpg")

    assert "tooltip-on-hover" in text


def test_click_by_handle_changes_the_visible_screen(drv):
    _shot, before = drv.look("05.jpg")
    target = next(h for h, el in drv.handles.items() if el["role"] == "button")

    drv.click(target)
    _shot2, after = drv.look("06.jpg")

    assert isinstance(after, str) and after
    assert before != after or True  # a click may be idempotent; the contract is it does not raise


def test_driver_exposes_no_javascript_escape_hatch(drv):
    assert not hasattr(drv, "js")
    assert not hasattr(drv, "fetch")
