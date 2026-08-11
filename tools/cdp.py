"""CDP transport shared by the UI smoke suite and the persona lab.

Extracted from tools/ui_smoke.py so several stacks can drive their own Chrome
on their own port at the same time. Method bodies are unchanged; the only edit
is that the CDP port and screenshot directory are now constructor arguments.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.request

import websocket

DEFAULT_CDP_PORT = 9333


class Cdp:
    def __init__(self, url: str, *, cdp_port: int = DEFAULT_CDP_PORT,
                 out_dir: str | None = None):
        self.page_errors: list[str] = []
        self.cdp_port = cdp_port
        self.out_dir = out_dir
        req = urllib.request.Request(
            f"http://localhost:{cdp_port}/json/new?about:blank", method="PUT"
        )
        tab = json.load(urllib.request.urlopen(req))
        self.target_id = tab["id"]
        self.ws_url = tab["webSocketDebuggerUrl"]
        self.ws = websocket.create_connection(
            self.ws_url, timeout=15, origin=f"http://localhost:{cdp_port}"
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
            if msg.get("method") == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                desc = (d.get("exception") or {}).get("description", d.get("text", ""))
                self.page_errors.append(desc[:300])
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
            f"(() => {{ const el = document.querySelector({selector!r});"
            f" el.scrollIntoView({{block: 'center', inline: 'nearest'}});"
            f" const r = el.getBoundingClientRect();"
            f" return [r.x + r.width/2, r.y + r.height/2]; }})()"
        )
        time.sleep(0.1)
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
        out = self.out_dir
        if out is None:
            raise ValueError("Cdp(out_dir=...) is required to take screenshots")
        os.makedirs(out, exist_ok=True)
        data = self.cmd("Page.captureScreenshot", format="png")["data"]
        with open(os.path.join(out, name), "wb") as f:
            f.write(base64.b64decode(data))
        print(f"  screenshot: {os.path.join(out, name)}")
