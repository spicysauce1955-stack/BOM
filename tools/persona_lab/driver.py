"""The only verbs a persona has.

Deliberately absent: js(), fetch, any API or DB access. If a persona wants to
know whether their work saved, they have to find out the way a קבלן would —
by looking at the screen.
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import websocket

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cdp import Cdp  # noqa: E402,F401

from . import outline as outline_mod


class Driver:
    """Attaches to the persona's already-open tab. Constructed fresh per action,
    so the browser — not this object — holds the session state."""

    def __init__(self, session: dict):
        self.session = session
        self.run_dir = Path(session["run_dir"])
        self.handles: dict[str, dict] = {}
        self.ws = websocket.create_connection(
            session["ws_url"], timeout=20,
            origin=f"http://localhost:{session['cdp_port']}",
        )
        self.mid = 0

    def _cmd(self, method: str, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        deadline = time.time() + 25
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                return msg.get("result", msg)
        raise TimeoutError(method)

    def _eval(self, expr: str):
        r = self._cmd("Runtime.evaluate", expression=expr,
                      awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")

    def _point(self, target: str | tuple[int, int]) -> tuple[int, int]:
        if isinstance(target, tuple):
            return target
        el = self.handles.get(target)
        if el is None:
            raise KeyError(f"unknown handle {target!r} — call look first")
        return el["x"], el["y"]

    def _mouse(self, type_: str, x, y, **kw):
        self._cmd("Input.dispatchMouseEvent", type=type_, x=x, y=y,
                  button="left", **kw)

    # --- the verbs ---------------------------------------------------------

    def look(self, shot_name: str) -> tuple[str, str]:
        items = self._eval(outline_mod.OUTLINE_JS) or []
        self.handles = {f"e{i:02d}": el for i, el in enumerate(items, start=1)}
        shots = self.run_dir / "shots"
        shots.mkdir(parents=True, exist_ok=True)
        data = self._cmd("Page.captureScreenshot", format="jpeg", quality=60)["data"]
        path = shots / shot_name
        path.write_bytes(base64.b64decode(data))
        return str(path), outline_mod.render(items)

    def click(self, target) -> None:
        x, y = self._point(target)
        self._mouse("mousePressed", x, y, clickCount=1)
        self._mouse("mouseReleased", x, y, clickCount=1)
        time.sleep(0.4)

    def hover(self, target) -> str:
        x, y = self._point(target)
        self._mouse("mouseMoved", x, y)
        time.sleep(0.4)
        if isinstance(target, str):
            return self.handles[target].get("title", "")
        return ""

    def type_text(self, text: str) -> None:
        for ch in text:
            self._cmd("Input.dispatchKeyEvent", type="char", text=ch)
            time.sleep(0.02)
        time.sleep(0.2)

    def key(self, name: str) -> None:
        mods = 0
        if name.startswith("Ctrl+"):
            mods, name = 2, name[5:]
        for t in ("keyDown", "keyUp"):
            self._cmd("Input.dispatchKeyEvent", type=t, key=name, modifiers=mods)
        time.sleep(0.4)

    def drag(self, x0, y0, x1, y1, steps: int = 8) -> None:
        self._mouse("mousePressed", x0, y0, clickCount=1)
        for i in range(1, steps + 1):
            self._mouse("mouseMoved", x0 + (x1 - x0) * i / steps,
                        y0 + (y1 - y0) * i / steps)
            time.sleep(0.03)
        self._mouse("mouseReleased", x1, y1, clickCount=1)
        time.sleep(0.4)

    def scroll(self, dy: int) -> None:
        self._cmd("Input.dispatchMouseEvent", type="mouseWheel",
                  x=700, y=500, deltaX=0, deltaY=dy)
        time.sleep(0.3)

    def wait(self, seconds: float) -> None:
        time.sleep(min(float(seconds), 10.0))

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass
