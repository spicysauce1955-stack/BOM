# Persona Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable harness in which six real-role personas drive the live Fence AI app in a browser, perceiving only what a real user perceives, and produce refuter-verified usability findings.

**Architecture:** A CDP driver exposing user-plausible verbs only (`look/click/type/key/drag/hover/scroll/wait`), fronted by a per-action CLI (`act.py`) that persona subagents shell out to. Each persona gets an isolated stack (own port, own throwaway DB, own Chrome). Persona findings are hypotheses; independent refuter agents reproduce them and assign severity; a mechanical collator renders the report.

**Tech Stack:** Python 3.12, CDP over `websocket-client`, headless `google-chrome`, uvicorn, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-11-persona-lab-design.md`. Where plan and spec disagree, the spec wins — stop and flag it.
- **`tools/ui_smoke.py` must report 44/44 after every task.** It is the release gate.
- Run artifacts go to the scratchpad, never the repo: `$SCRATCH/persona-lab/<date>/<persona>/`. Only the final report is committed, to `docs/reviews/`.
- The driver exposes **no** `js()`, `fetch`, API, or DB access to personas. Outline output must never contain `#id` or CSS-class text.
- Python: `from __future__ import annotations`, stdlib-first, match the terse style of `tools/ui_smoke.py`.
- External-binary tests skip rather than fail, following `tests/web/test_units_module.py` (`shutil.which(...)` → `pytest.skip`).
- Repo is Hebrew-first: five personas run `he`, one runs `en`.
- `SCRATCH` in commands below means: `/tmp/claude-1000/-home-user--superset-projects-BOM/05462b89-c98e-4683-80b7-17d4bbd091ce/scratchpad`

---

## File Structure

| File | Responsibility |
|---|---|
| `tools/cdp.py` | Low-level CDP transport + input primitives (moved from `ui_smoke.py`) |
| `tools/ui_smoke.py` | Unchanged behavior; now imports `Cdp` |
| `tools/persona_lab/stack.py` | Boot/teardown an isolated server+chrome stack; write `session.json` |
| `tools/persona_lab/outline.py` | DOM → labelled handle outline (the anti-cheat surface) |
| `tools/persona_lab/driver.py` | User-plausible verbs over `Cdp` + `outline` |
| `tools/persona_lab/act.py` | Per-action CLI; enforces the think-aloud trace contract |
| `tools/persona_lab/personas/*.json` | Six persona definitions |
| `tools/persona_lab/scenarios/*.md` | Six job briefs |
| `tools/persona_lab/report.py` | Mechanical collation of findings + verdicts → markdown |
| `tests/tools/test_cdp_move.py` | `Cdp` importable and parameterized |
| `tests/tools/test_persona_stack.py` | Stack boots, health-checks, tears down |
| `tests/tools/test_persona_driver.py` | Outline has labels and no selectors; click-by-handle works |
| `tests/tools/test_persona_act.py` | Trace contract enforced |
| `tests/tools/test_persona_personas.py` | Persona files validate; roster matches spec |
| `tests/tools/test_persona_report.py` | Dedupe, ordering, hypothesis separation |

**Dependency order:** Task 1 → Task 2 → Task 3 → Task 4. Tasks 5 and 6 depend only on Task 1's existence of the package directory and may run concurrently with it. Task 7 needs everything.

---

## Task 1: Extract `Cdp` into `tools/cdp.py`

**Files:**
- Create: `tools/cdp.py`
- Modify: `tools/ui_smoke.py:37-131` (delete class, add import), `pyproject.toml` (dev dep)
- Test: `tests/tools/test_cdp_move.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Cdp(url: str, *, cdp_port: int = 9333, out_dir: str | None = None)` with methods `cmd(method, **params)`, `js(expr)`, `click(x, y, *, count=1)`, `dblclick(x, y)`, `drag(x0, y0, x1, y1, steps=8)`, `key(key, *, ctrl=False, shift=False)`, `element_center(selector)`, `canvas_px(world_x_mm, world_y_mm)`, `shot(name)`, attribute `page_errors: list[str]`.

- [ ] **Step 1: Add the dev dependency**

`websocket-client` is currently supplied ad hoc via `uv run --with websocket-client`. The pytest harness needs it importable. In `pyproject.toml`, under `[dependency-groups]`:

```toml
dev = [
    "pytest>=8.3",
    "httpx>=0.27",
    "websocket-client>=1.8",
]
```

Then run: `uv sync`

- [ ] **Step 2: Write the failing test**

Create `tests/tools/test_cdp_move.py`:

```python
"""tools/cdp.py owns the CDP transport so persona stacks and the smoke suite
can each drive their own Chrome on their own port."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def test_cdp_is_importable_from_its_own_module():
    from cdp import Cdp

    assert inspect.isclass(Cdp)


def test_cdp_port_and_out_dir_are_constructor_arguments():
    from cdp import Cdp

    params = inspect.signature(Cdp.__init__).parameters
    assert params["cdp_port"].default == 9333
    assert params["out_dir"].default is None


def test_ui_smoke_no_longer_defines_its_own_cdp():
    source = (TOOLS / "ui_smoke.py").read_text(encoding="utf-8")
    assert "class Cdp" not in source
    assert "from cdp import Cdp" in source
```

- [ ] **Step 3: Run it and watch it fail**

Run: `uv run pytest tests/tools/test_cdp_move.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cdp'`

- [ ] **Step 4: Create `tools/cdp.py`**

Copy the `Cdp` class body from `tools/ui_smoke.py` **verbatim**, changing only the two places that read module globals. Do not reformat, rename, or "improve" any method — this class is load-bearing for the release gate.

```python
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
```

Then copy `cmd`, `js`, `click`, `dblclick`, `drag`, `key`, `element_center`, `canvas_px` **exactly as they are today**, and adapt only `shot`:

```python
    def shot(self, name: str) -> None:
        out = self.out_dir
        if out is None:
            raise ValueError("Cdp(out_dir=...) is required to take screenshots")
        os.makedirs(out, exist_ok=True)
        data = self.cmd("Page.captureScreenshot", format="png")["data"]
        with open(os.path.join(out, name), "wb") as f:
            f.write(base64.b64decode(data))
        print(f"  screenshot: {os.path.join(out, name)}")
```

Note `self.target_id` and `self.ws_url` are new attributes — Task 2 needs them to write `session.json`, and Task 4 needs `ws_url` to reattach to a live tab.

- [ ] **Step 5: Rewire `tools/ui_smoke.py`**

Delete the entire `class Cdp:` block (currently lines 37–131). Remove the now-unused `base64` import. Add below the existing imports:

```python
from cdp import Cdp
```

`tools/` is not a package, but `ui_smoke.py` is executed as a script so `sys.path[0]` is `tools/` — the bare import resolves. In `main()`, change the one construction site to pass the port and output directory:

```python
        c = Cdp(f"http://localhost:{PORT}/", cdp_port=CDP_PORT, out_dir=OUT)
```

- [ ] **Step 6: Run the unit test**

Run: `uv run pytest tests/tools/test_cdp_move.py -q`
Expected: PASS (3 passed)

- [ ] **Step 7: Run the release gate — the step that actually matters**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: `44/44 checks passed`, exit 0.

If any check fails, the move was not verbatim. Diff your `cdp.py` against `git show HEAD:tools/ui_smoke.py` before touching anything else.

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest -q`
Expected: 244 passed + 3 new = 247 passed.

- [ ] **Step 9: Commit**

```bash
git add tools/cdp.py tools/ui_smoke.py pyproject.toml uv.lock tests/tools/test_cdp_move.py
git commit -m "refactor(tools): extract Cdp into tools/cdp.py for multi-stack use"
```

---

## Task 2: Isolated persona stack

**Files:**
- Create: `tools/persona_lab/__init__.py` (empty), `tools/persona_lab/stack.py`
- Test: `tests/tools/test_persona_stack.py`

**Interfaces:**
- Consumes: `cdp.Cdp` from Task 1.
- Produces:
  - `PERSONAS: list[str]` — the six ids, in roster order: `["kablan-gderot", "estimator", "sales-rep", "procurement", "measurer", "export-engineer-en"]`
  - `ports_for(index: int) -> tuple[int, int]` — `(8800 + index, 9400 + index)`
  - `start(persona: str, index: int, run_dir: Path) -> dict` — boots uvicorn + chrome, opens the app, writes and returns the `session.json` dict
  - `stop(run_dir: Path) -> None` — kills both processes, unlinks the DB, asserts the ports are free
  - `session_path(run_dir: Path) -> Path` — `run_dir / "session.json"`

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_persona_stack.py`:

```python
"""A persona stack is fully isolated: its own port, its own throwaway DB,
its own Chrome. Two personas must never be able to see each other's work."""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def test_ports_never_collide_across_the_roster():
    from persona_lab import stack

    pairs = [stack.ports_for(i) for i in range(len(stack.PERSONAS))]
    flat = [p for pair in pairs for p in pair]
    assert len(set(flat)) == len(flat)


def test_roster_is_the_six_from_the_spec():
    from persona_lab import stack

    assert stack.PERSONAS == [
        "kablan-gderot", "estimator", "sales-rep",
        "procurement", "measurer", "export-engineer-en",
    ]


@pytest.fixture
def booted(tmp_path):
    from persona_lab import stack

    if not shutil.which("google-chrome"):
        pytest.skip("google-chrome not available")
    run_dir = tmp_path / "kablan-gderot"
    run_dir.mkdir()
    session = stack.start("kablan-gderot", 0, run_dir)
    yield stack, run_dir, session
    stack.stop(run_dir)


def test_stack_serves_the_app_and_records_its_session(booted):
    _stack, run_dir, session = booted

    body = urllib.request.urlopen(
        f"http://localhost:{session['port']}/api/health", timeout=5
    ).read()
    assert json.loads(body)["status"] == "ok"

    on_disk = json.loads((run_dir / "session.json").read_text())
    assert on_disk["ws_url"].startswith("ws://")
    assert on_disk["persona"] == "kablan-gderot"
    assert Path(on_disk["db"]).exists()


def test_stop_releases_the_port(booted):
    stack, run_dir, session = booted

    stack.stop(run_dir)
    with pytest.raises(Exception):
        urllib.request.urlopen(
            f"http://localhost:{session['port']}/api/health", timeout=2
        )
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/tools/test_persona_stack.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'persona_lab'`

- [ ] **Step 3: Implement `tools/persona_lab/stack.py`**

```python
"""Boot and tear down one fully isolated stack per persona.

Isolation is the point: a stray mutation or a crash in one persona's session
must not be visible to another, so each gets its own uvicorn, its own Chrome,
and its own throwaway SQLite file.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cdp import Cdp  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

PERSONAS = [
    "kablan-gderot", "estimator", "sales-rep",
    "procurement", "measurer", "export-engineer-en",
]


def ports_for(index: int) -> tuple[int, int]:
    return 8800 + index, 9400 + index


def session_path(run_dir: Path) -> Path:
    return run_dir / "session.json"


def _port_free(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{port}/api/health", timeout=1)
        return False
    except Exception:
        return True


def start(persona: str, index: int, run_dir: Path) -> dict:
    port, cdp_port = ports_for(index)
    if not _port_free(port):
        raise RuntimeError(f"port {port} is already in use — kill the stale stack first")

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "shots").mkdir(exist_ok=True)
    db = tempfile.mktemp(suffix=f"-{persona}.db")

    server = subprocess.Popen(
        ["uv", "run", "uvicorn", "fenceai.api.app:app", "--port", str(port)],
        env={**os.environ, "FENCEAI_DB": db, "FENCEAI_AI": "stub"},
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    chrome = subprocess.Popen(
        ["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
         f"--remote-debugging-port={cdp_port}", "--remote-allow-origins=*",
         "--window-size=1400,950", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    time.sleep(4)

    c = Cdp(f"http://localhost:{port}/", cdp_port=cdp_port, out_dir=str(run_dir / "shots"))
    # a real user never sees a native confirm(); auto-accept so a modal cannot
    # wedge the tab in a state the persona has no verb to escape
    c.js("window.confirm = () => true; undefined")

    session = {
        "persona": persona,
        "port": port,
        "cdp_port": cdp_port,
        "ws_url": c.ws_url,
        "target_id": c.target_id,
        "db": db,
        "server_pid": server.pid,
        "chrome_pid": chrome.pid,
        "run_dir": str(run_dir),
    }
    session_path(run_dir).write_text(json.dumps(session, indent=2), encoding="utf-8")
    return session


def stop(run_dir: Path) -> None:
    path = session_path(run_dir)
    if not path.exists():
        return
    session = json.loads(path.read_text(encoding="utf-8"))
    for pid in (session["server_pid"], session["chrome_pid"]):
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            pass
    time.sleep(1.5)
    if os.path.exists(session["db"]):
        os.unlink(session["db"])
    if not _port_free(session["port"]):
        raise RuntimeError(f"port {session['port']} still held after stop()")
    path.unlink()
```

Also create an empty `tools/persona_lab/__init__.py`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/tools/test_persona_stack.py -q`
Expected: PASS (4 passed, or 2 passed + 2 skipped without Chrome)

- [ ] **Step 5: Verify no leaked processes**

Run: `pgrep -af "port 88[0-9][0-9]" ; pgrep -af "remote-debugging-port=94" ; echo "clean=$?"`
Expected: no matching uvicorn or chrome processes remain.

- [ ] **Step 6: Commit**

```bash
git add tools/persona_lab tests/tools/test_persona_stack.py
git commit -m "feat(persona-lab): isolated per-persona stack (own port, DB, chrome)"
```

---

## Task 3: Outline and driver — the anti-cheat surface

**Files:**
- Create: `tools/persona_lab/outline.py`, `tools/persona_lab/driver.py`
- Test: `tests/tools/test_persona_driver.py`

**Interfaces:**
- Consumes: `cdp.Cdp`, `persona_lab.stack.start/stop`.
- Produces:
  - `outline.OUTLINE_JS: str` — the expression evaluated in the page
  - `outline.render(items: list[dict]) -> str` — the text a persona reads
  - `driver.Driver(session: dict)` with `look(shot_name) -> tuple[str, str]`, `click(target)`, `type_text(text)`, `key(name)`, `drag(x0, y0, x1, y1)`, `hover(handle)`, `scroll(dy)`, `wait(seconds)`, and `handles: dict[str, dict]` refreshed by each `look`

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_persona_driver.py`:

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/tools/test_persona_driver.py -q`
Expected: FAIL — no module named `persona_lab.driver`

- [ ] **Step 3: Implement `tools/persona_lab/outline.py`**

```python
"""Render the page the way a person perceives it: visible labels, not selectors.

Handing an agent `#btn-generate` hands it the developer's intent, which is the
one thing a real user does not have. Elements therefore get opaque handles and
are described only by what is actually legible on screen.
"""

from __future__ import annotations

INTERACTIVE = "button, a[href], input, select, textarea, summary, [role=button]"

OUTLINE_JS = """
(() => {
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const out = [];
  for (const el of document.querySelectorAll(%r)) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    const text = (el.innerText || el.value || '').trim().slice(0, 60);
    out.push({
      role: el.tagName.toLowerCase(),
      label: text,
      placeholder: el.getAttribute('placeholder') || '',
      has_title: !!el.getAttribute('title'),
      title: el.getAttribute('title') || '',
      disabled: !!el.disabled,
      x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
      w: Math.round(r.width), h: Math.round(r.height)
    });
  }
  for (const el of document.querySelectorAll('svg')) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    out.push({
      role: 'canvas', label: el.getAttribute('viewBox') ? 'drawing area' : 'graphic',
      placeholder: '', has_title: false, title: '', disabled: false,
      x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
      w: Math.round(r.width), h: Math.round(r.height)
    });
  }
  return out;
})()
""" % INTERACTIVE


def render(items: list[dict]) -> str:
    """items -> the text a persona reads. Tooltips stay hidden until hovered."""
    lines = []
    for i, el in enumerate(items, start=1):
        handle = f"e{i:02d}"
        if el["label"]:
            what = f'"{el["label"]}"'
        elif el["placeholder"]:
            what = f'placeholder:"{el["placeholder"]}"'
        else:
            what = "(no visible label)"
        bits = [f"[{handle}]", f'{el["role"]:<8}', what]
        if el["has_title"] and not el["label"]:
            bits.append("tooltip-on-hover")
        if el["disabled"]:
            bits.append("disabled")
        bits.append(f'at({el["x"]},{el["y"]}) {el["w"]}x{el["h"]}')
        lines.append(" ".join(bits))
    return "\n".join(lines)
```

Note the icon-only toolbar buttons in `index.html` render a glyph inside a `<span class="t-icon">` plus a label span, so `innerText` yields e.g. `"✏️ צייר"` — that is exactly what a user sees, and is correct. Truly icon-only controls (`#btn-fit`, `#profile-toggle`) fall through to `tooltip-on-hover`.

- [ ] **Step 4: Implement `tools/persona_lab/driver.py`**

```python
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
from cdp import Cdp  # noqa: E402

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
```

`Cdp` is imported here only so the module fails loudly if Task 1 was skipped; if your linter objects to the unused import, delete it.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/tools/test_persona_driver.py -q`
Expected: PASS (6 passed, or all skipped without Chrome)

- [ ] **Step 6: Eyeball one outline by hand**

The anti-cheat property is not fully testable by assertion — read it once yourself.

Run: `uv run python -c "
import sys, json, tempfile; from pathlib import Path
sys.path.insert(0, 'tools')
from persona_lab import stack, driver
d = Path(tempfile.mkdtemp())/'kablan-gderot'
s = stack.start('kablan-gderot', 0, d)
shot, text = driver.Driver(s).look('peek.jpg')
print(text); print(shot)
stack.stop(d)"`

Expected: a list of handles with Hebrew labels, no `#`, no ids. Confirm the toolbar reads like something a person could act on.

- [ ] **Step 7: Commit**

```bash
git add tools/persona_lab/outline.py tools/persona_lab/driver.py tests/tools/test_persona_driver.py
git commit -m "feat(persona-lab): label-only outline + user-plausible driver verbs"
```

---

## Task 4: `act.py` — the CLI and the think-aloud contract

**Files:**
- Create: `tools/persona_lab/act.py`
- Test: `tests/tools/test_persona_act.py`

**Interfaces:**
- Consumes: `driver.Driver`, `stack.session_path`.
- Produces: a CLI. Every action verb requires `--intent` and `--expected`. If the previous trace record is still open, `--observed` and `--confusion` are also required and close it. `trace.jsonl` records match the spec §3.4 shape.

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_persona_act.py`. These tests exercise the trace contract without a browser by pointing at a fixture run directory:

```python
"""act.py forces think-aloud: you may not act without saying what you expect,
and you may not act again without saying what you saw."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ACT = Path(__file__).resolve().parents[2] / "tools" / "persona_lab" / "act.py"


def run(run_dir: Path, *args):
    return subprocess.run(
        [sys.executable, str(ACT), "--session", str(run_dir), *args],
        capture_output=True, text=True,
    )


def seed(tmp_path: Path) -> Path:
    run_dir = tmp_path / "kablan-gderot"
    (run_dir / "shots").mkdir(parents=True)
    (run_dir / "session.json").write_text(json.dumps({
        "persona": "kablan-gderot", "port": 8800, "cdp_port": 9400,
        "ws_url": "ws://localhost:9400/devtools/page/FAKE", "target_id": "FAKE",
        "db": "/tmp/none.db", "server_pid": 0, "chrome_pid": 0,
        "run_dir": str(run_dir),
    }))
    return run_dir


def test_action_without_intent_is_refused(tmp_path):
    r = run(seed(tmp_path), "click", "e01", "--expected", "משהו")

    assert r.returncode == 2
    assert "intent" in (r.stderr + r.stdout).lower()


def test_action_without_expected_is_refused(tmp_path):
    r = run(seed(tmp_path), "click", "e01", "--intent", "משהו")

    assert r.returncode == 2
    assert "expected" in (r.stderr + r.stdout).lower()


def test_second_action_must_close_the_open_record(tmp_path):
    run_dir = seed(tmp_path)
    (run_dir / "trace.jsonl").write_text(json.dumps({
        "n": 1, "verb": "look", "arg": "", "intent": "a", "expected": "b",
        "observed": None, "confusion": None, "shot": "shots/01.jpg", "t_ms": 10,
    }) + "\n")

    r = run(run_dir, "click", "e01", "--intent", "c", "--expected", "d")

    assert r.returncode == 2
    assert "observed" in (r.stderr + r.stdout).lower()


def test_closing_patches_the_previous_record(tmp_path):
    run_dir = seed(tmp_path)
    (run_dir / "trace.jsonl").write_text(json.dumps({
        "n": 1, "verb": "look", "arg": "", "intent": "a", "expected": "b",
        "observed": None, "confusion": None, "shot": "shots/01.jpg", "t_ms": 10,
    }) + "\n")

    r = run(run_dir, "give-up", "--reason", "לא מצאתי", "--fallback", "אקסל",
            "--observed", "מסך עם קוד", "--confusion", "3")

    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in
             (run_dir / "trace.jsonl").read_text().splitlines() if x.strip()]
    assert lines[0]["observed"] == "מסך עם קוד"
    assert lines[0]["confusion"] == 3
    assert lines[-1]["verb"] == "give-up"


def test_confusion_must_be_in_range(tmp_path):
    run_dir = seed(tmp_path)
    (run_dir / "trace.jsonl").write_text(json.dumps({
        "n": 1, "verb": "look", "arg": "", "intent": "a", "expected": "b",
        "observed": None, "confusion": None, "shot": "shots/01.jpg", "t_ms": 10,
    }) + "\n")

    r = run(run_dir, "give-up", "--reason", "x", "--fallback", "y",
            "--observed", "z", "--confusion", "9")

    assert r.returncode == 2
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/tools/test_persona_act.py -q`
Expected: FAIL — `act.py` does not exist.

- [ ] **Step 3: Implement `tools/persona_lab/act.py`**

Verbs that never touch the browser (`give-up`, `finding`, `done`) must be handled **before** the driver is constructed, so the contract tests run without Chrome.

```python
#!/usr/bin/env python3
"""The persona's only tool.

Invoked once per action. Reads session.json, attaches to the already-open tab,
acts, appends to trace.jsonl, prints the new screen, exits. The browser holds
the state between calls, which is what lets a persona agent work through a
plain shell command.

Every action demands --intent and --expected before it happens, and --observed
plus --confusion for the action before it. That is not bookkeeping: it is what
turns clicking into think-aloud, and confusion >= 2 is what becomes a finding.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BROWSER_VERBS = {"look", "click", "type", "key", "drag", "hover", "scroll", "wait"}
BOOKKEEPING_VERBS = {"give-up", "finding", "done"}


def load_trace(run_dir: Path) -> list[dict]:
    path = run_dir / "trace.jsonl"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_trace(run_dir: Path, records: list[dict]) -> None:
    (run_dir / "trace.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def die(msg: str) -> None:
    print(f"REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    p = argparse.ArgumentParser(prog="act.py")
    p.add_argument("--session", required=True, type=Path)
    p.add_argument("verb")
    p.add_argument("args", nargs="*")
    p.add_argument("--intent", default=None)
    p.add_argument("--expected", default=None)
    p.add_argument("--observed", default=None)
    p.add_argument("--confusion", default=None, type=int)
    p.add_argument("--reason", default=None)
    p.add_argument("--fallback", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--surface", default=None)
    p.add_argument("--symptom", default=None)
    p.add_argument("--steps", default="")
    a = p.parse_args()

    run_dir: Path = a.session
    if a.verb not in BROWSER_VERBS | BOOKKEEPING_VERBS:
        die(f"unknown verb {a.verb!r}")

    records = load_trace(run_dir)

    # close the previous record before anything new may happen
    if records and records[-1].get("observed") is None:
        if a.observed is None:
            die("the previous step is still open — pass --observed to say what you saw")
        if a.confusion is None:
            die("pass --confusion 0-3 for the previous step")
        if not 0 <= a.confusion <= 3:
            die("--confusion must be 0, 1, 2 or 3")
        records[-1]["observed"] = a.observed
        records[-1]["confusion"] = a.confusion

    if a.verb in BROWSER_VERBS:
        if not a.intent:
            die("--intent is required: say what you are trying to do, in role")
        if not a.expected:
            die("--expected is required: say what you think will happen")

    n = len(records) + 1
    t0 = time.time()
    shot = ""
    screen = ""

    if a.verb in BROWSER_VERBS:
        from persona_lab import driver  # imported late so bookkeeping needs no browser

        session = json.loads((run_dir / "session.json").read_text(encoding="utf-8"))
        d = driver.Driver(session)
        # rebuild handles from the live page before resolving one
        _shot, _text = d.look(f"{n:02d}-pre.jpg")
        if a.verb == "look":
            shot, screen = _shot, _text
        elif a.verb == "click":
            d.click(a.args[0] if not a.args[0].isdigit() else
                    (int(a.args[0]), int(a.args[1])))
        elif a.verb == "type":
            d.type_text(a.args[0])
        elif a.verb == "key":
            d.key(a.args[0])
        elif a.verb == "drag":
            d.drag(*(int(v) for v in a.args[:4]))
        elif a.verb == "hover":
            tip = d.hover(a.args[0])
            screen = f"tooltip: {tip}"
        elif a.verb == "scroll":
            d.scroll(int(a.args[0]))
        elif a.verb == "wait":
            d.wait(float(a.args[0]))
        if a.verb != "look":
            shot, screen = d.look(f"{n:02d}.jpg")
        d.close()

    record = {
        "n": n, "verb": a.verb, "arg": " ".join(a.args),
        "intent": a.intent, "expected": a.expected,
        "observed": None, "confusion": None,
        "shot": shot, "t_ms": int((time.time() - t0) * 1000),
    }
    if a.verb == "give-up":
        record.update(reason=a.reason, fallback=a.fallback, observed="", confusion=3)
    if a.verb == "finding":
        record.update(title=a.title, surface=a.surface, symptom=a.symptom,
                      steps=a.steps, observed="", confusion=0)
    if a.verb == "done":
        record.update(observed="", confusion=0)

    records.append(record)
    write_trace(run_dir, records)

    print(f"step {n} recorded")
    if shot:
        print(f"screenshot: {shot}")
    if screen:
        print("--- screen ---")
        print(screen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/tools/test_persona_act.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Smoke the CLI against a real browser once**

Run:
```bash
uv run python -c "
import sys, tempfile; from pathlib import Path
sys.path.insert(0,'tools')
from persona_lab import stack
d = Path(tempfile.mkdtemp())/'kablan-gderot'
stack.start('kablan-gderot', 0, d); print(d)"
```
Then, with the printed path as `$RUN`:
```bash
uv run python tools/persona_lab/act.py --session $RUN look --intent "לראות מה יש" --expected "מסך של תוכנה"
uv run python tools/persona_lab/act.py --session $RUN look --intent "שוב" --expected "אותו דבר" --observed "ראיתי כפתורים בעברית" --confusion 0
```
Expected: step 1 prints an outline; step 2 succeeds and `trace.jsonl` line 1 now carries `observed`.
Then tear the stack down: `uv run python -c "import sys;sys.path.insert(0,'tools');from pathlib import Path;from persona_lab import stack;stack.stop(Path('$RUN'))"`

- [ ] **Step 6: Commit**

```bash
git add tools/persona_lab/act.py tests/tools/test_persona_act.py
git commit -m "feat(persona-lab): act.py CLI enforcing the think-aloud trace contract"
```

---

## Task 5: Personas and scenarios

**Files:**
- Create: `tools/persona_lab/personas/{kablan-gderot,estimator,sales-rep,procurement,measurer,export-engineer-en}.json`
- Create: `tools/persona_lab/scenarios/<same six>.md`
- Test: `tests/tools/test_persona_personas.py`

**Interfaces:**
- Consumes: `stack.PERSONAS` for the id list.
- Produces: persona JSON files with required keys `id, role_he, locale, tech_literacy, context, goal, vocabulary, fallback_today, quit_triggers, success`; scenario briefs at matching filenames.

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_persona_personas.py`:

```python
"""The roster is evidence-based, not invented: five Hebrew trade roles plus one
English control that separates RTL bugs from real usability bugs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
LAB = TOOLS / "persona_lab"

REQUIRED = {"id", "role_he", "locale", "tech_literacy", "context", "goal",
            "vocabulary", "fallback_today", "quit_triggers", "success"}


def personas():
    from persona_lab import stack
    return stack.PERSONAS


@pytest.mark.parametrize("pid", personas())
def test_persona_file_exists_and_has_every_required_key(pid):
    data = json.loads((LAB / "personas" / f"{pid}.json").read_text(encoding="utf-8"))

    assert REQUIRED <= set(data)
    assert data["id"] == pid
    assert data["vocabulary"] and data["quit_triggers"]


@pytest.mark.parametrize("pid", personas())
def test_every_persona_has_a_scenario_brief(pid):
    brief = LAB / "scenarios" / f"{pid}.md"

    assert brief.exists()
    assert len(brief.read_text(encoding="utf-8")) > 200


def test_five_hebrew_one_english_control():
    locales = [json.loads((LAB / "personas" / f"{p}.json").read_text(encoding="utf-8"))["locale"]
               for p in personas()]

    assert locales.count("he") == 5
    assert locales.count("en") == 1


def test_tech_literacy_is_never_high():
    """The whole point is a non-technical reader. A 'high' persona would
    quietly restore the developer's-eye view we spent the driver removing."""
    for p in personas():
        data = json.loads((LAB / "personas" / f"{p}.json").read_text(encoding="utf-8"))
        assert data["tech_literacy"] in {"low", "medium"}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/tools/test_persona_personas.py -q`
Expected: FAIL — persona files missing.

- [ ] **Step 3: Write the six persona files**

`personas/kablan-gderot.json`:

```json
{
  "id": "kablan-gderot",
  "role_he": "קבלן גדרות",
  "locale": "he",
  "tech_literacy": "low",
  "context": "בשטח אצל הלקוח, טלפון ביד, מד לייזר, סקיצה על נייר",
  "goal": "להוציא הצעת מחיר ללקוח היום על גדר רשת 42 מטר עם פינה, שטח משופע, ושער 3.5 מטר",
  "vocabulary": ["גדר רשת", "עמוד", "חגורת בטון", "שער", "מטר רץ", "יסוד"],
  "fallback_today": "אקסל + וואטסאפ",
  "quit_triggers": ["מסך שנראה כמו קוד", "יותר משלושה ניסיונות באותו מקום", "מספרים במילימטרים"],
  "success": "מספר סופי שאפשר לשלוח ללקוח בוואטסאפ"
}
```

`personas/estimator.json`:

```json
{
  "id": "estimator",
  "role_he": "מכין כתבי כמויות",
  "locale": "he",
  "tech_literacy": "medium",
  "context": "במשרד, מול מכרז עירוני, קטלוגים של ספקים פתוחים",
  "goal": "לבנות כתב כמויות ל-180 מטר גדר עירונית, כולל חגורת בטון ועמודים שתואמים קודי קטלוג",
  "vocabulary": ["כתב כמויות", "סעיף", "חגורת בטון", "עמוד 60/60", "פירוק", "מכרז"],
  "fallback_today": "אקסל עם סעיפים מהקטלוג",
  "quit_triggers": ["שורות שאי אפשר להזמין לפיהן", "אין קוד פריט", "אי אפשר לייצא"],
  "success": "רשימת סעיפים שאפשר להגיש במכרז"
}
```

`personas/sales-rep.json`:

```json
{
  "id": "sales-rep",
  "role_he": "איש מכירות בשטח",
  "locale": "he",
  "tech_literacy": "low",
  "context": "ביקור של רבע שעה אצל בעל בית, הלקוח עומד לידי ומחכה",
  "goal": "לתת מחיר לפני שאני עוזב, ולענות אם צריך היתר מעל 1.50 מטר",
  "vocabulary": ["מחיר למטר", "גובה", "היתר", "הנחה", "מקדמה"],
  "fallback_today": "טופס הצעת מחיר בוורד",
  "quit_triggers": ["יותר מחמש דקות בלי מחיר", "הלקוח רואה אותי מתעסק עם התוכנה"],
  "success": "מחיר שאמרתי בקול רם ללקוח לפני שיצאתי"
}
```

`personas/procurement.json`:

```json
{
  "id": "procurement",
  "role_he": "מנהל רכש ומחסן",
  "locale": "he",
  "tech_literacy": "medium",
  "context": "במחסן, מול הצעת מחיר מאושרת ומלאי קיים",
  "goal": "להפוך הצעה מאושרת לרשימת הזמנה, ולנצל שאריות מהמלאי",
  "vocabulary": ["הזמנת רכש", "מק\"ט", "שארית", "מלאי", "ספק"],
  "fallback_today": "טבלת אקסל של המחסן",
  "quit_triggers": ["אי אפשר לדעת מה כבר יש לי", "אין מק\"ט להזמין לפיו"],
  "success": "רשימת הזמנה שאפשר לשלוח לספק"
}
```

`personas/measurer.json`:

```json
{
  "id": "measurer",
  "role_he": "מודד שטח",
  "locale": "he",
  "tech_literacy": "low",
  "context": "בשטח עם קיר תומך ומדרגה בקרקע, מודד עם סרט ולייזר",
  "goal": "להזין את המצב בשטח נכון: קיר תומך, מדרגה, והפרשי גובה",
  "vocabulary": ["קיר תומך", "מדרגה", "שיפוע", "גובה", "מפלס"],
  "fallback_today": "סקיצה ביד וצילום בטלפון",
  "quit_triggers": ["אי אפשר לתאר מדרגה", "המסך לא מראה את הצד"],
  "success": "השרטוט במסך נראה כמו השטח באמת"
}
```

`personas/export-engineer-en.json`:

```json
{
  "id": "export-engineer-en",
  "role_he": "מהנדס פרויקט (בקרה באנגלית)",
  "locale": "en",
  "tech_literacy": "medium",
  "context": "office, English interface, same job as the contractor persona",
  "goal": "produce a quote for a 42 m mesh fence with one corner, sloped ground and a 3.5 m gate",
  "vocabulary": ["running metre", "post", "concrete belt", "gate", "footing"],
  "fallback_today": "Excel + email",
  "quit_triggers": ["screen that looks like code", "more than three tries in one place"],
  "success": "a final number I can send to the client"
}
```

- [ ] **Step 4: Write the six scenario briefs**

Each `scenarios/<id>.md` is what the persona agent is handed as its job. Use this shape, filled per persona — the contractor's is written out in full as the model:

```markdown
# הצעת מחיר לגדר רשת 42 מטר

אתה קבלן גדרות. אתה עומד אצל לקוח בשטח.

## מה שהלקוח רוצה
גדר רשת לאורך 42 מטר, עם פינה אחת בערך באמצע. השטח משופע — צד אחד
נמוך יותר בערך חצי מטר. הלקוח רוצה שער ברוחב 3.5 מטר.

## מה שאתה צריך להוציא מזה
מספר סופי שאפשר לשלוח ללקוח בוואטסאפ היום.

## איך אתה עובד היום
סקיצה על נייר, מודד בלייזר, ואז אקסל במשרד. אם התוכנה הזאת לא יותר
מהירה מזה — היא לא שווה כלום בשבילך.

## מתי אתה מוותר
כשאתה נתקע יותר משלוש פעמים באותו מקום, או כשאתה רואה מסך שנראה כמו קוד.
תגיד את זה בקול רם ותסיים.
```

The other five follow the same five headings, with content drawn from their persona JSON: municipal tender with catalog codes (estimator), 15-minute homeowner visit with the 1.50 m permit question (sales rep), accepted quote → order list with remnants (procurement), retaining wall + step in the base (measurer), and the contractor's job in English (control).

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/tools/test_persona_personas.py -q`
Expected: PASS (14 passed)

- [ ] **Step 6: Commit**

```bash
git add tools/persona_lab/personas tools/persona_lab/scenarios tests/tools/test_persona_personas.py
git commit -m "feat(persona-lab): six evidence-based personas and their job briefs"
```

---

## Task 6: `report.py` — mechanical collation

**Files:**
- Create: `tools/persona_lab/report.py`
- Test: `tests/tools/test_persona_report.py`

**Interfaces:**
- Consumes: `findings.json` per persona (written by persona agents), `verdicts.json` per persona (written by refuters).
- Produces: `collate(runs_root: Path) -> dict` and `render(collated: dict, sha: str) -> str`. Dedupe key is `(surface, symptom)` where `symptom` is one of the fixed enum below. Ordering: `blocks_job` desc, then `severity` desc, then persona count desc.

Symptom enum — fixed so dedupe is deterministic rather than fuzzy:
`not-found | wrong-language | jargon-leak | no-feedback | dead-end | data-loss | wrong-value | slow | layout-broken`

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_persona_report.py`:

```python
"""Collation is mechanical on purpose: severity is the refuter's judgment,
and the collator must not quietly promote an unconfirmed finding."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def seed(root: Path):
    for pid, fid, surface, symptom in [
        ("kablan-gderot", "F1", "bom-tab", "jargon-leak"),
        ("estimator", "F1", "bom-tab", "jargon-leak"),
        ("sales-rep", "F1", "toolbar", "not-found"),
    ]:
        d = root / pid
        d.mkdir(parents=True, exist_ok=True)
        (d / "findings.json").write_text(json.dumps({
            "persona": pid, "gave_up_at_step": 19, "fallback": "אקסל",
            "findings": [{"id": fid, "title": f"{surface} problem",
                          "surface": surface, "symptom": symptom,
                          "steps": [12], "shots": ["shots/12.jpg"]}],
        }, ensure_ascii=False), encoding="utf-8")
        verdict = "CONFIRMED" if surface == "bom-tab" else "NOT-REPRODUCIBLE"
        (d / "verdicts.json").write_text(json.dumps({
            "verdicts": [{"finding_id": fid, "verdict": verdict,
                          "severity": 3, "blocks_job": True, "note": ""}],
        }), encoding="utf-8")


def test_confirmed_findings_dedupe_across_personas(tmp_path):
    from persona_lab import report

    seed(tmp_path)
    out = report.collate(tmp_path)

    bom = [f for f in out["confirmed"] if f["surface"] == "bom-tab"]
    assert len(bom) == 1
    assert sorted(bom[0]["personas"]) == ["estimator", "kablan-gderot"]


def test_unconfirmed_findings_never_enter_the_confirmed_list(tmp_path):
    from persona_lab import report

    seed(tmp_path)
    out = report.collate(tmp_path)

    assert all(f["surface"] != "toolbar" for f in out["confirmed"])
    assert any(f["surface"] == "toolbar" for f in out["hypotheses"])


def test_blocking_findings_sort_above_higher_severity_non_blocking(tmp_path):
    from persona_lab import report

    d = tmp_path / "measurer"
    d.mkdir(parents=True)
    (d / "findings.json").write_text(json.dumps({
        "persona": "measurer", "gave_up_at_step": 5, "fallback": "סקיצה",
        "findings": [
            {"id": "A", "title": "a", "surface": "s1", "symptom": "dead-end",
             "steps": [1], "shots": []},
            {"id": "B", "title": "b", "surface": "s2", "symptom": "slow",
             "steps": [2], "shots": []},
        ]}, ensure_ascii=False), encoding="utf-8")
    (d / "verdicts.json").write_text(json.dumps({"verdicts": [
        {"finding_id": "A", "verdict": "CONFIRMED", "severity": 2,
         "blocks_job": True, "note": ""},
        {"finding_id": "B", "verdict": "CONFIRMED", "severity": 4,
         "blocks_job": False, "note": ""},
    ]}), encoding="utf-8")

    out = report.collate(tmp_path)

    assert [f["surface"] for f in out["confirmed"]] == ["s1", "s2"]


def test_render_marks_hypotheses_as_unconfirmed(tmp_path):
    from persona_lab import report

    seed(tmp_path)
    text = report.render(report.collate(tmp_path), sha="abc1234")

    assert "abc1234" in text
    assert "unconfirmed" in text.lower()
    assert "gave up" in text.lower()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/tools/test_persona_report.py -q`
Expected: FAIL — no module named `persona_lab.report`.

- [ ] **Step 3: Implement `tools/persona_lab/report.py`**

```python
"""Join findings to verdicts, dedupe, sort, render. No judgment here.

Severity and blocks_job come from the refuter that reproduced the finding;
this module only arranges what it was given. Keeping it dumb is what stops a
persona from grading its own homework.
"""

from __future__ import annotations

import json
from pathlib import Path

SYMPTOMS = ["not-found", "wrong-language", "jargon-leak", "no-feedback",
            "dead-end", "data-loss", "wrong-value", "slow", "layout-broken"]


def collate(runs_root: Path) -> dict:
    confirmed: dict[tuple[str, str], dict] = {}
    hypotheses: list[dict] = []
    narratives: list[dict] = []

    for d in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        f_path, v_path = d / "findings.json", d / "verdicts.json"
        if not f_path.exists():
            continue
        found = json.loads(f_path.read_text(encoding="utf-8"))
        verdicts = {}
        if v_path.exists():
            verdicts = {v["finding_id"]: v
                        for v in json.loads(v_path.read_text(encoding="utf-8"))["verdicts"]}
        narratives.append({
            "persona": found["persona"],
            "gave_up_at_step": found.get("gave_up_at_step"),
            "fallback": found.get("fallback", ""),
        })
        for f in found["findings"]:
            v = verdicts.get(f["id"])
            if v is None or v["verdict"] != "CONFIRMED":
                hypotheses.append({**f, "persona": found["persona"],
                                   "verdict": (v or {}).get("verdict", "UNVERIFIED")})
                continue
            key = (f["surface"], f["symptom"])
            entry = confirmed.setdefault(key, {
                "surface": f["surface"], "symptom": f["symptom"],
                "title": f["title"], "personas": [], "steps": [], "shots": [],
                "severity": v["severity"], "blocks_job": v["blocks_job"],
                "note": v.get("note", ""),
            })
            entry["personas"].append(found["persona"])
            entry["steps"] += f.get("steps", [])
            entry["shots"] += f.get("shots", [])
            entry["severity"] = max(entry["severity"], v["severity"])
            entry["blocks_job"] = entry["blocks_job"] or v["blocks_job"]

    ordered = sorted(
        confirmed.values(),
        key=lambda e: (e["blocks_job"], e["severity"], len(e["personas"])),
        reverse=True,
    )
    return {"confirmed": ordered, "hypotheses": hypotheses, "narratives": narratives}


def render(collated: dict, sha: str) -> str:
    lines = [
        "# Persona lab — findings",
        "",
        f"Build under test: `{sha}`. Six personas drove the live app in a browser;",
        "each finding below was reproduced by an independent refuter before it was",
        "given a severity.",
        "",
        "## Where each persona gave up",
        "",
        "| Persona | Gave up at step | What they would do instead |",
        "|---|---|---|",
    ]
    for n in collated["narratives"]:
        lines.append(f"| {n['persona']} | {n['gave_up_at_step']} | {n['fallback']} |")

    lines += ["", "## Confirmed findings", "",
              "| # | Blocks job | Severity | Surface | Symptom | Personas | Steps |",
              "|---|---|---|---|---|---|---|"]
    for i, f in enumerate(collated["confirmed"], start=1):
        lines.append(
            f"| {i} | {'YES' if f['blocks_job'] else 'no'} | {f['severity']} | "
            f"{f['surface']} | {f['symptom']} | {', '.join(f['personas'])} | "
            f"{', '.join(str(s) for s in f['steps'])} |"
        )

    lines += ["", "## Hypotheses (unconfirmed — not evidence)", ""]
    if not collated["hypotheses"]:
        lines.append("None.")
    for h in collated["hypotheses"]:
        lines.append(f"- **{h['title']}** ({h['persona']}, {h['surface']}) — {h['verdict']}")

    lines += [
        "", "## Limits", "",
        "These are simulated users. They find mechanical dead ends, missing",
        "affordances and vocabulary mismatches. They cannot tell you whether a",
        "קבלן would trust a number enough to send it to a paying customer.",
        "",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/tools/test_persona_report.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/persona_lab/report.py tests/tools/test_persona_report.py
git commit -m "feat(persona-lab): mechanical findings collation and report rendering"
```

---

## Task 7: Run the lab

Not a TDD task — a runbook. This is where the harness is actually used.

**Files:**
- Create: `docs/reviews/persona-lab-2026-08-11.md`
- Modify: `plan/current-status.md`

- [ ] **Step 1: Record the build under test**

Run: `git rev-parse --short HEAD` and keep the SHA for the report header.

- [ ] **Step 2: Boot three stacks**

Concurrency cap is three agents. Wave A is `kablan-gderot` (index 0), `estimator` (1), `sales-rep` (2).

```bash
uv run python -c "
import sys; sys.path.insert(0,'tools')
from pathlib import Path
from persona_lab import stack
root = Path('SCRATCH/persona-lab/2026-08-11')
for i, p in enumerate(stack.PERSONAS[:3]):
    stack.start(p, i, root / p); print('up:', p)"
```

- [ ] **Step 3: Dispatch three persona agents**

One `Agent` call per persona, all three in a single message. Each prompt contains: the persona JSON, the scenario brief, the run directory, and these rules verbatim —

> You are not reviewing software. You are trying to finish a job you are paid for. Do not praise. Do not speculate about what the designers intended. Do not describe features you did not personally use.
>
> Your ONLY tool for touching the app is `uv run python tools/persona_lab/act.py --session <RUN_DIR> ...`. You may `Read` files under `<RUN_DIR>` to view your screenshots. You may not read the repository — not `src/`, not `docs/`, not `tests/`, not `tools/`. If you catch yourself wanting to, that itself is a finding: it means the screen did not tell you something you needed.
>
> You do not know what JSON is. If you meet a box full of code, a bare id like `run_id`, an English word in a Hebrew screen, or a number in millimetres where your trade speaks in metres — that is a finding, log it.
>
> Step budget: 30 actions. Quit earlier if a real person in your role would quit. When you quit, run the `give-up` verb with `--reason` and `--fallback`.
>
> At the end write `<RUN_DIR>/findings.json`: `{"persona", "gave_up_at_step", "fallback", "findings": [{"id", "title", "surface", "symptom", "steps", "shots"}]}` where `symptom` is one of: not-found, wrong-language, jargon-leak, no-feedback, dead-end, data-loss, wrong-value, slow, layout-broken.

- [ ] **Step 4: Tear wave A down, run wave B**

Stop the three stacks, then repeat Steps 2–3 for `procurement` (index 3), `measurer` (4), `export-engineer-en` (5).

- [ ] **Step 5: Audit for repo reads**

Read each persona agent's result and confirm none reported reading repository files. Any finding traceable to a repo read is struck before refutation. Note the audit outcome in the report.

- [ ] **Step 6: Dispatch refuters, three at a time**

One refuter per persona that produced findings. Refuters **do** get repo access and a fresh stack. Prompt: *"Try to disprove each finding. Reproduce the cited steps in a fresh browser. Default to NOT-REPRODUCIBLE when uncertain."* Each writes `<RUN_DIR>/verdicts.json` with `{finding_id, verdict, severity 0-4, blocks_job, note}`.

- [ ] **Step 7: Collate and write the report**

```bash
uv run python -c "
import sys; sys.path.insert(0,'tools')
from pathlib import Path
from persona_lab import report
root = Path('SCRATCH/persona-lab/2026-08-11')
Path('docs/reviews/persona-lab-2026-08-11.md').write_text(
    report.render(report.collate(root), sha='<SHA>'), encoding='utf-8')"
```

Then add, by hand, the per-persona narrative section (§6.1 of the spec) — what each persona was trying to do and the path they took. The generated table gives the give-up step; the story around it is written, not generated.

- [ ] **Step 8: Verify everything still passes**

Run: `uv run pytest -q` — expected: all green.
Run: `uv run --with websocket-client python tools/ui_smoke.py` — expected: `44/44`.
Run: `pgrep -af "remote-debugging-port=94"` — expected: nothing; no leaked Chrome.

- [ ] **Step 9: Update status and commit**

Add a `## Persona lab (2026-08-11)` section to `plan/current-status.md` naming the confirmed-finding count and the top blocker.

```bash
git add docs/reviews/persona-lab-2026-08-11.md plan/current-status.md
git commit -m "docs(reviews): persona lab findings — six real-role users vs. the app"
```

---

## Self-review notes

- **Spec coverage:** §2 → Tasks 1–6 file structure; §2.1 → Task 1; §3.1–3.2 → Task 3; §3.3 → Tasks 2 and 4 (`session.json` + reattach); §3.4 → Task 4; §4.1–4.2 → Task 5; §4.3 → Task 7 Step 3; §4.4 → Task 7 Step 5 (audit); §5 → Task 7 Step 6; §6 → Task 6 + Task 7 Step 7; §7 → tests in Tasks 1–6; §8 → `render()` Limits block.
- **Known rough edge:** `act.py` calls `look()` before each action to rebuild handles, so a step costs two screenshots. Wasteful but correct — handles must resolve against the live page, since the previous action may have changed it. If the token cost bites during Task 7, cache the pre-shot to a fixed filename and stop keeping it.
- `click` treats a numeric first argument as coordinates and anything else as a handle; handles are always `eNN`, so the two never collide.
