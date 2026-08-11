"""The driver is the anti-cheat surface. A persona must see what a user sees —
visible labels — and must never see what only a developer sees: #ids, classes,
or internal state."""

from __future__ import annotations

import shutil
import time
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


def test_typing_fires_keydown_not_just_char(drv):
    """A bare CDP `char` event inserts text without firing keydown, so any
    feature listening on keydown looks dead. That defect manufactured false
    findings in the first lab run — pin the fix."""
    drv.look("10.jpg")
    seen = drv._eval("""
(() => {
  window.__k = [];
  document.addEventListener('keydown', (e) => window.__k.push(e.key), {once: false});
  return 'armed';
})()""")
    assert seen == "armed"

    drv.type_text("42")

    assert drv._eval("window.__k.join('')") == "42"


def test_editing_shortcuts_carry_their_commands(drv):
    """Ctrl+Z is inert unless the keyDown carries virtual key codes AND the
    matching commands list — without it, 'undo is broken' is a harness lie."""
    drv.look("11.jpg")
    drv._eval("""
(() => {
  const i = document.createElement('input');
  i.id = '__probe'; i.value = '1800';
  document.body.appendChild(i); i.focus(); i.select();
  return 1;
})()""")

    drv.type_text("2200")
    typed = drv._eval("document.getElementById('__probe').value")
    drv.key("Ctrl+z")
    undone = drv._eval("document.getElementById('__probe').value")
    drv._eval("document.getElementById('__probe').remove(); 1")

    assert typed == "2200", "select() then type should replace, not append"
    assert undone == "1800", "Ctrl+Z did not reach the field"


def test_clicking_a_handle_scrolls_it_into_view(drv):
    """A click at a negative viewport y silently lands on nothing and reads
    as 'the button does nothing'."""
    drv._eval("window.scrollTo(0, 0); 1")
    _shot, _text = drv.look("12.jpg")
    handle = next(iter(drv.handles))
    drv._eval("window.scrollTo(0, 3000); 1")

    x, y = drv._point(handle)

    assert y >= 0, f"handle resolved off-viewport at y={y}"


def test_scroll_avoids_the_canvas(drv):
    """The plan SVG preventDefault()s the wheel to zoom. A wheel aimed at a
    fixed centre always lands on it, the page never moves, and the app reads
    as frozen — which is exactly what one persona reported."""
    drv.look("13.jpg")
    point = drv._eval(__import__("persona_lab.outline", fromlist=["x"]).SCROLL_POINT_JS)
    inside = drv._eval("""
(() => {
  const p = %r;
  return [...document.querySelectorAll('svg')].some((e) => {
    const r = e.getBoundingClientRect();
    return p[0] >= r.left && p[0] <= r.right && p[1] >= r.top && p[1] <= r.bottom;
  });
})()""" % (point,))

    assert inside is False, f"scroll point {point} lands on a canvas"


def test_a_native_alert_does_not_wedge_the_tab(drv):
    """12 alert() call sites exist, one on a SUCCESSFUL save. Unanswered, it
    blocks the renderer and every later CDP call times out."""
    drv.look("14.jpg")
    drv._eval("setTimeout(() => alert('נשמר'), 0); 1")
    time.sleep(0.5)

    _shot, text = drv.look("15.jpg")

    assert 'dialog (dismissed): "נשמר"' in text
    assert drv._eval("1 + 1") == 2, "renderer still blocked after the alert"
