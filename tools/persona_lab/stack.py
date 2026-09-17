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

#: The account the stack signs in as before any persona looks (see `start()`).
#: Named once because `DevIdentity` (cookie first, env second — `identity/dev.py`)
#: means this same string also has to reach the server as `FENCEAI_DEV_USER`;
#: letting the two spellings drift is exactly how the "always already this
#: account" fact below would stop being true silently.
ADMIN_EMAIL = "admin@example.com"


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
             "FENCEAI_DEV_USER": ADMIN_EMAIL},
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
    # the same way a lab would hand a tester an already-logged-in machine.
    #
    # `DevIdentity` is cookie-first, env-second (`identity/dev.py`), and this
    # process's own `FENCEAI_DEV_USER` above is `ADMIN_EMAIL` — so the very
    # FIRST `GET /api/session` the page makes, before this function does
    # anything at all, already resolves to admin with no cookie in play. By
    # the time `dataset.auth` is readable it has gone `pending` -> `in`
    # directly; it never passes through `out`, and a loop waiting for `out`
    # spins for nothing.
    #
    # That matters for more than a wasted 30s: the ONE thing that shoves an
    # admin/backoffice account onto the Jobs queue tab (`queue.js`'s
    # `on("signed-in", ...)`) fires once per completed sign-in cascade. If this
    # function ALSO submits the form unconditionally, that is a SECOND,
    # redundant sign-in for the same identity, racing the first: `state.project`
    # is often already truthy from the first (automatic) sign-in by the time
    # this function checks it, so it proceeds to set the canvas tab while the
    # second (explicit) sign-in's own async chain — `become()` -> `POST
    # /api/dev/identity` -> `GET /api/session` -> `emit("signed-in", ...)` — is
    # still in flight, and queue.js's synchronous listener on THAT emission
    # flips the tab back to "queue" a few milliseconds later. Confirmed live: a
    # CDP-instrumented run of this exact sequence showed the active tab go
    # canvas -> queue 21ms after `setTab('canvas')` returned, timed to the
    # explicit sign-in's completion, not to anything `openWorkspace()` was
    # still doing.
    #
    # So: only drive the real form (still through it, not a cookie, so a
    # genuinely broken login fails here loudly) when the automatic identity
    # did NOT already land us on the right account. That is the common case
    # today and it means exactly one "signed-in" cascade happens, so nothing
    # is left to race the tab placement below.
    for _ in range(60):
        if c.js("document.documentElement.dataset.auth") != "pending":
            break
        time.sleep(0.5)
    already = c.js(
        "import('./js/state.js').then(m => document.documentElement"
        f".dataset.auth === 'in' && m.state.me?.email === {ADMIN_EMAIL!r})"
    )
    if not already:
        for _ in range(60):
            if c.js("document.documentElement.dataset.auth === 'out'"):
                break
            time.sleep(0.5)
        c.js(f"""document.getElementById('sign-in-email').value = {ADMIN_EMAIL!r};
                document.getElementById('sign-in').requestSubmit(); 'ok'""")
    for _ in range(60):
        if c.js(
            "import('./js/state.js').then(m => document.documentElement"
            f".dataset.auth === 'in' && m.state.me?.email === {ADMIN_EMAIL!r}"
            " && !!m.state.project)"
        ):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError(f"stack could not sign in as {ADMIN_EMAIL}")
    # An admin lands on the Jobs queue; the personas' work starts on the
    # drawing. Nothing after this point can send it back to "queue": the one
    # sign-in cascade able to do that has already completed above.
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
