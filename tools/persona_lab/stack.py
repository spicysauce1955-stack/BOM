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

#: The account the stack signs in as before any persona looks (see `start()`),
#: and the account `seed.py` signs itself in as (`seed.sign_in`'s default) to
#: write the portfolio it seeds. Named once so the two never drift apart.
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
        # No `FENCEAI_DEV_USER` here, deliberately: `DevIdentity` is
        # cookie-first, env-second (`identity/dev.py`), and an env default
        # authenticates EVERY request that carries no cookie — including the
        # browser's own first `GET /api/session`, before this function submits
        # anything. That used to make the real sign-in form below redundant
        # (the page was already `in` as admin), which raced its own tab
        # placement against `queue.js`'s `on("signed-in", ...)` — see the
        # comment below `start()` continues with. Leaving this unset means the
        # page genuinely starts signed OUT, so the form is exercised on every
        # run and a broken interactive login path fails here loudly, not just
        # in the atypical case.
        #
        # `**os.environ` is NOT enough by itself: `tests/conftest.py`'s
        # autouse `_dev_identity` fixture `monkeypatch.setenv`s exactly this
        # variable, for every test in the suite, including whichever test's
        # `os.environ` this line spreads — so under pytest this dict would
        # silently inherit it right back even though nothing here sets it.
        # Popping it is what actually keeps this process's `os.environ` from
        # deciding what the spawned server does; two agents confirmed the
        # RACE was fixed by this file alone before this popped, and the
        # deliberate-break check that is supposed to fail loudly here instead
        # passed silently under `pytest` for exactly this reason.
        #
        # `seed.py` used to be the reason this existed — its `urllib` calls
        # carry no cookie jar by default and the default-deny gate this slice
        # added refuses them with 401 `no_identity`. It now signs itself in
        # (`seed.sign_in`), the same way the browser does, and carries the
        # cookie it gets back — so nothing here needs to authenticate it.
        # `FENCEAI_IDENTITY` is set rather than inherited: it has no default and
        # the app refuses to boot without it, and the only reason this worked was
        # that `tests/conftest.py` puts it in the environment process-wide — so
        # the lab ran under pytest and died from a bare shell. `tools/ui_smoke.py`
        # sets it for the same reason.
        env={**{k: v for k, v in os.environ.items() if k != "FENCEAI_DEV_USER"},
             "FENCEAI_IDENTITY": "dev", "FENCEAI_DB": db, "FENCEAI_AI": "stub"},
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
    # Done through the real form, not a cookie, so a broken interactive login
    # — `wireIdentity()`'s submit handler, `become()`, or the
    # `POST /api/dev/identity` route itself — fails here loudly.
    #
    # With no `FENCEAI_DEV_USER` set above, the page genuinely starts signed
    # OUT: `dataset.auth` goes `pending` -> `out`, so this is now the normal
    # path taken on every run.
    #
    # The `already`-signed-in check below stays anyway, as defensive code, not
    # as the common path: a leftover `fenceai_dev_user` cookie in Chrome's
    # profile from an earlier run (this launches plain `google-chrome`, not a
    # fresh profile per stack) can still land the page `in` before this
    # function touches anything. Skipping a REDUNDANT sign-in for the identity
    # already in place matters because a second, unnecessary one is exactly
    # what raced this stack's own tab placement before: `state.project` can
    # already be truthy from the first sign-in by the time this function
    # checks it, so it would proceed to set the canvas tab while the second
    # sign-in's own async chain — `become()` -> `POST /api/dev/identity` ->
    # `GET /api/session` -> `emit("signed-in", ...)` — is still in flight, and
    # `queue.js`'s synchronous listener on THAT emission flips the tab back to
    # "queue" a few milliseconds later. Confirmed live with a CDP-instrumented
    # timeline: canvas -> queue 21ms after `setTab('canvas')` returned, timed
    # to the redundant sign-in's completion, not to anything `openWorkspace()`
    # was still doing.
    for _ in range(60):
        if c.js("document.documentElement.dataset.auth") != "pending":
            break
        time.sleep(0.5)
    already = c.js(
        "import('./js/state.js').then(m => document.documentElement"
        f".dataset.auth === 'in' && m.state.me?.email === {ADMIN_EMAIL!r})"
    )
    if not already:
        # Wait for whatever `dataset.auth` resolved to above to settle into
        # something that is not the wrong account still signed in — `out` (the
        # expected case now) or `denied` both qualify, and neither one is
        # going to spontaneously become `out` on its own, so there is nothing
        # to gain waiting specifically for that exact string the way the
        # original loop did (it spun for the full timeout on `denied`, which
        # is exactly the latency the `!= "pending"` check above already fixed
        # for the ordinary case).
        for _ in range(60):
            if c.js("document.documentElement.dataset.auth") != "in":
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
        # A broken sign-in must fail LOUDLY, not leak a server and a browser
        # behind it: the exception below used to leave both processes running,
        # holding `port` and `cdp_port` open for whoever ran this next.
        for pid in (server.pid, chrome.pid):
            try:
                os.killpg(pid, signal.SIGTERM)
            except Exception:
                pass
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
