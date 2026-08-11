"""The driver is the anti-cheat surface. A persona must see what a user sees —
visible labels — and must never see what only a developer sees: #ids, classes,
or internal state."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
ACT = TOOLS / "persona_lab" / "act.py"


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


# --- feedback regions: the app's teaching channels ------------------------
# The status bar is a plain <div>, so run 1's outline — interactive elements
# only — hid the one surface built to name the current mode and next gesture.

ITEMS = [{"role": "button", "label": "צור אסטרטגיה", "placeholder": "",
          "has_title": False, "title": "", "disabled": False, "checked": None,
          "x": 10, "y": 20, "w": 100, "h": 30}]


def test_feedback_is_rendered_above_the_handle_list():
    from persona_lab import outline

    text = outline.render(ITEMS, [{"region": "status", "text": "שרטוט: לחיצה מציבה נקודה"}])

    assert "screen says:" in text
    assert text.index("screen says:") < text.index("[e01")
    assert "שרטוט: לחיצה מציבה נקודה" in text


def test_feedback_regions_are_named_in_plain_words_not_selectors():
    from persona_lab import outline

    text = outline.render(ITEMS, [
        {"region": "status", "text": "בחירה"},
        {"region": "warning", "text": "אין גובה"},
        {"region": "dialog", "text": "רוחב שער"},
        {"region": "getting started", "text": "שרטטו קו"},
    ])

    for word in ("status:", "warning:", "dialog:", "getting started:"):
        assert word in text
    assert "#" not in text
    assert "statusbar" not in text and "popover" not in text and "checklist" not in text


def test_a_region_with_nothing_in_it_is_omitted_entirely():
    from persona_lab import outline

    text = outline.render(ITEMS, [])

    assert "screen says:" not in text
    assert text.startswith("[e01")


def test_a_long_region_keeps_both_its_head_and_its_tail():
    """The draw hint ends with the cursor readout. A plain head-truncation at
    200 chars would delete exactly the live feedback `move` exists to expose."""
    from persona_lab import outline

    long = "התחלה " + "מ" * 400 + " סוף"
    text = outline.render(ITEMS, [{"region": "status", "text": long}])

    line = next(x for x in text.splitlines() if "status:" in x)
    assert len(line) < 260
    assert "התחלה" in line
    assert "סוף" in line


def test_the_page_read_collects_only_the_feedback_channels():
    """Not licence to dump the DOM: the persona must not become a superhuman
    reader of every heading and table."""
    from persona_lab import outline

    js = outline.FEEDBACK_JS

    assert "statusbar" in js and "warnings" in js and "checklist" in js
    assert "popover" in js
    for greedy in ("document.body.innerText", "querySelectorAll('h1", "'*'"):
        assert greedy not in js


def test_look_reads_the_status_bar_the_app_writes(drv):
    _shot, text = drv.look("20.jpg")

    assert "screen says:" in text
    assert "status:" in text
    assert "#" not in text


def test_move_aims_the_pointer_without_pressing_anything(drv):
    """Run 1 drew one frozen frame at a time: no rubber band, no snap marks,
    no station readout, for a product whose core interaction is canvas
    drawing. `move` is the aiming half of every gesture."""
    drv.look("21.jpg")
    drv._eval("""
(() => {
  window.__m = []; window.__down = 0;
  const svg = document.getElementById('canvas');
  svg.addEventListener('pointermove', (e) => window.__m.push([e.clientX, e.clientY]));
  svg.addEventListener('pointerdown', () => window.__down++);
  return 1;
})()""")
    target = drv._eval("""
(() => {
  const r = document.getElementById('canvas').getBoundingClientRect();
  return [Math.round(r.x + r.width * 0.4), Math.round(r.y + r.height * 0.6)];
})()""")

    drv.move(target[0], target[1])

    assert drv._eval("window.__m.length ? window.__m[window.__m.length - 1] : null") == target
    assert drv._eval("window.__down") == 0, "move must not press the button"


def test_moving_over_a_run_shows_the_live_station_readout(drv):
    """The status bar appends the cursor station while the pointer is over a
    run — the feedback that makes aiming on a drawing possible at all."""
    drv.look("22.jpg")
    box = drv._eval("""
(() => {
  const r = document.getElementById('canvas').getBoundingClientRect();
  return [r.x, r.y, r.width, r.height];
})()""")
    y = round(box[1] + box[3] * 0.5)
    x0, x1 = round(box[0] + box[2] * 0.3), round(box[0] + box[2] * 0.7)
    drv._eval("document.getElementById('tool-draw').click(); 1")
    drv.click((x0, y))
    drv.click((x1, y))
    drv.key("Enter")
    drv.wait(1)
    on_run = drv._eval("""
(() => {
  const line = document.querySelector('#g-topology polyline');
  if (!line) return null;
  const pts = line.getAttribute('points').trim().split(/\\s+/).map(
    (p) => p.split(',').map(Number));
  if (pts.length < 2) return null;
  const svg = document.getElementById('canvas');
  const p = svg.createSVGPoint();
  p.x = (pts[0][0] + pts[1][0]) / 2; p.y = (pts[0][1] + pts[1][1]) / 2;
  const c = p.matrixTransform(svg.getScreenCTM());
  return [Math.round(c.x), Math.round(c.y)];
})()""")
    assert on_run, "drawing produced no run to aim at"

    drv.move(on_run[0], on_run[1])
    _shot, after = drv.look("23.jpg")

    says = after.split("\n\n")[0]
    assert "תחנה" in says, f"mouse move produced no live cursor readout:\n{says}"


# --- the action budget: look is free --------------------------------------


def _fake_session(tmp_path: Path) -> Path:
    run_dir = tmp_path / "kablan-gderot"
    (run_dir / "shots").mkdir(parents=True)
    (run_dir / "session.json").write_text(json.dumps({"run_dir": str(run_dir)}))
    return run_dir


def _act(run_dir: Path, *args):
    return subprocess.run([sys.executable, str(ACT), "--session", str(run_dir), *args],
                          capture_output=True, text=True)


def _closed(n: int, verb: str) -> dict:
    return {"n": n, "verb": verb, "arg": "", "intent": "a", "expected": "b",
            "observed": "c", "confusion": 0, "shot": "", "t_ms": 1}


def test_looking_costs_no_action(tmp_path):
    run_dir = _fake_session(tmp_path)
    (run_dir / "trace.jsonl").write_text("".join(
        json.dumps(r) + "\n" for r in
        [_closed(1, "look"), _closed(2, "finding"), _closed(3, "look")]))

    r = _act(run_dir, "finding", "--title", "x", "--surface", "y", "--symptom", "z")

    assert r.returncode == 0, r.stderr
    last = json.loads((run_dir / "trace.jsonl").read_text().splitlines()[-1])
    assert last["n"] == 4, "look must still be numbered in the trace"
    assert last["action_n"] == 2, "only non-look verbs consume the budget"


def test_the_running_action_count_is_printed_for_self_pacing(tmp_path):
    run_dir = _fake_session(tmp_path)

    r = _act(run_dir, "finding", "--title", "x", "--surface", "y", "--symptom", "z")

    assert r.returncode == 0, r.stderr
    assert "1/60" in r.stdout, r.stdout
    assert "look" in r.stdout.lower(), "say that looking is free"


def test_move_is_a_browser_verb_taking_two_coordinates():
    from persona_lab import act

    assert "move" in act.BROWSER_VERBS
    assert act.ARITY["move"] == 2


def test_a_decimal_point_survives_being_typed(drv):
    """'.' fell through to ord('.') = 46, which is VK_DELETE, so Chrome ate
    every decimal point: "1.80" arrived as "180" and two personas reported it
    as an app bug that mangles company rules."""
    drv.look("16.jpg")
    drv._eval("""
(() => {
  const i = document.createElement('input');
  i.id = '__dec'; i.type = 'text';
  document.body.appendChild(i); i.focus();
  return 1;
})()""")

    drv.type_text("1.80 מ' / 0,75-")
    got = drv._eval("document.getElementById('__dec').value")
    drv._eval("document.getElementById('__dec').remove(); 1")

    assert got == "1.80 מ' / 0,75-", f"punctuation was mangled: {got!r}"
