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

_VK = {"Enter": 13, "Escape": 27, "Backspace": 8, "Tab": 9, "Delete": 46,
       "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40,
       " ": 32, "Home": 36, "End": 35}
_CODE = {"Enter": "Enter", "Escape": "Escape", "Backspace": "Backspace",
         "Tab": "Tab", "Delete": "Delete", "ArrowLeft": "ArrowLeft",
         "ArrowUp": "ArrowUp", "ArrowRight": "ArrowRight",
         "ArrowDown": "ArrowDown", " ": "Space", "Home": "Home", "End": "End"}
_TEXT = {"Enter": "\r", "Tab": "\t", " ": " "}
# Chrome runs these only when the keyDown carries an explicit commands list.
_COMMANDS = {("z", 2): ["undo"], ("y", 2): ["redo"], ("a", 2): ["selectAll"],
             ("z", 10): ["redo"], ("c", 2): ["copy"], ("v", 2): ["paste"]}


def _code_for(name: str) -> str:
    if len(name) == 1 and name.isdigit():
        return f"Digit{name}"
    if len(name) == 1 and name.isalpha() and name.isascii():
        return f"Key{name.upper()}"
    return name


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
        idx = int(target[1:]) - 1
        fresh = self._eval(outline_mod.POINT_JS % idx)
        if fresh:
            return fresh[0], fresh[1]
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
        """Type as a keyboard does — keyDown/keyUp per character.

        A bare CDP `char` event inserts text without ever firing `keydown`,
        so any feature listening on keydown (the canvas typed-length grammar)
        appears dead. That defect manufactured false findings in the first
        lab run; every character now carries its real key identity.
        """
        for ch in text:
            self._key_events(ch, 0, text=ch)
            time.sleep(0.02)
        time.sleep(0.2)

    def key(self, name: str) -> None:
        mods = 0
        while "+" in name:
            prefix, name = name.split("+", 1)
            mods |= {"ctrl": 2, "shift": 8, "alt": 1, "meta": 4}.get(prefix.lower(), 0)
        text = name if len(name) == 1 and not mods & 0b0110 else _TEXT.get(name, "")
        self._key_events(name, mods, text=text)
        time.sleep(0.4)

    def _key_events(self, name: str, mods: int, *, text: str = "") -> None:
        """One keyDown/keyUp pair carrying the identity a real key would.

        Chrome ignores editing shortcuts (undo, select-all) unless the event
        carries virtual key codes AND the matching `commands` list — without
        them Ctrl+Z is silently inert and reads as "undo is broken".
        """
        vk = _VK.get(name) or (ord(name.upper()) if len(name) == 1 else 0)
        code = _CODE.get(name) or _code_for(name)
        down: dict = {
            "type": "keyDown", "key": name, "code": code, "modifiers": mods,
            "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk,
        }
        if text:
            down["text"] = text
        commands = _COMMANDS.get((name.lower(), mods))
        if commands:
            down["commands"] = commands
        self._cmd("Input.dispatchKeyEvent", **down)
        self._cmd("Input.dispatchKeyEvent", type="keyUp", key=name, code=code,
                  modifiers=mods, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)

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
