"""UI smoke test: drives the real app in headless Chrome via CDP (spec §7).

Run manually at milestones (not part of pytest — keeps CI browser-free):

    uv run --with websocket-client python tools/ui_smoke.py

Prereqs: google-chrome on PATH. Boots its own server on :8791 with a throwaway DB,
drives the drawing/editing/undo/locale flows, saves screenshots to
tools/smoke-out/, and exits non-zero on any failed check.
"""

from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

PORT = 8791
CDP_PORT = 9333
OUT = os.path.join(os.path.dirname(__file__), "smoke-out")
CHECKS: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    CHECKS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name)


class Cdp:
    def __init__(self, url: str):
        req = urllib.request.Request(
            f"http://localhost:{CDP_PORT}/json/new?about:blank", method="PUT"
        )
        tab = json.load(urllib.request.urlopen(req))
        self.ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], timeout=15, origin=f"http://localhost:{CDP_PORT}"
        )
        self.mid = 0
        self.cmd("Runtime.enable")
        self.cmd("Page.enable")
        self.cmd("Page.navigate", url=url)
        time.sleep(3)

    def cmd(self, method: str, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        deadline = time.time() + 20
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                return msg.get("result", msg)
        raise TimeoutError(method)

    def js(self, expr: str):
        r = self.cmd("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        res = r.get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(res.get("description", "")[:500])
        return res.get("value")

    def click(self, x: float, y: float, *, count: int = 1) -> None:
        for t_ in ("mousePressed", "mouseReleased"):
            self.cmd("Input.dispatchMouseEvent", type=t_, x=x, y=y,
                     button="left", clickCount=count)
        time.sleep(0.15)

    def dblclick(self, x: float, y: float) -> None:
        self.click(x, y)
        self.click(x, y, count=2)

    def drag(self, x0, y0, x1, y1, steps: int = 8) -> None:
        self.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0,
                 button="left", clickCount=1)
        for i in range(1, steps + 1):
            self.cmd("Input.dispatchMouseEvent", type="mouseMoved",
                     x=x0 + (x1 - x0) * i / steps, y=y0 + (y1 - y0) * i / steps,
                     button="left")
            time.sleep(0.03)
        self.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1,
                 button="left", clickCount=1)
        time.sleep(0.2)

    def key(self, key: str, *, ctrl: bool = False, shift: bool = False) -> None:
        mods = (2 if ctrl else 0) | (8 if shift else 0)
        for t_ in ("keyDown", "keyUp"):
            self.cmd("Input.dispatchKeyEvent", type=t_, key=key, modifiers=mods)
        time.sleep(0.15)

    def element_center(self, selector: str) -> tuple[float, float]:
        rect = self.js(
            f"(() => {{ const r = document.querySelector({selector!r}).getBoundingClientRect();"
            f" return [r.x + r.width/2, r.y + r.height/2]; }})()"
        )
        return rect[0], rect[1]

    def canvas_px(self, world_x_mm: int, world_y_mm: int) -> tuple[float, float]:
        """World mm -> viewport px through the live SVG transform."""
        return tuple(self.js(f"""
(() => {{
  const svg = document.getElementById('canvas');
  const pt = new DOMPoint(60 + {world_x_mm}*0.045, 260 - {world_y_mm}*0.045);
  const m = svg.getScreenCTM();
  const p = pt.matrixTransform(m);
  return [p.x, p.y];
}})()"""))

    def shot(self, name: str) -> None:
        os.makedirs(OUT, exist_ok=True)
        data = self.cmd("Page.captureScreenshot", format="png")["data"]
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(base64.b64decode(data))
        print(f"  screenshot: {os.path.join(OUT, name)}")


def main() -> int:
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
        c = Cdp(f"http://localhost:{PORT}/")
        c.js("window.confirm = () => true; undefined")

        # --- draw a 6 m run with the Draw tool ------------------------------
        c.click(*c.element_center("#tool-draw"))
        c.click(*c.canvas_px(0, 0))
        c.click(*c.canvas_px(6000, 0))
        c.key("Enter")
        time.sleep(1)
        runs = c.js("fetch(`/api/projects/${document.querySelector('#project-select').value}/topology`).catch(()=>null), null")
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
            c.js("""(() => { const b = [...document.querySelectorAll('.popover button')]
                 .find(x => x.dataset.action === 'save' || x.type === 'submit' || true); b.click(); })()""")
            time.sleep(1)
        c.click(*c.element_center("#btn-generate"))
        time.sleep(1.5)
        n_posts = c.js("document.querySelectorAll('#g-overlay circle').length")
        check("generate renders posts", (n_posts or 0) >= 3)
        c.shot("03-generated.png")

        # --- profile panel renders -------------------------------------------
        profile_children = c.js("document.getElementById('profile-svg').childNodes.length")
        check("profile panel has content", (profile_children or 0) > 0)

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

        # --- Hebrew switch ----------------------------------------------------
        c.click(*c.element_center("#btn-locale"))
        time.sleep(1)
        dir_ = c.js("document.documentElement.dir")
        canvas_dir = c.js("getComputedStyle(document.getElementById('canvas')).direction")
        check("locale toggle flips chrome to RTL", dir_ == "rtl")
        check("canvas is never mirrored", canvas_dir == "ltr")
        c.shot("04-hebrew-rtl.png")

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
