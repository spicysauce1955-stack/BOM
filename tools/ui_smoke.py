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
        c.shot("03-generated.png")

        # --- profile panel renders -------------------------------------------
        profile_drawn = c.js("document.querySelectorAll('#p-result *').length")
        profile_ground = c.js("document.querySelectorAll('#p-ground *').length")
        check("profile renders generated panels/posts", (profile_drawn or 0) > 0)
        check("profile renders the ground line", (profile_ground or 0) > 0)

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
        c.shot("07-quotes.png")
        c.js("document.querySelector('#tabs button[data-tab=\"canvas\"]').click(); 'ok'")
        time.sleep(0.3)

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
