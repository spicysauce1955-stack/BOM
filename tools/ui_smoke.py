"""UI smoke test: drives the real app in headless Chrome via CDP (spec §7).

Run manually at milestones (not part of pytest — keeps CI browser-free):

    uv run --with websocket-client python tools/ui_smoke.py

Prereqs: google-chrome on PATH. Boots its own server on :8791 with a throwaway DB,
drives the drawing/editing/undo/locale flows, saves screenshots to
tools/smoke-out/, and exits non-zero on any failed check.
"""

from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from cdp import Cdp

# Overridable so two worktrees can run the suite at once. Both preflight checks
# below abort on a busy port, and without this the second run's only options are
# to wait or to kill somebody else's browser.
PORT = int(os.environ.get("FENCEAI_SMOKE_PORT", "8791"))
CDP_PORT = int(os.environ.get("FENCEAI_SMOKE_CDP_PORT", "9333"))
OUT = os.path.join(os.path.dirname(__file__), "smoke-out")
CHECKS: list[tuple[str, bool]] = []


def wait_for(c, expr: str, timeout: float = 8.0, step: float = 0.4):
    """Poll a JS expression until it is truthy, then return it.

    The suite otherwise waits on the clock, which is fine for a re-render and
    wrong after `location.reload()`: the bootstrap re-fetches health, the project
    list and the project itself, and how long that takes is not a constant. A
    fixed sleep there does not fail when the app is broken — it fails when the
    machine is busy, which is worse than either outcome."""
    deadline = time.time() + timeout
    value = None
    while time.time() < deadline:
        value = c.js(expr)
        if value:
            return value
        time.sleep(step)
    return value


def check(name: str, ok: bool, detail: object = None) -> None:
    """`detail` is printed only on a FAIL, and only when the caller has something
    to say. A check whose JS can fail in several distinct ways otherwise reports
    one word, and the reader has to re-run the suite to learn which way it went."""
    CHECKS.append((name, bool(ok)))
    line = ("PASS " if ok else "FAIL ") + name
    print(line if ok or detail is None else f"{line}  [{detail}]")


def hover(c, x: float, y: float) -> None:
    """Aim without clicking — the status readout follows the pointer, not clicks."""
    c.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    time.sleep(0.25)


def type_text(c, text: str) -> None:
    """Type into the focused field. Cdp.key() carries no `text`, so Chrome fires
    the keydown but inserts nothing — useless for checking what a field holds."""
    for ch in text:
        vk = ord(ch.upper())
        code = f"Digit{ch}" if ch.isdigit() else f"Key{ch.upper()}"
        c.cmd("Input.dispatchKeyEvent", type="keyDown", key=ch, code=code, text=ch,
              windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        c.cmd("Input.dispatchKeyEvent", type="keyUp", key=ch, code=code,
              windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        time.sleep(0.05)
    time.sleep(0.2)


def _smoke_choices_panel(c) -> None:
    """The plan's open questions, answered from the plan itself (spec §2).

    Three things only a browser can say. That the panel offers BOTH answers —
    the layout the engine built and the one it displaced, because a default is
    never eliminated (§5.2) and a panel missing its own answer is the failure
    that rule exists to retire. That answering writes a selection and **fires no
    generation** (§16): the run on screen is still the run that was built, the
    answer shows as PENDING, and nothing here reaches `generate`. And that a
    difference nobody can count is STATED ("no material change") rather than
    left as a blank cell, which reads as a panel that failed to load.

    On its own project, deliberately. These assertions are about one question on
    a 5 m run; on whatever project the previous case last drew they would be
    about whatever it drew.
    """
    pid = c.js("""
fetch('/api/projects', {method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({name: 'choices'})})
  .then((r) => r.json())
  .then((p) => fetch(`/api/projects/${p.id}/topology`, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({revision: 0,
      nodes: [{id: 'n1', x_mm: 0, y_mm: 0}, {id: 'n2', x_mm: 5000, y_mm: 0}],
      runs: [{id: 'run1', start_node_id: 'n1', end_node_id: 'n2'}]}),
  }).then(() => p.id))""")
    check("a 5 m run to ask the question about", bool(pid), pid)
    if not pid:
        return
    # The case before this one deep-links the evidence viewer, which leaves an
    # overlay over the drawing and a hash in the URL. Clear both: a click on
    # `#btn-generate` that lands on somebody else's overlay reports this panel
    # broken and is not.
    # ...and pin the display unit, because an earlier case may have left it in
    # centimetres and the toggle assertion below is about a KNOWN starting point.
    c.js("localStorage.setItem('fenceai.units', 'mm');"
         " location.hash = ''; location.reload(); 'ok'")
    wait_for(c, "!!document.getElementById('project-select').value", timeout=20)
    c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
    c.js("""
{
  const sel = document.getElementById('project-select');
  const o = document.createElement('option');
  o.value = %r; o.textContent = 'choices';
  sel.appendChild(o); sel.value = %r;
  sel.dispatchEvent(new Event('change'));
}
'ok'""" % (pid, pid))
    wait_for(c, "!!document.getElementById('choices')")
    c.click(*c.element_center("#btn-generate"))
    # The two halves, separately: a question the backend never asked and a
    # question the panel never drew fail the same check otherwise.
    asked = wait_for(c, """
fetch(`/api/projects/%s/runs`).then((r) => r.json()).then((rs) => rs.length
  ? fetch(`/api/runs/${rs[rs.length - 1].id}`).then((x) => x.json())
      .then((run) => (run.choice_sets || []).length)
  : 0)""" % pid, timeout=20)
    check("the ⚙ button generated a run, and it carries an open question",
          asked == 1, asked)
    wait_for(c, "document.querySelectorAll('#choices .choice-point').length")

    read = """
(() => {
  const host = document.getElementById('choices');
  const pts = [...host.querySelectorAll('.choice-point')];
  return {
    sets: host.querySelectorAll('.choice-set').length,
    answers: pts.map((p) => p.querySelector('.choice-answer').textContent.trim()),
    deltas: pts.map((p) => p.querySelector('.choice-delta').textContent.trim()),
    built: pts.filter((p) => p.querySelector('.tag.active')).length,
    pending: host.querySelectorAll('.choice-pending').length,
    withdraw: host.querySelectorAll('.choice-withdraw').length,
  };
})()"""
    shown = c.js(read)
    check("the plan carries its open question, with the answer it was built "
          "with AND the one it was not",
          shown["sets"] == 1 and len(shown["answers"]) == 2
          and shown["built"] == 1
          and any("1667" in a for a in shown["answers"])
          and any("1800" in a for a in shown["answers"]), shown)
    check("a difference nobody can count is stated, not left blank",
          all(d for d in shown["deltas"]), shown["deltas"])
    check("nothing is pending before anybody answers", shown["pending"] == 0)

    # the widths are LENGTHS: a centimetre preference has to reach them, while
    # storage and the payload stay integer millimetres (asserted below)
    c.click(*c.element_center("#btn-units"))
    time.sleep(0.6)
    cm = c.js(read)
    check("the widths read in the reader's display unit",
          any("166.7" in a for a in cm["answers"]), cm["answers"])
    c.click(*c.element_center("#btn-units"))
    time.sleep(0.6)

    runs_before = c.js(
        "fetch(`/api/projects/%s/runs`).then((r) => r.json()).then((rs) => rs.length)" % pid)
    posts_before = c.js("document.querySelectorAll('#g-overlay circle').length")
    clicked = c.js("""
(() => {
  const row = [...document.querySelectorAll('#choices .choice-point')]
    .find((p) => p.textContent.includes('1800'));
  if (!row) return false;
  row.click();
  return true;
})()""")
    check("the answer the plan was NOT built with can be given", bool(clicked))
    if not clicked:
        return
    time.sleep(1.5)
    answered = c.js(read)
    runs_after = c.js(
        "fetch(`/api/projects/%s/runs`).then((r) => r.json()).then((rs) => rs.length)" % pid)
    posts_after = c.js("document.querySelectorAll('#g-overlay circle').length")
    stored = c.js(
        "fetch(`/api/projects/%s`).then((r) => r.json()).then((p) => p.choices)" % pid)

    check("answering a question does not fire a generation",
          runs_after == runs_before and posts_after == posts_before,
          {"runs": [runs_before, runs_after], "posts": [posts_before, posts_after]})
    check("the answer is visible as pending rather than silently stored",
          answered["pending"] == 1 and answered["withdraw"] == 1, answered)
    check("the selection records the widths it chose, in millimetres, against "
          "the gap it answers",
          stored == [{"choice_set": "bay_layout", "scope": "gap:run1:0",
                      "widths": [1800, 1800, 1400], "bindings": {},
                      "asked": True, "author": "user", "created_at": ""}], stored)
    c.shot("22-choices-panel.png")

    c.js("document.querySelector('#choices .choice-withdraw')?.click(); 'ok'")
    time.sleep(1.5)
    withdrawn = c.js(read)
    left = c.js(
        "fetch(`/api/projects/%s`).then((r) => r.json()).then((p) => p.choices)" % pid)
    check("withdrawing an answer takes the pending marker with it",
          withdrawn["pending"] == 0 and withdrawn["withdraw"] == 0 and left == [],
          {"panel": withdrawn, "stored": left})
def _smoke_post_inspector(c) -> None:
    """The post inspector: four directives that never had a control, and the
    refusal that keeps the fourth from writing an override the generator drops.

    Every check here asserts a CONSEQUENCE, not a rendering. Forcing a sku has
    to reach the BOM line for that post; forcing masonry has to remove that
    post's footing line; and refusing to suppress a corner has to leave the
    project with no override at all — a panel that drew three selects and wrote
    nothing would screenshot identically to one that works.
    """
    project_js = "document.getElementById('project-select').value"

    def overrides():
        return c.js(f"""
(async () => {{
  const p = await (await fetch(`/api/projects/${{{project_js}}}`)).json();
  return (p.overrides || []).map(o => o.directive);
}})()""")

    def last_run():
        return c.js(f"""
(async () => {{
  const runs = await (await fetch(`/api/projects/${{{project_js}}}/runs`)).json();
  const id = runs[runs.length - 1].id;
  const result = await (await fetch(`/api/runs/${{id}}`)).json();
  const bom = await (await fetch(`/api/runs/${{id}}/bom`)).json();
  return {{
    id, n_runs: runs.length,
    orphaned: result.orphaned_overrides || [],
    posts: result.strategy.posts.map(p => ({{
      id: p.id, kind: p.kind, sku: p.sku, mounting: p.mounting,
      run_ref: p.run_ref, pinned: p.pinned, station_mm: p.station_mm,
    }})),
    // the RESOLVED demand lines: `role` says what a line is for and `pegs`
    // says which element caused it, so "this post's product" and "this post's
    // footing" are both answerable without parsing a sku
    lines: (bom.requirements || []).map(l => ({{
      role: l.role, sku: l.sku, pegs: l.pegs,
    }})),
  }};
}})()""")

    def post_title(post_id):
        """What the plan canvas currently says this post IS — drawn from the last
        generation, which is exactly the thing a directive must NOT change."""
        return c.js("""
(() => {
  const id = %s;
  const title = [...document.querySelectorAll('#g-overlay title')]
    .find(n => n.textContent.split('\\n')[0] === id);
  return title ? title.textContent : '';
})()""" % json.dumps(post_id))

    def select_post(post_id):
        """A real click on the post's circle, at the coordinates it occupies —
        the same gesture a person makes, through whatever handler owns it.

        The empty-canvas click first is not ceremony. `#g-handles` is painted
        OVER `#g-overlay`, so while a section is selected its VERTEX HANDLES sit
        exactly on top of the posts at those stations — and a click there
        reaches the handle, not the post. (The midpoint ghost used to do this
        too, on every run that divides evenly into its bays; it now renders 12 px
        off its segment, so that half is no longer a hazard. A vertex handle
        still is: it marks a corner, which is where a post also always stands,
        and there the two really are the same place.) Deselecting first is what
        a person does anyway, and it makes the target unambiguous.

        The wait is keyed on `data-post`, never on the panel merely existing: the
        previous post's panel is still on screen when the click misses, so
        "a panel is open" would report success for a click that did nothing.
        """
        c.click(*c.canvas_px(1000, -3000))
        time.sleep(0.4)
        box = c.js("""
(() => {
  const id = %s;
  const title = [...document.querySelectorAll('#g-overlay title')]
    .find(n => n.textContent.split('\\n')[0] === id);
  if (!title) return null;
  const r = title.parentNode.getBoundingClientRect();
  return [r.x + r.width / 2, r.y + r.height / 2];
})()""" % json.dumps(post_id))
        if not box:
            return False
        c.click(box[0], box[1])
        return bool(wait_for(
            c,
            "document.getElementById('post-inspector')?.dataset.post === %s"
            % json.dumps(post_id),
            timeout=6))

    # --- a project of this case's own -----------------------------------------
    # This case runs last, after a reload that discarded the tab and project
    # state everything above it built. It rebuilds what it needs rather than
    # inheriting it, so the order of the cases in _CHOICE_CASES cannot matter.
    c.cmd("Page.navigate", url=f"http://localhost:{PORT}/")
    time.sleep(3)
    c.js("window.confirm = () => true; window.alert = () => {}; undefined")
    wait_for(c, f"!!{project_js}", timeout=10)
    if c.js("document.documentElement.lang") != "en":
        c.click(*c.element_center("#btn-locale"))
        time.sleep(1)
    c.js("document.getElementById('new-project-name').value = 'post-inspector'; 'ok'")
    c.click(*c.element_center("#btn-new-project"))
    time.sleep(1.5)
    # An L, drawn as two runs meeting at a node the fence TURNS at: the corner
    # post the suppress control has to refuse, plus a straight 6 m run with
    # interior line posts for the three controls that apply.
    c.click(*c.element_center("#tool-draw"))
    c.click(*c.canvas_px(0, 0))
    c.click(*c.canvas_px(6000, 0))
    c.click(*c.canvas_px(6000, 4000))
    c.key("Enter")
    time.sleep(1.5)
    c.click(*c.element_center("#tool-select"))
    c.click(*c.element_center("#btn-generate"))
    time.sleep(2.5)

    before = last_run()
    lines = [p for p in before["posts"]
             if p["kind"] == "line" and not p["run_ref"].startswith("node:")
             and not p["pinned"]]
    corners = [p for p in before["posts"] if p["kind"] == "corner"]
    check("the fixture has line posts to edit and a corner to refuse",
          len(lines) >= 2 and len(corners) >= 1,
          {"kinds": sorted({p["kind"] for p in before["posts"]}),
           "n_posts": len(before["posts"])})
    if len(lines) < 2 or not corners:
        return
    sku_post, mount_post, corner_post = lines[0], lines[1], corners[0]

    # --- force_post_sku --------------------------------------------------------
    opened = select_post(sku_post["id"])
    panel = c.js("""
({ sku: !!document.getElementById('post-force-sku'),
   mounting: !!document.getElementById('post-force-mounting'),
   vertical: !!document.getElementById('post-force-vertical'),
   suppress: !!document.getElementById('post-suppress') })""")
    check("selecting a post opens a panel with a control for each directive",
          opened and all(panel.values()), panel)
    forced_sku = c.js("""
(() => {
  const sel = document.getElementById('post-force-sku');
  if (!sel) return null;
  const cur = %s;
  const others = [...sel.options].map(o => o.value).filter(v => v && v !== cur);
  if (!others.length) return null;
  const pick = others.includes('POST-S-HD') ? 'POST-S-HD' : others[0];
  sel.value = pick;
  sel.dispatchEvent(new Event('change'));
  return pick;
})()""" % json.dumps(sku_post["sku"]))
    time.sleep(2)
    stored = overrides()
    pending = c.js("!!document.getElementById('post-pending')")
    drawn = post_title(sku_post["id"])
    check("forcing a product stores the directive and says so",
          forced_sku is not None
          and any(d["kind"] == "force_post_sku" and d["sku"] == forced_sku
                  and abs(d["station_mm"] - sku_post["station_mm"]) <= 25
                  for d in stored)
          and pending,
          {"forced": forced_sku, "stored": stored, "pending": pending})
    # ...and nothing regenerated behind it: the plan still draws the post the
    # last run resolved, which is the whole reason the pending line exists
    check("the forced product does not regenerate the run behind the user",
          forced_sku is not None and sku_post["id"] in drawn
          and forced_sku not in drawn
          and last_run()["n_runs"] == before["n_runs"],
          {"drawn": drawn, "forced": forced_sku})

    # --- force_mounting on a DIFFERENT post ------------------------------------
    # Different because `_make_post` puts a forced sku ABOVE a masonry mount: on
    # one post the sku check would mask the mounting check entirely.
    footing_before = [l for l in before["lines"]
                      if l["role"] == "concrete" and mount_post["id"] in l["pegs"]]
    opened_mount = select_post(mount_post["id"])
    if opened_mount:
        c.js("""
{ const sel = document.getElementById('post-force-mounting');
  sel.value = 'masonry';
  sel.dispatchEvent(new Event('change')); }
'ok'""")
        time.sleep(2)

    # --- suppress_post: refused on a corner ------------------------------------
    opened_corner = select_post(corner_post["id"])
    refusal = c.js("""
({ present: !!document.getElementById('post-suppress'),
   disabled: !!document.getElementById('post-suppress')?.disabled,
   why: document.getElementById('post-suppress-why')?.textContent || '' })""")
    c.js("document.getElementById('post-suppress')?.click(); 'ok'")
    time.sleep(1.2)
    after_attempt = overrides()
    check("a corner post refuses suppression at the control, with the reason",
          opened_corner and refusal["present"] and refusal["disabled"]
          and "corner" in refusal["why"].lower()
          and not any(d["kind"] == "suppress_post" for d in after_attempt),
          {"refusal": refusal, "stored": after_attempt})
    c.shot("22-post-inspector.png")

    # --- and now the consequences ----------------------------------------------
    c.click(*c.element_center("#btn-generate"))
    time.sleep(2.5)
    after = last_run()
    post_line = next((l for l in after["lines"]
                      if l["role"] == "post" and sku_post["id"] in l["pegs"]), None)
    check("the forced product is the product the BOM buys for that post",
          post_line is not None and post_line["sku"] == forced_sku,
          {"line": post_line, "forced": forced_sku})
    footing_after = [l for l in after["lines"]
                     if l["role"] == "concrete" and mount_post["id"] in l["pegs"]]
    mounted = next((p for p in after["posts"] if p["id"] == mount_post["id"]), None)
    check("forcing masonry changes that post's footing line",
          opened_mount and len(footing_before) == 1 and not footing_after
          and mounted is not None and mounted["mounting"] == "masonry",
          {"opened": opened_mount, "before": footing_before,
           "after": footing_after, "post": mounted})
    # The refusal's real claim: nothing the panel wrote is an override the
    # generator has to disown. A control that offered suppression on the corner
    # would land here as an `orphaned_override` and nowhere else.
    check("every directive the panel wrote is one the run applies",
          not after["orphaned"], after["orphaned"])
def _smoke_side_drag(c) -> None:
    """Adapter B — dragging a post in the SIDE VIEW (plan Task 3, spec §9.1).

    The profile's x axis is NOT the station. `buildChain()` lays runs end to end
    with a `reversed` flag — `gsOf = offset + (reversed ? L - s : s)` — so the
    topology built below exists to make that visible: run2 is walked backwards
    (its END is the shared corner), and a pointer moving RIGHT must therefore
    move the post toward a SMALLER local station. A naive `x / scale` reads the
    same drop as a much larger station on run1's side of the chain, and passes
    any check that only asserts "an override exists". Every case here asserts a
    number: the harness does no image diffing, so a screenshot-only case would
    report PASS while the post lands in the wrong section.
    """
    # --- a chain with a reversed section ---------------------------------
    c.js("document.getElementById('new-project-name').value = 'side-drag'; 'ok'")
    c.click(*c.element_center("#btn-new-project"))
    time.sleep(1.5)
    pid = c.js("document.getElementById('project-select').value")

    topo = {
        "revision": 0,
        "nodes": [{"id": "nA", "x_mm": 0, "y_mm": 0},
                  {"id": "nB", "x_mm": 6000, "y_mm": 0},
                  {"id": "nC", "x_mm": 6000, "y_mm": 6000}],
        # run2 ENDS at the shared corner, so the walk enters it backwards
        "runs": [{"id": "run1", "start_node_id": "nA", "end_node_id": "nB"},
                 {"id": "run2", "start_node_id": "nC", "end_node_id": "nB"}],
    }
    put = c.js(
        "fetch('/api/projects/" + pid + "/topology', {method: 'PUT',"
        " headers: {'Content-Type': 'application/json'},"
        " body: JSON.stringify(" + json.dumps(topo) + ")}).then(r => r.status)")
    c.js("{const s = document.getElementById('project-select');"
         " s.dispatchEvent(new Event('change'));} 'ok'")
    time.sleep(2.0)
    c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
    time.sleep(0.8)
    # the panel and its scope are user preferences that survive in localStorage;
    # drive them through their own controls rather than assuming a default
    c.js("""(() => {
  const p = document.getElementById('profile');
  if (p.classList.contains('collapsed')) document.getElementById('profile-toggle').click();
  const s = document.getElementById('profile-scope');
  if (s.value !== 'all') { s.value = 'all'; s.dispatchEvent(new Event('change')); }
  return 'ok';
})()""")
    c.click(*c.element_center("#btn-generate"))
    time.sleep(2.5)
    c.element_center("#profile-svg")     # scroll the side view into frame
    time.sleep(0.4)

    runs_before = c.js("fetch('/api/projects/" + pid + "/runs')"
                       ".then(r => r.json()).then(l => l.length)")
    posts = c.js("""
(() => [...document.querySelectorAll('#profile-svg .profile-post-hit[data-run]')]
  .map(e => {
    const r = e.getBoundingClientRect();
    return {run: e.dataset.run, s: Number(e.dataset.station),
            drag: e.dataset.drag === '1',
            x: r.x + r.width / 2, y: r.y + r.height / 2};
  }))()""") or []
    on_run1 = sorted([p for p in posts if p["run"] == "run1"], key=lambda p: p["s"])
    movable = sorted([p for p in posts if p["run"] == "run2" and p["drag"]],
                     key=lambda p: p["s"])
    # Without this the three cases below are vacuous: nothing draggable means
    # nothing dragged, and "no override was created" is not a passing state.
    check("the side view offers a movable post on the reversed section",
          put == 200 and len(on_run1) >= 2 and len(movable) >= 1
          and all(0 < p["s"] < 6000 for p in movable),
          {"put": put, "run1": len(on_run1), "movable": [p["s"] for p in movable]})
    if not (len(on_run1) >= 2 and movable):
        return

    # run1 is walked FORWARDS, so on it the chain coordinate IS the station —
    # which is what calibrates chain-mm to viewport px without this test having
    # to know PAD, the viewBox or the container width.
    span_px = (on_run1[-1]["x"] - on_run1[0]["x"]) / (on_run1[-1]["s"] - on_run1[0]["s"])
    origin_px = on_run1[0]["x"] - span_px * on_run1[0]["s"]
    target = movable[len(movable) // 2]
    gs0 = 12000 - target["s"]          # run2: offset 6000, reversed, L 6000
    gs1 = gs0 + 1000                   # the pointer moves 1 m along the CHAIN
    expect = 12000 - gs1               # ...which is 1 m BACK along run2
    naive = gs1 - 6000                 # what x/scale would have said
    drop_x = origin_px + span_px * gs1
    c.drag(target["x"], target["y"], drop_x, target["y"])
    wait_for(c, "fetch('/api/projects/" + pid + "').then(r => r.json())"
                ".then(p => p.overrides.length)")
    time.sleep(0.8)
    pins = c.js("fetch('/api/projects/" + pid + "').then(r => r.json())"
                ".then(p => p.overrides.filter(o => o.directive.kind === 'pin_post'))") or []

    check("a post dragged in the side view lands on the right run of the chain",
          [o["run_id"] for o in pins] == ["run2"],
          {"pins": [(o["run_id"], o["directive"]) for o in pins]})
    if len(pins) != 1:
        return
    got = pins[0]["directive"]["anchor"]["offset_mm"]
    # `naive` is 2 m away on this topology and on the far side of where the post
    # started, so a reversal the adapter got wrong cannot slip through the band.
    check("a reversed section drags in the direction the pointer moved",
          abs(got - expect) <= 150 and abs(got - naive) > 500 and got < target["s"],
          {"got": got, "expected": expect, "naive": naive, "from": target["s"]})
    check("the pin carries a segment-local RIGID anchor, not a station",
          pins[0]["directive"]["anchor"]["segment_index"] == 0
          and pins[0]["directive"]["anchor"]["reanchor"] == "rigid",
          pins[0]["directive"])

    # The dropped post STAYS where it was dropped. `reloadProject()` does not
    # refresh `state.result`, so without the pending marker the post springs
    # back to where the previous run put it and a working feature reads broken.
    marker = c.js("""
(() => {
  const m = document.querySelector('#profile-svg .profile-post-pending');
  if (!m) return null;
  const r = m.getBoundingClientRect();
  return r.x + r.width / 2;
})()""")
    check("the dropped post is drawn where it was dropped, as a pending marker",
          marker is not None and abs(marker - drop_x) <= 6,
          {"marker": marker, "drop_x": drop_x})
    runs_after = c.js("fetch('/api/projects/" + pid + "/runs')"
                      ".then(r => r.json()).then(l => l.length)")
    check("dropping a post does not regenerate", runs_after == runs_before,
          {"before": runs_before, "after": runs_after})

    # The cross-view property. `#override-list` is drawn by inspector.js, which
    # has never heard of profile.js: both re-render from `state.project` after
    # one write through state.js, which is the whole reason two adapters can
    # move the same post without an edge between them.
    #
    # Task 2 landed, so the stronger form is now assertable: the PLAN CANVAS
    # draws its own pending marker for an override the side view created. It is
    # scoped to `#canvas` because `inspector.js` also writes `data-post`, and a
    # global query would count the card as a second post.
    #
    # `pinned == 1` and not merely "a marker exists": the generated posts in the
    # same canvas carry `data-pinned="0"` (this run predates the override and
    # was never regenerated), so a marker drawn with the wrong flag — or a stale
    # canvas still showing the pre-drag layout — reads as 0 or 2 here, never 1.
    other_view = c.js("""
(() => {
  const cards = [...document.querySelectorAll('#override-list .card')];
  const canvas = document.getElementById('canvas');
  return {n: cards.length, text: cards.map(c => c.textContent).join(' | '),
          pinned: canvas
            ? canvas.querySelectorAll('[data-post][data-pinned="1"]').length : -1};
})()""")
    check("another module shows the same drop, without either knowing the other",
          other_view["n"] == 1 and "pin_post" in other_view["text"]
          and "run2" in other_view["text"], other_view)
    check("the plan canvas draws the post the SIDE view moved, marked pinned",
          other_view["pinned"] == 1, other_view)
    c.shot("40-side-drag.png")

    # --- the same post, dragged again ------------------------------------
    # There is no PUT /overrides: without the DELETE this leaves two pins and a
    # bay nobody asked for. The second gesture starts on the PENDING marker,
    # which is the post as the user now sees it.
    again = c.js("""
(() => {
  const e = document.querySelector('#profile-svg .profile-post-hit[data-ov]');
  if (!e) return null;
  const r = e.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2, s: Number(e.dataset.station)};
})()""")
    check("the pending post is draggable in its own right", again is not None, again)
    if again:
        # LEFT along the chain is BACK along run2 — the reversal again, this
        # time starting from a station the generator never placed
        c.drag(again["x"], again["y"], again["x"] - span_px * 2500, again["y"])
        time.sleep(1.5)
        after_two = c.js("fetch('/api/projects/" + pid + "').then(r => r.json())"
                         ".then(p => p.overrides.filter("
                         "o => o.directive.kind === 'pin_post'))") or []
        check("dragging the same post twice leaves ONE pin",
              len(after_two) == 1
              and after_two[0]["directive"]["anchor"]["offset_mm"] != got,
              [o["directive"] for o in after_two])

    # One gesture is one undo step: the snapshot is pushed once, past the
    # threshold, however many pointermoves the drag took.
    c.click(*c.element_center("#btn-undo"))
    time.sleep(2.0)
    undone = c.js("fetch('/api/projects/" + pid + "').then(r => r.json())"
                  ".then(p => p.overrides.filter("
                  "o => o.directive.kind === 'pin_post').length)")
    check("one drag is one undo step", undone == (1 if again else 0), undone)
def _smoke_plan_drag(c) -> None:
    """Adapter A: dragging a generated post in the plan canvas (spec §9).

    Its own project, because every assertion counts overrides and a run somebody
    else drew lays out differently. 4200 mm under the demo knowledge's 1800 mm
    maximum becomes three 1400 bays, so the interior LINE posts sit at 1400 and
    2800 — and a drop at 2500 leaves 1100 and 1700, breaking no rule. That is
    deliberate: these checks are about where a pin lands, not about the
    over-maximum path, which `tests/strategy/test_lock_bay.py` owns.

    Nothing here is a screenshot: the harness does no image diffing and
    `tools/smoke_baseline/` does not exist, so a case that only photographs the
    canvas reports PASS while the bug ships. Every assertion is a `check()`.
    """

    def st(expr: str) -> str:
        """Read the LIVE app state from a CDP evaluate.

        There is no `window.state`: every module talks through `state.js`, which
        is an ES module. Importing the URL the page itself imported hands back
        the very object the views mutate — the module registry is keyed by URL —
        rather than a fresh copy. `Runtime.evaluate` is called with
        awaitPromise, so the promise has resolved by the time `c.js` returns.
        """
        return ("import('./js/state.js').then(m => { const state = m.state;"
                f" return ({expr}); }})")

    def drag(from_mm: int, to_mm: int) -> None:
        """Press on the post at `from_mm`, ONE move to `to_mm`, release.

        NOT `c.drag`, and the difference is the whole point. Its eight
        intermediate moves are what a hand does, but headless Chrome under load
        fires `pointercancel` on a CAPTURED pointer partway through a gesture —
        it does it to the pre-existing vertex drag too, so it is the input layer
        and not this feature. A cancelled gesture that had already reached its
        destination still commits there (`pointercancel` ends the drag through
        the same `onDragEnd`), while a truncated eight-step one drops the post
        one step in and reports a wrong station as a product bug.

        One move is also enough: the 4 px threshold and the destination are both
        crossed by it.
        """
        x0, y0 = c.canvas_px(from_mm, 0)
        x1, y1 = c.canvas_px(to_mm, 0)
        c.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0,
              button="left", buttons=1, clickCount=1)
        c.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x1, y=y1,
              button="left", buttons=1)
        time.sleep(0.05)
        c.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1,
              button="left", buttons=0, clickCount=1)
        time.sleep(0.3)

    def run() -> None:
        # The evidence viewer is deep-linked open by the case before this one and
        # its overlay covers the page, so every click below would land on IT.
        # Close it the way a person would, and drop the hash it left behind.
        c.js("document.querySelector('[data-evidence-close]')?.click();"
             " if (location.hash) location.hash = ''; 'ok'")
        time.sleep(0.5)
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.4)
        c.js("document.getElementById('new-project-name').value = 'placement'; 'ok'")
        c.click(*c.element_center("#btn-new-project"))
        time.sleep(1.5)
        # ...and SAY that it worked. Without this the case would silently run
        # against whatever project the previous case left open — which is
        # exactly what a swallowed click looks like from here.
        empty_start = c.js(st("state.project.topology.runs.length === 0"))
        check("this case runs on a project of its own", bool(empty_start))
        # an empty project fits back to the default view, so the world
        # coordinates below are on screen whatever the previous case left the
        # viewBox at
        c.click(*c.element_center("#btn-fit"))
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(0, 0))
        c.click(*c.canvas_px(4200, 0))
        c.key("Enter")
        time.sleep(1.5)
        c.click(*c.element_center("#tool-select"))
        c.click(*c.element_center("#btn-fit"))   # zoom to the run: 1 px is ~11 mm
        c.js("document.getElementById('chk-overlay').checked = true; 'ok'")
        c.click(*c.element_center("#btn-generate"))
        posts = wait_for(c, st("JSON.stringify((state.result"
                               " ? state.result.strategy.posts : [])"
                               ".filter(p => p.run_ref === 'run1')"
                               ".map(p => p.station_mm))"), timeout=25)
        check("the run laid out where this case's coordinates assume it did",
              posts == "[1400,2800]", posts)
        if posts != "[1400,2800]":
            return   # every coordinate below is derived from that layout

        # --- a press under the threshold is still a click --------------------
        c.js("document.getElementById('inspector-body').textContent = 'SENTINEL'; 'ok'")
        c.click(*c.canvas_px(1400, 0))
        opened = wait_for(c, "document.getElementById('inspector-body')"
                             ".textContent.indexOf('SENTINEL') < 0")
        check("a press under 4 px still opens the post inspector", bool(opened))

        # --- drag the post at 2800 to 2500 -----------------------------------
        # Let the explanation fetch above finish first: `inspect()` APPENDS its
        # lines after an await, so a sentinel planted mid-flight would be
        # overwritten by the click already made rather than by the drag.
        time.sleep(1.5)
        run_before = c.js(st("state.result.run.id"))
        c.js("document.getElementById('inspector-body').textContent = 'SENTINEL'; 'ok'")
        drag(2800, 2500)
        wait_for(c, st("(state.project.overrides || [])"
                       ".filter(o => o.directive.kind === 'pin_post').length"),
                 timeout=15)
        pins = c.js(st("state.project.overrides"
                       ".filter(o => o.directive.kind === 'pin_post').length"))
        check("a post can be dragged and lands where the pointer did", pins == 1, pins)
        anchor = c.js(st("JSON.stringify(state.project.overrides"
                         ".filter(o => o.directive.kind === 'pin_post')"
                         ".map(o => [o.directive.anchor.segment_index,"
                         "           o.directive.anchor.offset_mm,"
                         "           o.directive.anchor.reanchor]))"))
        check("the pin carries a segment-local RIGID anchor, not a station",
              anchor == '[[0,2500,"rigid"]]', anchor)
        body = c.js("document.getElementById('inspector-body').textContent")
        check("a drag does not also open the inspector", body == "SENTINEL", body)
        # the overlay still holds the previous run's posts, so without this
        # marker the dropped post springs back and a working feature reads as a
        # broken one
        pending = c.js(
            "document.querySelectorAll('#g-overlay circle[data-pending]').length")
        check("the drop is drawn as a pending marker, distinct from a generated post",
              pending == 1, pending)
        check("a drop does not fire a generation",
              c.js(st("state.result.run.id")) == run_before)
        c.shot("30-post-dragged.png")

        # --- and again, on the same post: there is no PUT /overrides ---------
        # 3200 rather than somewhere nearer: the selected run's midpoint GHOST
        # sits at 2100 and is painted above the overlay, so a gesture that
        # starts within ~110 mm of it inserts a vertex instead of moving a post.
        drag(2500, 3200)
        wait_for(c, st("state.project.overrides.some("
                       "o => o.directive.kind === 'pin_post'"
                       " && o.directive.anchor.offset_mm === 3200)"), timeout=15)
        pins = c.js(st("state.project.overrides"
                       ".filter(o => o.directive.kind === 'pin_post').length"))
        check("dragging the same post twice leaves ONE pin", pins == 1, pins)

        # --- dropping a post onto its neighbour ------------------------------
        # Refused first: a PINNED post is not suppressible, and the refusal has
        # to happen at the pointer rather than as an override that immediately
        # reports itself orphaned.
        drag(3200, 2800)
        time.sleep(1.5)
        after = c.js(st("JSON.stringify((state.project.overrides || []).map("
                        "o => [o.directive.kind, o.directive.anchor.offset_mm]))"))
        check("dropping a post that may not be suppressed writes nothing at all",
              after == '[["pin_post",3200]]', after)
        # ...and allowed for a plain line post, which is the gesture the
        # backend's anchored `suppress_post` matching exists for
        drag(1400, 2800)
        wait_for(c, st("state.project.overrides"
                       ".some(o => o.directive.kind === 'suppress_post')"), timeout=15)
        killed = c.js(st("JSON.stringify(state.project.overrides"
                         ".filter(o => o.directive.kind === 'suppress_post')"
                         ".map(o => [o.directive.anchor.segment_index,"
                         "           o.directive.anchor.offset_mm,"
                         "           o.directive.anchor.reanchor]))"))
        check("dropping a LINE post onto its neighbour suppresses it, anchored",
              killed == '[[0,1400,"rigid"]]', killed)
        check("suppressing one post does not disturb the pin on another",
              c.js(st("state.project.overrides"
                      ".filter(o => o.directive.kind === 'pin_post').length")) == 1)
        c.shot("31-post-suppressed.png")

        # --- one drag is one undo step ---------------------------------------
        # Last, because undo restores through saveTopology() and that clears
        # state.result: there are no generated posts left to drag afterwards.
        # Four gestures are on the stack (draw, drag, drag, suppress) and the
        # REFUSED drop is deliberately not one of them, so each Ctrl+Z peels
        # exactly one thing that actually happened.
        c.key("z", ctrl=True)
        wait_for(c, st("!state.project.overrides"
                       ".some(o => o.directive.kind === 'suppress_post')"), timeout=15)
        c.key("z", ctrl=True)
        back = wait_for(c, st("state.project.overrides.some("
                              "o => o.directive.kind === 'pin_post'"
                              " && o.directive.anchor.offset_mm === 2500)"), timeout=15)
        check("one drag is one undo step — the second drag alone comes off", bool(back))
        c.key("z", ctrl=True)
        empty = wait_for(c, st("state.project.overrides.length === 0"), timeout=15)
        check("the next step is the first drag, and the drawing survives both",
              bool(empty) and c.js(st("state.project.topology.runs.length")) == 1)

    print("  -- plan canvas: hand placement --")
    try:
        run()
    except Exception as exc:   # noqa: BLE001
        # A raise here aborts main() before the tally line and takes every other
        # agent's cases with it. A crash IS a failure, and it is reported as one
        # through the same channel as everything else.
        check("the plan-canvas placement case ran to completion", False, repr(exc))


# Cases added by the choice-set and hand-placement work. Append your function
# to this list; define the function itself directly above this comment.
def _smoke_sales_mode(c) -> None:
    """The salesperson's app is the same app with the engineering taken out.

    Three things only a browser can answer. That the hide-list actually HIDES —
    `role.js` and `style.css` hold the list twice and `tests/web/test_role_sync.py`
    proves they agree with each other, which is not the same as proving either
    agrees with the rendered page. That the surfaces recording what was SOLD
    survive, because a mode that hid those would be small rather than useful.
    And that the words change: a salesperson is non-technical, so "⚙ Generate
    strategy" and "Height intent" are the defect, not the labels around them.

    Asserted through `getComputedStyle`, never `offsetParent`: a panel inside a
    tab that happens to be inactive is invisible for a reason that has nothing to
    do with the role, and would report this mode working when it is not.
    """
    c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
    time.sleep(0.4)

    shown = """
(() => {
  const vis = (sel) => {
    const e = document.querySelector(sel);
    if (!e) return "missing";
    return getComputedStyle(e).display === "none" ? "hidden" : "shown";
  };
  return {
    pin: vis("#tool-pin"),
    knowledge: vis('#tabs button[data-tab="knowledge"]'),
    bom: vis('#tabs button[data-tab="bom"]'),
    inspector: vis("#inspector"),
    gaps: vis("#gaps"),
    base: vis("#tool-base"),
    height: vis("#tool-height"),
    model_row: vis("#model-row"),
    profile: vis("#profile"),
    generate: document.getElementById("btn-generate").textContent.trim(),
    tab1: document.querySelector('#tabs button[data-tab="canvas"]').textContent.trim(),
    height_label: document.querySelector("#tool-height .t-label").textContent.trim(),
  };
})()"""

    before = c.js(shown)
    check("the full app shows the engineering surfaces to begin with",
          before["pin"] == "shown" and before["knowledge"] == "shown"
          and before["inspector"] == "shown", before)

    c.js("""(() => {
  const s = document.getElementById('role-select');
  s.value = 'sales';
  s.dispatchEvent(new Event('change'));
  return 'ok';
})()""")
    time.sleep(0.6)
    sales = c.js(shown)

    check("sales mode hides every surface that decides how the fence is BUILT",
          all(sales[k] == "hidden" for k in
              ("pin", "knowledge", "bom", "inspector", "gaps")), sales)
    check("sales mode keeps every surface that records what was SOLD",
          all(sales[k] == "shown" for k in
              ("base", "height", "model_row", "profile")), sales)
    # The rename is the half a hide-list cannot do. `sales.<key>` beats `<key>`
    # in `t()` only in this mode, so these strings prove the layer resolves —
    # and prove it on the STATIC pass, which runs over the whole page at once.
    check("the words are a salesperson's, not an engineer's",
          "Generate strategy" not in sales["generate"]
          and sales["tab1"] != before["tab1"]
          and sales["height_label"] == "Height", sales)
    c.shot("50-sales-mode.png")

    # Hebrew, because the app opens in it and a sales key present in one bundle
    # and missing from the other renders an English word to a Hebrew reader.
    c.js("document.getElementById('btn-locale').click(); 'ok'")
    time.sleep(0.8)
    he = c.js(shown)
    check("the sales vocabulary exists in Hebrew too",
          all(not re.search(r"[A-Za-z]{3}", he[k])
              for k in ("generate", "tab1", "height_label")), he)
    check("switching language does not un-hide the engineering surfaces",
          he["pin"] == "hidden" and he["knowledge"] == "hidden", he)
    c.js("document.getElementById('btn-locale').click(); 'ok'")
    time.sleep(0.8)

    # ...and back, because a mode nobody can leave is a mode that traps the
    # office person who borrowed the salesperson's laptop.
    c.js("""(() => {
  const s = document.getElementById('role-select');
  s.value = 'all';
  s.dispatchEvent(new Event('change'));
  return 'ok';
})()""")
    time.sleep(0.6)
    back = c.js(shown)
    check("leaving sales mode restores the whole app",
          back["pin"] == "shown" and back["knowledge"] == "shown"
          and back["generate"] == before["generate"], back)


def _smoke_job_identity(c) -> None:
    """A project is a JOB somebody sold (slice 1 of the salesperson MVP).

    `Project` was `id, name`, so the picker said "project 7" — the first thing a
    salesperson sees and the last thing that told them anything.

    The assertion that matters is the SECOND save. A salesperson enters this
    after the visit from paper: they start with a customer name, draw for twenty
    minutes, and only then find the address on the sketch. If naming the job cost
    them the drawing, the panel would be worse than the blank field it replaced.
    """
    c.js("""(() => {
  const s = document.getElementById('role-select');
  if (s.value !== 'all') { s.value = 'all'; s.dispatchEvent(new Event('change')); }
  return 'ok';
})()""")
    c.js("document.getElementById('new-project-name').value = 'jobtest'; 'ok'")
    c.click(*c.element_center("#btn-new-project"))
    time.sleep(1.5)
    pid = c.js("document.getElementById('project-select').value")
    check("a job to name", bool(pid), pid)
    if not pid:
        return

    fill = """
(() => {
  const set = (id, v) => {
    const e = document.getElementById(id);
    if (!e) return false;
    e.value = v;
    return true;
  };
  const ok = %s;
  document.getElementById('job-save').click();
  return ok;
})()"""
    check("the job panel is on screen before anything is drawn",
          c.js("!!document.getElementById('job-panel')"))

    # --- name the customer, then draw ------------------------------------
    c.js(fill % "set('job-customer', 'Dana Levy')")
    time.sleep(1.2)
    after_first = c.js("fetch(`/api/projects/%s`).then(r => r.json())"
                       ".then(p => p.job)" % pid)
    check("a job can be started with only a customer",
          (after_first or {}).get("customer") == "Dana Levy", after_first)

    topo = {"revision": 0,
            "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                      {"id": "n2", "x_mm": 5000, "y_mm": 0}],
            "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}]}
    c.js("fetch('/api/projects/" + pid + "/topology', {method: 'PUT',"
         " headers: {'Content-Type': 'application/json'},"
         " body: JSON.stringify(" + json.dumps(topo) + ")}).then(r => r.status)")
    c.js("{const s = document.getElementById('project-select');"
         " s.dispatchEvent(new Event('change'));} 'ok'")
    time.sleep(2.0)

    # --- ...and only now find the address on the sketch ------------------
    c.js(fill % ("set('job-address', 'Herzl 12') && "
                 "set('job-sold_by', 'bob') && set('job-sold_on', '2026-09-04')"))
    time.sleep(1.5)
    final = c.js("fetch(`/api/projects/%s`).then(r => r.json())"
                 ".then(p => ({job: p.job, runs: p.topology.runs.length}))" % pid)
    check("the address can be added afterwards WITHOUT losing the drawing",
          final["job"]["address"] == "Herzl 12" and final["runs"] == 1, final)
    check("the whole job is recorded",
          final["job"]["customer"] == "Dana Levy"
          and final["job"]["sold_by"] == "bob"
          and final["job"]["sold_on"] == "2026-09-04", final["job"])

    # The picker is the payoff: this is the surface that said "project 7".
    # By id, not by "whichever is selected": an earlier case may have left the
    # selection elsewhere, and this case is about how THIS job is labelled.
    label = c.js("""
(() => {
  const s = document.getElementById('project-select');
  return [...s.options].find((o) => o.value === %s)?.textContent || '(no option)';
})()""" % json.dumps(pid))
    check("the picker calls the job what a person would call it",
          label == "Dana Levy — Herzl 12", label)
    c.shot("51-job-identity.png")

    # A date that is not a date is refused AT THE BOUNDARY, and changes nothing.
    c.js(fill % "set('job-sold_on', '') && set('job-customer', 'Dana Levy')")
    time.sleep(1.2)
    kept = c.js("fetch(`/api/projects/%s`).then(r => r.json())"
                ".then(p => p.job.customer)" % pid)
    check("clearing an optional field leaves the rest of the job intact",
          kept == "Dana Levy", kept)


def _smoke_property_context(c) -> None:
    """The house and the street (slice 3 of the salesperson MVP).

    A salesperson describes a layout relative to the house and the road, and the
    office person cannot read an abstract coordinate plane as a PLACE. What only
    a browser can say here: that a press-drag-release actually reaches
    `shapeFor` and persists, that the backdrop does NOT eat clicks meant for the
    fence in front of it, and — the property that keeps this slice cheap — that
    drawing a house does not touch the topology revision.

    The geometry itself is pinned in `tests/web/test_context_module.py`, so this
    case asserts the wiring rather than re-deriving the rectangle.
    """
    c.js("""(() => {
  const s = document.getElementById('role-select');
  if (s.value !== 'all') { s.value = 'all'; s.dispatchEvent(new Event('change')); }
  return 'ok';
})()""")
    c.js("document.getElementById('new-project-name').value = 'property'; 'ok'")
    c.click(*c.element_center("#btn-new-project"))
    time.sleep(1.5)
    pid = c.js("document.getElementById('project-select').value")
    topo = {"revision": 0,
            "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                      {"id": "n2", "x_mm": 8000, "y_mm": 0}],
            "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}]}
    c.js("fetch('/api/projects/" + pid + "/topology', {method: 'PUT',"
         " headers: {'Content-Type': 'application/json'},"
         " body: JSON.stringify(" + json.dumps(topo) + ")}).then(r => r.status)")
    c.js("{const s = document.getElementById('project-select');"
         " s.dispatchEvent(new Event('change'));} 'ok'")
    time.sleep(2.0)
    rev_before = c.js("fetch(`/api/projects/%s`).then(r => r.json())"
                      ".then(p => p.topology.revision)" % pid)

    # --- drag a house ----------------------------------------------------
    c.click(*c.element_center("#tool-house"))
    time.sleep(0.3)
    c.drag(*c.canvas_px(1000, 3000), *c.canvas_px(7000, 8000))
    time.sleep(1.2)
    ctx = c.js("fetch(`/api/projects/%s`).then(r => r.json()).then(p => p.context)" % pid)
    marks = (ctx or {}).get("landmarks", [])
    check("dragging with the house tool records a closed outline",
          len(marks) == 1 and marks[0]["kind"] == "house"
          and marks[0]["closed"] is True and len(marks[0]["points"]) == 4, ctx)

    # --- and a street ----------------------------------------------------
    c.click(*c.element_center("#tool-street"))
    time.sleep(0.3)
    c.drag(*c.canvas_px(-1000, -2000), *c.canvas_px(10000, -2000))
    time.sleep(1.2)
    ctx = c.js("fetch(`/api/projects/%s`).then(r => r.json()).then(p => p.context)" % pid)
    marks = (ctx or {}).get("landmarks", [])
    check("dragging with the street tool records an open line",
          len(marks) == 2 and marks[1]["kind"] == "street"
          and marks[1]["closed"] is False and len(marks[1]["points"]) == 2, ctx)
    check("the two landmarks do not share an id",
          len({m["id"] for m in marks}) == len(marks), marks)

    drawn = c.js("document.querySelectorAll('#g-context path').length")
    check("both are drawn on the canvas", drawn == 2, drawn)
    c.shot("52-property-context.png")

    # --- the property that keeps this slice cheap ------------------------
    rev_after = c.js("fetch(`/api/projects/%s`).then(r => r.json())"
                     ".then(p => p.topology.revision)" % pid)
    check("drawing the property does NOT touch the topology revision",
          rev_after == rev_before, {"before": rev_before, "after": rev_after})

    # --- the backdrop must not eat the fence -----------------------------
    # The house was drawn straddling the run. With the select tool, a click on
    # the run inside the house's footprint must still select the RUN — a
    # backdrop that swallowed clicks would make the drawing harder to edit than
    # it was before there was a house.
    c.click(*c.element_center("#tool-select"))
    time.sleep(0.3)
    c.click(*c.canvas_px(4000, 0))
    time.sleep(0.5)
    selected = c.js("document.getElementById('run-select')?.value || ''")
    check("a click through the house still reaches the fence", selected == "run1",
          selected)
    hits = c.js("""
(() => [...document.querySelectorAll('#g-context *')]
  .filter((e) => getComputedStyle(e).pointerEvents !== 'none').length)()""")
    check("nothing in the property layer accepts a pointer at all", hits == 0, hits)

    # --- naming one, and removing it -------------------------------------
    named = c.js("""
(() => {
  const input = document.querySelector('#context-panel .context-label-input');
  if (!input) return false;
  input.value = "the neighbour's side";
  input.dispatchEvent(new Event('change'));
  return true;
})()""")
    check("a landmark can be named from the panel", bool(named))
    time.sleep(1.2)
    labelled = c.js("fetch(`/api/projects/%s`).then(r => r.json())"
                    ".then(p => p.context.landmarks[0].label)" % pid)
    check("the label is what the office person will read",
          labelled == "the neighbour's side", labelled)

    c.js("document.querySelector('#context-panel .context-remove')?.click(); 'ok'")
    time.sleep(1.2)
    left = c.js("fetch(`/api/projects/%s`).then(r => r.json())"
                ".then(p => p.context.landmarks.length)" % pid)
    check("a landmark can be removed", left == 1, left)


def _smoke_handover_sheet(c) -> None:
    """What the office still needs, and an estimate that says it is one
    (slice 4 of the salesperson MVP).

    The whole MVP succeeds or fails on this panel: *captured completely enough
    that the office person never has to phone the salesperson.* So the case
    walks a job from empty to complete and asserts the sheet empties out — a
    checklist that never reaches zero is noise and gets ignored.

    The wording RULES are pinned in `tests/web/test_handover_module.py`; what
    only a browser can say is that the sheet reacts to a job being filled in, and
    that the number never appears without the sentence that qualifies it.
    """
    c.js("""(() => {
  const s = document.getElementById('role-select');
  if (s.value !== 'all') { s.value = 'all'; s.dispatchEvent(new Event('change')); }
  return 'ok';
})()""")
    c.js("document.getElementById('new-project-name').value = 'handover'; 'ok'")
    c.click(*c.element_center("#btn-new-project"))
    time.sleep(1.5)
    pid = c.js("document.getElementById('project-select').value")

    read = """
(() => {
  const host = document.getElementById('handover-panel');
  if (!host) return null;
  return {
    gaps: [...host.querySelectorAll('.handover-gaps li')].map(e => e.textContent.trim()),
    blocking: host.querySelectorAll('.handover-gaps li.blocking').length,
    amount: host.querySelector('.handover-amount .num')?.textContent.trim() || null,
    note: host.querySelector('.handover-estimate .meta')?.textContent.trim() || '',
    ready: host.querySelectorAll('.handover-ready').length,
  };
})()"""
    empty = c.js(read)
    check("an empty job says the first thing that is wrong, and only that",
          empty is not None and len(empty["gaps"]) == 1
          and empty["blocking"] == 1, empty)
    check("no number is shown for a fence that does not exist",
          empty["amount"] is None and empty["note"] != "", empty)

    # --- draw, name, and place the property ------------------------------
    topo = {"revision": 0,
            "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                      {"id": "n2", "x_mm": 5000, "y_mm": 0}],
            "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}]}
    c.js("fetch('/api/projects/" + pid + "/topology', {method: 'PUT',"
         " headers: {'Content-Type': 'application/json'},"
         " body: JSON.stringify(" + json.dumps(topo) + ")}).then(r => r.status)")
    c.js("{const s = document.getElementById('project-select');"
         " s.dispatchEvent(new Event('change'));} 'ok'")
    time.sleep(2.0)
    drawn = c.js(read)
    check("a drawn fence turns one item into the real list",
          len(drawn["gaps"]) > 1, drawn)
    # The silent defaults are the point of the exercise: nobody said how tall.
    check("the assumed height is named with the number that will be built",
          any("1800" in g for g in drawn["gaps"]), drawn["gaps"])

    # Say what was sold. Without this the sheet correctly BLOCKS the estimate —
    # `generate()` still works via the M-LEGACY compatibility path, but "the
    # engine can price something" and "the salesperson said what they sold" are
    # different claims, and only the second one the office can order from.
    # `active_version` non-null is what makes a row SELECTABLE: the listing
    # deliberately keeps draft-only models visible so they read as "not yet
    # published" rather than vanishing, and picking one is a 422.
    model = c.js("""
fetch('/api/fence-models').then(r => r.json()).then((ms) => {
  const id = (ms.find((m) => m.active_version != null) || {}).id;
  if (!id) return 'none';
  return fetch('/api/projects/%s/fence-model', {method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({model_id: id})}).then(r => r.status);
})""" % pid)
    check("the model that was sold could be recorded", model == 200, model)
    c.js("{const s = document.getElementById('project-select');"
         " s.dispatchEvent(new Event('change'));} 'ok'")
    time.sleep(2.0)

    # Read BEFORE the save, or the "-4" below is measured against the answer.
    before_naming = c.js(read)
    c.js("""(() => {
  document.getElementById('job-customer').value = 'Dana Levy';
  document.getElementById('job-address').value = 'Herzl 12';
  document.getElementById('job-sold_by').value = 'bob';
  document.getElementById('job-sold_on').value = '2026-09-04';
  document.getElementById('job-save').click();
  return 'ok';
})()""")
    time.sleep(1.5)
    named = c.js(read)
    check("naming the job removes exactly those four questions",
          len(named["gaps"]) == len(before_naming["gaps"]) - 4,
          {"before": before_naming["gaps"], "after": named["gaps"]})

    # --- generate, and check the number arrives WITH its sentence --------
    c.click(*c.element_center("#btn-generate"))
    time.sleep(3.0)
    priced = c.js(read)
    check("a generated run produces an estimate", priced["amount"], priced)
    check("the estimate never stands without the sentence that qualifies it",
          bool(priced["note"]), priced)
    # Items are still outstanding here (no property drawn), so the number must
    # say it will move — the failure this guards is a salesperson sending a
    # customer a figure that reads as a commitment.
    check("an estimate from an incomplete layout says it will move",
          len(priced["gaps"]) > 0 and priced["note"] != "", priced)
    c.shot("53-handover-sheet.png")

    # --- and the state the whole MVP aims at -----------------------------
    ctx = {"landmarks": [{"id": "lm1", "kind": "street", "label": "",
                          "points": [[-1000, -2000], [9000, -2000]],
                          "closed": False}]}
    c.js("fetch('/api/projects/" + pid + "/context', {method: 'PUT',"
         " headers: {'Content-Type': 'application/json'},"
         " body: JSON.stringify(" + json.dumps(ctx) + ")}).then(r => r.status)")
    ev = {"height": 1500}
    c.js("""(() => {
  const p = window.__fenceaiTest || {};
  return 'ok';
})()""")
    # height + base stated through the API, because this case is about the
    # SHEET rather than about the two tools that already have their own cases
    full = c.js("""
fetch('/api/projects/%s').then(r => r.json()).then((p) => {
  const run = p.topology.runs[0];
  const a0 = {segment_index: 0, offset_mm: 0, seg_len_at_authoring_mm: 5000};
  const a1 = {segment_index: 0, offset_mm: 5000, seg_len_at_authoring_mm: 5000};
  run.interval_events.push(
    {id: 'ev-h', start_anchor: a0, end_anchor: a1,
     payload: {kind: 'height_intent', height_mm: %d}},
    {id: 'ev-b', start_anchor: a0, end_anchor: a1,
     payload: {kind: 'base', surface: 'soil'}});
  return fetch('/api/projects/%s/topology', {method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(p.topology)}).then(r => r.status);
})""" % (pid, ev["height"], pid))
    check("the height and base could be stated", full == 200, full)
    c.js("{const s = document.getElementById('project-select');"
         " s.dispatchEvent(new Event('change'));} 'ok'")
    time.sleep(2.0)
    done = c.js(read)
    check("a fully recorded job has nothing left for the office to ask",
          done["gaps"] == [] and done["ready"] == 1, done)


_CHOICE_CASES: list = [
    _smoke_sales_mode,
    _smoke_job_identity,
    _smoke_property_context,
    _smoke_handover_sheet,
    _smoke_choices_panel,
    _smoke_post_inspector,
    _smoke_side_drag,
    _smoke_plan_drag,
]


def main() -> int:
    # a stale server on our port would silently serve old code/data — abort loudly
    try:
        urllib.request.urlopen(f"http://localhost:{PORT}/api/health", timeout=1)
        print(f"FATAL: something is already listening on :{PORT} — kill it first "
              f"(pkill -f 'port {PORT}')")
        return 2
    except Exception:
        pass  # port free, good

    # ... and the same question about the BROWSER, which is not a smaller one. A
    # Chrome already holding :9333 answers `/json/version`, so the readiness loop
    # below is satisfied by SOMEBODY ELSE'S browser: the fresh profile Chrome
    # started underneath never binds the port and is never spoken to, and the run
    # drives the developer's own profile — the surviving `fenceai.locale` and the
    # whole failure the private profile exists to prevent, back again and quieter
    # than before, because a readiness wait that succeeds says nothing about WHO
    # answered.
    try:
        urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version", timeout=1)
        # the bracket in the hint is not a typo: `pkill -f` matches the shell's
        # OWN command line, so the obvious spelling kills the terminal that runs it
        print(f"FATAL: something is already listening on :{CDP_PORT} — a browser "
              f"is holding the debug port; kill it first "
              f"(pkill -f 'remote-debugging-po[r]t={CDP_PORT}')")
        return 2
    except Exception:
        pass  # port free, good

    db = tempfile.mktemp(suffix=".db")
    env = {**os.environ, "FENCEAI_DB": db, "FENCEAI_AI": "stub"}
    server = subprocess.Popen(
        ["uv", "run", "uvicorn", "fenceai.api.app:app", "--port", str(PORT)],
        env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    # A profile of its own, for the same reason the DB above is a fresh file.
    # Without it Chrome uses the DEFAULT profile — the developer's own — and
    # `localStorage` for this origin SURVIVES the run: `fenceai.locale` and
    # `fenceai.units` are persisted preferences (i18n.js:32, units.js:162), and
    # this suite ends by toggling to English. The next run then opened in English
    # with every Hebrew assertion failing, or in cm with every mm one failing —
    # 33 unrelated red checks from the first generation onward, and green again
    # whenever Chrome happened to fall back to a throwaway profile because the
    # real one was locked by a running browser. That is not flakiness under load,
    # which is what it was first written off as: a gate whose answer depends on
    # the developer's browser profile is not a gate.
    profile = tempfile.mkdtemp(prefix="fenceai-smoke-profile-")
    chrome = subprocess.Popen(
        ["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
         f"--user-data-dir={profile}",
         f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*",
         "--window-size=1400,950", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    try:
        # Wait for BOTH to answer rather than sleeping a fixed 3 s. A brand-new
        # Chrome profile initialises slower than a warm one, so the old sleep
        # turned a hermetic run into a connection-refused traceback — and a fixed
        # sleep is what made the whole start-up fragile in the first place.
        for url in (f"http://localhost:{CDP_PORT}/json/version",
                    f"http://localhost:{PORT}/api/health"):
            for _ in range(120):          # 60 s, checked twice a second
                try:
                    urllib.request.urlopen(url, timeout=1)
                    break
                except Exception:
                    time.sleep(0.5)
            else:
                print(f"FATAL: {url} never answered")
                return 2
        c = Cdp(f"http://localhost:{PORT}/", cdp_port=CDP_PORT, out_dir=OUT)
        # `confirm` true so a destructive action proceeds unattended. `alert` is
        # swallowed for a harder reason: `Page.enable` (cdp.py) makes a JS dialog
        # BLOCK until it is explicitly handled, and `apiSend` alerts on every
        # refused request — so one 422 anywhere in the app hangs the evaluate that
        # triggered it, and the run dies on a socket timeout instead of reporting a
        # red check. A hang is not a check result: with this stubbed, a save the
        # server refuses fails the check that asked for it.
        c.js("window.confirm = () => true; window.alert = () => {}; undefined")

        # fresh DBs now open into the seeded sample project (which already has
        # runs + a gate); create an EMPTY project so every check below starts
        # from known-zero state
        c.js("document.getElementById('new-project-name').value = 'smoke'; 'ok'")
        c.click(*c.element_center("#btn-new-project"))
        time.sleep(1.5)
        n_runs0 = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.topology.runs.length)""")
        check("fresh project starts empty", n_runs0 == 0)

        # --- draw a 6 m run with the Draw tool ------------------------------
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(0, 0))
        c.click(*c.canvas_px(6000, 0))
        c.key("Enter")
        time.sleep(1)
        n_runs = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.topology.runs.length)""")
        check("draw creates a run", n_runs == 1)
        c.shot("01-drawn.png")

        # --- select + drag the end dot --------------------------------------
        c.click(*c.element_center("#tool-select"))
        c.click(*c.canvas_px(3000, 0))       # select the run
        c.drag(*c.canvas_px(6000, 0), *c.canvas_px(6000, 2000))
        length = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => {
    const run = p.topology.runs[0];
    const n = (id) => p.topology.nodes.find(x => x.id === id);
    const a = n(run.start_node_id), b = n(run.end_node_id);
    return Math.round(Math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm));
  })""")
        check("drag moved the end dot (run length changed)", length != 6000)
        c.shot("02-dragged.png")

        # --- undo restores ----------------------------------------------------
        c.key("z", ctrl=True)
        time.sleep(1)
        length2 = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => {
    const run = p.topology.runs[0];
    const n = (id) => p.topology.nodes.find(x => x.id === id);
    const a = n(run.start_node_id), b = n(run.end_node_id);
    return Math.round(Math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm));
  })""")
        check("undo restored the drag", length2 == 6000)

        # --- gate tool + generate --------------------------------------------
        c.click(*c.element_center("#tool-gate"))
        c.click(*c.canvas_px(2000, 0))
        time.sleep(0.5)
        has_popover = c.js("!!document.querySelector('.popover')")
        check("gate popover opens", has_popover)
        # the offered opening is the kit's DECLARED width (catalog attrs), never
        # digits parsed out of its sku — another catalog's sku carries other
        # numbers entirely (tools/catalogs/barrette.json: BAR-GATE-1168)
        declared = c.js("""
fetch('/api/catalog').then(r => r.json()).then(cat => {
  const sku = document.getElementById('pop-kit')?.value;
  const p = sku && cat.products[sku];
  return p ? ((p.capabilities || {}).opening_width_mm ?? null) : null;
})""")
        width_field = c.js("document.getElementById('pop-width')?.value")
        check("the gate width offered is the kit's declared opening",
              declared is not None and str(declared) == (width_field or ""))
        if has_popover:
            c.js("document.getElementById('pop-save').click(); 'saved'")
            time.sleep(1)
            n_gates = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json())
  .then(p => p.topology.runs[0].point_events.filter(e => e.payload.kind === 'gate').length)""")
            check("gate saved to topology", n_gates == 1)
        c.click(*c.element_center("#btn-generate"))
        time.sleep(1.5)
        n_posts = c.js("document.querySelectorAll('#g-overlay circle').length")
        check("generate renders posts", (n_posts or 0) >= 3)
        # the strategy must SAY what it produced, not only draw it
        summary = c.js("document.getElementById('strategy-summary').textContent")
        check("the strategy summary reports posts, spans and fence length",
              all(w in (summary or "") for w in ["עמודים", "מפתחים", "גדר"])
              and str(n_posts) in (summary or ""))
        c.shot("03-generated.png")

        # --- the selected section's decisions, and a conversation about one ----
        # The roadmap asks to "focus on specific sections of the fence and get
        # only the decisions related to the selected section — change, comment
        # or start a conversation about it". Both halves are checked here
        # because only the browser has the two of them together: the panel reads
        # its section from the SAME `#run-select` the side column already has,
        # and a comment has to survive the round trip to the server and come
        # back rendered — which is the half that did not exist at all (there was
        # no GET for corrections anywhere).
        section = c.js("""
(() => {
  const host = document.getElementById('section-decisions');
  if (!host) return null;
  return {
    decisions: host.querySelectorAll('.decision').length,
    sentences: [...host.querySelectorAll('.decision .expl')]
      .map(d => d.textContent.trim()).filter(Boolean).length,
    start: !!host.querySelector('[data-act="say"]'),
    comments: host.querySelectorAll('.verbatim').length,
  };
})()""")
        check("the selected section lists its own decisions, localized",
              section is not None and section["decisions"] > 0
              and section["sentences"] == section["decisions"]
              and section["start"] and section["comments"] == 0)

        # start a conversation on the first decision and read it back
        c.js("""
document.querySelector('#section-decisions [data-act="say"]').click(); 'ok'""")
        time.sleep(0.6)
        c.js("""
{
  const box = document.querySelector('#section-decisions [data-f="comment"]');
  box.value = 'למה דווקא כאן?';
  document.querySelector('#section-decisions [data-act="send"]').click();
}
'ok'""")
        time.sleep(1.5)
        said = c.js("""
(() => {
  const host = document.getElementById('section-decisions');
  return {
    comments: host.querySelectorAll('.verbatim').length,
    text: host.textContent,
    open_forms: host.querySelectorAll('[data-form]').length,
  };
})()""")
        check("a comment on a decision is stored and read back on the panel",
              said["comments"] == 1 and "למה דווקא כאן?" in said["text"]
              and said["open_forms"] == 0)
        # the boundary, visible to the user rather than only true in the backend
        # against the BUNDLE, not the copy: a wording change is not a regression
        note = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(b => b['decisions.comment_note'])""")
        check("the panel says a comment changes nothing on its own",
              bool(note) and note in said["text"])
        # --- and the loop the boundary promises, walked ------------------------
        # "A comment becomes an interpretation, an interpretation becomes a
        # PROPOSAL, and only a human confirms." The propose route existed and was
        # reachable from nothing; a boundary nobody can walk is a sentence in a
        # doc. The demo proposer reads a narrow vocabulary on purpose, so the
        # comment below is one it recognises — and the check asserts the answer
        # is NAMED either way, because "nothing suggests a rule" is the ordinary
        # outcome and a silent button reads as broken.
        c.js("""
document.querySelector('#section-decisions [data-act="say"]').click(); 'ok'""")
        time.sleep(0.5)
        c.js("""
{
  const box = document.querySelector('#section-decisions [data-f="comment"]');
  box.value = 'תמיד להשתמש ביסוד קיים';
  document.querySelector('#section-decisions [data-act="send"]').click();
}
'ok'""")
        time.sleep(1.5)
        c.js("""document.querySelector('#section-decisions [data-act="propose"]').click(); 'ok'""")
        time.sleep(2.0)
        proposed = c.js(
            "document.getElementById('propose-said')?.textContent || ''")
        check("a conversation can be turned into a candidate rule",
              bool(proposed.strip()))
        queued = c.js("""
fetch('/api/candidates').then(r => r.json()).then(cs => ({
  n: cs.length, inert: cs.every(c => c.status === 'proposed')}))""")
        check("the candidate arrives INERT, for a person to approve",
              (queued or {}).get("n", 0) > 0 and queued["inert"])
        c.shot("03b-section-decisions.png")

        # --- the map moves: dragging empty canvas pans, a click still edits ---
        vb_before = c.js("document.getElementById('canvas').getAttribute('viewBox')")
        empty = c.canvas_px(1000, 4000)          # away from the run
        c.drag(empty[0], empty[1], empty[0] + 120, empty[1] + 60)
        vb_after = c.js("document.getElementById('canvas').getAttribute('viewBox')")
        check("dragging empty canvas moves the map", vb_before != vb_after)
        # each cursor promises a different thing — the map's hand must not leak
        # onto the elements drawn on it
        c.js("document.getElementById('tool-select').click(); 'ok'")
        time.sleep(0.3)
        cursors = c.js("""
(() => {
  const cur = (sel) => { const el = document.querySelector(sel);
    return el ? getComputedStyle(el).cursor : null; };
  const canvas = document.getElementById('canvas');
  const before = getComputedStyle(canvas).cursor;
  canvas.classList.add('panning');
  const panning = { canvas: getComputedStyle(canvas).cursor, run: cur('.run-hit') };
  canvas.classList.remove('panning');
  return { map: before, run: cur('.run-hit'), overlay: cur('#g-overlay circle'),
           panning };
})()""")
        check("empty canvas advertises panning", cursors["map"] == "grab")
        check("drawn elements keep their own cursor, not the map's hand",
              cursors["run"] == "pointer" and cursors["overlay"] == "help")
        check("a pan in progress overrides every cursor under the pointer",
              cursors["panning"]["canvas"] == "grabbing"
              and cursors["panning"]["run"] == "grabbing")
        c.js("document.getElementById('tool-draw').click(); 'ok'")
        time.sleep(0.3)
        check("the draw tool aims instead of grabbing",
              c.js("getComputedStyle(document.getElementById('canvas')).cursor")
              == "crosshair")
        c.js("document.getElementById('tool-gate').click(); 'ok'")
        time.sleep(0.3)
        check("an event tool aims at a station on the run",
              c.js("getComputedStyle(document.querySelector('.run-hit')).cursor")
              == "crosshair")
        c.js("document.getElementById('tool-select').click(); 'ok'")
        time.sleep(0.3)
        n_runs_after_pan = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.topology.runs.length)""")
        check("panning never edits the drawing", n_runs_after_pan == 1)
        c.click(*c.element_center("#btn-fit"))
        time.sleep(0.4)

        # --- profile panel renders -------------------------------------------
        profile_drawn = c.js("document.querySelectorAll('#p-result *').length")
        profile_ground = c.js("document.querySelectorAll('#p-ground *').length")
        check("profile renders generated panels/posts", (profile_drawn or 0) > 0)
        check("profile renders the ground line", (profile_ground or 0) > 0)
        # a side view without a scale is a picture, not a measurement
        zlabels = c.js("document.querySelectorAll('.profile-zlabel').length")
        axis_unit = c.js("document.querySelector('.profile-axis-unit')?.textContent")
        check("side view has an elevation scale", (zlabels or 0) >= 2)
        check("the scale names its unit and the exaggeration",
              'מ"מ' in (axis_unit or "") and "×" in (axis_unit or ""))

        # --- structure tab: setting out, bays, and what each consists of ------
        c.js("document.querySelector('#tabs button[data-tab=\"structure\"]').click(); 'ok'")
        time.sleep(1.5)
        struct = c.js("document.getElementById('structure-body').textContent")
        check("the structure tab lists setting out and bays",
              all(w in (struct or "") for w in ["מקטע A", "P1", "B1", "סימון בשטח"]))
        rows = c.js("document.querySelectorAll('#structure-body tr[data-element]').length")
        expected_rows = c.js("""
(async () => {
  const runs = await (await fetch(
    `/api/projects/${document.getElementById('project-select').value}/runs`)).json();
  const doc = await (await fetch(`/api/runs/${runs[runs.length - 1].id}/structure`)).json();
  return doc.sections.reduce((n, s) =>
    n + s.setting_out.length + s.bays.length + s.gates.length, 0);
})()""")
        check("every element in the document has a row", rows == expected_rows)
        # --- the ANNEXE, on the sheet that goes to site (item 8, §3.3.5) ------
        # The obligation names its own failure: a document-scoped warning shown
        # on every line is noise that trains a reader to ignore warnings. So the
        # check is a COUNT, not a presence — the sentence is in the annexe, and
        # it is in the whole sheet exactly once.
        annexe = c.js("""
(async () => {
  const runs = await (await fetch(
    `/api/projects/${document.getElementById('project-select').value}/runs`)).json();
  const doc = await (await fetch(`/api/runs/${runs[runs.length - 1].id}/structure`)).json();
  const placed = (doc.quoted_warnings || {}).placements || [];
  const box = placed.find(p => p.where === 'annexe');
  const host = document.getElementById('structure-annexe');
  const sheet = document.getElementById('structure-body').textContent;
  const sentence = box ? box.warning.text_raw : '';
  const note = placed.find(p => p.where === 'product');
  // An INLINED entry is wrapped in `.doc-warnings` and labelled with what it
  // attaches to; a job-wide one sits directly in the panel. Counting all
  // `.doc-warning` together is what made the first version of this check stale
  // the moment the sheet started carrying the other buckets.
  const loose = host ? [...host.querySelectorAll('.doc-warning')]
    .filter(d => !d.closest('.doc-warnings')) : [];
  return {
    host: !!host,
    annexe_entries: loose.length,
    // the sentence appears in the sheet ONCE, and it is inside the annexe
    occurrences: sentence ? sheet.split(sentence).length - 1 : -1,
    in_annexe: host && sentence ? host.textContent.includes(sentence) : false,
    // an English quotation on a Hebrew sheet keeps its own direction
    dir: loose.length ? loose[0].getAttribute('dir') : '',
    lang: loose.length ? loose[0].getAttribute('lang') : '',
    // ...and the panel's own furniture is in the reader's language
    title: host ? (host.querySelector('h3')?.textContent || '') : '',
    // this legacy document was never traced to a source, and says so
    unattributed: host ? host.textContent.includes('סימוכין') : false,
    // The product notice IS here, and labelled — because the print stylesheet
    // emits only the canvas and structure tabs, so a sheet that cited the BOM
    // tab would be sending a reader to a page the printout does not contain.
    product_inline: !!(note && host && [...host.querySelectorAll('.doc-warnings')]
      .some(g => g.textContent.includes(note.warning.text_raw))),
    product_occurrences: note ? sheet.split(note.warning.text_raw).length - 1 : -1,
  };
})()""")
        check("a document-scoped warning is in the annexe and appears once",
              annexe is not None and annexe["host"]
              and annexe["annexe_entries"] == 1
              and annexe["occurrences"] == 1 and annexe["in_annexe"],
              annexe and f"entries={annexe['annexe_entries']} "
                         f"n={annexe['occurrences']}")
        # The printed plan carries every warning or says so. It used to cite a
        # panel sheet and a BOM tab that the printout does not contain, which put
        # "do not load an uncured footing" on no page that reaches site.
        check("the sheet that goes to site carries the line notices too, labelled",
              annexe is not None and annexe["product_inline"]
              and annexe["product_occurrences"] == 1,
              annexe and f"inline={annexe['product_inline']} "
                         f"n={annexe['product_occurrences']}")
        # The split, in one place: the quotation keeps the language it was
        # published in and the panel around it follows the reader's. Zero of the
        # corpus's elements are Hebrew, so translating a manufacturer's liability
        # sentence would be publishing a claim they never made.
        check("the quotation keeps its own language and the annexe keeps the reader's",
              annexe is not None and annexe["dir"] == "ltr"
              and annexe["lang"] == "en"
              and "נספח" in annexe["title"] and annexe["unattributed"],
              annexe and f"dir={annexe['dir']} title={annexe['title']!r}")
        # scrolled to, because the annexe is the LAST panel on the sheet and a
        # screenshot of the top of the page named after it documents nothing
        c.js("""document.getElementById('structure-annexe')
  ?.scrollIntoView({block: 'center'}); 'ok'""")
        time.sleep(0.4)
        c.shot("11d-structure-annexe.png")
        c.js("window.scrollTo(0, 0); 'ok'")
        # the stations must be the ones the API reports, in order
        stations = c.js("""
[...document.querySelectorAll('#structure-body table')][0]
  ? [...document.querySelectorAll('#structure-body tr[data-element]')]
      .slice(0, 5).map(tr => tr.cells[1].textContent.trim())
  : null""")
        check("stations read as running distances from the section start",
              stations and stations[0] == "0"
              and stations == sorted(stations, key=lambda v: float(v)))
        # a bay says what it is made of, with the cut length and the bar
        parts_text = c.js("""
[...document.querySelectorAll('#structure-body tr[data-element]')]
  .map(tr => tr.textContent).join(' | ')""")
        check("a bay lists its rails with the cut length and the bar",
              "RAIL-3000" in (parts_text or "") and "חתך" in (parts_text or "")
              and "#1" in (parts_text or ""))
        check("consumables are itemised on the installer sheet",
              "SCREW-S10" in (parts_text or "") and "CONC-25" in (parts_text or ""))
        # clicking a row selects that element and explains it
        picked = c.js("""
(() => {
  const row = [...document.querySelectorAll('#structure-body tr[data-element]')]
    .find(tr => tr.dataset.element.startsWith('span@'));
  row.dispatchEvent(new MouseEvent('click', {bubbles: true}));
  return row.dataset.element;
})()""")
        time.sleep(1.2)
        selected = c.js("""
(() => {
  const rows = [...document.querySelectorAll('#structure-body tr.selected')]
    .map(tr => tr.dataset.element);
  const body = document.getElementById('inspector-body').textContent;
  return { rows, body, id: (body.match(/span@[\w:@.-]+/) || [])[0] };
})()""")
        check("clicking a row selects THAT element and explains THAT element",
              selected["rows"] == [picked] and selected["id"] == picked
              and "מפתח" in (selected["body"] or ""))
        # …and that bay is DRAWN, from the report the schedule was built from.
        # `Bay.elevation` rides along on the structure-data cache: a second fetch
        # here would race the one already in flight for this run (that module's
        # in-flight guard exists because a fetch belongs to the run it was
        # STARTED for) and could label one drawing with another's schedule.
        drawn_bay = c.js("""
(() => {
  const host = document.getElementById('structure-elevation');
  const rects = [...host.querySelectorAll('.elev-member')];
  const row = document.querySelector('#structure-body tr.selected');
  return {
    title: host.querySelector('h3')?.textContent || '',
    tag: row ? row.cells[0].textContent.trim() : '',
    rails: rects.filter(r => r.dataset.slot === 'rail').length,
    total: rects.length,
    row_rails: Number(row?.querySelector('.part[data-slot="rail"] .num')?.textContent || 0),
    dir: getComputedStyle(host.querySelector('svg')).direction,
  };
})()""")
        check("the structure tab draws the bay the schedule row selected",
              drawn_bay["tag"] and drawn_bay["tag"] in drawn_bay["title"]
              and drawn_bay["rails"] == drawn_bay["row_rails"] > 0
              and drawn_bay["total"] == drawn_bay["rails"]
              and drawn_bay["dir"] == "ltr")
        c.shot("12-structure-installer.png")
        # the schedule is a document: it must speak both languages and both units
        station_mm = c.js("""
[...document.querySelectorAll('#structure-body tr[data-element]')][1].cells[1].textContent.trim()""")
        c.click(*c.element_center("#btn-units"))
        time.sleep(0.8)
        station_cm = c.js("""
[...document.querySelectorAll('#structure-body tr[data-element]')][1].cells[1].textContent.trim()""")
        check("the schedule follows the display unit",
              float(station_cm) == float(station_mm) / 10)
        header_he = c.js("document.querySelector('#structure-body th').textContent")
        c.click(*c.element_center("#btn-locale"))
        time.sleep(1.0)
        header_en = c.js("document.querySelector('#structure-body th').textContent")
        check("the schedule follows the language",
              header_en != header_he and header_en.strip() == "Tag")
        leftovers = c.js("""
(() => {
  const html = document.getElementById('tab-structure').innerHTML;
  return [...html.matchAll(/\{[a-z_]+\}/g)].map(m => m[0]);
})()""")
        check("no unsubstituted placeholders in the schedule", not leftovers)
        if leftovers:
            print("  leftovers:", leftovers)
        c.click(*c.element_center("#btn-locale"))
        time.sleep(1.0)
        c.click(*c.element_center("#btn-units"))
        time.sleep(0.8)
        # tags on the drawings must be the SAME tags as in the schedule
        tag_match = c.js("""
(() => {
  const row = [...document.querySelectorAll('#structure-body tr[data-element]')]
    .find(tr => tr.dataset.element.startsWith('span@'));
  if (!row) return null;
  const tag = row.cells[0].textContent.trim();
  const id = row.dataset.element;
  document.querySelector('#tabs button[data-tab="canvas"]').click();
  const drawn = [...document.querySelectorAll('#g-overlay text.elem-tag')]
    .map(t => t.textContent);
  const profileTags = [...document.querySelectorAll('#p-result text.elem-tag')]
    .map(t => t.textContent);
  document.querySelector('#tabs button[data-tab="structure"]').click();
  return { tag, id, drawn, profileTags };
})()""")
        check("the plan canvas labels elements with the schedule's tags",
              tag_match and tag_match["tag"] in tag_match["drawn"])
        check("the side view uses the same tags",
              tag_match and tag_match["tag"] in tag_match["profileTags"])
        # the customer sheet describes fixings instead of counting them
        c.js("""
{
  const sel = document.getElementById('structure-detail');
  sel.value = 'customer';
  sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.8)
        customer = c.js("document.getElementById('structure-body').textContent")
        check("the customer sheet names materials but not screw counts",
              "POST-S" in (customer or "") and "SCREW-S10" not in (customer or "")
              and "CONC-25" not in (customer or ""))
        # ...and the annexe is on the CUSTOMER sheet too. The consumables filter
        # exists because a customer is not told a screw count, and a warranty or
        # pool-barrier condition is not a screw count. Contract obligation 10.
        annexe_customer = c.js("""
(() => {
  const host = document.getElementById('structure-annexe');
  if (!host) return null;
  return {job_wide: [...host.querySelectorAll('.doc-warning')]
            .filter(d => !d.closest('.doc-warnings')).length,
          text: host.textContent};
})()""")
        check("the annexe reaches the customer sheet as well as the installer's",
              annexe_customer is not None and annexe_customer["job_wide"] == 1
              and "not a pool barrier" in annexe_customer["text"],
              annexe_customer and annexe_customer["job_wide"])
        c.shot("12-structure-customer.png")
        c.js("""
{
  const sel = document.getElementById('structure-detail');
  sel.value = 'installer';
  sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.5)
        # the printable sheet: drawings AND schedules, no chrome. Chrome can render
        # the print media without printing, so the stylesheet is testable.
        # zoom the plan away from the fence, then print: the sheet must frame it
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.3)
        cx, cy = c.canvas_px(1000, 0)
        c.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=cx, y=cy, deltaX=0, deltaY=600)
        time.sleep(0.4)
        vb_zoomed = c.js("document.getElementById('canvas').getAttribute('viewBox')")
        c.js("document.querySelector('#tabs button[data-tab=\"structure\"]').click(); 'ok'")
        time.sleep(0.5)
        c.click(*c.element_center("#btn-structure-print"))
        time.sleep(0.8)
        vb_printed = c.js("document.getElementById('canvas').getAttribute('viewBox')")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        c.click(*c.element_center("#btn-fit"))
        time.sleep(0.4)
        vb_fit = c.js("document.getElementById('canvas').getAttribute('viewBox')")
        c.js("document.querySelector('#tabs button[data-tab=\"structure\"]').click(); 'ok'")
        time.sleep(0.5)
        check("printing frames the plan on the fence first",
              vb_printed != vb_zoomed and vb_printed == vb_fit)
        c.cmd("Emulation.setEmulatedMedia", media="print")
        time.sleep(0.5)
        printed = c.js("""
(() => {
  const vis = (sel) => { const el = document.querySelector(sel);
    return el ? getComputedStyle(el).display : null; };
  return { header: vis('header'), tabs: vis('nav#tabs'), toolbar: vis('#toolbar'),
           side: vis('.side-col'), canvasTab: vis('#tab-canvas'),
           structureTab: vis('#tab-structure'), canvas: vis('svg#canvas'),
           profile: vis('#profile-svg'), title: vis('.print-title'),
           titleText: document.getElementById('print-title').textContent };
})()""")
        c.shot("13-print-sheet.png")
        c.cmd("Emulation.setEmulatedMedia", media="")
        check("printing drops the chrome",
              printed["header"] == "none" and printed["tabs"] == "none"
              and printed["toolbar"] == "none" and printed["side"] == "none")
        check("the sheet carries both drawings and the schedules",
              printed["canvasTab"] == "block" and printed["structureTab"] == "block"
              and printed["canvas"] not in (None, "none")
              and printed["profile"] not in (None, "none"))
        printed_rows = c.js("""
[...document.querySelectorAll('#structure-body tr[data-element]')]
  .filter(tr => getComputedStyle(tr).display !== 'none').length""")
        printed_tags = c.js("""
[...document.querySelectorAll('#g-overlay text.elem-tag')]
  .filter(t => getComputedStyle(t).display !== 'none').length""")
        check("the schedule's rows survive printing", printed_rows == rows)
        check("the drawing keeps its tags on paper", (printed_tags or 0) > 0)
        check("the sheet has a title block naming the job and when it was printed",
              printed["title"] == "block" and "smoke" in (printed["titleText"] or "")
              and "הודפס" in (printed["titleText"] or ""))
        # The sheet's part rows print `from_bars` — which bar each piece was cut
        # from — and those move with the stock on hand. So two printings of ONE
        # run can carry different cut lists, and under a title block naming only
        # the design they were indistinguishable on paper. Both ids, or the sheet
        # cannot say which yard it belongs to.
        check("the title block names the yard it was cut against, not only the fence",
              "run_" in (printed["titleText"] or "")
              and "sup_" in (printed["titleText"] or ""))
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.3)

        # --- the Assembly tab: the fence standing up, beside one panel ---------
        # The plan looks DOWN and the schedule is a table; neither shows a panel
        # docked between two posts, a footing under one, or a step-down as a
        # fence. Both viewports here are drawn from the SAME structure report the
        # schedule is drawn from, which is what stops them disagreeing.
        c.js("document.querySelector('#tabs button[data-tab=\"assembly\"]').click(); 'ok'")
        time.sleep(1.6)
        macro = c.js("""
(async () => {
  const pid = document.getElementById('project-select').value;
  const runs = await (await fetch(`/api/projects/${pid}/runs`)).json();
  const report = await (await fetch(
    `/api/runs/${runs[runs.length - 1].id}/structure`)).json();
  const stations = report.sections.reduce((n, s) => n + s.setting_out.length, 0);
  const report_members = report.sections.flatMap(s => s.bays)
    .reduce((n, b) => n + (b.elevation?.members?.length || 0), 0);
  const bays = report.sections.reduce((n, s) => n + s.bays.length, 0);
  const gates = report.sections.reduce((n, s) => n + s.gates.length, 0);
  const svg = document.querySelector('#assembly-macro .macro-svg');
  return {
    stations, bays, gates, report_members,
    drawn_posts: svg ? svg.querySelectorAll('.macro-post').length : 0,
    drawn_bays: svg ? svg.querySelectorAll('.macro-bay').length : 0,
    drawn_gates: svg ? svg.querySelectorAll('.macro-gate').length : 0,
    embeds: svg ? svg.querySelectorAll('.macro-embed').length : 0,
    footings: svg ? svg.querySelectorAll('.macro-footing').length : 0,
    members: svg ? svg.querySelectorAll('.macro-member').length : 0,
    dims: svg ? svg.querySelectorAll('.macro-dims text').length : 0,
    micro: document.querySelectorAll('#assembly-micro .elevation-svg').length,
    notes: [...document.querySelectorAll('#assembly-macro .elevation-note')]
      .map(n => n.textContent).join(' '),
  };
})()""")
        # one drawn thing per scheduled thing: a viewport that quietly dropped a
        # post would still look like a fence
        check("the macro view draws every post, bay and gate the schedule lists",
              macro["drawn_posts"] == macro["stations"]
              and macro["drawn_bays"] == macro["bays"]
              and macro["drawn_gates"] == macro["gates"])
        check("posts are drawn in the ground they are set in",
              macro["embeds"] > 0 and macro["footings"] > 0)
        check("a bay is drawn as its own members, not as a grey block",
              macro["members"] == macro["report_members"] and macro["members"] > 0)
        # one width and one height per bay, plus the run total, plus one embed
        # per buried post: "> 0" passed with every branch but one deleted
        check("the macro drawing is dimensioned",
              macro["dims"] >= 2 * macro["bays"] + 1)
        check("the micro viewport assembles a panel beside it", macro["micro"] == 1)
        # every demo post declares `capabilities.face_width_mm`, so the nominal note must
        # NOT be showing — which is what proves the catalog lookup happened at all
        # (the nominal and POST-S's real width are both 80 mm, so the drawing
        # looks identical either way)
        check("posts are drawn at their declared face width, not at a nominal",
              "נומינלי" not in (macro["notes"] or ""))
        c.shot("25-assembly-split.png")

        # selection is SHARED: clicking a bay up there opens it down here. Two
        # viewports that each kept their own idea of "the current bay" is the
        # failure this prevents — and it is invisible until you compare tags.
        picked = c.js("""
(() => {
  const bays = [...document.querySelectorAll('#assembly-macro .macro-bay')];
  const last = bays[bays.length - 1];
  last.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return last.getAttribute('data-element');
})()""")
        time.sleep(0.8)
        micro_head = c.js(
            "document.querySelector('#assembly-micro .summary-line b')?.textContent || ''")
        picked_tag = c.js(f"""
(async () => {{
  const pid = document.getElementById('project-select').value;
  const runs = await (await fetch(`/api/projects/${{pid}}/runs`)).json();
  const report = await (await fetch(
    `/api/runs/${{runs[runs.length - 1].id}}/structure`)).json();
  const bay = report.sections.flatMap(s => s.bays)
    .find(b => b.element_id === {picked!r});
  return bay ? bay.tag : '';
}})()""")
        check("clicking a bay in the macro view assembles THAT bay in the micro view",
              bool(picked_tag) and picked_tag in micro_head)

        # the toggle is a layout change, not a third renderer
        c.js("document.querySelector('#assembly-bar [data-mode=\"micro\"]').click(); 'ok'")
        time.sleep(0.5)
        hidden = c.js("""
({ macro: getComputedStyle(document.getElementById('assembly-macro')).display,
   micro: getComputedStyle(document.getElementById('assembly-micro')).display })""")
        check("the viewport toggle hides the other view",
              hidden["macro"] == "none" and hidden["micro"] != "none")
        c.js("document.querySelector('#assembly-bar [data-mode=\"split\"]').click(); 'ok'")
        time.sleep(0.5)

        # dimensions come off, and the drawing stays
        c.js("""
{ const box = document.getElementById('assembly-dims');
  box.checked = false; box.dispatchEvent(new Event('change')); }""")
        time.sleep(0.6)
        bare = c.js("""
({ dims: document.querySelectorAll('#assembly-macro .macro-dims text').length,
   micro_dims: document.querySelectorAll('#assembly-micro .elev-dim').length,
   posts: document.querySelectorAll('#assembly-macro .macro-post').length,
   members: document.querySelectorAll('#assembly-micro .elev-member').length })""")
        # BOTH viewports: they are one drawing at two scales, and a switch that
        # cleared half the annotations would look broken rather than clean
        check("the dimension layer can be switched off without losing the drawing",
              bare["dims"] == 0 and bare["micro_dims"] == 0
              and bare["posts"] == macro["stations"] and bare["members"] > 0)
        c.js("""
{ const box = document.getElementById('assembly-dims');
  box.checked = true; box.dispatchEvent(new Event('change')); }""")
        time.sleep(0.6)
        c.shot("26-assembly-macro.png")

        # --- the assembly film: the fence going up in build order -------------
        # The one thing on this tab that is not a drawing but a REVEAL of one:
        # footings, then posts, then frame, then infill, then fixings, over
        # rectangles both viewports have already placed. Nothing is moved and
        # nothing is recomputed — which is why every check below reads the
        # OPACITY class (`.anim-pending`) rather than any coordinate.
        #
        # Scoped to #assembly-play and to the .anim-part class it stamps: a
        # check that counted things in the page at large would pass on the
        # strength of the fence being drawn at all, which is the one thing this
        # feature does not do.
        film = c.js("""
({ play: !!document.getElementById('btn-anim-play'),
   scrub: !!document.getElementById('anim-scrub'),
   caption: document.getElementById('anim-stage')?.textContent || '',
   macro_parts: document.querySelectorAll('#assembly-macro .anim-part').length,
   micro_parts: document.querySelectorAll('#assembly-micro .anim-part').length,
   hidden: document.querySelectorAll('#assembly-macro .anim-pending').length
         + document.querySelectorAll('#assembly-micro .anim-pending').length })""")
        check("the assembly tab offers a film of what both viewports have drawn",
              film["play"] and film["scrub"]
              and film["macro_parts"] > 0 and film["micro_parts"] > 0)
        # the resting state is the FINISHED fence: a tab whose drawing starts
        # hidden until somebody presses play is a tab that looks broken
        check("the fence is fully assembled until the film is asked for",
              film["hidden"] == 0 and bool(film["caption"]))

        # Scrubbed rather than watched: the ordering is a property of the film,
        # not of how fast this machine runs, and a check that waited on a clock
        # would be measuring the machine.
        frames = c.js("""
(() => {
  const scrub = document.getElementById('anim-scrub');
  const n = (sel) => document.querySelectorAll(sel).length;
  const out = [];
  for (let p = 0; p <= 1000; p += 25) {
    scrub.value = String(p);
    scrub.dispatchEvent(new Event('input', { bubbles: true }));
    out.push({
      parts: n('#assembly-macro .anim-part') + n('#assembly-micro .anim-part'),
      hidden: n('#assembly-macro .anim-pending') + n('#assembly-micro .anim-pending'),
      footing_wait: n('#assembly-macro .macro-footing.anim-pending'),
      footings: n('#assembly-macro .macro-footing'),
      post_wait: n('#assembly-macro .macro-post-face.anim-pending'),
      posts: n('#assembly-macro .macro-post-face'),
      rail_wait: n('#assembly-macro .macro-member[data-role="rail"].anim-pending'),
      rails: n('#assembly-macro .macro-member[data-role="rail"]'),
      caption: document.getElementById('anim-stage')?.textContent || '',
    });
  }
  return out;
})()""")
        placed = [f["parts"] - f["hidden"] for f in frames]
        check("scrubbing the film only ever adds parts to the drawing",
              placed == sorted(placed) and placed[0] == 0
              and placed[-1] == frames[-1]["parts"] and frames[-1]["parts"] > 20)
        # THE claim, read off the drawing rather than off the schedule: while a
        # footing is still to come no post is standing, and while a post is
        # still to come no rail is up. The `any` clauses are the non-vacuity
        # guard — an implementation that revealed everything at frame 1
        # satisfies every `all` above trivially, and one that revealed each
        # stage in a single jump satisfies the first two.
        #
        # Footings/posts/frame rather than the whole ladder because THIS fence
        # is the default rail model and has no infill: the infill and fixings
        # rungs are pinned in tests/web/test_animate_module.py, where a panel
        # with slats in it costs nothing to construct.
        check("the film builds in order: footings, then posts, then the frame",
              frames[0]["footings"] > 0 and frames[0]["posts"] > 0
              and frames[0]["rails"] > 0
              and all(f["post_wait"] == f["posts"]
                      for f in frames if f["footing_wait"] > 0)
              and all(f["rail_wait"] == f["rails"]
                      for f in frames if f["post_wait"] > 0)
              and any(0 < f["footing_wait"] < f["footings"] for f in frames)
              and any(f["post_wait"] > 0 and f["footing_wait"] == 0 for f in frames)
              and any(f["rail_wait"] > 0 and f["post_wait"] == 0 for f in frames))
        check("the film names the stage it is placing, and it changes",
              len({f["caption"] for f in frames}) >= 3)

        # the clock: play advances it, pause freezes it, and the button says which
        c.js("""
{ const s = document.getElementById('anim-scrub');
  s.value = '0'; s.dispatchEvent(new Event('input', { bubbles: true })); }""")
        idle_label = c.js("document.getElementById('btn-anim-play').textContent")
        c.js("document.getElementById('btn-anim-play').click(); 'ok'")
        time.sleep(0.7)
        playing = c.js("""
({ label: document.getElementById('btn-anim-play').textContent,
   scrub: +document.getElementById('anim-scrub').value,
   hidden: document.querySelectorAll('#assembly-macro .anim-pending').length
         + document.querySelectorAll('#assembly-micro .anim-pending').length })""")
        check("pressing play runs the clock and withholds what is not built yet",
              playing["scrub"] > 0 and playing["hidden"] > 0
              and playing["label"] != idle_label)
        c.js("document.getElementById('btn-anim-play').click(); 'ok'")
        time.sleep(0.15)
        paused_at = c.js("+document.getElementById('anim-scrub').value")
        time.sleep(0.9)
        still = c.js("""
({ scrub: +document.getElementById('anim-scrub').value,
   label: document.getElementById('btn-anim-play').textContent })""")
        check("pause really stops the clock",
              still["scrub"] == paused_at and still["label"] != playing["label"])
        c.shot("28-assembly-film.png")

        # prefers-reduced-motion: no film offered at all, the fence shown
        # finished, and the panel says why — a disabled button reads as broken
        # rather than as respected, and a fence left half-hidden reads as a bug.
        c.cmd("Emulation.setEmulatedMedia",
              features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.4)
        c.js("document.querySelector('#tabs button[data-tab=\"assembly\"]').click(); 'ok'")
        time.sleep(1.6)
        calm = c.js("""
({ play: !!document.getElementById('btn-anim-play'),
   scrub: !!document.getElementById('anim-scrub'),
   note: document.getElementById('anim-reduced')?.textContent || '',
   parts: document.querySelectorAll('#assembly-macro .anim-part').length,
   hidden: document.querySelectorAll('#assembly-macro .anim-pending').length
         + document.querySelectorAll('#assembly-micro .anim-pending').length })""")
        check("a reader who asked for less motion gets the finished fence, and is told why",
              not calm["play"] and not calm["scrub"] and bool(calm["note"])
              and calm["parts"] > 0 and calm["hidden"] == 0)
        c.cmd("Emulation.setEmulatedMedia", features=[])
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.4)
        c.js("document.querySelector('#tabs button[data-tab=\"assembly\"]').click(); 'ok'")
        time.sleep(1.6)
        check("the film comes back when motion is welcome again",
              bool(c.js("!!document.getElementById('btn-anim-play')"))
              and c.js("document.querySelectorAll('#assembly-micro .anim-pending')"
                       ".length") == 0)

        # --- the part drawer, and a what-if that generates nothing ------------
        # Clicking a member asks "what is that made of, what else fits, do we
        # have any" — three documents joined on one sku. And the whole point of
        # the what-if is what it does NOT do: no run is created behind it.
        # not just the COUNT: an implementation that PUT a new revision of the
        # existing run, or re-priced it, keeps the count and changes the answer
        runs_before = c.js("""
(async () => {
  const pid = document.getElementById('project-select').value;
  const runs = await (await fetch(`/api/projects/${pid}/runs`)).json();
  const last = runs[runs.length - 1];
  const bom = await (await fetch(`/api/runs/${last.id}/bom`)).json();
  return { runs: runs.length, last_id: last.id, last_total: bom.bom.total_cents };
})()""")
        c.js("""
{ const m = document.querySelector('#assembly-micro .elev-member');
  m.dispatchEvent(new MouseEvent('click', { bubbles: true })); }""")
        time.sleep(1.4)
        # the cost strip must be showing THIS bay's panel before anything is
        # compared against it — selecting a bay re-prices, and the previous
        # bay's figure under this bay's tag is the defect this waits out
        time.sleep(0.8)
        drawer = c.js("""
({ rows: document.querySelectorAll('#assembly-drawer .drawer-table tr').length,
   chosen: document.querySelectorAll('#assembly-drawer .tag.active').length,
   text: document.getElementById('assembly-drawer')?.textContent || '',
   priced: /\u20aa/.test(document.getElementById('assembly-drawer')?.textContent || '') })""")
        check("clicking a member opens its material & inventory drawer",
              drawer["rows"] >= 2 and drawer["chosen"] == 1 and drawer["priced"])
        # The drawer's price is THIS BAY's, resolved the way the run resolved it
        # — not the model's list price under the default preset. Pinned against
        # the run's own BOM line for that sku, which is the number the drawer
        # would otherwise contradict while calling itself "as generated".
        priced_like_the_run = c.js("""
(async () => {
  const pid = document.getElementById('project-select').value;
  const runs = await (await fetch(`/api/projects/${pid}/runs`)).json();
  const runId = runs[runs.length - 1].id;
  const doc = await (await fetch(`/api/runs/${runId}/bom`)).json();
  const chosen = document.querySelector('#assembly-drawer .drawer-table tr.selected');
  const sku = chosen?.querySelector('.sku')?.textContent || '';
  const line = (doc.bom.lines || []).find(l => l.sku === sku);
  const shown = chosen?.querySelectorAll('td.num')[0]?.textContent || '';
  return { sku, in_bom: !!line, unit: line ? line.unit_price_cents : null, shown };
})()""")
        check("the drawer prices the part the run actually bought",
              priced_like_the_run["in_bom"]
              and str(priced_like_the_run["unit"] // 100)
                  in priced_like_the_run["shown"])
        # the caveat is not optional: stock here cannot reach the next job
        # The other direction of the shared selection, and the headline of the
        # two-viewport design: a member picked in the panel lights up in EVERY
        # bay that carries it, which is the macro question the micro view cannot
        # answer on its own. Verified nowhere until the test review said so.
        spread = c.js("""
(() => {
  const slot = document.querySelector('#assembly-micro .elev-member.selected')
    ?.getAttribute('data-slot');
  const all = [...document.querySelectorAll('#assembly-macro .macro-member')];
  return {
    slot,
    of_that_slot: all.filter(m => m.getAttribute('data-slot') === slot).length,
    lit: all.filter(m => m.classList.contains('selected')).length,
    others_lit: all.filter(m => m.classList.contains('selected')
                            && m.getAttribute('data-slot') !== slot).length,
  };
})()""")
        check("a member picked in the panel lights up in every bay that carries it",
              bool(spread["slot"]) and spread["lit"] == spread["of_that_slot"]
              and spread["lit"] >= macro["bays"] and spread["others_lit"] == 0)

        check("the drawer states the stock scope it is reporting",
              "מחסן" in drawer["text"] or "warehouse" in drawer["text"])
        # the joint section renders for the SELECTED member, or says there is no
        # joint. The demo line lands its rails face to face, so this exercises
        # the honest-negative branch — an empty space where a detail was is not
        # an answer, and the section for a housed member is pinned in node
        # (tests/web/test_joint_module.py) against M-SLAT@v2's channel.
        section = c.js("""
({ box: !!document.getElementById('assembly-sections'),
   figures: document.querySelectorAll('#assembly-sections .joint-figure').length,
   text: document.getElementById('assembly-sections')?.textContent || '' })""")
        check("a selected member either shows its joint in section or says it has none",
              section["box"] and (section["figures"] > 0
                                  or "פנים אל פנים" in section["text"]))
        c.shot("27-assembly-drawer.png")

        # a dimension change re-prices the panel in place — and nothing else
        cost_before = c.js(
            "document.getElementById('assembly-cost')?.textContent || ''")
        c.js("""
{ const f = document.getElementById('assembly-height');
  f.value = '2400'; f.dispatchEvent(new Event('input')); }""")
        time.sleep(1.6)
        after = c.js("""
(async () => {
  const pid = document.getElementById('project-select').value;
  const runs = await (await fetch(`/api/projects/${pid}/runs`)).json();
  const last = runs[runs.length - 1];
  const bom = await (await fetch(`/api/runs/${last.id}/bom`)).json();
  return {
    runs: runs.length,
    last_id: last.id,
    last_total: bom.bom.total_cents,
    cost: document.getElementById('assembly-cost')?.textContent || '',
    badge: document.querySelector('#assembly-micro .tag.medium')?.textContent || '',
    back: !!document.getElementById('btn-as-built'),
    macro_bays: document.querySelectorAll('#assembly-macro .macro-bay').length,
  };
})()""")
        check("a dimension change re-prices the panel in real time",
              after["cost"] != cost_before and "\u20aa" in after["cost"])
        # THE check of this wave: the project rule is that generation stays behind
        # an explicit press, so a live preview must not have fired one
        check("a what-if generates nothing behind the user's back",
              after["runs"] == runs_before["runs"]
              and after["last_id"] == runs_before["last_id"]
              and after["last_total"] == runs_before["last_total"])
        check("a what-if says it is one, and offers the way back",
              bool(after["badge"]) and after["back"])
        check("the macro view is untouched by a panel what-if",
              after["macro_bays"] == macro["bays"])
        c.js("document.getElementById('btn-as-built').click(); 'ok'")
        time.sleep(1.4)
        restored = c.js("""
({ badge: document.querySelector('#assembly-micro .tag.medium')?.textContent || '',
   cost: document.getElementById('assembly-cost')?.textContent || '' })""")
        check("back to as-generated restores the panel that was built",
              not restored["badge"] and restored["cost"] == cost_before)

        # --- stock, net of what this fence already takes ----------------------
        # LAST in this section, because it regenerates: the yard's offcuts are
        # not offcuts available to a change of mind if this run is already
        # cutting from them. The first version of this column read the inventory
        # alone and said "2 offcuts" about a product with one to spare.
        #
        # Remnants rather than whole units, because the part under the drawer is
        # bought by the LENGTH: the cut planner takes offcuts as bins and never
        # touches `full_stock` of a divisible product, so stocking whole bars
        # here would allocate nothing and the check would pass by measuring
        # nothing.
        sku = c.js(
            "document.querySelector('#assembly-drawer .drawer-table tr.selected"
            " .sku')?.textContent || ''")
        c.js(f"""
(async () => {{
  const pid = document.getElementById('project-select').value;
  await fetch(`/api/projects/${{pid}}/inventory`, {{
    method: 'PUT', headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ items: [
      {{ id: 'smoke-off-1', sku: {sku!r}, kind: 'remnant', length_mm: 2600 }},
      {{ id: 'smoke-off-2', sku: {sku!r}, kind: 'remnant', length_mm: 2400 }},
    ] }}),
  }});
  return 'ok';
}})()""")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.4)
        c.click(*c.element_center("#btn-generate"))
        time.sleep(3.0)
        c.js("document.querySelector('#tabs button[data-tab=\"assembly\"]').click(); 'ok'")
        # a new run is a new bay, and opening the drawer before the tab has
        # settled on it just clears the selection again — wait for the drawing,
        # then for the drawer, rather than for the clock
        wait_for(c, "document.querySelectorAll('#assembly-micro .elev-member').length")
        time.sleep(1.2)
        # Clear first, then select. Element ids are deterministic from the
        # topology, so regenerating the SAME fence keeps the member the user had
        # selected — which is right, and means a blind click here toggles it OFF.
        c.js("""
{ const svg = document.querySelector('#assembly-micro .elevation-svg');
  const open = svg.querySelector('.elev-member.selected');
  if (open) open.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  svg.querySelector('.elev-member')
     .dispatchEvent(new MouseEvent('click', { bubbles: true })); }""")
        wait_for(c,
                 "document.querySelectorAll('#assembly-drawer .drawer-table tr').length")
        netted = c.js(f"""
(async () => {{
  const pid = document.getElementById('project-select').value;
  const runs = await (await fetch(`/api/projects/${{pid}}/runs`)).json();
  const doc = await (await fetch(`/api/runs/${{runs[runs.length - 1].id}}/bom`)).json();
  const cut = (doc.bom.allocations || [])
    .filter(a => a.sku === {sku!r} && a.length_used_mm).length;
  const row = [...document.querySelectorAll('#assembly-drawer .drawer-table tr')]
    .find(tr => tr.querySelector('.sku')?.textContent === {sku!r});
  return {{ cut, cell: row?.querySelectorAll('td')[4]?.textContent || '' }};
}})()""")
        # in Hebrew, like the rest of this suite: "none free · +2 offcuts already
        # being cut from" — the offcuts on the shelf are the ones NOT already
        # spoken for by this fence
        check("the drawer reports offcuts net of the ones this fence is cutting from",
              netted["cut"] > 0 and "שכבר נחתכות" in netted["cell"]
              and f"+{netted['cut']}" in netted["cell"]
              and "אין פנוי" in netted["cell"])
        # and put the yard back: offcuts change the cut plan, and a later check
        # reads one. A step that leaves the project different from how it found
        # it makes every check after it depend on this one having run.
        c.js("""
(async () => {
  const pid = document.getElementById('project-select').value;
  await fetch(`/api/projects/${pid}/inventory`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items: [] }),
  });
  return 'ok';
})()""")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.4)
        c.click(*c.element_center("#btn-generate"))
        time.sleep(3.0)

        # --- quotes: snapshot, freeze, accept ---------------------------------
        # save-quote opens an inline label form (no window.prompt anymore)
        c.js("document.querySelector('#tabs button[data-tab=\"bom\"]').click(); 'ok'")
        time.sleep(1.2)
        c.click(*c.element_center("#btn-save-quote"))
        c.js("document.getElementById('quote-label-input').value = 'smoke offer'; 'ok'")
        c.click(*c.element_center("#btn-quote-confirm"))
        time.sleep(1.2)
        quote_rows = c.js("document.querySelectorAll('[data-view-quote]').length")
        check("saved quote appears in the quotes table", (quote_rows or 0) >= 1)
        c.js("document.querySelector('[data-accept-quote]')?.click(); 'ok'")
        time.sleep(1.2)
        accepted = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}/quotes`)
  .then(r => r.json()).then(qs => qs.filter(q => q.status === 'accepted').length)""")
        check("quote accepted via UI", accepted == 1)

        # Currency: every price on this tab is `units.money()`, and the ₪ comes
        # from ONE locale key. The lie this prevents is a half-migrated app —
        # a BOM header in ₪ over a quotes table still totalling in €, which is
        # exactly the shape the five hardcoded formatters had.
        prices = c.js("""
(() => {
  const body = document.getElementById('bom-body');
  const text = body ? body.textContent : '';
  const cells = [...document.querySelectorAll('#bom-body td.num')]
    .map(td => td.textContent.trim()).filter(s => /[\u20aa\u20ac$]/.test(s));
  return {
    nis: (text.match(/\u20aa/g) || []).length,
    other: (text.match(/[\u20ac$\u00a3]/g) || []).length,
    grouped: cells.filter(s => /^-?\u20aa[\\d,]+\\.\\d\\d$/.test(s)).length,
    cells: cells.length,
    // the BOM total's own heading, found by what it says rather than by
    // position: this tab stacks four panels and the totals one is not the first
    total: [...document.querySelectorAll('#bom-body h3')]
      .map(h => h.textContent).find(s => /₪/.test(s)) || '',
  };
})()""")
        # --- and what the DOCUMENT says about a line (item 8, §3.3.5) ---------
        # "On the BOM lines using it, once per line group." A `Bom.line` IS the
        # line group — already pooled per sku across the whole run — which is why
        # this is the surface the contract names for a product-scoped warning.
        # The count is the check: the same notice under three bays' worth of rail
        # rows would be the noise the annexe exists to keep off a plan.
        product_note = c.js("""
(async () => {
  const runs = await (await fetch(
    `/api/projects/${document.getElementById('project-select').value}/runs`)).json();
  const doc = await (await fetch(`/api/runs/${runs[runs.length - 1].id}/bom`)).json();
  const placed = (doc.quoted_warnings || {}).placements || [];
  const note = placed.find(p => p.where === 'product');
  const body = document.getElementById('bom-body');
  const rows = [...body.querySelectorAll('tr.doc-warning-row')];
  const sentence = note ? note.warning.text_raw : '';
  return {
    sku: note ? note.ref : '',
    rows: rows.length,
    occurrences: sentence ? body.textContent.split(sentence).length - 1 : -1,
    // it sits under the row for its own sku and not under another
    after: rows.length === 1
      ? (rows[0].previousElementSibling?.textContent || '').includes(note.ref)
      : false,
    // the ANNEXE is not duplicated here: it belongs to the plan, and the same
    // notice on two screens is how a reader learns to skip both
    annexe_here: !!body.querySelector('.panel.annexe'),
    annexe_exists: placed.some(p => p.where === 'annexe'),
  };
})()""")
        check("a product warning is on its BOM line, once, and the annexe is not",
              product_note is not None and product_note["rows"] == 1
              and product_note["occurrences"] == 1 and product_note["after"]
              and product_note["annexe_exists"]
              and not product_note["annexe_here"],
              product_note and f"rows={product_note['rows']} "
                               f"n={product_note['occurrences']}")
        # --- the BOM, grouped by what caused it -------------------------------
        # `Bom.lines` are flat and sorted by sku, which answers "what do I
        # order" and none of "what does this section need", "what is in this
        # panel", "which choice bought that". The grouped panel is checked for
        # the two things that can go silently wrong: the tags come from
        # structure-data.js (the single tag source), and NO group carries a
        # price — a purchase is pooled across the run, so a per-section figure
        # would be an apportionment nothing measured.
        grouped = c.js("""
(async () => {
  const host = document.getElementById('bom-grouped');
  if (!host) return null;
  const rows = [...host.querySelectorAll('.group-row')];
  // The tags this view has to agree with, taken from the DOCUMENT rather than
  // from the page. Reading them out of the structure tab would only prove the
  // app agrees with itself; `structure-data.js` is the single tag source, so an
  // independent check has to re-derive the mapping the way that module does.
  const runs = await (await fetch(
    `/api/projects/${document.getElementById('project-select').value}/runs`)).json();
  const doc = await (await fetch(
    `/api/runs/${runs[runs.length - 1].id}/structure`)).json();
  const ofElement = new Map(), ofSection = new Map();
  for (const s of doc.sections) {
    ofSection.set(s.run_id, s.tag);
    for (const r of [...s.setting_out, ...s.bays, ...s.gates])
      ofElement.set(r.element_id, r.tag);
  }
  const expected = (id, kind) =>
    kind === 'section' ? ofSection.get(id)
      : kind === 'node' ? ofElement.get(`post@${id}`)
        : ofElement.get(id);
  const num = (s) => Number(String(s).replace(/[^0-9.-]/g, ''));
  return {
    kinds: [...host.querySelectorAll('[data-group-kind]')]
      .map(h => h.dataset.groupKind),
    rows: rows.length,
    money: (host.textContent.match(/[\u20aa\u20ac$]/g) || []).length,
    cells: rows.reduce((n, r) => n + r.querySelectorAll('td').length, 0),
    // what the document calls each row, beside what the row prints. A decision
    // group is named by the sku it chose, not by a tag, so it is not in here.
    named: rows.filter(r => r.dataset.kind !== 'decision').map(r => ({
      kind: r.dataset.kind, id: r.dataset.group,
      want: expected(r.dataset.group, r.dataset.kind) ?? null,
      got: (r.querySelector('.group-head strong')?.textContent || '').trim(),
    })),
    // the QUANTITIES, which nothing at browser level had ever read: per row,
    // one (sku -> summed qty) map taken from the column the reader reads
    qty: rows.map(r => ({
      kind: r.dataset.kind, id: r.dataset.group,
      lines: [...r.querySelectorAll('table tr')].reduce((acc, tr) => {
        const sku = tr.querySelector('td.sku')?.textContent.trim();
        const cells = [...tr.querySelectorAll('td')];
        if (sku) acc[sku] = (acc[sku] || 0) + num(cells[2]?.textContent);
        return acc;
      }, {}),
    })),
  };
})()""")
        check("the BOM is grouped by section, panel and decision",
              grouped is not None
              and {"section", "bay"} <= set(grouped["kinds"] or [])
              and grouped["rows"] > 0 and grouped["cells"] > 0)
        # the tag, not the raw element id: `A/B1` is what the schedule and both
        # drawings call that bay, and a money view calling it
        # `span@run1:0-1500` is a third name for one thing.
        #
        # Asserted against the DOCUMENT's tag for THAT element, rather than
        # against the SHAPE of the printed string. "It does not look like a raw
        # id" is satisfied by printing `A` on every row of the table — one name
        # for four different bays, which is precisely the confusion a single tag
        # source exists to prevent, and it passed. Three different lookups feed
        # this (a section's key is a RUN id, a node's names the post standing
        # there, a bay's is already an element id), and each can be wrong on its
        # own; a row the document cannot name at all must fall back to its own
        # id rather than to a blank cell that reads as "no section".
        wrong = [r for r in grouped["named"] if r["got"] != (r["want"] or r["id"])]
        check("every grouped row prints the tag the document gives that element",
              grouped["named"] and not wrong
              and len({r["want"] for r in grouped["named"] if r["want"]}) > 1,
              wrong[:3] or "one tag for every row")
        check("no group is priced, because a purchase is not per section",
              grouped["money"] == 0)

        # A NUMBER, read out of the column a reader reads. Nothing at any level
        # did that in the browser: the checks above count cells and rows, so a
        # renderer printing the CUT LENGTH where the quantity belongs passed all
        # of them. Cross-checked rather than merely present, because a lone
        # number proves only that a digit reached the page.
        #
        # The property: a bay is a strict SUBSET of its section (a post belongs
        # to no bay), so per sku the bays can never total more than the sections
        # — and a part that lives only in bays must total exactly the same in
        # both. That second half is what fails when one `GroupedLine` object is
        # shared between a bay list and a section list and merged in place, the
        # corruption `report/bom_groups.py` guards with `model_copy`.
        def total(kind, sku):
            return sum(g["lines"].get(sku, 0) for g in grouped["qty"]
                       if g["kind"] == kind)
        bay_skus = sorted({s for g in grouped["qty"] if g["kind"] == "bay"
                           for s in g["lines"]})
        over = [(s, total("bay", s), total("section", s)) for s in bay_skus
                if total("bay", s) > total("section", s)]
        exact = [s for s in bay_skus if 0 < total("bay", s) == total("section", s)]
        check("the quantity column holds quantities, and the bays add up to their section",
              bay_skus and not over and exact,
              over[:3] or f"no bay-only sku among {bay_skus}")

        check("every price on the BOM tab is a ₪ figure, and no other symbol is left",
              (prices["nis"] or 0) > 0 and prices["other"] == 0
              and "\u20aa" in prices["total"])
        check("prices render grouped with two decimals through one formatter",
              prices["cells"] > 0 and prices["grouped"] == prices["cells"])
        c.shot("07-quotes.png")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.3)

        # --- the Panel tab: choose a model, and SEE the panel before generating -
        # The user's complaint this answers: "I don't see an option to see the
        # Panel spec and choose a model before the strategy." `variant` and
        # `preset` had zero hits in the whole frontend, and the only product
        # choice anywhere was the gate kit picker — the model that decides every
        # material, size and structure below it was unreachable from the UI.
        project_id = c.js("document.getElementById('project-select').value")
        c.js("document.querySelector('#tabs button[data-tab=\"panel\"]').click(); 'ok'")
        time.sleep(1.5)
        c.js("""
{
  const sel = document.getElementById('panel-model');
  sel.value = 'M-SLAT'; sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.5)
        slat = c.js("""
(() => {
  const rows = [...document.querySelectorAll('#panel-parts tr[data-slot]')];
  return {
    slots: rows.map(r => r.dataset.slot),
    priced: rows.filter(r => /₪\\d/.test(r.textContent)).length,
    total: document.getElementById('panel-total')?.textContent || '',
    head: document.querySelector('#panel-parts h3')?.textContent || '',
  };
})()""")
        # a picker that shows a name and a price but no parts is a dropdown; the
        # point of the tab is what one panel is MADE of
        # frame, then infill, then fixings — the panel's OWN structure, which is
        # the order `resolve_panel` emits slots in and therefore the order demand
        # asks in. It used to read rail/screw/slat, which was the order supply
        # GROUPING happened to produce; grouping is an internal optimisation and
        # no longer reorders the answer.
        check("the Panel tab prices a parts table for M-SLAT",
              slat["slots"] == ["rail", "slat", "screw"]
              and slat["priced"] == 3 and "M-SLAT@v1" in slat["head"]
              and "₪" in slat["total"])

        # --- and DRAWS it ------------------------------------------------------
        # "See the panel" was this wave's headline and it shipped as a table of
        # numbers: the backend computed a panel elevation that no JS ever read
        # (`grep elevation js/` found only ground profiles). The drawing is the
        # part that makes "the model affects the panel" legible at a glance.
        drawn = c.js("""
(() => {
  const host = document.getElementById('panel-elevation');
  const svg = host?.querySelector('svg');
  const rects = [...(host?.querySelectorAll('.elev-member') || [])];
  const slats = rects.filter(r => r.dataset.slot === 'slat');
  const box = (r) => r.getBoundingClientRect();
  return {
    qty: Object.fromEntries([...document.querySelectorAll('#panel-parts tr[data-slot]')]
      .map(r => [r.dataset.slot, Number(r.cells[2].textContent)])),
    total: rects.length,
    slats: slats.length,
    rails: rects.filter(r => r.dataset.slot === 'rail').length,
    nominal: rects.filter(r => r.classList.contains('elev-nominal')).length,
    dir: svg ? getComputedStyle(svg).direction : '',
    ascending: slats.every((r, i) => i === 0 || box(r).left > box(slats[i - 1]).left),
    spread: slats.length ? Math.round(box(slats.at(-1)).left - box(slats[0]).left) : 0,
    gaps: host?.querySelector('.elev-gaps')?.textContent || '',
    text: host?.textContent || '',
  };
})()""")
        # one rectangle per member the table says is BOUGHT — and screws, which
        # are counted rather than drawn, add none: a dot per screw buries the panel
        check("the Panel tab draws one rectangle per bought member for M-SLAT",
              drawn["slats"] == drawn["qty"]["slat"] == 21
              and drawn["rails"] == drawn["qty"]["rail"] == 2
              and drawn["total"] == drawn["qty"]["slat"] + drawn["qty"]["rail"])
        # the standing rule the plan canvas and the side view already live by.
        # The page is in Hebrew here (the locale toggle is at the end of this
        # run), so this is the RTL case: mirroring the drawing would reverse the
        # slat order against the plan drawn one tab over.
        check("the elevation is never mirrored, with the page in Hebrew RTL",
              drawn["dir"] == "ltr" and drawn["ascending"] and drawn["spread"] > 100)
        # a rail's face height is a nominal this read model invented (the catalog
        # carries no face width): drawn dashed, and SAID to be, or the picture
        # claims a precision nothing measured
        check("the drawing says which face sizes are a nominal, not a measurement",
              drawn["nominal"] == 2 and "מקווקו" in drawn["text"])
        # gaps_mm is a LIST for a reason — the fitted gaps are the number the
        # sphere test measures, and they belong beside the picture of them
        check("the fitted gaps are stated beside the drawing, in the display unit",
              "20 מרווחים" in drawn["gaps"] and 'מ"מ' in drawn["gaps"])

        # the browser check the fence-model spec asked for and nothing implemented
        c.click(*c.element_center("#panel-elevation .elev-member[data-slot='slat']"))
        time.sleep(0.5)
        picked = c.js("""
(() => {
  const lit = [...document.querySelectorAll('#panel-elevation .elev-member.selected')];
  return {
    rows: [...document.querySelectorAll('#panel-parts tr.selected')].map(r => r.dataset.slot),
    slots: [...new Set(lit.map(r => r.dataset.slot))],
    count: lit.length,
  };
})()""")
        check("clicking a drawn member selects its part row",
              picked["rows"] == ["slat"] and picked["slots"] == ["slat"]
              and picked["count"] == 21)
        c.shot("18a-panel-elevation.png")
        # and back the other way — which is the ONLY way to see a rail on a slat
        # panel, because the slats are genuinely in front of it
        c.click(*c.element_center("#panel-parts tr[data-slot='rail']"))
        time.sleep(0.4)
        from_row = c.js("""
(() => {
  const rects = [...document.querySelectorAll('#panel-elevation .elev-member')];
  const lit = rects.filter(r => r.classList.contains('selected'));
  return {
    slots: [...new Set(lit.map(r => r.dataset.slot))],
    rows: [...document.querySelectorAll('#panel-parts tr.selected')].map(r => r.dataset.slot),
    raised: lit.length > 0 && lit.every(r => rects.indexOf(r) >= rects.length - lit.length),
  };
})()""")
        check("selecting a part row lights up its members, raised over the ones in front",
              from_row["slots"] == ["rail"] and from_row["rows"] == ["rail"]
              and from_row["raised"])
        # --- a routed line: the model's OWN post decides the opening ----------
        # The one check that can see W3 end to end. `preview_panel` resolves
        # M-VINYL's post from the bay's height, and the panel is then fitted
        # across the opening between two of them (1500 - 90 = 1410) rather than
        # across the centre-to-centre width. That is the whole difference between
        # nine slats and ten, and no pytest test drives the route AND the drawing.
        c.js("""
{
  const sel = document.getElementById('panel-model');
  sel.value = 'M-VINYL'; sel.dispatchEvent(new Event('change'));
  const w = document.getElementById('panel-width');
  w.value = '1500'; w.dispatchEvent(new Event('input'));
  const h = document.getElementById('panel-height');
  h.value = '1800'; h.dispatchEvent(new Event('input'));
}
'ok'""")
        time.sleep(2.0)
        vinyl = c.js("""
(() => {
  const rows = [...document.querySelectorAll('#panel-parts tr[data-slot]')];
  const rects = [...document.querySelectorAll('#panel-elevation .elev-member')];
  return {
    slots: rows.map(r => r.dataset.slot),
    qty: Object.fromEntries(rows.map(r => [r.dataset.slot, Number(r.cells[2].textContent)])),
    slats: rects.filter(r => r.dataset.slot === 'slat').length,
    warnings: document.querySelectorAll('#tab-panel .warning').length,
    head: document.querySelector('#panel-parts h3')?.textContent || '',
  };
})()""")
        # nine, not ten: ten 150 mm boards need 1500 and the opening is 1410
        check("the routed line is fitted across the opening its own post leaves",
              vinyl["qty"].get("slat") == 9 and vinyl["slats"] == 9
              and "M-VINYL@v1" in vinyl["head"])
        # a board held in a channel top and bottom is not screwed, and the model
        # says so by carrying no fixing rule at all
        check("a channelled panel buys no screws and reports no gap",
              vinyl["slots"] == ["rail", "slat"] and vinyl["warnings"] == 0)
        # --- and how it goes together -----------------------------------------
        # Roadmap Admin 3. M-VINYL is the line where ORDER is the assembly:
        # nothing is screwed, so a board dropped in before its top rail is a
        # board that cannot be dropped in at all. Checked here because only the
        # browser has the model, the resolved panel and the reader's language
        # together.
        steps = c.js("""
(() => {
  const host = document.getElementById('panel-assembly');
  if (!host) return null;
  const li = [...host.querySelectorAll('li.step')];
  return {
    n: li.length,
    kinds: li.map(x => x.dataset.kind),
    keys: li.map(x => x.dataset.step),
    scopes: li.map(x => x.dataset.scope),
    stages: li.map(x => x.dataset.stage),
    order: host.querySelector('[data-order]')?.dataset.order || '',
    unique: host.querySelector('[data-unique]')?.dataset.unique || '',
    text: host.textContent,
    unplaced: host.querySelectorAll('.warning').length,
  };
})()""")
        # The order the model's own PREREQUISITES imply, not the order it prints
        # them in (contract obligation 11): `cure` is authored SECOND and is not
        # here at all, because it is site-scoped. `cap_posts` is last because it
        # says so, not because it is last in the list.
        check("the panel says how it goes together, in order",
              steps is not None
              and steps["keys"] == ["set_posts", "rails", "boards", "cap_posts"]
              and steps["kinds"] == ["assembly"] * 4)
        # Obligation 12, on screen. A sheet is for ONE bay: a `site` step is
        # carried by the payload (asserted below, from the document itself) and
        # drawn by nothing here, and the sheet SAYS it withheld one rather than
        # quietly disagreeing with the model it rendered.
        check("a step about the site is carried and not drawn on a panel sheet",
              steps["scopes"] == ["post", "panel", "panel", "post"]
              and "cure" not in steps["keys"])
        # Obligation 11's real cost, on screen. A numbered list reads as THE
        # order; this one is a linearisation of a partial order — `cure` and
        # `rails` both wait only on `set_posts` — and a fitter planning a crew
        # around a sequence the model never claimed is what saying so prevents.
        check("the sheet admits the order is one of several",
              steps["order"] == "requires" and steps["unique"] == "0"
              and steps["stages"] == ["0", "1", "2", "3"])
        # Asserted POSITIVELY. `unplaced == 0` is the absence of a warning, which
        # is equally absent when the branch that would render it is deleted — a
        # check that passes against the feature removed. What the sheet claims is
        # that its steps fit exactly the panel's parts, so compare the two.
        fitted = c.js("""
(() => {
  const named = (sel) => [...document.querySelectorAll(sel)].map(x => x.textContent.trim());
  return {
    panel: named('#panel-assembly li.step[data-scope="panel"] .sku'),
    bay: named('#panel-assembly li.step[data-scope="post"] .sku'),
    rows: [...document.querySelectorAll('#panel-parts tr[data-slot]')]
      .map(r => r.dataset.slot),
    warned: document.querySelectorAll('#panel-assembly .warning').length,
  };
})()""")
        # Split by SCOPE, because there are now two vocabularies and one owner
        # each. The panel-scoped steps must fit exactly the panel's own parts —
        # unchanged, and still asserted positively, since `warned == 0` is equally
        # true when the branch that renders the warning is deleted.
        check("the steps fit exactly the parts the panel is made of",
              sorted(fitted["panel"]) == sorted(fitted["rows"])
              and len(fitted["panel"]) > 0 and fitted["warned"] == 0)
        # And the half that was prose until now: a post and its cap are elements
        # of the BAY, so they are named by a post-scoped step and appear in no
        # panel parts row. "Set the posts plumb" is data.
        check("an instruction about the posts NAMES them instead of being prose",
              sorted(fitted["bay"]) == ["cap", "post"]
              and not set(fitted["bay"]) & set(fitted["rows"]))
        # Expert prose, in the reader's language rather than through t() —
        # asserted against the MODEL's own `text_i18n` rather than against a word
        # copied out of it. A single word proves too little and breaks too
        # easily: rewording an instruction is the author's prerogative and not a
        # regression, and "השחילו" would equally have matched that sentence
        # rendered under the WRONG step, or one step's text rendered three times.
        # Every authored sentence must appear, and the English of a Hebrew UI
        # must not — which is the actual claim, and the one a `text_i18n[locale]
        # ?? text_i18n.en` fallback silently breaks.
        prose = c.js("""
(async () => {
  const doc = await (await fetch('/api/fence-models/M-VINYL/1')).json();
  const text = document.getElementById('panel-assembly').textContent;
  const all = doc.assembly || [];
  const drawn = all.filter(s => !['run', 'site'].includes(s.scope || 'panel'));
  const held = all.filter(s => ['run', 'site'].includes(s.scope || 'panel'));
  return {
    steps: drawn.length,
    missing: drawn.map(x => (x.text_i18n || {}).he).filter(s => s && !text.includes(s)),
    leaked: all.map(x => (x.text_i18n || {}).en).filter(s => s && text.includes(s)),
    // present-and-unrendered, proved BOTH ways: the document carries it and the
    // sheet does not print it. Either half alone is satisfied by dropping it.
    held: held.length,
    held_drawn: held.map(x => (x.text_i18n || {}).he).filter(s => s && text.includes(s)),
  };
})()""")
        check("every authored instruction is on the sheet, in the reader's language",
              prose is not None and prose["steps"] == 4
              and not prose["missing"] and not prose["leaked"],
              prose and f"missing={len(prose['missing'])} leaked={len(prose['leaked'])}")
        # Obligation 12 as a property of the DOCUMENT and the SHEET together.
        # `held == 1` alone would pass if the sheet drew it; `held_drawn == []`
        # alone would pass if the model had lost the step. Both, or neither
        # proves anything.
        check("a run- or site-scoped step is present in the model and unrendered here",
              prose["held"] == 1 and not prose["held_drawn"],
              prose and f"held={prose['held']} drawn={len(prose['held_drawn'])}")
        # --- and what its DOCUMENT warns, each where §3.3.5 says --------------
        # Only 19.9% of a real guide's warnings are about a step, so the property
        # is a placement rather than a presence: M-VINYL's four warnings must
        # land in four different places off one payload, and the browser is where
        # all four surfaces exist at once.
        quoted = c.js("""
(async () => {
  const doc = await (await fetch('/api/fence-models/M-VINYL/1')).json();
  const ws = doc.warnings || [];
  const of = (k) => ws.find(w => (w.attaches_to || {}).kind === k) || null;
  const steps = [...document.querySelectorAll('#panel-assembly li.step')];
  const annexe = document.getElementById('panel-annexe');
  const parts = document.getElementById('panel-parts');
  const box = of('document'), cure = of('step'), line = of('product');
  const stepText = steps.map(li => li.textContent).join(' ');
  const cureLi = steps.find(li => li.dataset.step === 'cure');
  return {
    authored: ws.length,
    // the safety box previews into the annexe and onto no step
    in_annexe: !!annexe && box ? annexe.textContent.includes(box.text_raw) : false,
    box_on_a_step: box ? stepText.includes(box.text_raw) : true,
    // `cure` is SITE-scoped, so this sheet draws no step for it (obligation
    // 12's present-and-unrendered) — and its warning must still reach the
    // reader, labelled as belonging to a step the sheet does not draw. It is
    // the most safety-relevant sentence in the document; withholding it to keep
    // a surface tidy is the one trade this must not make.
    cure_step_drawn: !!cureLi,
    cure_on_a_step: cure ? steps.some(
      li => li.textContent.includes(cure.text_raw)) : true,
    cure_shown: cure ? document.getElementById('panel-assembly')
      .textContent.includes(cure.text_raw) : false,
    // the product notice is on the parts row for its own slot's sku
    on_line: parts && line ? [...parts.querySelectorAll('tr.doc-warning-row')]
      .filter(tr => tr.textContent.includes(line.text_raw)).length : -1,
    // the publisher's own words, unmapped: CAUTION beside WARNING. `.lexeme`,
    // not `.sku` — the attribution line under each quotation is a `.sku` too
    lexemes: [...document.querySelectorAll('#panel-preview .doc-warning .lexeme')]
      .map(x => x.textContent),
    // an English quotation on a Hebrew page keeps its own direction
    dirs: [...document.querySelectorAll('#panel-preview .doc-warning')]
      .map(x => x.getAttribute('dir')),
    // ...and the author is told this text is quoted and not translated
    quoted_note: !!annexe && annexe.textContent.includes('מצוטט'),
  };
})()""")
        check("each quoted warning previews where it will actually render",
              quoted is not None and quoted["authored"] == 4
              and quoted["in_annexe"] and not quoted["box_on_a_step"]
              and quoted["on_line"] == 1,
              quoted)
        # Found by this suite: `cure` is site-scoped, so the panel sheet draws no
        # step for it and the warning hanging off it rendered NOWHERE — silently,
        # on the surface a fitter reads. Both halves, or neither proves anything:
        # the step is genuinely not drawn AND its warning is on the sheet anyway.
        check("a warning on a step this sheet withholds is still shown, and labelled",
              not quoted["cure_step_drawn"] and not quoted["cure_on_a_step"]
              and quoted["cure_shown"],
              quoted and f"drawn={quoted['cure_step_drawn']} "
                         f"shown={quoted['cure_shown']}")
        # The registry split, visible: the words are the publisher's and the
        # frame around them is the reader's. A `CAUTION` mapped onto this
        # engine's severity enum would be indistinguishable here from a
        # `WARNING`, and the two carry different legal weight.
        # M-VINYL's four sentences: two lead with the publisher's own word, so
        # their badge is suppressed as a duplicate ("WARNING WARNING: ..." is what
        # the first screenshot showed), and two do not, so it is printed. Both
        # branches in one document, which is why the assertion names the set.
        check("the publisher's own words survive and the page does not offer to translate",
              set(quoted["lexemes"]) == {"NOTICE", "IMPORTANT"}
              and set(quoted["dirs"]) == {"ltr"} and quoted["quoted_note"],
              quoted and f"lexemes={quoted['lexemes']} dirs={quoted['dirs']}")
        c.shot("18d-panel-annexe.png")
        c.shot("18c-panel-vinyl.png")

        # --- evidence viewer (frontend design §3): a citation becomes clickable ---
        # `#panel-annexe` just proved it carries the document-scoped CAUTION
        # `quoted` above — the same one M-VINYL authors with a real citation
        # (`DEMO-src-vinyl-1`, fencemodel/demo.py). `gaps.js`/`doc-warnings.js`
        # render every citation as `.evidence-link`; this is the click that
        # `js/evidence.js` promises to turn into an open viewer.
        evidence_link = c.js("""
document.querySelector('#panel-annexe .evidence-link')?.dataset.evidenceId || null""")
        check("the annexe's cited warning renders as a clickable evidence link",
              evidence_link == "DEMO-src-vinyl-1", evidence_link)
        c.click(*c.element_center("#panel-annexe .evidence-link"))
        opened = wait_for(c, """
(() => {
  const overlay = document.querySelector('#evidence-viewer .evidence-overlay');
  if (!overlay) return null;
  return {
    hash: location.hash,
    id_shown: overlay.querySelector('.evidence-head + .meta bdi.sku')?.textContent || '',
  };
})()""")
        check("clicking a citation opens the viewer for the id that was clicked, "
              "and the deep-link hash follows it",
              opened is not None and opened["hash"] == "#evidence=DEMO-src-vinyl-1"
              and opened["id_shown"] == "DEMO-src-vinyl-1", opened)
        # `DEMO-src-vinyl-1` is a demo-only id, deliberately not one of the seven
        # fence-rag records the fixture-backed resolver knows — the honest "not
        # found" state IS the correct answer here, and its appearance proves the
        # click, the batch POST and the re-render all actually completed rather
        # than the panel sitting frozen on "Resolving…" forever. Hebrew is the
        # default locale and the toggle to English does not happen until much
        # later in this run, so the check reads the bundle's OWN Hebrew
        # `evidence.not_found` sentence rather than the English one — the
        # English-locale version of this same claim is asserted at the very
        # end of the suite, against the deep-linked record.
        not_found = wait_for(c, """
(document.querySelector('#evidence-viewer .evidence-overlay')?.textContent || '')
  .includes('לא ניתן היה לפענח')""")
        check("an id outside the fixture renders the honest 'not found' state, "
              "not a blank or frozen panel", bool(not_found))
        c.shot("18e-evidence-viewer-open.png")
        # closing it clears both the panel and the deep-link hash together
        c.click(*c.element_center("#evidence-viewer .evidence-close"))
        time.sleep(0.3)
        closed = c.js("""({
  empty: document.getElementById('evidence-viewer').innerHTML === '',
  hash: location.hash,
})""")
        check("closing the evidence viewer clears the panel and the hash",
              closed["empty"] and closed["hash"] == "", closed)

        # the panel is priced from the model, not from a fixed shape: M-LEGACY's
        # two-slot panel and M-SLAT's three-slot one must not render the same.
        # The bay goes back to the tab's own defaults with it: the display-unit
        # checks below read the width field and the drawing's dimensions, and a
        # size left behind by the block above would have them measuring it.
        c.js("""
{
  const sel = document.getElementById('panel-model');
  sel.value = 'M-LEGACY'; sel.dispatchEvent(new Event('change'));
  const w = document.getElementById('panel-width');
  w.value = '2500'; w.dispatchEvent(new Event('input'));
  const h = document.getElementById('panel-height');
  h.value = '1800'; h.dispatchEvent(new Event('input'));
}
'ok'""")
        time.sleep(1.5)
        legacy = c.js("""
(() => {
  const rows = [...document.querySelectorAll('#panel-parts tr[data-slot]')];
  return {slots: rows.map(r => r.dataset.slot),
          total: document.getElementById('panel-total')?.textContent || ''};
})()""")
        check("switching the model changes the parts and the price",
              legacy["slots"] == ["rail", "screw"]
              and legacy["total"] != slat["total"])
        legacy_drawn = c.js("""
(() => {
  const host = document.getElementById('panel-elevation');
  const rects = [...host.querySelectorAll('.elev-member')];
  return {total: rects.length,
          slats: rects.filter(r => r.dataset.slot === 'slat').length,
          gaps: host.querySelector('.elev-gaps')?.textContent || ''};
})()""")
        # the picture is of THIS model, not a generic fence: a legacy panel is
        # two rails and nothing else, and it fits no gaps to report
        check("switching the model redraws the panel, not only the price",
              legacy_drawn["total"] == 2 and legacy_drawn["slats"] == 0
              and legacy_drawn["gaps"] == "")
        # the panel is a length surface like every other: it reads in the display
        # unit, and the stored/API figures stay int mm
        length_mm = c.js("""
[...document.querySelectorAll('#panel-parts tr[data-slot]')][0].cells[3].textContent.trim()""")
        c.click(*c.element_center("#btn-units"))
        time.sleep(1.5)
        length_cm = c.js("""
[...document.querySelectorAll('#panel-parts tr[data-slot]')][0].cells[3].textContent.trim()""")
        width_field_cm = c.js("document.getElementById('panel-width').value")
        header_cm = c.js("""
[...document.querySelectorAll('#panel-parts th')][3].textContent""")
        check("the panel's lengths and fields read in cm when the unit is cm",
              float(length_cm) == float(length_mm) / 10 and width_field_cm == "250"
              and 'ס"מ' in (header_cm or ""))
        # the drawing is a length surface too — its dimensions are rendered with
        # tu(), so they follow the unit like every other figure on the page
        dims_cm = c.js("""
[...document.querySelectorAll('#panel-elevation .elev-dim-label')].map(t => t.textContent)""")
        check("the drawing's overall dimensions read in the display unit",
              set(dims_cm or []) == {'250 ס"מ', '180 ס"מ'})
        c.shot("18-panel-cm.png")
        c.click(*c.element_center("#btn-units"))   # back to mm
        time.sleep(1)
        # "use for this project" is a NON-topology mutation: it must persist on
        # the project and survive a reload, or the answer to "what is this fence
        # built from" lasts only as long as the tab is open
        c.js("""
{
  const sel = document.getElementById('panel-model');
  sel.value = 'M-SLAT'; sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.2)
        c.click(*c.element_center("#btn-panel-use"))
        time.sleep(1.5)
        c.shot("19-panel-slat.png")
        c.js("location.reload(); 'ok'")
        time.sleep(5)
        c.js("window.confirm = () => true; window.alert = () => {}; undefined")
        c.js(f"""
{{
  const sel = document.getElementById('project-select');
  if (sel.value !== {project_id!r}) {{
    sel.value = {project_id!r}; sel.dispatchEvent(new Event('change'));
  }}
}}
'ok'""")
        time.sleep(2.5)
        stored_model = c.js(f"""
fetch('/api/projects/{project_id}').then(r => r.json())
  .then(p => (p.fence_model || {{}}).model_id || null)""")
        aside = wait_for(
            c, "document.getElementById('model-row')?.textContent || ''")
        check("the project's chosen model persists across a reload",
              stored_model == "M-SLAT")
        # and it is legible from the DRAWING: "what is this fence built from"
        # must not require opening another tab
        check("the canvas aside names the project's model, localized",
              "פאנל שלבים" in aside and "M-SLAT" in aside
              and "Slat panel" not in aside)
        c.shot("20-panel-aside.png")
        # Clearing is the other half of choosing, and it returns this project to
        # the legacy panel — which is what every check after this one was written
        # against, so the model choice must not leak into them.
        c.js("document.querySelector('#tabs button[data-tab=\"panel\"]').click(); 'ok'")
        time.sleep(1.5)
        c.click(*c.element_center("#btn-panel-clear"))
        time.sleep(1.5)
        cleared = c.js(f"""
fetch('/api/projects/{project_id}').then(r => r.json())
  .then(p => p.fence_model === null)""")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.5)
        aside_cleared = c.js("document.getElementById('model-row')?.textContent || ''")
        check("clearing the model returns the project to the legacy panel",
              cleared is True and "M-SLAT" not in aside_cleared)

        # --- zoom / pan / fit --------------------------------------------------
        vb0 = c.js("document.getElementById('canvas').getAttribute('viewBox')")
        cx, cy = c.canvas_px(3000, 0)
        c.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=cx, y=cy,
              deltaX=0, deltaY=-240)
        time.sleep(0.4)
        vb1 = c.js("document.getElementById('canvas').getAttribute('viewBox')")
        check("wheel zooms the canvas viewBox", vb1 != vb0 and bool(vb1))
        c.click(*c.element_center("#btn-fit"))
        time.sleep(0.4)
        vb2 = c.js("document.getElementById('canvas').getAttribute('viewBox')")
        check("fit view reframes the topology", vb2 != vb1 and bool(vb2))
        # grid still covers the view after zoom/fit
        check("grid re-renders for the new view",
              c.js("document.querySelectorAll('#g-grid line').length") > 5)

        # --- rule impact preview (knowledge tab) ------------------------------
        c.js("document.querySelector('#tabs button[data-tab=\"knowledge\"]').click(); 'ok'")
        time.sleep(0.5)
        # the actions JSON textarea became a rule builder — drive its default
        # set_param row (max_span_mm) through the real number input
        c.js("""
document.getElementById('k-object').value = 'K-MAXSPAN';
document.getElementById('k-title').value = 'tighter test';
const row = document.querySelector('#k-action-rows .builder-row');
const num = row.querySelector('input[type="number"]');
num.value = 1400;
num.dispatchEvent(new Event('change'));
'filled'""")
        c.click(*c.element_center("#btn-knowledge-impact"))
        time.sleep(2)
        impact_text = c.js("document.querySelector('#knowledge-impact-out .impact')?.textContent || ''")
        check("impact preview reports affected projects", "1" in (impact_text or ""))
        # preview must persist nothing
        k_versions = c.js("""
fetch('/api/knowledge').then(r => r.json())
  .then(vs => vs.filter(v => v.object_id === 'K-MAXSPAN').length)""")
        check("impact preview persists nothing", k_versions == 1)
        c.shot("06-impact-preview.png")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.3)

        # --- multi-segment anchors (final-review blocker regression) ---------
        # insert a vertex via the midpoint ghost, then place a ground point on
        # the SECOND segment; the stored anchor must be segment-local
        c.click(*c.element_center("#tool-select"))
        c.click(*c.canvas_px(1500, 0))       # select the run
        time.sleep(0.3)
        # Grab the ghost where it actually IS, rather than at the midpoint it
        # marks: the handle is drawn 12 px off its segment so it cannot collide
        # with the post that stands at that midpoint whenever a run divides
        # evenly. A hardcoded midpoint here would drag empty canvas and pan.
        ghost = c.js("""
(() => {
  const e = document.querySelector('#g-handles .ghost');
  if (!e) return null;
  const r = e.getBoundingClientRect();
  return [r.x + r.width / 2, r.y + r.height / 2];
})()""")
        check("the selected section offers a midpoint ghost", ghost is not None)
        if ghost:
            c.drag(ghost[0], ghost[1], *c.canvas_px(3000, 1000))  # ghost -> vertex
        time.sleep(0.5)
        n_vertices = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.topology.runs[0].interior_vertices.length)""")
        check("midpoint ghost inserts an interior vertex", n_vertices == 1)
        c.click(*c.element_center("#tool-ground"))
        c.click(*c.canvas_px(4500, 500))     # on the second segment
        time.sleep(0.4)
        if c.js("!!document.querySelector('.popover')"):
            c.js("document.getElementById('pop-save').click(); 'ok'")
            time.sleep(1)
        anchor = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => {
    const ev = p.topology.runs[0].point_events.find(e => e.payload.kind === 'elevation_sample');
    return ev ? ev.anchor : null;
  })""")
        check("event on segment 2 stores a segment-local anchor",
              bool(anchor) and anchor.get("segment_index") == 1
              and anchor.get("seg_len_at_authoring_mm", 99999) < 4000)

        # --- display units: mm <-> cm (storage stays int mm) -----------------
        label_mm = c.js("document.querySelector('.run-label').textContent")
        run_len = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => {
    const run = p.topology.runs[0];
    const n = (id) => p.topology.nodes.find(x => x.id === id);
    const pts = [n(run.start_node_id), ...run.interior_vertices.map(v => ({x_mm: v[0], y_mm: v[1]})),
                 n(run.end_node_id)];
    let L = 0;
    for (let i = 0; i + 1 < pts.length; i++)
      L += Math.round(Math.hypot(pts[i+1].x_mm - pts[i].x_mm, pts[i+1].y_mm - pts[i].y_mm));
    return L;
  })""")
        check("canvas run label reads in mm by default", str(run_len) in (label_mm or ""))
        c.click(*c.element_center("#btn-units"))
        time.sleep(0.6)
        label_cm = c.js("document.querySelector('.run-label').textContent")
        check("switching to cm re-renders the canvas in cm",
              f"{run_len / 10:g}" in (label_cm or "") and label_cm != label_mm)
        check("unit choice is remembered",
              c.js("localStorage.getItem('fenceai.units')") == "cm")
        # a length typed in cm must be stored as the equivalent int mm
        c.click(*c.element_center("#tool-height"))
        c.click(*c.canvas_px(1500, 500))     # on segment 1 (0,0)->(3000,1000)
        time.sleep(0.5)
        field_cm = c.js("document.getElementById('pop-height')?.value")
        check("popover length fields open in cm", field_cm == "180")
        # every {u} placeholder must have been substituted (t() instead of tu())
        check("no unsubstituted unit placeholders",
              not c.js("document.documentElement.innerHTML.includes('{u}')"))
        events_before = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.topology.runs[0].interval_events.length)""")
        c.js("""
{
  const field = document.getElementById('pop-height');
  if (field) { field.value = ''; field.dispatchEvent(new Event('change'));
               document.getElementById('pop-save').click(); }
}
'ok'""")
        time.sleep(1)
        events_after_blank = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.topology.runs[0].interval_events.length)""")
        check("a blank length field saves nothing (no null reaches the API)",
              events_after_blank == events_before
              and c.js("!!document.querySelector('.popover input.invalid')"))
        c.js("""
{
  const field = document.getElementById('pop-height');
  if (field) {
    field.value = '210'; field.dispatchEvent(new Event('change'));
    document.getElementById('pop-save').click();
  }
}
'ok'""")
        time.sleep(1)
        stored_h = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => {
    const ev = p.topology.runs[0].interval_events.find(e => e.payload.kind === 'height_intent');
    return ev ? ev.payload.height_mm : null;
  })""")
        check("210 cm stores as 2100 mm", stored_h == 2100)
        c.shot("08-units-cm.png")
        # typed draw lengths follow the unit too: in cm mode a bare "90" is 90 cm,
        # NOT 90 metres (the mm-mode "under 100 is metres" shortcut must not apply)
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.element_center("#canvas"))   # anywhere on the canvas: draw places a dot
        time.sleep(0.4)
        drafted = c.js("document.getElementById('g-draft').childNodes.length")
        c.key("9"); c.key("0")
        c.key("Enter")        # places the next dot at exactly the typed length
        c.key("Enter")        # finishes the run
        time.sleep(1.2)
        typed_len = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => {
    const run = p.topology.runs[p.topology.runs.length - 1];
    const n = (id) => p.topology.nodes.find(x => x.id === id);
    const a = n(run.start_node_id), b = n(run.end_node_id);
    return Math.round(Math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm));
  })""")
        check("a bare typed length reads as cm while in cm mode (90 -> 900 mm)",
              (drafted or 0) > 0 and typed_len == 900)
        c.click(*c.element_center("#tool-select"))
        # the BOM follows too: cut plans are lengths, priced per purchase unit
        c.click(*c.element_center("#btn-generate"))
        time.sleep(1.5)
        # the decision trail is server-rendered: it must follow BOTH the language
        # and the unit, with enum values as Hebrew words (not raw "line"/"soil")
        c.js("document.querySelector('#g-overlay circle')"
             ".dispatchEvent(new MouseEvent('click', {bubbles: true})); 'ok'")
        time.sleep(1.2)
        trail = c.js("document.getElementById('inspector-body').textContent")
        check("decision trail renders in the chosen unit", 'ס"מ' in (trail or ""))
        check("decision trail uses Hebrew enum words",
              "קרקע" in (trail or "") and "soil" not in (trail or "")
              and " line" not in (trail or ""))
        c.shot("09-decision-trail-cm.png")
        c.js("document.querySelector('#tabs button[data-tab=\"bom\"]').click(); 'ok'")
        time.sleep(1.5)
        bom_text = c.js("document.getElementById('tab-bom').textContent")
        check("BOM cut plan is labelled in the chosen unit", 'ס"מ' in (bom_text or ""))
        # The priced table says what the job costs; this says what it was costed
        # AGAINST. Without it two totals for one unchanged run are a disagreement
        # nobody on the page can settle. Localized: the objective is prose, so
        # finding the English token here would mean it bypassed t().
        provenance = c.js(
            "document.querySelector('#tab-bom .supply-provenance')?.textContent || ''")
        check("the BOM says which yard and objective it was priced against",
              "sup_" in provenance and "עלות מזערית" in provenance
              and "least_cost" not in provenance)
        # Scoped to the cut-plan panel. Unscoped it read cell 1 of EVERY table on
        # the tab, so it measured whichever table came first — and a new panel
        # whose second column happens to hold a product name ("Rail stock 3000
        # mm") failed it while every cut length was converted correctly. The
        # assertion is unchanged: a relabelled-but-unconverted stock length
        # still reads 3000 and still fails.
        stock = c.js("""
[...document.querySelectorAll('#tab-bom .cut-plan table tr')]
  .map(r => r.cells?.[1]?.textContent || '').join('|')""")
        check("BOM cut-plan lengths are converted, not just relabelled",
              "300" in (stock or "") and "3000" not in (stock or ""))
        # the raw-JSON editors are the STORAGE view: they must stay in mm
        c.js("document.querySelector('#tabs button[data-tab=\"knowledge\"]').click(); 'ok'")
        time.sleep(0.8)
        c.click(*c.element_center("#btn-k-advanced"))
        time.sleep(0.5)
        raw = c.js("document.getElementById('k-actions').value")
        check("raw action JSON stays in millimetres", '"value": 1400' in (raw or ""))
        c.click(*c.element_center("#btn-k-advanced"))
        time.sleep(0.3)
        # A rule's `*_mm` value is persisted DATA, not a view. The param name can
        # be typed freehand, and that box commits without re-rendering its row —
        # the value field must still know it is a length at commit time, or a
        # figure entered in cm is stored as millimetres (10x, silently).
        c.js("""
{
  const row = document.querySelector('#k-action-rows .builder-row');
  const params = row.querySelectorAll('select')[1];
  params.value = '__other';
  params.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.5)
        c.js("""
{
  const row = document.querySelector('#k-action-rows .builder-row');
  const name = row.querySelector('input[type="text"]');
  name.value = 'max_gap_mm';           // now a length — with NO re-render
  name.dispatchEvent(new Event('input'));
  const value = row.querySelector('input[type="number"]');
  value.value = '40';                  // 40 cm
  value.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.5)
        c.click(*c.element_center("#btn-k-advanced"))
        time.sleep(0.5)
        raw2 = c.js("document.getElementById('k-actions').value")
        check("a freehand *_mm rule param stores 40 cm as 400 mm, not 40",
              '"param": "max_gap_mm"' in (raw2 or "") and '"value": 400' in (raw2 or ""))
        c.click(*c.element_center("#btn-k-advanced"))
        time.sleep(0.3)
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.3)
        check("no unit placeholder survives once warnings are rendered",
              not c.js("document.documentElement.innerHTML.includes('{u}')"))
        pid = c.js("document.getElementById('project-select').value")
        c.cmd("Page.navigate", url=f"http://localhost:{PORT}/")
        time.sleep(3)
        # the reload dropped both stubs
        c.js("window.confirm = () => true; window.alert = () => {}; undefined")
        check("the unit preference survives a reload",
              'ס"מ' in (c.js("document.getElementById('btn-units').textContent") or ""))
        # a reload opens the FIRST project in the list — come back to the smoke one
        c.js(f"""
{{
  const sel = document.getElementById('project-select');
  sel.value = {pid!r};
  sel.dispatchEvent(new Event('change'));
}}
'ok'""")
        time.sleep(2)
        c.click(*c.element_center("#btn-units"))   # back to mm for the checks below
        time.sleep(0.6)
        event_row = c.js("""
[...document.querySelectorAll('#run-events .event-row')]
  .map(d => d.textContent).join(' | ')""")
        check("switching back to mm shows the same length in mm",
              "2100" in (event_row or ""))

        # dimension string: chained bay dimensions + one overall per section
        dims = c.js("""
(() => {
  const texts = [...document.querySelectorAll('#p-dims text')];
  return {
    count: document.querySelectorAll('#p-dims line').length,
    labels: texts.map(t => t.textContent),
    starred: texts.filter(t => t.textContent.includes('*')
        && (t.getAttribute('class') || '').includes('profile-dim-label'))
      .map(t => t.getAttribute('class')),
    gates: texts.filter(t => (t.getAttribute('class') || '').includes('gate'))
      .map(t => t.textContent),
  };
})()""")
        check("the side view carries a chained dimension string",
              (dims["count"] or 0) >= 6
              and any('מ"מ' in l for l in dims["labels"]))     # the overall dimension
        check("only a bay closes the chain — never a gate opening",
              dims["starred"]
              and all("closing" in c and "gate" not in c for c in dims["starred"])
              and not any("*" in g for g in dims["gates"]))   # the overall dimension

        # --- side view: scope switch + base-top actions -----------------------
        c.click(*c.element_center("#btn-units"))   # drive this block in cm
        time.sleep(0.6)
        c.js("document.getElementById('profile-scope').value = 'section';"
             "document.getElementById('profile-scope').dispatchEvent(new Event('change'));"
             "'ok'")
        time.sleep(0.8)
        sections_drawn = c.js(
            "new Set([...document.querySelectorAll('.profile-section-label')]"
            ".map(e => e.textContent)).size")
        check("section scope draws exactly one section", sections_drawn == 1)
        check("focused side view gets a taller panel",
              c.js("document.getElementById('profile-svg').clientHeight") > 200)
        # a soil section has no base top to edit — say so, offer nothing
        bar = c.js("document.getElementById('profile-base-bar').textContent")
        check("a soil section explains why there is no base profile",
              "קרקע" in (bar or "") and not c.js("!!document.getElementById('base-height')"))
        # give the section a built base, then drive the four base actions.
        # the picker decides which section the bar edits — pin it explicitly so
        # the checks below read back the very same run
        c.js("""
{
  const sel = document.getElementById('profile-section');
  sel.value = sel.options[0].value;
  sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.8)
        focus_id = c.js("document.getElementById('profile-section').value")
        c.click(*c.element_center("#tool-base"))
        c.click(*c.canvas_px(1500, 500))
        time.sleep(0.5)
        c.js("""
{
  const s = document.getElementById('pop-surface');
  if (s) { s.value = 'masonry_wall'; document.getElementById('pop-save').click(); }
}
'ok'""")
        time.sleep(1.2)
        c.js("""
{
  const h = document.getElementById('base-height');
  h.value = '60';                      // 60 cm, in cm mode
  h.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.2)
        top_points = c.js(f"""
fetch(`/api/projects/${{document.getElementById('project-select').value}}`)
  .then(r => r.json()).then(p => {{
    const run = p.topology.runs.find(r => r.id === {focus_id!r});
    const ev = run.interval_events.find(e => e.payload.kind === 'base_top');
    return ev ? ev.payload.points : null;
  }})""")
        if top_points is None:
            print("  base bar said:", c.js("document.getElementById('profile-base-bar').textContent"))
        check("typing a base height creates the top profile in mm",
              top_points is not None and [p["z_mm"] for p in top_points] == [600, 600])
        c.click(*c.element_center("#base-step"))
        time.sleep(1.2)
        stepped = c.js(f"""
fetch(`/api/projects/${{document.getElementById('project-select').value}}`)
  .then(r => r.json()).then(p => {{
    const run = p.topology.runs.find(r => r.id === {focus_id!r});
    const ev = run.interval_events.find(e => e.payload.kind === 'base_top');
    return ev ? ev.payload.points : null;
  }})""")
        positions = [p["pos_permille"] for p in (stepped or [])]
        check("add-step inserts a real step (two points at one position)",
              positions.count(500) == 2
              and [p["z_mm"] for p in stepped] == [600, 600, 800, 800])
        # the step's rule must SURVIVE the round trip: a vertical riser, then a
        # horizontal tread (new BaseTopPoint.lock field)
        check("a step is stored as a vertical riser then a horizontal tread",
              [p.get("lock") for p in stepped] == [None, "step", "level", None])
        # and the rule sticks: set segment 0 horizontal from the segment popover
        c.js("""
{
  const seg = document.querySelector('.profile-top-hit[data-idx="0"]');
  seg.dispatchEvent(new MouseEvent('click', {bubbles: true}));
}
'ok'""")
        time.sleep(0.6)
        has_popover = c.js("!!document.querySelector('.segment-locks')")
        c.js("""
{
  const b = document.querySelector('.segment-locks [data-lock="level"]');
  if (b) b.click();
}
'ok'""")
        time.sleep(1.2)
        locks = c.js(f"""
fetch(`/api/projects/${{document.getElementById('project-select').value}}`)
  .then(r => r.json()).then(p => {{
    const run = p.topology.runs.find(r => r.id === {focus_id!r});
    const ev = run.interval_events.find(e => e.payload.kind === 'base_top');
    return ev ? ev.payload.points.map(pt => pt.lock ?? null) : null;
  }})""")
        check("clicking a segment sets a rule that persists",
              has_popover and locks is not None and locks[0] == "level")
        c.click(*c.element_center("#base-level"))
        time.sleep(1.2)
        levelled = c.js(f"""
fetch(`/api/projects/${{document.getElementById('project-select').value}}`)
  .then(r => r.json()).then(p => {{
    const run = p.topology.runs.find(r => r.id === {focus_id!r});
    const ev = run.interval_events.find(e => e.payload.kind === 'base_top');
    return ev ? ev.payload.points : null;
  }})""")
        check("horizontal replaces the step with one level elevation",
              levelled is not None
              and len({p["pos_permille"] for p in levelled}) == len(levelled)
              and max(p["z_mm"] for p in levelled) == 800)
        # match-neighbours: the headline complaint ("aligning two sections is
        # hard"). Draw a second section off run1's END node, give it its own
        # base height, then make run1 meet it at the shared corner.
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(6000, 0))      # snaps onto run1's end node
        c.click(*c.canvas_px(6000, 2000))
        c.key("Enter")
        time.sleep(1.2)
        neighbour_id = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => {
    const run1 = p.topology.runs[0];
    const nb = p.topology.runs.find(r => r.id !== run1.id &&
      (r.start_node_id === run1.end_node_id || r.end_node_id === run1.end_node_id));
    return nb ? nb.id : null;
  })""")
        check("the new section shares run1's end node", bool(neighbour_id))
        c.click(*c.element_center("#tool-base"))
        c.click(*c.canvas_px(6000, 1000))   # midpoint of the new section
        time.sleep(0.5)
        c.js("""
{
  const s = document.getElementById('pop-surface');
  if (s) { s.value = 'concrete'; document.getElementById('pop-save').click(); }
}
'ok'""")
        time.sleep(1.2)
        c.js(f"""
{{
  const sel = document.getElementById('profile-section');
  sel.value = {neighbour_id!r};
  sel.dispatchEvent(new Event('change'));
}}
'ok'""")
        time.sleep(0.8)
        c.js("""
{
  const h = document.getElementById('base-height');
  h.value = '40';                      // the neighbour's top: 40 cm
  h.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.2)
        c.js(f"""
{{
  const sel = document.getElementById('profile-section');
  sel.value = {focus_id!r};            // back to run1, whose top is at 80 cm
  sel.dispatchEvent(new Event('change'));
}}
'ok'""")
        time.sleep(0.8)
        # the section is currently held horizontal end to end, so a corner match
        # must be REFUSED rather than silently breaking the rule
        c.click(*c.element_center("#base-match"))
        time.sleep(0.8)
        check("a corner match refuses to break a standing horizontal rule",
              bool(c.js("document.getElementById('base-note').textContent")))
        # free the last segment, then the match applies
        c.js("""
{
  const segs = document.querySelectorAll('.profile-top-hit');
  segs[segs.length - 1].dispatchEvent(new MouseEvent('click', {bubbles: true}));
}
'ok'""")
        time.sleep(0.6)
        c.js("""
{
  const b = document.querySelector('.segment-locks [data-lock=""]');
  if (b) b.click();
}
'ok'""")
        time.sleep(1.2)
        c.click(*c.element_center("#base-match"))
        time.sleep(1.2)
        matched = c.js(f"""
fetch(`/api/projects/${{document.getElementById('project-select').value}}`)
  .then(r => r.json()).then(p => {{
    const run = p.topology.runs.find(r => r.id === {focus_id!r});
    const ev = run.interval_events.find(e => e.payload.kind === 'base_top');
    return ev ? ev.payload.points.map(pt => pt.z_mm) : null;
  }})""")
        check("match-neighbours moves the shared end to the neighbour's top",
              matched is not None and matched[-1] == 400 and matched[0] == 800)
        # the fence STANDS ON the wall: regenerate with the base in place and
        # check the drawn post starts at the wall top, not down at the ground
        c.click(*c.element_center("#btn-generate"))
        time.sleep(1.8)
        stand = c.js("""
(() => {
  const post = document.querySelector('#p-result .profile-post');
  const ground = document.querySelector('#p-ground polyline');
  if (!post || !ground) return null;
  const gy = parseFloat(ground.getAttribute('points').split(' ')[0].split(',')[1]);
  return { bottom: parseFloat(post.getAttribute('y1')),
           top: parseFloat(post.getAttribute('y2')), ground: gy };
})()""")
        check("a post on a wall is drawn standing on the wall top",
              stand is not None and stand["bottom"] < stand["ground"] - 4
              and stand["top"] < stand["bottom"])
        api_post = c.js(f"""
fetch(`/api/projects/${{document.getElementById('project-select').value}}/runs`)
  .then(r => r.json()).then(runs =>
    fetch(`/api/runs/${{runs[runs.length - 1].id}}`).then(r => r.json()))
  .then(res => {{
    const p = res.strategy.posts.find(p => p.run_ref === {focus_id!r});
    return p ? {{ ground: p.ground_z_mm, base: p.base_z_mm }} : null;
  }})""")
        check("the post's standing elevation is the wall top, not the ground",
              api_post is not None and api_post["base"] > api_post["ground"])
        c.element_center("#profile-svg")     # scroll the side view into frame
        c.shot("11-fence-on-wall.png")

        # finish on a stepped profile so the screenshot shows what a step IS now
        c.click(*c.element_center("#base-step"))
        time.sleep(1.2)
        check("segments carrying a rule are drawn differently",
              (c.js("document.querySelectorAll('.profile-top-locked').length") or 0) >= 2)
        c.shot("10-side-view-section.png")
        c.click(*c.element_center("#btn-units"))   # back to mm
        time.sleep(0.6)

        # --- the schedule with SEVERAL sections (it was only ever seen with one)
        c.click(*c.element_center("#btn-generate"))
        time.sleep(1.8)
        c.js("document.querySelector('#tabs button[data-tab=\"structure\"]').click(); 'ok'")
        time.sleep(1.5)
        multi = c.js("""
(() => {
  const cards = [...document.querySelectorAll('#structure-body .structure-section')];
  return {
    count: cards.length,
    tags: cards.map(c => (c.textContent.match(/מקטע (\w+)/) || [])[1]),
    runs: [...new Set([...document.querySelectorAll('#structure-body tr[data-element]')]
      .map(tr => tr.dataset.run))],
  };
})()""")
        check("every section gets its own schedule card",
              multi["count"] >= 3 and multi["tags"][:3] == ["A", "B", "C"]
              and len(multi["runs"]) == multi["count"])
        # a post shared by two sections is set out by BOTH, at each one's own station
        shared = c.js("""
(() => {
  const rows = [...document.querySelectorAll('#structure-body tr[data-element]')]
    .filter(tr => tr.dataset.element.includes('node:'));
  const byId = {};
  for (const r of rows) (byId[r.dataset.element] ||= []).push(r.dataset.run);
  return Object.values(byId).some(runs => new Set(runs).size > 1);
})()""")
        check("a corner post is set out by both sections that share it", bool(shared))
        # a shared corner post carries ONE tag, and both sections say so
        shared_tags = c.js("""
(() => {
  const rows = [...document.querySelectorAll('#structure-body tr[data-element]')]
    .filter(tr => tr.dataset.element.includes('node:'));
  const byId = {};
  for (const r of rows) (byId[r.dataset.element] ||= []).push(r.cells[0].textContent.trim());
  const shared = Object.values(byId).filter(t => t.length > 1);
  return { shared, drawn: [...document.querySelectorAll('#p-result text.elem-tag')]
    .map(t => t.textContent) };
})()""")
        check("a shared post has one tag in both schedules",
              bool(shared_tags["shared"])
              and all(len({t.split(" ")[0] for t in tags}) == 1
                      for tags in shared_tags["shared"]))
        c.shot("14-structure-multi.png")

        # editing the catalog invalidates a stored run's read views the same way
        # editing the drawing does: /structure must refuse (409 catalog_changed)
        # rather than silently reprice against a different catalog (task 10)
        orig_price = c.js("""
(async () => {
  const cat = await (await fetch('/api/catalog')).json();
  const product = cat.products['RAIL-3000'];
  const orig = product.price_cents;
  product.price_cents = 9999;
  await fetch('/api/catalog/products', {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(product),
  });
  return orig;
})()""")
        c.js("""
{
  const sel = document.getElementById('project-select');
  sel.dispatchEvent(new Event('change'));   // reload: re-reads the (now stale) run
}
'ok'""")
        time.sleep(2)
        c.js("document.querySelector('#tabs button[data-tab=\"structure\"]').click(); 'ok'")
        time.sleep(1.5)
        catalog_stale_text = c.js("document.getElementById('structure-body').textContent")
        check("a catalog edit makes the structure tab refuse, not reprice silently",
              "הקטלוג השתנה" in (catalog_stale_text or ""))
        check("a catalog-stale structure leaves no tags on the drawing",
              (c.js("document.querySelectorAll('#g-overlay text.elem-tag').length") or 0) == 0)
        # restore the price — throwaway DB, but keep behaviour predictable for
        # whatever runs later in this session
        c.js(f"""
(async () => {{
  const cat = await (await fetch('/api/catalog')).json();
  const product = cat.products['RAIL-3000'];
  product.price_cents = {orig_price};
  await fetch('/api/catalog/products', {{
    method: 'PUT', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(product),
  }});
  return 'restored';
}})()""")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.3)

        # editing the drawing invalidates the schedule: it must SAY so, never lay
        # the old strategy over the new geometry
        c.js("""
(async () => {
  const pid = document.getElementById('project-select').value;
  const project = await (await fetch(`/api/projects/${pid}`)).json();
  const topo = project.topology;
  topo.nodes[0].x_mm -= 500;               // the drawing moves under the run
  await fetch(`/api/projects/${pid}/topology`, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(topo),
  });
  return 'edited';
})()""")
        time.sleep(1.2)
        c.js("""
{
  const sel = document.getElementById('project-select');
  sel.dispatchEvent(new Event('change'));   // reload: the last run comes back
}
'ok'""")
        time.sleep(3)
        c.js("document.querySelector('#tabs button[data-tab=\"structure\"]').click(); 'ok'")
        time.sleep(1.5)
        time.sleep(1.0)   # let the refetch settle before reading the panel
        stale_text = c.js("document.getElementById('structure-body').textContent")

        print("  overlay tags:",
              c.js("document.querySelectorAll('#g-overlay text.elem-tag').length"))
        check("an edited drawing makes the schedule say so, not invent stations",
              "השרטוט השתנה" in (stale_text or "")
              or "עדיין אין" in (stale_text or ""))
        check("a stale schedule leaves no tags on the drawing",
              (c.js("document.querySelectorAll('#g-overlay text.elem-tag').length") or 0) == 0)
        # ...and the section decisions say the same thing, which is the ONLY
        # place that 409 branch is reachable: node cannot fetch and no other
        # check moves the drawing under a generated run. A section is a topology
        # object, so "the decisions for section A" stops being true here.
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(1.5)
        stale_decisions = c.js(
            "document.getElementById('section-decisions')?.textContent || ''")
        stale_key = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(b => b['decisions.stale'])""")
        check("a moved drawing makes the section decisions say so, not answer anyway",
              bool(stale_key) and stale_key in stale_decisions)
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.3)

        # --- clear topology (draft + persisted, the original bug) ------------
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(1000, 3000))   # start a draft, leave it unfinished
        c.click(*c.element_center("#btn-clear"))
        time.sleep(1)
        draft_left = c.js("document.getElementById('g-draft').childNodes.length")
        n_runs3 = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.topology.runs.length)""")
        check("clear wipes persisted topology", n_runs3 == 0)
        check("clear wipes the draft layer too", draft_left == 0)

        # --- the corner of an L: one answer per pixel (persona-lab B4) --------
        # An L is TWO runs. The readout used to loop runs in array order while
        # the click used SVG paint order, so the second leg's round end-cap
        # swallowed the first leg's last ~200 mm: clicking there recorded the
        # event on the wrong leg, and the first leg's final station could not be
        # reached by any event tool.
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(0, 0))
        c.click(*c.canvas_px(6000, 0))
        c.click(*c.canvas_px(6000, 4000))
        c.key("Enter")
        time.sleep(1.2)
        legs = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.topology.runs.map(r => r.id))""")
        check("an L is drawn as two runs", len(legs or []) == 2)
        first_leg = (legs or [""])[0]
        # 126 mm short of the corner: inside the second leg's painted band, but
        # geometrically on the first leg — and at the corner itself
        stations = []
        for offset in (126, 0):
            c.click(*c.element_center("#tool-gate"))
            # WHOLE pixels: CDP keeps sub-pixel coordinates on mouseMoved but not
            # on mousePressed, and half a pixel is 12 mm on this canvas — the
            # check is about hover vs click, not about CDP's rounding
            x, y = (int(v) for v in c.canvas_px(6000 - offset, 0))
            hover(c, x, y)
            c.click(x, y)
            time.sleep(0.5)
            meta = c.js("document.querySelector('.popover .meta')?.textContent || ''")
            num = c.js("document.querySelector('.popover .meta .num')?.textContent || ''")
            readout = c.js("document.getElementById('statusbar').textContent || ''")
            stations.append((meta, "".join(ch for ch in (num or "") if ch.isdigit()), readout))
            c.js("document.getElementById('pop-cancel')?.click(); 'ok'")
            time.sleep(0.2)
        check("a click by the corner resolves to the leg the pointer is on",
              all(first_leg and first_leg in m for m, _, _ in stations))
        check("the first leg's final station is reachable",
              all(s.isdigit() and int(s) > 5500 for _, s, _ in stations))
        check("the status readout names the station the click records",
              all(st in hov for _, st, hov in stations))

        # --- an auto-focused field is SELECTED, not just focused --------------
        # a caret parked at position 0 of a pre-filled number field turned a
        # typed 1000 into 10000 — ten metres, saveable without a murmur
        c.click(*c.element_center("#tool-gate"))
        c.click(*c.canvas_px(3000, 0))
        time.sleep(0.5)
        prefilled = c.js("document.getElementById('pop-width')?.value")
        type_text(c, "1234")
        check("typing into the auto-focused popover field replaces its value",
              bool(prefilled) and c.js("document.getElementById('pop-width').value") == "1234")
        c.js("document.getElementById('pop-cancel')?.click(); 'ok'")

        # --- the model changes partway along, like base and height do ---------
        # A whole fence is not always one fence. `fence_model` is an interval
        # event on the run, authored through the same popover as height intent,
        # and the generator makes its edges structural boundaries so no bay
        # straddles the place the fence visibly becomes a different fence.
        c.click(*c.element_center("#tool-model"))
        c.click(*c.canvas_px(3000, 0))
        time.sleep(0.6)
        model_options = c.js("""
[...(document.getElementById('pop-model')?.options || [])].map(o => o.value)""")
        check("the model tool offers the published models",
              # exact, not a subset: a model the library publishes and the tool
              # does not offer is unreachable, and one it offers that is not
              # published (M-SLAT@v2 is a draft) is a fence nobody can order
              sorted(model_options or []) == ["M-LEGACY", "M-SLAT", "M-VINYL"])
        c.js("""
{
  document.getElementById('pop-model').value = 'M-SLAT';
  document.getElementById('pop-end').value = '3000';
}
'ok'""")
        c.js("document.getElementById('pop-save').click(); 'saved'")
        time.sleep(1.5)
        model_ev = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => {
    const run = p.topology.runs[0];
    return run.interval_events.filter(e => e.payload.kind === 'fence_model')
      .map(e => e.payload);
  })""")
        check("the model tool writes ONE fence_model interval event",
              len(model_ev or []) == 1 and model_ev[0]["model_id"] == "M-SLAT"
              and model_ev[0]["version_pin"] is None)
        # the stations are read back through the event list, which resolves the
        # segment-local anchor — never by reading anchor.offset_mm as a station
        events_text = c.js("document.getElementById('run-events')?.textContent || ''")
        check("the run's event list names the model event and its stretch, localized",
              "דגם גדר" in events_text and "M-SLAT" in events_text
              and "0–3000" in events_text)
        c.shot("21-model-event.png")

        c.click(*c.element_center("#btn-clear"))
        time.sleep(1)

        # --- a part nothing can supply is SAID, on both money views -----------
        # Two calls a user can make from the catalog and knowledge editors (an
        # 800 mm stock length, and a rail DefaultComponent aiming at it) used to
        # make a saved run permanently unreadable: /bom, /structure and /quote
        # all answered 400 with a raw English sentence out of the cut planner.
        # The structure tab matched none of its known refusal reasons and said
        # "generate a strategy to see how it is laid out" — false, there IS
        # structure — and the BOM tab threw into an unhandled rejection and
        # rendered nothing (which the "no uncaught page errors" check below
        # would have caught, had anything in this suite ever reached the state).
        c.js("""
(async () => {
  await fetch('/api/catalog/products', {method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sku: 'RAIL-SHORT', name: 'Short rail',
      consumption: {kind: 'divisible_linear', purchase_length_mm: 800},
      price_cents: 1000})});
  await fetch('/api/knowledge', {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({object_id: 'K-RAIL-SHORT', type: 'fact',
      title: 'short rail default',
      actions: [{kind: 'default_component', role: 'rail', sku: 'RAIL-SHORT'}]})});
  return 'ok';
})()""")
        c.js("document.getElementById('new-project-name').value = 'unsupplied'; 'ok'")
        c.click(*c.element_center("#btn-new-project"))
        time.sleep(1.5)
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(0, 0))
        c.click(*c.canvas_px(6000, 0))
        c.key("Enter")
        time.sleep(1.2)
        c.click(*c.element_center("#btn-generate"))
        time.sleep(3)
        c.js("document.querySelector('#tabs button[data-tab=\"bom\"]').click(); 'ok'")
        time.sleep(2)
        # EVERY assertion below reads the supply-problems PANEL, never the page.
        # The first version of the bay-naming check read `#structure-body` whole
        # and passed with the panel deleted, because the ordinary bays table
        # prints "A/B1" too — a check that proved the feature was there by
        # finding something else.
        bom_panel = c.js(
            "document.querySelector('#bom-body .supply-problems')?.textContent || ''")
        check("the BOM tab names the part it cannot supply, localized",
              "no_feasible_item" in bom_panel and "RAIL-SHORT" in bom_panel
              and "לספק" in bom_panel)
        check("the BOM tab still prices what it CAN supply beside the gap",
              (c.js("document.querySelectorAll('#bom-body table').length") or 0) >= 2)
        # ...and the PRICED table has to look short too. The problems panel above
        # it was the only place that said anything, so the table a reader prints
        # and adds up looked complete while missing a part, and the total at its
        # head read as the price of the fence rather than the price of the part
        # of it that can be bought.
        priced = c.js("""
(() => {
  const panels = [...document.querySelectorAll('#bom-body .panel')];
  const p = panels.find(x => x.querySelector('tr.unfulfilled'));
  return {
    rows: document.querySelectorAll('#bom-body tr.unfulfilled').length,
    heading: p ? p.querySelector('h3').textContent : '',
    incomplete: !!p && p.classList.contains('incomplete'),
    row: p ? p.querySelector('tr.unfulfilled').textContent : '',
  };
})()""")
        check("the priced BOM carries the line it cannot supply, with no money on it",
              priced["rows"] >= 1 and "מסילה" in priced["row"]
              and "לא סופק" in priced["row"], priced)
        check("the priced total says it excludes the lines nothing supplies",
              priced["incomplete"] and "לא כולל" in priced["heading"], priced)
        c.shot("15-bom-unsupplied.png")
        c.js("document.querySelector('#tabs button[data-tab=\"structure\"]').click(); 'ok'")
        time.sleep(2)
        struct_text = c.js("document.getElementById('structure-body').textContent") or ""
        struct_panel = c.js(
            "document.querySelector('#structure-body .supply-problems')?.textContent || ''")
        check("the structure sheet says the bay cannot be supplied, not 'generate a strategy'",
              "לספק" in struct_panel and "חשבו אסטרטגיה" not in struct_text)
        warning_rows = c.js("""
[...document.querySelectorAll('#structure-body .supply-problems .warning')]
  .map(n => n.textContent).join(' | ')""") or ""
        check("the supply WARNING ROW names the bay, not a raw element id",
              "A/B1" in warning_rows and "span@run" not in warning_rows)
        check("the warning row reads the role as a word, not a raw English id",
              "מסילה" in warning_rows and " rail" not in warning_rows)
        c.shot("16-structure-unsupplied.png")

        # The customer sheet must still SAY a part cannot be supplied. That it
        # describes rather than itemises an unsuppliable CONSUMABLE cannot be
        # checked from here — no UI path makes a screw or concrete unsuppliable
        # (fixings carry no cut length, so the feasibility gate never rejects
        # one), and a check for an absent screw would pass with the filter
        # deleted. tests/web/test_supply_panel_module.py covers that half in node.
        c.js("""
{
  const sel = document.getElementById('structure-detail');
  sel.value = 'customer'; sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1)
        customer_panel = c.js(
            "document.querySelector('#structure-body .supply-problems')?.textContent || ''")
        check("the customer sheet still says a part cannot be supplied",
              "לספק" in customer_panel and "A/B1" in customer_panel)
        c.shot("17-structure-customer-unsupplied.png")
        c.js("""
{
  const sel = document.getElementById('structure-detail');
  sel.value = 'installer'; sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.5)
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.5)

        # --- the Models tab: authoring a fence model ---------------------------
        # The user's complaint this answers: "what if the user wants to edit,
        # change or add a panel? variant?" W1-W3 made models persisted,
        # versioned, selectable data with a working preview, and left the ONLY
        # way to author one a hand-written JSON POST — so the structure that
        # decides every material, size and price below it was editable by
        # everyone except the expert who owns it.
        #
        # The fixture first: a project that USES M-SLAT, because "editing a
        # model's slat gap is a portfolio-wide change" is only demonstrable
        # against a portfolio that has one. M-LEGACY would not do — the
        # compatibility path is SYNTHESIZED per run (generator.py:652) and never
        # read from the library, so editing it changes nothing.
        c.js("document.getElementById('new-project-name').value = 'models'; 'ok'")
        c.click(*c.element_center("#btn-new-project"))
        time.sleep(1.5)
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(0, 0))
        c.click(*c.canvas_px(6000, 0))
        c.key("Enter")
        time.sleep(1.2)
        c.js("document.querySelector('#tabs button[data-tab=\"panel\"]').click(); 'ok'")
        time.sleep(1.5)
        c.js("""
{
  const sel = document.getElementById('panel-model');
  sel.value = 'M-SLAT'; sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.2)
        c.click(*c.element_center("#btn-panel-use"))
        time.sleep(1.5)

        c.js("document.querySelector('#tabs button[data-tab=\"models\"]').click(); 'ok'")
        time.sleep(1.5)
        # "New model" is a gallery of starters now, each card a REAL preview of
        # the panel it opens — a card that only named a structure would be a
        # name, and the point of the gallery is that you can see what you get.
        c.click(*c.element_center("#btn-model-new"))
        time.sleep(4.0)
        gallery = c.js("""
({
  cards: [...document.querySelectorAll('#model-gallery .template-card')]
    .map(b => b.dataset.template),
  drawn: [...document.querySelectorAll('#model-gallery .template-card')]
    .filter(b => b.querySelector('svg .elev-member')).length,
})""")
        check("New model offers starters that are already drawn panels",
              len(gallery["cards"]) >= 5 and "blank" in gallery["cards"]
              and gallery["drawn"] >= 5)
        c.shot("21a-models-gallery.png")
        # this block builds M-SMOKE from nothing, so it takes the blank card
        c.click(*c.element_center('#model-gallery [data-template="blank"]'))
        time.sleep(1.2)
        # name it, then build the smallest publishable panel: one rail slot,
        # cut centre-to-centre, supplied by RAIL-3000
        c.js("""
{
  const id = document.querySelector('#model-head [data-f="id"]');
  id.value = 'M-SMOKE'; id.dispatchEvent(new Event('input'));
  const name = document.querySelector('#model-head [data-f="name"]');
  name.value = 'דגם בדיקה'; name.dispatchEvent(new Event('input'));
}
'ok'""")
        time.sleep(1.0)
        c.click(*c.element_center("#btn-model-add-slot"))
        time.sleep(1.0)
        # adding an element SELECTS it, so the inspector is already pointed at
        # the thing that was just made — the fields below are its own
        # The key stopped being a field: an element is CALLED "Rail" and the
        # schema key is generated. Renaming is a mode behind a double-click on
        # the chip, so the suite reaches it the way a person does.
        chip = c.element_center('#model-elements [data-element^="frame:"]')
        c.dblclick(*chip)
        time.sleep(0.5)
        c.js("""
{
  const key = document.querySelector('#model-elements [data-f="key"]');
  key.value = 'rail';
  key.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
}
'ok'""")
        time.sleep(1.0)
        # ... and the length rule is DEFERRED BEHIND ADVANCED, not deleted — so
        # the suite has to open it the way a person does. Reaching straight for
        # the control would pass whether it was deferred or deleted, which is the
        # distinction this whole change turns on.
        # DEFERRED, not deleted — and the difference has to be asserted
        # structurally. A closed <details> keeps its children queryable, and
        # this Chrome still reports a laid-out box for content it is hiding
        # (verified against a freshly-built control <details> on the same page),
        # so neither "is it in the DOM" nor "does it have a height" can tell the
        # two apart. What CAN: the control lives inside the disclosure, and the
        # disclosure starts shut.
        deferred = c.js("""
{
  const rule = document.querySelector('#model-inspector [data-f="length_rule"]');
  const box = rule && rule.closest('details.inspect-advanced');
  const shut = box ? box.open === false : null;
  if (box) box.open = true;
  ({rule: !!rule, inside_advanced: !!box, starts_shut: shut});
}""")
        check("the length rule is deferred behind Advanced, not deleted",
              deferred["rule"] and deferred["inside_advanced"]
              and deferred["starts_shut"] is True)
        time.sleep(0.6)
        # ... and it is populated from the BACKEND, not from a list in the JS.
        # The editor used to carry its own array of length rules and fixing
        # bases, pinned to the schema by a test that a person had to notice. Now
        # `GET /api/vocabularies` answers, and this is the only check that can
        # see the whole path — module, request, route, schema — with a real
        # browser doing the fetching. A stale hardcoded fallback reintroduced
        # "just in case" would still render a working select in every unit test;
        # it shows up here as options the server does not offer.
        #
        # `between_frame` is excluded on a FRAME slot on purpose (it is the one
        # rule that reads a member's base/top refs, which a slot has none of), so
        # the expected set is the served vocabulary minus that one — narrowing a
        # served list is allowed, inventing one is not.
        served = json.loads(urllib.request.urlopen(
            f"http://localhost:{PORT}/api/vocabularies", timeout=5).read())
        rule_select = c.js("""
{
  const rule = document.querySelector('#model-inspector [data-f="length_rule"]');
  ({options: [...rule.options].map((o) => o.value).filter((v) => v !== ""),
    disabled: rule.disabled});
}""")
        check("the length rule select is populated from /api/vocabularies",
              rule_select["disabled"] is False
              and rule_select["options"]
              == [r for r in served["length_rules"] if r != "between_frame"],
              (rule_select, served["length_rules"]))
        c.js("""
{
  const rule = document.querySelector('#model-inspector [data-f="length_rule"]');
  rule.value = 'centre_to_centre'; rule.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.0)
        # THE hole this arc repairs: a fresh slot names no part
        # (`eligibilitySource` reads "unspecified"), so the pane offers the part
        # picker, not the members list — `add-eligible` only renders once a slot
        # already authors a SKU list (`authored_members`), which naming a part is
        # never allowed to do alongside (`_part_or_authored` refuses the pair).
        # This step used to click `add-eligible` and hand the row a bare SKU; it
        # now names the part the demo catalog built FOR this exact SKU
        # (`rail-rail-3000`, `parts/demo.py`) through the control the repair
        # actually ships.
        c.js("""
{
  const sel = document.querySelector('#model-inspector [data-f="part"]');
  sel.value = 'rail-rail-3000'; sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.0)
        # NOTHING is written until Save is pressed: the preview prices the
        # document in the body, so an editor that is being typed into does not
        # mint library rows — least of all one per character of a model id.
        before_save = c.js("""
fetch('/api/fence-models').then(r => r.json()).then(l => l.map(x => x.id).join(','))""") or ""
        check("editing writes nothing until the author asks",
              "M-SMOKE" not in before_save and "M-NEW" not in before_save)
        priced_unsaved = c.js(
            "document.getElementById('model-preview-total')?.textContent || ''")
        check("an unsaved model is priced anyway",
              "₪" in priced_unsaved and priced_unsaved.strip() != "")
        c.shot("21-models-canvas.png")
        c.click(*c.element_center("#btn-model-publish"))
        time.sleep(2.5)
        smoke_row = c.js("""
fetch('/api/fence-models').then(r => r.json())
  .then(l => l.find(x => x.id === 'M-SMOKE') || null)""")
        # Read the STORED SPEC, not just the listing metadata. An empty model
        # publishes perfectly well (`validate_model` requires no slots), so a
        # check on `active_version` alone passes with every row-level write in
        # this block silently doing nothing — the "found something else" trap
        # this suite has been caught by before.
        stored = c.js("""
fetch('/api/fence-models/M-SMOKE/1').then(r => r.json()).then(m => {
  const slot = (m.default_spec.frame || [])[0];
  return slot ? {key: slot.key, rule: slot.requirement.length_rule,
                 part_id: slot.requirement.part_id} : null;
})""")
        check("a model authored from the rows publishes, with the rows in it",
              bool(smoke_row) and smoke_row["active_version"] == 1
              and smoke_row["status"] == "active"
              and stored and stored["key"] == "rail"
              and stored["rule"] == "centre_to_centre"
              and stored["part_id"] == "rail-rail-3000")
        # publishing changes which models are SELECTABLE, and the picker's
        # listing is a cache — without an invalidation it keeps the old library
        c.js("document.querySelector('#tabs button[data-tab=\"panel\"]').click(); 'ok'")
        time.sleep(1.5)
        picker_options = c.js("""
[...document.querySelectorAll('#panel-model option')]
  .map(o => o.value + (o.disabled ? ':disabled' : '')).join(',')""") or ""
        check("a model published one tab over is offered by the Panel picker",
              "M-SMOKE" in picker_options and "M-SMOKE:disabled" not in picker_options)
        c.js("document.querySelector('#tabs button[data-tab=\"models\"]').click(); 'ok'")
        time.sleep(1.2)

        # --- editing a published version never touches it ----------------------
        # A run stamps (id, version, content hash) and an accepted quote was
        # priced against that document. "Edit" therefore opens a COPY, and the
        # first save lands it at the next free version.
        c.js("""
document.querySelector('#model-list [data-model="M-SMOKE"] [data-act="edit"]').click();
'ok'""")
        time.sleep(1.5)

        # --- the slot inspector saves what it shows ----------------------------
        # THE hole this arc repairs. The suite has always opened this tab and
        # left again, so a slot pane that showed "no product" for every slot and
        # refused the save that would fix it passed 183 checks. A tab that is
        # opened and not used is not covered.
        # `data-slot` is written by elevation.js (`:369`, `:386`, `:417`) on
        # every drawn member and read back by the canvas' own click handler
        # (`elevation.js:442`, mirrored in `panel-canvas.js:120` for the Panel
        # tab's canvas). Scoped to `#model-canvas` — unscoped it can also match
        # a row `structure.js`/`panel.js` left in the DOM for a tab that is
        # merely hidden, not gone, from an earlier step of this same run.
        wait_for(c, "document.querySelectorAll('#model-canvas [data-slot]').length")
        c.js("""
document.querySelector('#model-canvas [data-slot]')?.dispatchEvent(
  new MouseEvent('click', { bubbles: true })); 'ok'""")
        part_shown = wait_for(
            c, "document.querySelector('#model-inspector [data-f=\"part\"]')?.value || ''")
        check("a slot pane names the part the slot names", bool(part_shown))

        chips = c.js(
            "document.querySelectorAll('#model-inspector [data-chip]').length")
        check("the part's spec is shown beside its name", (chips or 0) > 0)

        candidates = c.js(
            "document.querySelector('#model-inspector [data-candidates]')"
            "?.textContent || ''")
        check("the slot says how many products can fill it",
              any(ch.isdigit() for ch in candidates))

        # and the save that used to be refused. `rail-rail-3000-40` is named
        # rather than "the first other option" on purpose: the picker lists
        # every part in the library ungated by the slot's own kind
        # (`partSelect`, `panel-inspector.js`), so an unfiltered pick could just
        # as easily hand this FRAME slot an infill part. Both it and
        # `rail-rail-3000` are permanently seeded (`parts/demo.py`), so there is
        # always an alternative and "nothing to do" is never an answer here.
        #
        # THE STORED DOCUMENT IS WHAT IS ASSERTED, and that is the whole point of
        # the check. `saveDraft` (`model-editor.js`) copies back only
        # version/status/invalid — `session.model` stays the object this script
        # itself mutated — so reading the select back after the save answers "did
        # the JS keep what I typed", which it does whether the PUT returned 200 or
        # 422. That is the shape of green this arc exists to remove, and it is
        # what this check used to be. So: name the part, save, and GET the draft
        # back off the server.
        #
        # The diff is taken over every `part_id` in the document rather than over
        # one slot, because which slot the canvas click selected is the canvas'
        # answer and not this script's — so the assertion is the exact one that
        # matters: ONE slot changed, from what it named to what was chosen.
        #
        # Reverted at the end so the rest of the run sees the model it expects.
        # (The publish refusal two blocks down does NOT depend on it: both parts
        # declare `sku among ['RAIL-3000']`, so that refusal holds either way.)
        saved = c.js("""
(async () => {
  const q = () => document.querySelector('#model-inspector [data-f="part"]');
  const before = q()?.value;
  const alt = 'rail-rail-3000-40';
  if (!before) return 'no-part-selected';
  if (![...q().options].some((o) => o.value === alt)) return 'alt-not-offered';
  if (before === alt) return 'already-the-alternative';

  const save = async () => {
    document.getElementById('btn-model-save')?.click();
    await new Promise((r) => setTimeout(r, 1600));
  };
  // every part_id the STORED draft names, in document order
  const storedPartIds = async () => {
    const rows = await (await fetch('/api/fence-models')).json();
    const v = rows.find((m) => m.id === 'M-SMOKE')?.draft_version;
    if (!v) return null;
    const doc = await (await fetch(`/api/fence-models/M-SMOKE/${v}`)).json();
    const out = [];
    (function walk(node) {
      if (Array.isArray(node)) return node.forEach(walk);
      if (node && typeof node === 'object') {
        if (typeof node.part_id === 'string') out.push(node.part_id);
        Object.values(node).forEach(walk);
      }
    })(doc);
    return out;
  };
  const changes = (a, b) => (a && b && a.length === b.length)
    ? a.map((v, i) => [i, v, b[i]]).filter(([, v, w]) => v !== w) : null;

  await save();                       // materialise the draft as it stands
  const base = await storedPartIds();
  if (!base) return 'no-draft-stored';

  const pick = async (value) => {
    const sel = q();
    if (!sel) return false;           // the save re-rendered the pane away
    sel.value = value;
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    await save();
    return true;
  };

  if (!await pick(alt)) return 'pane-gone-before-the-change';
  const changed = changes(base, await storedPartIds());
  if (!await pick(before)) return 'pane-gone-before-the-revert';
  const reverted = changes(base, await storedPartIds());

  if (!changed || changed.length !== 1)
    return `stored ${JSON.stringify(changed)} instead of one change`;
  if (changed[0][1] !== before || changed[0][2] !== alt)
    return `stored ${changed[0][1]} -> ${changed[0][2]}`;
  if (!reverted || reverted.length !== 0)
    return `revert left ${JSON.stringify(reverted)}`;
  return 'stored';
})()""")
        check("changing a slot's part is STORED, and reads back off the server",
              saved == "stored", saved)

        # The Advanced-JSON escape hatch, exercised with BROKEN json, because
        # the rule is that the exit is never gated on the thing that is broken
        # (`tabs.js:93-95`, learned when the rule editor trapped users behind a
        # stray comma). `window.confirm` is stubbed true at the top of this run.
        c.click(*c.element_center("#btn-model-advanced"))
        time.sleep(0.6)
        c.js("""
{
  const ta = document.getElementById('model-json');
  ta.value = '{"id": "M-SMOKE", oops';
}
'ok'""")
        c.click(*c.element_center("#btn-model-advanced"))
        time.sleep(1.0)
        escaped = c.js("""
({
  editor_shown: !document.getElementById('model-editor').hidden,
  json_hidden: document.getElementById('model-json').hidden,
  rows: document.querySelectorAll('#model-elements .element-chip').length,
})""")
        check("the Advanced-JSON exit is never gated on the JSON being valid",
              escaped["editor_shown"] is True and escaped["json_hidden"] is True
              and escaped["rows"] >= 1)

        # A length surface reads and writes in the DISPLAY unit while storage
        # stays int mm. Typing 25 in cm must store 250, not 25 — the 10x bug
        # this suite already pins for a freehand knowledge param.
        c.click(*c.element_center("#btn-units"))
        time.sleep(1.2)
        c.js("""
{
  document.getElementById('btn-model-toggle-infill').click();
}
'ok'""")
        time.sleep(0.8)
        c.js("""
{
  const w = document.querySelector('#model-inspector [data-f="width_mm"]');
  w.value = '25'; w.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.8)
        c.click(*c.element_center("#btn-model-save"))
        time.sleep(2.0)
        cm_width = c.js("""
fetch('/api/fence-models/M-SMOKE/2').then(r => r.json())
  .then(m => m.default_spec.infill.pattern[0].width_mm)""")
        cm_field = c.js("""
document.querySelector('#model-inspector [data-f="width_mm"]')?.value""")
        check("a length typed in cm is stored as millimetres and reads back in cm",
              cm_width == 250 and str(cm_field) == "25")
        c.click(*c.element_center("#btn-units"))    # back to mm for what follows
        time.sleep(1.2)
        # and remove the infill again, so the invalid-publish check below fails
        # for the ONE reason it names
        c.js("document.getElementById('btn-model-toggle-infill').click(); 'ok'")
        time.sleep(0.8)
        # drop the length rule while a DIVISIBLE product supplies the slot: the
        # slot would be neither cut nor priced, which validate_model refuses
        c.js("""
document.querySelector('#model-elements [data-element="frame:rail"]').click(); 'ok'""")
        time.sleep(1.0)
        c.js("""
{
  const rule = document.querySelector('#model-inspector [data-f="length_rule"]');
  rule.value = ''; rule.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.8)
        c.click(*c.element_center("#btn-model-save"))
        time.sleep(2.0)
        after_edit = c.js("""
Promise.all([
  fetch('/api/fence-models').then(r => r.json()),
  fetch('/api/fence-models/M-SMOKE/1').then(r => r.json()),
]).then(([listing, v1]) => ({
  row: listing.find(x => x.id === 'M-SMOKE'),
  v1_rule: v1.default_spec.frame[0].requirement.length_rule,
  v1_status: v1.status,
}))""")
        check("editing a published model opens a NEW draft version and leaves v1 alone",
              after_edit["row"]["draft_version"] == 2
              and after_edit["row"]["active_version"] == 1
              and after_edit["v1_rule"] == "centre_to_centre"
              and after_edit["v1_status"] == "active")

        # --- the publish gate refuses, in Hebrew, and publishes nothing --------
        # A draft may be SAVED invalid — authoring is iterative and a save that
        # refuses until the whole panel is coherent is a save nobody can use.
        # Publish is the gate, and its 422 carries code + params so the refusal
        # is a Hebrew sentence rather than the engine's English authoring text.
        c.click(*c.element_center("#btn-model-publish"))
        time.sleep(2.5)
        refusal = c.js("document.getElementById('model-errors')?.textContent || ''")
        still = c.js("""
fetch('/api/fence-models').then(r => r.json())
  .then(l => l.find(x => x.id === 'M-SMOKE'))""")
        check("publishing an invalid model is refused in Hebrew and publishes nothing",
              "לא פורסם" in refusal and "RAIL-3000" in refusal
              and still["active_version"] == 1 and still["draft_version"] == 2)
        c.shot("22-models-publish-refused.png")

        # --- a model edit is priced, and its portfolio impact shown BEFORE it --
        # Foundation §11: a portfolio-wide change is exposed before it is made.
        # Editing M-SLAT's slat gap is exactly that — it re-fits every bay of
        # every project built to it.
        # what the library says about M-SLAT BEFORE the editor is opened: the
        # property is "nothing was stored", and pinning it to a literal version
        # made it a property of the seed instead (M-SLAT gained a v2 draft when
        # joint geometry landed, and this check failed for a reason that had
        # nothing to do with what it is about)
        slat_before = c.js("""
fetch('/api/fence-models').then(r => r.json())
  .then(l => l.find(x => x.id === 'M-SLAT'))""")
        c.js("""
document.querySelector('#model-list [data-model="M-SLAT"] [data-act="edit"]').click();
'ok'""")
        time.sleep(1.5)
        c.js("""
document.querySelector('#model-elements [data-element="infill:slat"]').click(); 'ok'""")
        time.sleep(1.0)
        c.js("""
{
  const gap = document.querySelector('#model-inspector [data-f="gap_after_mm"]');
  gap.value = '60'; gap.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(2.0)      # the debounced re-price
        total_60 = c.js(
            "document.getElementById('model-preview-total')?.textContent || ''")
        slats_60 = c.js("""
document.querySelector('#model-parts tr[data-slot="slat"] td:nth-child(3)')
  ?.textContent.trim() || ''""")
        c.click(*c.element_center("#btn-model-impact"))
        time.sleep(5)
        impact_text = c.js(
            "document.getElementById('model-impact-out')?.textContent || ''")
        impact_rows = c.js(
            "document.querySelectorAll('#model-impact-out .impact-row').length") or 0
        slat_row = c.js("""
fetch('/api/fence-models').then(r => r.json())
  .then(l => l.find(x => x.id === 'M-SLAT'))""")
        # BEFORE it is made, and before it is even stored: the impact is asked of
        # the document in the editor, so M-SLAT must still be untouched at v1
        # with no draft version at all.
        check("the impact of a model edit is reported before it is published",
              impact_rows >= 1 and "models" in impact_text
              and "אף פרויקט לא ישתנה" not in impact_text
              and slat_row["active_version"] == slat_before["active_version"]
              and slat_row["draft_version"] == slat_before["draft_version"])
        c.shot("23-models-impact.png")

        # --- the preview beside the editor follows the spec --------------------
        # A preview that does not move when the spec does is worse than none: it
        # is a priced picture of a panel the author is no longer editing. 100 mm
        # slats at a 300 mm gap fit far fewer times across the same bay.
        c.js("""
{
  const gap = document.querySelector('#model-inspector [data-f="gap_after_mm"]');
  gap.value = '300'; gap.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(2.5)
        total_300 = c.js(
            "document.getElementById('model-preview-total')?.textContent || ''")
        slats_300 = c.js("""
document.querySelector('#model-parts tr[data-slot="slat"] td:nth-child(3)')
  ?.textContent.trim() || ''""")
        # "it changed" is not the claim — a re-render changes a string. The
        # claim is arithmetic: a wider gap fits FEWER slats across the same bay.
        check("the live preview re-prices the panel when a spec field changes",
              "₪" in total_60 and "₪" in total_300 and total_60 != total_300
              and slats_60.isdigit() and slats_300.isdigit()
              and int(slats_60) > int(slats_300) > 0)
        c.shot("24-models-preview.png")

        # --- the canvas: the drawing IS the editor ----------------------------
        # Everything above drove the inspector. What the canvas claims on top of
        # that is that the DRAWING can be edited directly — and, crucially, that
        # it is a VIEW over the same model rather than a second answer to what a
        # panel is. Driven on a starter, because a starter arrives already drawn.
        c.click(*c.element_center("#btn-model-close"))
        time.sleep(0.8)
        c.click(*c.element_center("#btn-model-new"))
        time.sleep(4.0)
        c.click(*c.element_center('#model-gallery [data-template="slat"]'))
        time.sleep(3.0)
        drawn = c.js("""
({
  members: document.querySelectorAll('#model-canvas .elev-member').length,
  dots: document.querySelectorAll('#model-canvas .elev-fixing').length,
  handles: [...document.querySelectorAll('#model-canvas [data-handle]')]
    .map(h => h.dataset.handle),
})""")
        # A diagram that is PRESENT and 0x0 is the failure no DOM assertion sees:
        # `document.createElement("svg")` builds an HTMLUnknownElement, which
        # takes its CSS, reports a computed width, holds its children — and
        # paints nothing. Only a laid-out box can tell the two apart, so the
        # check is a rectangle rather than a selector.
        c.js("""
document.querySelector('#model-elements [data-element^="fixing:"]').click(); 'ok'""")
        time.sleep(1.2)
        diagram = c.js("""
{
  const d = document.querySelector('#model-inspector .basis-diagram');
  const r = d && d.getBoundingClientRect();
  ({tag: d && d.tagName, w: r ? Math.round(r.width) : 0,
    h: r ? Math.round(r.height) : 0,
    dots: document.querySelectorAll('#model-inspector .basis-dot').length});
}""")
        check("the basis diagram is drawn, not merely present",
              diagram["tag"] == "svg" and diagram["w"] > 10
              and diagram["h"] > 10 and diagram["dots"] > 0)
        # the other half of the served vocabulary, on the control that is a whole
        # SENTENCE ("where every board meets every rail"): every basis the
        # backend offers, in the backend's order, and every one of them worded
        # — a member registered after the bundles were written would show its
        # raw token here rather than a blank or a dotted key
        basis_select = c.js("""
{
  const b = document.querySelector('#model-inspector [data-f="basis"]');
  ({options: [...b.options].map((o) => o.value).filter((v) => v !== ""),
    labels: [...b.options].map((o) => o.textContent),
    disabled: b.disabled});
}""")
        served_bases = json.loads(urllib.request.urlopen(
            f"http://localhost:{PORT}/api/vocabularies", timeout=5).read())["fixing_bases"]
        check("the fixing basis select is populated from /api/vocabularies",
              basis_select["disabled"] is False
              and basis_select["options"] == served_bases,
              (basis_select["options"], served_bases))
        check("every offered basis is worded, never a raw i18n key",
              all(lbl and not lbl.startswith("model.basis.")
                  for lbl in basis_select["labels"]),
              basis_select["labels"])
        c.js("""
document.querySelector('#model-elements [data-element^="fixing:"]').click(); 'ok'""")
        time.sleep(0.8)

        check("a starter opens as a panel that is already drawn, with handles on it",
              drawn["members"] > 4
              and any(h.startswith("placement:") for h in drawn["handles"])
              and any(h.startswith("width:") for h in drawn["handles"]))

        # the fasteners on the drawing are PLACES with a count on each, derived
        # by the same read model the BOM line comes from — so they cannot
        # disagree with it. A drawing showing twelve dots beside a line buying
        # eight screws is the exact drift this is derived server-side to prevent.
        fastened = c.js("""
{
  const dots = [...document.querySelectorAll('#model-canvas .elev-fixing')];
  const each = dots.map(d => Number((d.querySelector('title')?.textContent || '')
    .split('\u00d7')[1] || 0));
  const row = document.querySelector('#model-parts tr[data-slot="screw"] td:nth-child(3)');
  ({dots: dots.length, drawn: each.reduce((a, b) => a + b, 0),
    counted: Number(row?.textContent.trim() || -1)});
}""")
        check("the fasteners drawn total exactly the screws counted",
              fastened["dots"] > 0 and fastened["drawn"] == fastened["counted"])

        # dragging a rail writes the AUTHORED number, and the drawing follows the
        # re-price rather than the pointer — the panel is refitted by the server.
        rail_before = c.js("""
{
  const r = [...document.querySelectorAll('#model-canvas .elev-member')]
    .find(m => m.dataset.slot === 'rail');
  ({y: Number(r.getAttribute('y'))});
}""")
        hx, hy = c.element_center('#model-canvas [data-handle^="placement:"]')
        c.drag(hx, hy, hx, hy - 70)
        time.sleep(3.0)
        rail_after = c.js("""
{
  const r = [...document.querySelectorAll('#model-canvas .elev-member')]
    .find(m => m.dataset.slot === 'rail');
  ({y: Number(r.getAttribute('y'))});
}""")
        c.click(*c.element_center("#btn-model-advanced"))
        time.sleep(0.8)
        dragged_doc = c.js("JSON.parse(document.getElementById('model-json').value)")
        c.click(*c.element_center("#btn-model-advanced"))
        time.sleep(1.5)
        placement = dragged_doc["default_spec"]["frame"][0]["placement"]
        check("dragging a rail writes the placement, and the drawing follows it",
              placement["bottom_inset_mm"] > 0
              and rail_after["y"] < rail_before["y"])

        # the overlap is a CHECKBOX, and a negative gap underneath it. The sign
        # was the thing an author had to remember from a hint; the control
        # remembers it, and the document still says the thing that makes
        # board-on-board expressible at all.
        c.js("""
document.querySelector('#model-elements [data-element="infill:slat"]').click(); 'ok'""")
        time.sleep(1.2)
        c.js("""
{
  const box = document.querySelector('#model-inspector [data-f="overlaps"]');
  box.checked = true; box.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.5)
        c.js("""
{
  const amount = document.querySelector('#model-inspector [data-f="gap_after_mm"]');
  amount.value = '30'; amount.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(2.0)
        c.click(*c.element_center("#btn-model-advanced"))
        time.sleep(0.8)
        overlapped = c.js("JSON.parse(document.getElementById('model-json').value)")
        c.click(*c.element_center("#btn-model-advanced"))
        time.sleep(1.5)
        check("an overlap is a checkbox, and a negative gap underneath it",
              overlapped["default_spec"]["infill"]["pattern"][0]["gap_after_mm"] == -30)

        # DEFERRED, and every one of them. The pytest guards for this are source
        # greps — they stayed green with a control replaced by a comment, and with
        # the raw justification/excess row wrapped in `false ? … :`. Only the
        # rendered DOM can tell "moved" from "deleted", so the whole set is
        # enumerated here, inside the disclosure, in the real browser.
        # a chip click TOGGLES, so "click the board" is not the same as "have the
        # board selected" — ask for the state, do not assume it
        c.js("""
{
  const chip = document.querySelector('#model-elements [data-element^="infill:"]');
  const showing = () => !!document.querySelector('#model-inspector [data-f="width_mm"]');
  if (!showing()) chip.click();
}
'ok'""")
        time.sleep(1.4)
        advanced = c.js("""
{
  const inside = (f) => {
    const el = document.querySelector(`#model-inspector [data-f="${f}"]`);
    return !!(el && el.closest('details.inspect-advanced'));
  };
  // `base_ref`/`top_ref` are NOT here on purpose: they are offered only under
  // `between_frame`, the one rule that reads them, so on a board cut to the
  // panel height their absence is the "never offer what the gate refuses" rule
  // working. Everything else is unconditional.
  // `role` was in this set and is deliberately NOT any more: it did not move
  // behind Advanced, it left AUTHORING. The part's type is the one authority on
  // what a piece is (`resolve_model_parts` fills `role` from it, and
  // `PartRequirement` refuses a slot that names a part and states a role too),
  // so the control was removed rather than deferred. Keeping it here would be a
  // check demanding the editor re-offer the field whose offer was the defect.
  // The word is still in the system — `ResolvedSlot.role`, and the BOM reads it
  // — it is just no longer something an author types.
  const want = ['length_rule', 'option_axis', 'face_offset_mm',
                'thickness_mm', 'justification', 'excess'];
  // no claim about the disclosure's open state here: it PERSISTS across
  // renders, and by this point in the session the author has opened it. That it
  // starts shut is asserted where a fresh element is first selected.
  ({board: !!document.querySelector('#model-inspector [data-f="width_mm"]'),
    refs_hidden_under_this_rule:
      !document.querySelector('#model-inspector [data-f="base_ref"]'),
    missing: want.filter((f) => !inside(f))});
}""")
        check("every deferred control is inside Advanced, not deleted",
              advanced["board"] is True and advanced["missing"] == []
              and advanced["refs_hidden_under_this_rule"] is True)

        # ... and the raw pair really RENDERS, which is what keeps the four
        # spacing combinations the segmented control cannot say reachable
        pairs = c.js("""
{
  const box = document.querySelector('#model-inspector .inspect-advanced');
  if (box) box.open = true;
  const opts = (f) => {
    const el = document.querySelector(`#model-inspector [data-f="${f}"]`);
    return el ? [...el.options].map((o) => o.value).filter(Boolean) : [];
  };
  ({justification: opts('justification'), excess: opts('excess')});
}""")
        check("all eight spacing pairs are reachable, not merely mentioned",
              len(pairs["justification"]) == 4 and len(pairs["excess"]) == 2)

        # BOTH steps below still hold, and it is worth saying why rather than
        # leaving the next reader to re-derive it. The narrowing this arc shipped
        # hides `width_mm` on a holder whose PART owns the width, and renders the
        # preference list only for a slot whose eligibility source is
        # `authored_members`. Neither narrowing bites here: this block is driving
        # the `slat` STARTER (`#btn-model-new` → `[data-template="slat"]` above),
        # not M-SLAT, and `panel-templates.js` builds its board out of
        # `defaultMember` + `defaultEligibleMember("SLAT-100")` — a member that
        # authors a sku list and states its own 100 mm width, naming no part. So
        # the width field renders and `add-eligible` renders, and the two things
        # these steps prove are still true of the pane they open.
        #
        # the disclosure must SURVIVE a rebuild — every edit re-renders the pane,
        # and a version that slams it shut loses the author's place on each
        # keystroke. Asserting only "shut on first render" cannot see that.
        c.js("""
{
  const w = document.querySelector('#model-inspector [data-f="width_mm"]');
  w.value = '120'; w.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.5)
        check("the Advanced disclosure stays open across a re-render",
              c.js("""(() => {
                const box = document.querySelector('#model-inspector .inspect-advanced');
                return !!box && box.open === true;
              })()""") is True)

        # the preference list IS the priority: dropping a row renumbers from 1,
        # so the order it reads in and the order it resolves in cannot disagree.
        # It lives behind Advanced now — the default screen carries ONE product
        # picker, because a board is usually supplied by one thing.
        c.js("""
{
  const box = document.querySelector('#model-inspector .inspect-advanced');
  if (box) box.open = true;
}
'ok'""")
        time.sleep(0.6)
        c.js("""
document.querySelector('#model-inspector [data-act="add-eligible"]').click(); 'ok'""")
        time.sleep(1.2)
        c.js("""
{
  const sel = document.querySelector(
    '#model-inspector [data-eligible-row="1"] [data-f="sku"]');
  sel.value = 'SLAT-V-150'; sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.5)
        # drag row 1 onto row 0 — a DataTransfer the drop handler reads back
        c.js("""
{
  const list = document.querySelectorAll('#model-inspector .pref-item');
  const dt = new DataTransfer();
  dt.setData('text/plain', '1');
  list[0].dispatchEvent(new DragEvent('drop', {bubbles: true, dataTransfer: dt}));
}
'ok'""")
        time.sleep(2.0)
        c.click(*c.element_center("#btn-model-advanced"))
        time.sleep(0.8)
        reordered = c.js("JSON.parse(document.getElementById('model-json').value)")
        c.click(*c.element_center("#btn-model-advanced"))
        time.sleep(1.5)
        members = (reordered["default_spec"]["infill"]["pattern"][0]
                   ["requirement"]["eligibility"]["members"])
        check("reordering the preference list renumbers priority from 1",
              [m["sku"] for m in members] == ["SLAT-V-150", "SLAT-100"]
              and [m["priority"] for m in members] == [1, 2])

        # --- and the whole claim: a VIEW, not a second source of truth --------
        # The canvas computes no geometry: every rectangle on it is one
        # `report/elevation.py` placed, from the same resolved slots the priced
        # table below is derived from. So the two have to agree about how many
        # boards this panel has — and they can only disagree if something in the
        # browser started working the answer out for itself.
        agreement = c.js("""
{
  const drawn = [...document.querySelectorAll('#model-canvas .elev-member')]
    .filter(m => m.dataset.slot === 'slat').length;
  const row = document.querySelector('#model-parts tr[data-slot="slat"] td:nth-child(3)');
  ({drawn, counted: Number(row?.textContent.trim() || -1)});
}""")
        check("the canvas is a view over the model, not a second answer",
              agreement["drawn"] > 0
              and agreement["drawn"] == agreement["counted"])

        # ... and what it authored is a model the gate takes, which is the other
        # half: a surface that produced a document the backend refuses would be
        # a view of nothing.
        c.click(*c.element_center("#btn-model-publish"))
        time.sleep(3.0)
        published = c.js("""
fetch('/api/fence-models').then(r => r.json())
  .then(l => l.find(x => x.id === 'M-SLAT-NEW') || null)""")
        check("a panel authored entirely on the canvas publishes",
              bool(published) and published["active_version"] is not None)
        c.shot("25-models-canvas-published.png")
        c.click(*c.element_center("#btn-model-close"))
        time.sleep(0.8)

        # --- retire: the one destructive transition in the library -------------
        # It removes a model from every picker in the app, and nothing in the UI
        # puts it back.
        c.click(*c.element_center("#btn-model-close"))
        time.sleep(0.8)
        c.js("""
document.querySelector('#model-list [data-model="M-SMOKE"] [data-act="retire"]').click();
'ok'""")
        time.sleep(2.0)
        retired_row = c.js("""
fetch('/api/fence-models').then(r => r.json())
  .then(l => l.find(x => x.id === 'M-SMOKE'))""")
        c.js("document.querySelector('#tabs button[data-tab=\"panel\"]').click(); 'ok'")
        time.sleep(1.5)
        after_retire = c.js("""
[...document.querySelectorAll('#panel-model option')]
  .map(o => o.value + (o.disabled ? ':disabled' : '')).join(',')""") or ""
        check("retiring a model takes it out of every picker without hiding it",
              retired_row["active_version"] is None
              and "M-SMOKE:disabled" in after_retire)
        c.js("document.querySelector('#tabs button[data-tab=\"models\"]').click(); 'ok'")
        time.sleep(1.0)
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.5)

        # --- variant conditions: site.* becomes authorable, not just JSON ------
        #
        # The backend has matched and evaluated `site.hvhz` /
        # `site.exposure_category` variant conditions since 2026-08-26; only the
        # picker offered them. `writeSentence`'s blind `Number()` coercion meant
        # adding the two fields without fixing it would have let a curator
        # silently author `site.hvhz == 0` — valid, and meaning nothing. This
        # checks the actual widgets render (a checkbox, a token select — not a
        # number input left standing in for them), that what gets typed survives
        # a save and reads back as the same TYPE (a JSON bool, not 0/1; a JSON
        # string, not a coerced number), and that switching between the two
        # NUMERIC fields keeps whatever was already typed — only a field's TYPE
        # changing may reset the value.
        c.js("document.querySelector('#tabs button[data-tab=\"models\"]').click(); 'ok'")
        time.sleep(1.0)
        c.click(*c.element_center("#btn-model-new"))
        time.sleep(4.0)
        c.click(*c.element_center('#model-gallery [data-template="blank"]'))
        time.sleep(1.2)
        c.js("""
{
  const id = document.querySelector('#model-head [data-f="id"]');
  id.value = 'M-COND'; id.dispatchEvent(new Event('input'));
  const name = document.querySelector('#model-head [data-f="name"]');
  name.value = 'תנאי וריאנט'; name.dispatchEvent(new Event('input'));
}
'ok'""")
        time.sleep(0.6)
        # the only button in the spec picker before a variant exists — no
        # "remove" button has appeared yet to disambiguate against
        c.js("""
document.querySelector('#model-spec-picker button:not(.remove-row)').click();
'ok'""")
        time.sleep(0.6)
        fresh = c.js("""
(() => {
  const val = document.querySelector('#model-spec-picker [data-f="condition_value"]');
  const fld = document.querySelector('#model-spec-picker [data-f="condition_field"]');
  return {tag: val.tagName, type: val.type || null, value: val.value, field: fld.value};
})()""")
        check("a fresh variant starts as the numeric panel.height_mm >= 1800 sentence",
              fresh == {"tag": "INPUT", "type": "number", "value": "1800",
                        "field": "panel.height_mm"}, fresh)

        def stored_condition():
            return c.js("""
(async () => {
  const listing = await (await fetch('/api/fence-models')).json();
  const row = listing.find((m) => m.id === 'M-COND');
  const model = await (await fetch(`/api/fence-models/M-COND/${row.draft_version}`)).json();
  return model.variants[0].condition;
})()""")

        # --- numeric -> numeric: the typed value must survive the switch -------
        c.js("""
{
  const val = document.querySelector('#model-spec-picker [data-f="condition_value"]');
  val.value = '2100'; val.dispatchEvent(new Event('change'));
}
'ok'""")
        c.js("""
{
  const fld = document.querySelector('#model-spec-picker [data-f="condition_field"]');
  fld.value = 'panel.width_mm'; fld.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.4)
        after_numeric_switch = c.js("""
(() => {
  const val = document.querySelector('#model-spec-picker [data-f="condition_value"]');
  return {type: val.type, value: val.value};
})()""")
        check("switching panel.height_mm to panel.width_mm keeps the typed value",
              after_numeric_switch == {"type": "number", "value": "2100"},
              after_numeric_switch)
        c.click(*c.element_center("#btn-model-save"))
        time.sleep(1.5)
        persisted_numeric = stored_condition()
        check("the numeric switch round-trips through a save: width_mm >= 2100",
              persisted_numeric == {
                  "op": "cmp", "cmp": ">=",
                  "left": {"op": "field", "path": "panel.width_mm"},
                  "right": {"op": "lit", "value": 2100},
              }, persisted_numeric)

        # --- numeric -> boolean: a TYPE change, so the widget itself swaps to a
        # checkbox and the value resets to a sensible default -------------------
        c.js("""
{
  const fld = document.querySelector('#model-spec-picker [data-f="condition_field"]');
  fld.value = 'site.hvhz'; fld.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.4)
        hvhz_widget = c.js("""
(() => {
  const val = document.querySelector('#model-spec-picker [data-f="condition_value"]');
  const cmp = document.querySelector('#model-spec-picker [data-f="condition_cmp"]');
  return {tag: val.tagName, type: val.type, checked: val.checked,
          cmps: [...cmp.options].map((o) => o.value)};
})()""")
        check("switching to site.hvhz renders a checkbox, unchecked, equality-only",
              hvhz_widget == {"tag": "INPUT", "type": "checkbox", "checked": False,
                               "cmps": ["==", "!="]}, hvhz_widget)
        c.js("""
{
  const val = document.querySelector('#model-spec-picker [data-f="condition_value"]');
  val.checked = true; val.dispatchEvent(new Event('change'));
}
'ok'""")
        c.click(*c.element_center("#btn-model-save"))
        time.sleep(1.5)
        persisted_hvhz = stored_condition()
        check("a checked HVHZ box round-trips as an actual JSON boolean, not 0/1",
              persisted_hvhz == {
                  "op": "cmp", "cmp": "==",
                  "left": {"op": "field", "path": "site.hvhz"},
                  "right": {"op": "lit", "value": True},
              } and persisted_hvhz["right"]["value"] is True, persisted_hvhz)

        # --- boolean -> enum: another TYPE change, another widget swap ---------
        c.js("""
{
  const fld = document.querySelector('#model-spec-picker [data-f="condition_field"]');
  fld.value = 'site.exposure_category'; fld.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.4)
        exposure_widget = c.js("""
(() => {
  const val = document.querySelector('#model-spec-picker [data-f="condition_value"]');
  const cmp = document.querySelector('#model-spec-picker [data-f="condition_cmp"]');
  return {tag: val.tagName, options: [...val.options].map((o) => o.value),
          value: val.value, cmps: [...cmp.options].map((o) => o.value)};
})()""")
        check("switching to site.exposure_category renders a B/C/D token select",
              exposure_widget == {"tag": "SELECT", "options": ["B", "C", "D"],
                                   "value": "B", "cmps": ["==", "!="]}, exposure_widget)
        c.js("""
{
  const val = document.querySelector('#model-spec-picker [data-f="condition_value"]');
  val.value = 'C'; val.dispatchEvent(new Event('change'));
}
'ok'""")
        c.click(*c.element_center("#btn-model-save"))
        time.sleep(1.5)
        persisted_exposure = stored_condition()
        check("a chosen exposure category round-trips as the same string token",
              persisted_exposure == {
                  "op": "cmp", "cmp": "==",
                  "left": {"op": "field", "path": "site.exposure_category"},
                  "right": {"op": "lit", "value": "C"},
              }, persisted_exposure)
        c.shot("25b-model-variant-conditions.png")
        c.click(*c.element_center("#btn-model-close"))
        time.sleep(0.8)
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.5)

        # --- site conditions: the panel that makes a conditional rule reachable
        #
        # Until this panel existed, `PUT /projects/{id}/site` was the only way in,
        # so THREE shipped strings had never been rendered by a browser —
        # `warning.site_condition_missing`, `structure.site_changed` and
        # `decisions.stale_site` — and no smoke scenario could reach them, because
        # nothing in the app could move a site condition. That is what this block
        # is for: not that a form saves, but that the engine's answer changes and
        # that the three refusals say so in Hebrew.
        #
        # The rule is arranged through the API (the knowledge form authors actions,
        # not conditions) and everything after it is done by clicking. 1200 is not
        # 1800: the unconditioned demo maximum lays a 6 m run out as 4 x 1500, and
        # exposure C lays the same run out as 5 x 1200 — the engine's own
        # acceptance criterion for site conditions, walked in a browser.
        c.js("""
fetch('/api/knowledge', {method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({object_id: 'K-EXPOSURE-C', type: 'hard_constraint',
    title: 'max span 1200 on exposure C',
    condition: {op: 'cmp', cmp: '==',
      left: {op: 'field', path: 'site.exposure_category'},
      right: {op: 'lit', value: 'C'}},
    actions: [{kind: 'set_param', param: 'max_span_mm', value: 1200}]})})
  .then(r => r.ok)""")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.5)
        c.js("document.getElementById('new-project-name').value = 'site'; 'ok'")
        c.click(*c.element_center("#btn-new-project"))
        time.sleep(1.5)
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(0, 0))
        c.click(*c.canvas_px(6000, 0))
        c.key("Enter")
        time.sleep(1.2)
        c.click(*c.element_center("#btn-generate"))
        time.sleep(2.5)
        posts_before = c.js("document.querySelectorAll('#g-overlay circle').length")

        # The conservative-substitution case the frontend design names in §7 —
        # "exposure category not set" — said out loud for the first time. A rule
        # in this snapshot asks about the site and the site has not answered.
        # the needle is the longest LITERAL run of the bundle sentence — the
        # string starts with `{n}`, so cutting at the first placeholder would
        # leave an empty needle and a check that passes against anything
        missing = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(b => {
  const stem = b['warning.site_condition_missing']
    .split('}').map(p => p.split('{')[0].trim())
    .sort((a, b) => b.length - a.length)[0];
  const text = document.getElementById('warnings').textContent || '';
  return {stem, said: text.includes(stem), key: text.includes('warning.site_condition')};
})""")
        # the CODE is printed beside the sentence on purpose (`warningRowHtml`);
        # what must never appear is the bundle KEY, which is what a warning with
        # no entry in this language renders as
        check("an unstated exposure category is SAID, in Hebrew, not left silent",
              len(missing["stem"]) > 12 and missing["said"] and not missing["key"],
              missing)

        panel = c.js("""
(() => {
  const host = document.getElementById('site-conditions');
  if (!host) return null;
  return {
    fields: ['#site-exposure', '#site-hvhz', '#site-frost', '#site-jurisdiction',
             '#site-code-edition'].filter(s => host.querySelector(s)).length,
    categories: [...host.querySelectorAll('#site-exposure option')].map(o => o.value),
    hvhz_options: [...host.querySelectorAll('#site-hvhz option')].map(o => o.value),
    status: document.getElementById('site-status').textContent,
    keys: /site\\.[a-z_]/.test(host.textContent),
  };
})()""")
        none_set = c.js(
            "fetch('/i18n/he.json').then(r => r.json()).then(b => b['site.none_set'])")
        # the unset option is a VALUE OF ITS OWN in both closed vocabularies: a
        # two-state control could not express "nobody has said", which is the
        # state the evaluator turns into "this rule does not apply"
        check("the site panel offers all five dimensions, with an unset state",
              panel is not None and panel["fields"] == 5
              and panel["categories"] == ["", "B", "C", "D"]
              and panel["hvhz_options"] == ["", "true", "false"]
              and not panel["keys"]
              # the needle has to BE something: an empty bundle value would make
              # every `includes` in this block a vacuous pass
              and len(none_set or "") > 20 and none_set in panel["status"], panel)

        # --- "no" is not "nobody has said" -----------------------------------
        # Answering the hurricane-zone question with NO must reach the server as
        # `false`, while the four dimensions nobody touched stay `null`. The
        # engine leans on the difference: a missing dimension makes a rule not
        # applicable, `false` makes it decide.
        c.js("""
{
  const s = document.getElementById('site-hvhz');
  s.value = 'false'; s.dispatchEvent(new Event('change'));
}
'ok'""")
        c.click(*c.element_center("#btn-site-save"))
        time.sleep(1.5)
        said_no = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.site)""")
        check("saying NO to the hurricane zone is stored as false, not as unset",
              said_no["hvhz"] is False
              and said_no["exposure_category"] is None
              and said_no["frost_depth_mm"] is None
              and said_no["jurisdiction"] is None and said_no["code_edition"] is None
              # the client never sends a revision; the route owns the counter
              and said_no["revision"] == 1, said_no)
        # ...and the CONTROL says it back. The panel was rebuilt from the server's
        # answer by `reloadProject`, so a `|| null` on the way home would show
        # "not stated" to an estimator who answered no — the same fact lost on the
        # return leg, where the payload assertion above cannot see it.
        shown = c.js("""
(() => {
  const v = (id) => document.getElementById(id).value;
  return {hvhz: v('site-hvhz'), exposure: v('site-exposure'), frost: v('site-frost')};
})()""")
        check("the control shows NO after the reload, not 'not stated'",
              shown == {"hvhz": "false", "exposure": "", "frost": ""}, shown)
        # Saving site conditions is NOT a topology change, and the rule that says
        # so is invisible to every other check in this suite: `openProject()`
        # instead of `reloadProject()` resets history, and the undo stack of
        # whoever was drawing is gone. The run drawn above is still undoable.
        undo_alive = c.js("!document.getElementById('btn-undo').disabled")
        check("saving the site leaves the drawing's undo stack alone", bool(undo_alive))

        # --- an exposure category, and a length through the display boundary ---
        c.click(*c.element_center("#btn-units"))     # drive the depth in cm
        time.sleep(0.6)
        c.js("""
{
  const e = document.getElementById('site-exposure');
  e.value = 'C'; e.dispatchEvent(new Event('change'));
  const f = document.getElementById('site-frost');
  f.value = '90'; f.dispatchEvent(new Event('input'));
  const j = document.getElementById('site-jurisdiction');
  j.value = 'Miami-Dade County'; j.dispatchEvent(new Event('input'));
}
'ok'""")
        c.click(*c.element_center("#btn-site-save"))
        time.sleep(1.5)
        stored = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}`)
  .then(r => r.json()).then(p => p.site)""")
        check("a depth typed in cm is stored as integer millimetres, and the rest holds",
              stored["frost_depth_mm"] == 900 and stored["exposure_category"] == "C"
              and stored["hvhz"] is False
              and stored["jurisdiction"] == "Miami-Dade County"
              and stored["code_edition"] is None and stored["revision"] == 2, stored)
        # BOTH sides of the round trip are read, and the cm side FIRST: a panel
        # that stopped converting on the way out would still say 900 in mm, so an
        # mm-only assertion passes with the display boundary deleted.
        in_cm = c.js("document.getElementById('site-frost').value")
        c.click(*c.element_center("#btn-units"))     # back to mm
        time.sleep(0.8)
        in_mm = c.js("document.getElementById('site-frost').value")
        chosen = c.js("document.getElementById('site-exposure').value")
        check("the depth reads 90 in cm and 900 in mm — the round trip is lossless",
              in_cm == "90" and in_mm == "900" and chosen == "C",
              {"cm": in_cm, "mm": in_mm, "exposure": chosen})
        c.shot("29-site-conditions.png")

        # --- the two refusals that had never reached a browser ----------------
        # The strategy on screen was laid out for a site the project no longer
        # describes. Both derived views must NAME that, in Hebrew, rather than
        # print a code or claim there is nothing to show.
        c.js("document.querySelector('#tabs button[data-tab=\"structure\"]').click(); 'ok'")
        time.sleep(2.0)
        stale_structure = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(b => {
  const text = document.getElementById('structure-body').textContent || '';
  const sentence = b['structure.site_changed'];
  return {said: sentence.length > 20 && text.includes(sentence),
          raw: text.includes('site_conditions_changed'),
          no_run: text.includes(b['structure.empty']), text: text.slice(0, 160)};
})""")
        check("the structure sheet refuses a run laid out for other site conditions",
              stale_structure["said"] and not stale_structure["raw"]
              and not stale_structure["no_run"], stale_structure)
        c.shot("30-structure-site-changed.png")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(1.5)
        stale_decisions = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(b => {
  const text = document.getElementById('section-decisions').textContent || '';
  const sentence = b['decisions.stale_site'];
  const status = document.getElementById('site-status').textContent || '';
  return {said: sentence.length > 20 && text.includes(sentence),
          raw: text.includes('site_conditions_changed'),
          // ...and the panel that CAUSED the refusal says so itself, rather than
          // leaving the estimator to find it by opening another tab
          panel: b['site.run_stale'].length > 20 && status.includes(b['site.run_stale']),
          text: text.slice(0, 160)};
})""")
        check("the section's decisions refuse the same way, naming the site",
              stale_decisions["said"] and not stale_decisions["raw"], stale_decisions)
        check("the site panel says the strategy on screen predates these conditions",
              stale_decisions["panel"], stale_decisions)

        # --- and the whole point: the fence itself is different ---------------
        c.click(*c.element_center("#btn-generate"))
        time.sleep(2.5)
        posts_after = c.js("document.querySelectorAll('#g-overlay circle').length")
        spans = c.js("""
fetch(`/api/projects/${document.getElementById('project-select').value}/runs`)
  .then(r => r.json()).then(l => fetch(`/api/runs/${l[l.length - 1].id}`))
  .then(r => r.json()).then(o => o.strategy.spans.map(s => s.width_mm))""")
        check("an exposure category entered in the app changes the fence that is planned",
              posts_before == 5 and posts_after == 6 and spans == [1200] * 5,
              {"before": posts_before, "after": posts_after, "spans": spans})
        settled = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(b => {
  const text = document.getElementById('warnings').textContent || '';
  const stem = b['warning.site_condition_missing']
    .split('}').map(p => p.split('{')[0].trim())
    .sort((a, b) => b.length - a.length)[0];
  return !text.includes(stem);
})""")
        check("and the run generated FOR that site no longer says nobody stated it",
              bool(settled))
        c.js("document.querySelector('#tabs button[data-tab=\"structure\"]').click(); 'ok'")
        time.sleep(2.0)
        readable = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(b => {
  const text = document.getElementById('structure-body').textContent || '';
  return {rows: document.querySelectorAll('#structure-body tr').length,
          stale: text.includes(b['structure.site_changed'])};
})""")
        check("the regenerated run lays out again, so the refusal was a state and not a wall",
              readable["rows"] > 0 and not readable["stale"], readable)
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(1.0)

        # --- a depth that is not a depth is refused BEFORE the server ---------
        # `SiteConditions` is `extra="forbid"` and `Mm` is an integer: the panel
        # must not turn a fat-fingered figure into a site nobody measured, and it
        # must not report a save that did not happen.
        c.js("""
{
  const f = document.getElementById('site-frost');
  // a number input SANITISES a non-numeric string to "", which reads as
  // "not stated" and is a legitimate answer — a negative depth is the typo
  // that actually has to be caught
  f.value = '-5'; f.dispatchEvent(new Event('input'));
}
'ok'""")
        c.click(*c.element_center("#btn-site-save"))
        time.sleep(1.0)
        refused = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(async (b) => {
  const id = document.getElementById('project-select').value;
  const p = await (await fetch(`/api/projects/${id}`)).json();
  const sentence = b['site.invalid_frost'];
  return {said: sentence.length > 20 && document.getElementById('site-status')
            .textContent.includes(sentence),
          revision: p.site.revision, depth: p.site.frost_depth_mm};
})""")
        check("an unreadable depth is named and nothing is saved",
              refused["said"] and refused["revision"] == 2
              and refused["depth"] == 900, refused)
        c.click(*c.element_center("#btn-site-revert"))
        time.sleep(0.8)
        reverted = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(b => ({
  depth: document.getElementById('site-frost').value,
  error: document.getElementById('site-status').textContent
    .includes(b['site.invalid_frost']),
}))""")
        check("discarding the edit restores the stored depth and clears the complaint",
              reverted["depth"] == "900" and not reverted["error"], reverted)

        # --- un-saying a condition is a statement too --------------------------
        # The other half of the tri-state, and the half a server that MERGED
        # instead of replacing would break in silence: returning exposure to
        # "not stated" must reach the wire as `null`, make the rule not
        # applicable again, and lay the fence back out as 4 x 1500.
        c.js("""
{
  const e = document.getElementById('site-exposure');
  e.value = ''; e.dispatchEvent(new Event('change'));
}
'ok'""")
        c.click(*c.element_center("#btn-site-save"))
        time.sleep(1.5)
        c.click(*c.element_center("#btn-generate"))
        time.sleep(2.5)
        unsaid = c.js("""
fetch('/i18n/he.json').then(r => r.json()).then(async (b) => {
  const id = document.getElementById('project-select').value;
  const p = await (await fetch(`/api/projects/${id}`)).json();
  const stem = b['warning.site_condition_missing']
    .split('}').map(q => q.split('{')[0].trim())
    .sort((x, y) => y.length - x.length)[0];
  return {exposure: p.site.exposure_category, revision: p.site.revision,
          depth: p.site.frost_depth_mm, hvhz: p.site.hvhz,
          posts: document.querySelectorAll('#g-overlay circle').length,
          missing_again: (document.getElementById('warnings').textContent || '')
            .includes(stem)};
})""")
        check("clearing a condition says 'nobody has stated it' again, and the fence follows",
              unsaid["exposure"] is None and unsaid["revision"] == 3
              # the dimensions nobody touched are untouched: a PUT replaces the
              # site, and the depth stated two saves ago is still stated
              and unsaid["depth"] == 900 and unsaid["hvhz"] is False
              and unsaid["posts"] == 5 and unsaid["missing_again"], unsaid)

        # --- and it is a panel in the OTHER language too -----------------------
        c.click(*c.element_center("#btn-locale"))
        time.sleep(1.2)
        english = c.js("""
fetch('/i18n/en.json').then(r => r.json()).then(b => {
  const host = document.getElementById('site-conditions');
  const text = host.textContent || '';
  return {title: text.includes(b['site.title']),
          category: [...host.querySelectorAll('#site-exposure option')]
            .some(o => o.textContent.trim() === b['site.exposure.C']),
          keys: /site\\.[a-z_]/.test(text)};
})""")
        check("the site panel is localized, not Hebrew strings in an English page",
              english["title"] and english["category"] and not english["keys"], english)
        c.click(*c.element_center("#btn-locale"))   # back to Hebrew for what follows
        time.sleep(1.2)
        # --- a hole in the knowledge is a NAMED hole, not a missing plan ------
        # LAST, because it retires a rule the whole demo knowledge base rests on
        # and nothing in the UI puts one back.
        #
        # Retiring K-MAXSPAN leaves the run with no maximum-span knowledge at
        # all. Until `Gap` became a return type that produced NO PLAN — a 422, an
        # empty canvas, and a user with nothing to correct — on the single most
        # important parameter in the system, and an exposure category no
        # published row covers reaches the same state without anyone retiring
        # anything. The boundary contract's §3.2.4 forbids it: "never fail a run
        # over a gap; warned, named, unfulfilled lines instead."
        #
        # These gap codes had never been rendered by a browser at all, in either
        # language, which is why the check reads the PANEL and not the page.
        retired = c.js("""
(async () => {
  const a = await fetch('/api/knowledge/K-MAXSPAN/1/retire', {method: 'POST'});
  // ...and the ground-post default, which is the SECOND converted site (audit
  // row 3). It gives the same screen the other half of the story: posts that
  // stand with no product, which demand already reports as unresolved lines.
  // One gap explains a plan; two show that the panel is a QUEUE.
  const b = await fetch('/api/knowledge/K-POST-DEFAULT/1/retire', {method: 'POST'});
  return [a.status, b.status].join(',');
})()""")
        check("the two rules under the converted failure sites can be retired",
              retired == "200,200", retired)
        c.js("document.getElementById('new-project-name').value = 'gap'; 'ok'")
        c.click(*c.element_center("#btn-new-project"))
        time.sleep(1.5)
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(0, 0))
        c.click(*c.canvas_px(6000, 0))
        c.key("Enter")
        time.sleep(1.2)
        c.click(*c.element_center("#btn-generate"))
        time.sleep(3)
        posts_after_gap = c.js("document.querySelectorAll('#g-overlay circle').length") or 0
        check("a run with no max-span and no post knowledge still produces a plan",
              posts_after_gap >= 3, posts_after_gap)
        gaps = c.js("""
(() => {
  const panel = document.querySelector('#gaps .panel.gaps');
  if (!panel) return null;
  const rows = [...panel.querySelectorAll('.gap')];
  const group = (k) => panel.querySelector(`.gap-group[data-closes-by="${k}"]`);
  const span = rows.find(r => r.dataset.gapCode === 'uncovered_max_span');
  return {
    text: panel.textContent,
    codes: rows.map(r => r.dataset.gapCode),
    knowledge: group('knowledge') ? group('knowledge').textContent : '',
    planning: group('planning') ? group('planning').textContent : '',
    subjects: rows.map(r => r.querySelector('.gap-subject')?.textContent.trim() || ''),
    span_severity: span ? span.dataset.severity : '',
    span_closes: span ? span.dataset.closesBy : '',
    would_close: span ? (span.querySelector('.gap-verbatim')?.textContent || '') : '',
    would_close_lang: span ? (span.querySelector('.gap-verbatim')?.lang || '') : '',
    would_close_dir: span ? (span.querySelector('.gap-verbatim')?.getAttribute('dir') || '') : '',
    raw_keys: /gaps\\.[a-z_]+/.test(panel.textContent),
  };
})()""")
        check("the gap surface renders at all", bool(gaps), gaps)
        gaps = gaps or {}
        check("it NAMES both holes, in Hebrew, from the code and not the English message",
              set(gaps.get("codes") or []) == {"uncovered_max_span", "no_default_post"}
              and "אין כלל הקובע מפתח מרבי" in (gaps.get("text") or "")
              and "אין כלל הקובע מוצר ברירת מחדל" in (gaps.get("text") or ""),
              {"codes": gaps.get("codes"), "text": gaps.get("text", "")[:200]})
        # the contract's first binding clause: a gap that only says something is
        # missing sends a curator hunting. It is on the row, not behind a click.
        check("it shows what would close it, verbatim and marked as English",
              "max_span_mm row for series" in (gaps.get("would_close") or "")
              and gaps.get("would_close_lang") == "en"
              and gaps.get("would_close_dir") == "ltr", gaps.get("would_close"))
        check("the curator sentence is labelled as written for the knowledge team",
              "נכתב עבור אוצרי הידע" in (gaps.get("text") or ""))
        # ...and the second binding clause. Both of today's gaps close on the
        # knowledge platform, so what the browser can prove is the half that
        # matters most: the panel offers exactly the group with work in it, and
        # does NOT print an empty "needs a change in this repository" heading
        # over nothing. The other direction — a `planning` row never landing in a
        # curator's group — has no backend fixture and is pinned in node
        # (tests/web/test_gaps_module.py).
        check("every gap is filed under who can close it, and no empty group is offered",
              "uncovered_max_span" in (gaps.get("knowledge") or "")
              and "no_default_post" in (gaps.get("knowledge") or "")
              and gaps.get("planning") == "",
              {"k": (gaps.get("knowledge") or "")[:160], "p": gaps.get("planning")})
        # a parameter and a slot are different subjects and are named as such —
        # the first queue that groups by subject kind depends on it
        check("each gap says WHAT is missing, addressably",
              any("max_span_mm" in s for s in gaps.get("subjects") or [])
              and any("post_ground" in s for s in gaps.get("subjects") or []),
              gaps.get("subjects"))
        check("a gap that costs a line is marked as costing one",
              gaps.get("span_severity") == "warns_line"
              and gaps.get("span_closes") == "knowledge"
              and "משפיע על שורה" in (gaps.get("text") or ""))
        check("no raw locale key reached the gap panel", not gaps.get("raw_keys"))
        # the SAME fact reaches the warning list beside it, from the same code
        warn_text = c.js("document.getElementById('warnings').textContent") or ""
        check("the gap is a warning row too, in Hebrew",
              "מפתח מרבי" in warn_text)
        # the panel sits under the drawing, so an unscrolled shot is a shot of
        # the canvas — a screenshot that proves nothing about the thing it is named for
        c.js("""
document.querySelector('#gaps .panel.gaps')
  ?.scrollIntoView({block: 'center'}); 'ok'""")
        time.sleep(0.5)
        c.shot("18-gaps.png")
        # and it is on the money view as well, because "why is this BOM short?"
        # and "why is this rule missing?" are one question with one answer
        c.js("document.querySelector('#tabs button[data-tab=\"bom\"]').click(); 'ok'")
        time.sleep(2.5)
        bom_gaps = c.js(
            "document.querySelector('#bom-body .panel.gaps')?.textContent || ''")
        check("the BOM tab carries the same gap surface",
              "uncovered_max_span" in bom_gaps and "max_span_mm" in bom_gaps)
        # ...and the BOM below it is visibly short, because a post with no
        # product is a line nothing supplies. This is the pair the design asks
        # for: the missing LINE and the missing RULE, on one screen, so "why is
        # this short?" is answered where it is asked.
        short = c.js("""
(() => {
  const panels = [...document.querySelectorAll('#bom-body .panel')];
  const p = panels.find(x => x.querySelector('tr.unfulfilled'));
  return {
    rows: document.querySelectorAll('#bom-body tr.unfulfilled').length,
    heading: p ? p.querySelector('h3').textContent : '',
    incomplete: !!p && p.classList.contains('incomplete'),
  };
})()""")
        check("the priced BOM shows the posts nothing can supply and says the "
              "total excludes them",
              short["rows"] >= 1 and short["incomplete"]
              and "לא כולל" in short["heading"], short)
        c.shot("19-bom-gaps.png")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.5)

        # --- locale: Hebrew is the default; toggle flips to English -----------
        dir0 = c.js("document.documentElement.dir")
        check("Hebrew RTL is the default", dir0 == "rtl")
        canvas_dir = c.js("getComputedStyle(document.getElementById('canvas')).direction")
        profile_dir = c.js("getComputedStyle(document.getElementById('profile-svg')).direction")
        check("canvas is never mirrored", canvas_dir == "ltr")
        check("profile is never mirrored", profile_dir == "ltr")
        hebrew_font = c.js("document.fonts.check('13px \"Noto Sans Hebrew\"', 'שלום')")
        check("Hebrew font loaded", bool(hebrew_font))
        c.shot("04-hebrew-rtl.png")
        label_he = c.js("document.getElementById('btn-generate').textContent")
        c.click(*c.element_center("#btn-locale"))
        time.sleep(1)
        check("toggle flips chrome to LTR English",
              c.js("document.documentElement.dir") == "ltr")
        label_en = c.js("document.getElementById('btn-generate').textContent")
        check("toggle actually swaps strings", label_he != label_en and bool(label_en))
        c.shot("05-english-ltr.png")

        # The elevation in the other language. "Never mirrored" has to hold in
        # BOTH directions — a drawing that only happened to be left-to-right
        # because the page was would pass the RTL check above by accident — and
        # its labels are localized figures like every other length on the page.
        c.js("document.querySelector('#tabs button[data-tab=\"panel\"]').click(); 'ok'")
        time.sleep(1.5)
        c.js("""
{
  const sel = document.getElementById('panel-model');
  sel.value = 'M-SLAT'; sel.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(1.8)
        en_drawn = c.js("""
(() => {
  const host = document.getElementById('panel-elevation');
  const rects = [...host.querySelectorAll('.elev-member')];
  const slats = rects.filter(r => r.dataset.slot === 'slat');
  const box = (r) => r.getBoundingClientRect();
  return {
    slats: slats.length,
    dims: [...host.querySelectorAll('.elev-dim-label')].map(t => t.textContent),
    gaps: host.querySelector('.elev-gaps')?.textContent || '',
    ascending: slats.length > 1
      && slats.every((r, i) => i === 0 || box(r).left > box(slats[i - 1]).left),
  };
})()""")
        # 120 mm is the PITCH — a 100 mm slat plus its 20 mm gap, the figure a
        # slat fence is actually specified by and the one neither the member
        # width nor the gap states on its own
        check("the elevation reads the same way round in English, with English labels",
              en_drawn["slats"] == 21 and en_drawn["ascending"]
              and set(en_drawn["dims"]) == {"2500 mm", "1800 mm", "20 mm", "120 mm"}
              and "20 gaps" in en_drawn["gaps"])
        c.shot("05b-panel-elevation-en.png")

        # --- evidence viewer: the deep link round-trips through a real reload --
        # Earlier, clicking a citation proved the open/close wiring and the
        # honest "not found" degrade for an id outside the fixture. This is the
        # other half frontend design §3 asks for — "deep-linkable, so a
        # citation is shareable" — and it has to be proved against an actual
        # navigation, not `location.hash =` from within the running page: a
        # page loaded FRESH with `#evidence=<id>` in the URL must open the
        # viewer on its own, before any click, with the real resolved content
        # a person who was sent the link would need to see. Last in the run on
        # purpose: nothing after this depends on the project/tab state a full
        # reload discards.
        c.cmd("Page.navigate", url=(
            f"http://localhost:{PORT}/#evidence="
            "sref_00000000000000000000000000000001"))
        time.sleep(3)
        c.js("window.confirm = () => true; window.alert = () => {}; undefined")
        deep = wait_for(c, """
(() => document.querySelector('#evidence-viewer .evidence-body') ? true : false)()""",
                         timeout=10)
        check("a URL carrying #evidence=<id> opens the viewer on load, unclicked",
              bool(deep))
        deep_content = c.js("""
(() => {
  const overlay = document.querySelector('#evidence-viewer .evidence-overlay');
  return {
    hash: location.hash,
    text: overlay ? overlay.textContent : '',
  };
})()""")
        # real content from the real vendored fixture record — not a blank
        # shell, not the "not found" degrade the demo id produced above
        check("the deep-linked record shows its real document, quote and "
              "provenance state",
              deep_content["hash"] == "#evidence=sref_00000000000000000000000000000001"
              and "CertainTeed" in deep_content["text"]
              and "30" in deep_content["text"]
              and "extracted" in deep_content["text"].lower()
              and "could not be resolved" not in deep_content["text"],
              deep_content and deep_content["text"][:200])
        c.shot("21-evidence-deep-link.png")

        check("no uncaught page errors", not c.page_errors)
        if c.page_errors:
            print("  page errors:", *c.page_errors[:5], sep="\n    ")

        # -- CHOICE-SET AND PLACEMENT CASES ------------------------------------
        # Each lives in its own `_smoke_*(c)` function defined above `main()`,
        # called from here by ONE line. That is not style: this function is
        # 4000 lines, and several people adding cases inline turns every
        # addition into a merge conflict with every other.
        for _case in _CHOICE_CASES:
            _case(c)

        failed = [n for n, ok in CHECKS if not ok]
        print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
        return 1 if failed else 0
    finally:
        for proc in (server, chrome):
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except Exception:
                pass
        if os.path.exists(db):
            os.unlink(db)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
