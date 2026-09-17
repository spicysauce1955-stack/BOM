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

# Roles, taken from the architecture rather than from market research: the
# expert correcting proposals in context is the product's central user
# (foundation §9), and every role below maps onto golden scenarios that exist.
PERSONAS = [
    "expert", "knowledge-owner", "topology-author",
    "fulfillment", "approver",
]


#: What the ports were before they were overridable, and still are by default.
DEFAULT_PORT_BASE = 8800
DEFAULT_CDP_BASE = 9400


def ports_for(index: int) -> tuple[int, int]:
    """The two ports this persona's stack listens on.

    The base is read from the environment and DEFAULTS to what it always was, so
    a single run is unchanged. It is overridable because a hard-coded port is a
    land mine for concurrency: two checkouts running `pytest` at once — two
    worktrees, two agents, a developer beside CI — collided here and produced 22
    errors that read exactly like real failures, on a suite where nothing was
    wrong with either copy.

    `_port_free` below already refuses to start on a busy port, which is the
    right behaviour and not the problem; the problem was that every caller
    wanted the same port.

    **Read at CALL time, not at import.** A module-level `PORT_BASE` was the
    first attempt and it silently did nothing: `stack.py` is imported before any
    fixture runs, so the constant froze at the default and both copies collided
    exactly as before — with the override in place and looking like it worked.
    """
    base = int(os.environ.get("FENCEAI_LAB_PORT_BASE", DEFAULT_PORT_BASE))
    cdp = int(os.environ.get("FENCEAI_LAB_CDP_BASE", DEFAULT_CDP_BASE))
    return base + index, cdp + index


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
        # `FENCEAI_DEV_USER` is what `DevIdentity` resolves a caller to when NO
        # cookie is presented (see `identity/dev.py`) — the same fallback
        # `tests/conftest.py` sets for the whole test suite. Every browser tab
        # this stack drives signs in for itself through the real form below,
        # but `seed.py` talks to this server over plain `urllib`, with no
        # cookie jar at all; without this, the default-deny gate this slice
        # added refuses every one of those calls with 401 `no_identity` before
        # a single project can be seeded.
        env={**os.environ, "FENCEAI_DB": db, "FENCEAI_AI": "stub",
             "FENCEAI_DEV_USER": "admin@example.com"},
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
    # The app opens on a login screen and loads nothing behind it. The personas
    # here are engineering roles evaluating the whole app, which is the admin
    # account's `all` view — so the STACK signs in before any persona looks,
    # the same way a lab would hand a tester an already-logged-in machine. Done
    # through the real form, not a cookie, so a broken login fails here loudly.
    # ...once the app has wired the form: submitted earlier, it posts natively
    # and reloads the page instead of signing in.
    for _ in range(60):
        if c.js("document.documentElement.dataset.auth === 'out'"):
            break
        time.sleep(0.5)
    c.js("""document.getElementById('sign-in-email').value = 'admin@example.com';
            document.getElementById('sign-in').requestSubmit(); 'ok'""")
    for _ in range(60):
        if c.js("import('./js/state.js').then(m => document.documentElement"
                ".dataset.auth === 'in' && !!m.state.project)"):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("stack could not sign in as admin@example.com")
    # An admin lands on the Jobs queue; the personas' work starts on the drawing.
    c.js("import('./js/tabs.js').then(m => { m.setTab('canvas'); return 'ok'; })")

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
