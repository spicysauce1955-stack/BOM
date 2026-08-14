"""UI smoke test: drives the real app in headless Chrome via CDP (spec §7).

Run manually at milestones (not part of pytest — keeps CI browser-free):

    uv run --with websocket-client python tools/ui_smoke.py

Prereqs: google-chrome on PATH. Boots its own server on :8791 with a throwaway DB,
drives the drawing/editing/undo/locale flows, saves screenshots to
tools/smoke-out/, and exits non-zero on any failed check.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

from cdp import Cdp

PORT = 8791
CDP_PORT = 9333
OUT = os.path.join(os.path.dirname(__file__), "smoke-out")
CHECKS: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    CHECKS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name)


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


def main() -> int:
    # a stale server on our port would silently serve old code/data — abort loudly
    try:
        urllib.request.urlopen(f"http://localhost:{PORT}/api/health", timeout=1)
        print(f"FATAL: something is already listening on :{PORT} — kill it first "
              f"(pkill -f 'port {PORT}')")
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
    chrome = subprocess.Popen(
        ["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
         f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*",
         "--window-size=1400,950", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    try:
        time.sleep(3)
        c = Cdp(f"http://localhost:{PORT}/", cdp_port=CDP_PORT, out_dir=OUT)
        c.js("window.confirm = () => true; undefined")

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
  return p ? ((p.attrs || {}).opening_width_mm ?? null) : null;
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
fetch(`/api/runs/${document.getElementById('project-select').value ? '' : ''}`)
  .then(() => 0)""")
        expected_rows = c.js("""
(async () => {
  const runs = await (await fetch(
    `/api/projects/${document.getElementById('project-select').value}/runs`)).json();
  const doc = await (await fetch(`/api/runs/${runs[runs.length - 1].id}/structure`)).json();
  return doc.sections.reduce((n, s) =>
    n + s.setting_out.length + s.bays.length + s.gates.length, 0);
})()""")
        check("every element in the document has a row", rows == expected_rows)
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
  const bays = report.sections.reduce((n, s) => n + s.bays.length, 0);
  const gates = report.sections.reduce((n, s) => n + s.gates.length, 0);
  const svg = document.querySelector('#assembly-macro .macro-svg');
  return {
    stations, bays, gates,
    drawn_posts: svg ? svg.querySelectorAll('.macro-post').length : 0,
    drawn_bays: svg ? svg.querySelectorAll('.macro-bay').length : 0,
    drawn_gates: svg ? svg.querySelectorAll('.macro-gate').length : 0,
    embeds: svg ? svg.querySelectorAll('.macro-embed').length : 0,
    footings: svg ? svg.querySelectorAll('.macro-footing').length : 0,
    members: svg ? svg.querySelectorAll('.macro-member').length : 0,
    dims: svg ? svg.querySelectorAll('.macro-dims text').length : 0,
    micro: document.querySelectorAll('#assembly-micro .elevation-svg').length,
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
              macro["members"] > 0)
        check("the macro drawing is dimensioned", macro["dims"] > 0)
        check("the micro viewport assembles a panel beside it", macro["micro"] == 1)
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
   posts: document.querySelectorAll('#assembly-macro .macro-post').length })""")
        check("the dimension layer can be switched off without losing the drawing",
              bare["dims"] == 0 and bare["posts"] == macro["stations"])
        c.js("""
{ const box = document.getElementById('assembly-dims');
  box.checked = true; box.dispatchEvent(new Event('change')); }""")
        time.sleep(0.6)
        c.shot("26-assembly-macro.png")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.3)

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
        check("the Panel tab prices a parts table for M-SLAT",
              slat["slots"] == ["rail", "screw", "slat"]
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
        # the panel is priced from the model, not from a fixed shape: M-LEGACY's
        # two-slot panel and M-SLAT's three-slot one must not render the same
        c.js("""
{
  const sel = document.getElementById('panel-model');
  sel.value = 'M-LEGACY'; sel.dispatchEvent(new Event('change'));
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
        aside = c.js("document.getElementById('model-row')?.textContent || ''")
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
        c.drag(*c.canvas_px(3000, 0), *c.canvas_px(3000, 1000))  # ghost -> vertex
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
        stock = c.js("""
[...document.querySelectorAll('#tab-bom table tr')]
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
        c.js("window.confirm = () => true; undefined")  # the reload dropped the stub
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
              sorted(model_options or []) == ["M-LEGACY", "M-SLAT"])
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
        c.click(*c.element_center("#btn-model-new"))
        time.sleep(0.8)
        # name it, then build the smallest publishable panel out of the rows:
        # one rail slot, cut centre-to-centre, supplied by RAIL-3000
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
        time.sleep(0.6)
        c.js("""
{
  const g = document.querySelector('#model-frame [data-slot-row="0"]');
  const key = g.querySelector('[data-f="key"]');
  key.value = 'rail'; key.dispatchEvent(new Event('input'));
  const rule = g.querySelector('[data-f="length_rule"]');
  rule.value = 'centre_to_centre'; rule.dispatchEvent(new Event('change'));
}
'ok'""")
        time.sleep(0.8)
        c.js("""
document.querySelector('#model-frame [data-slot-row="0"] [data-act="add-eligible"]').click();
'ok'""")
        time.sleep(0.6)
        c.js("""
{
  const sel = document.querySelector(
    '#model-frame [data-slot-row="0"] [data-eligible-row="0"] [data-f="sku"]');
  sel.value = 'RAIL-3000'; sel.dispatchEvent(new Event('change'));
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
        c.shot("21-models-editor.png")
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
                 members: slot.requirement.eligibility.members} : null;
})""")
        check("a model authored from the rows publishes, with the rows in it",
              bool(smoke_row) and smoke_row["active_version"] == 1
              and smoke_row["status"] == "active"
              and stored and stored["key"] == "rail"
              and stored["rule"] == "centre_to_centre"
              and stored["members"] == [{"kind": "catalog_item", "sku": "RAIL-3000",
                                         "priority": 1, "approval": "auto"}])
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
  rows: document.querySelectorAll('#model-frame [data-slot-row]').length,
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
  const w = document.querySelector('#model-infill [data-member-row="0"] [data-f="width_mm"]');
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
document.querySelector('#model-infill [data-member-row="0"] [data-f="width_mm"]')?.value""")
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
{
  const rule = document.querySelector(
    '#model-frame [data-slot-row="0"] [data-f="length_rule"]');
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
        c.js("""
document.querySelector('#model-list [data-model="M-SLAT"] [data-act="edit"]').click();
'ok'""")
        time.sleep(1.5)
        c.js("""
{
  const gap = document.querySelector(
    '#model-infill [data-member-row="0"] [data-f="gap_after_mm"]');
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
              and slat_row["active_version"] == 1
              and slat_row["draft_version"] is None)
        c.shot("23-models-impact.png")

        # --- the preview beside the editor follows the spec --------------------
        # A preview that does not move when the spec does is worse than none: it
        # is a priced picture of a panel the author is no longer editing. 100 mm
        # slats at a 300 mm gap fit far fewer times across the same bay.
        c.js("""
{
  const gap = document.querySelector(
    '#model-infill [data-member-row="0"] [data-f="gap_after_mm"]');
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
        check("the elevation reads the same way round in English, with English labels",
              en_drawn["slats"] == 21 and en_drawn["ascending"]
              and set(en_drawn["dims"]) == {"2500 mm", "1800 mm", "20 mm"}
              and "20 gaps" in en_drawn["gaps"])
        c.shot("05b-panel-elevation-en.png")

        check("no uncaught page errors", not c.page_errors)
        if c.page_errors:
            print("  page errors:", *c.page_errors[:5], sep="\n    ")

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


if __name__ == "__main__":
    sys.exit(main())
