"""Seed a stack with a portfolio of finished projects.

Two of the run-2 roles are cross-project by nature: the knowledge owner asks
"would this rule change break work I already did?", and the approver asks "what
moved since I accepted?". Against a single project both questions are empty, so
run 1 could not have tested either.

Everything goes through the HTTP API rather than the store, so the seeded state
is reachable exactly the way a user's own work would be.
"""

from __future__ import annotations

import http.cookiejar
import json
import time
import urllib.request

# Relative, not `stack.py`'s own `sys.path`-then-bare-import trick: that trick
# is for reaching `cdp.py`, a SIBLING of the `persona_lab` package, one level
# up. `stack` is a sibling MODULE inside this same package, so the ordinary
# package-relative import is both correct and avoids loading `stack.py` twice
# under two different module names (once as `persona_lab.stack`, once as a
# bare `stack`) the way copying that trick here would have. Every current
# caller reaches this module as `from persona_lab import seed, ...` (the
# tests) — nothing runs `python seed.py` directly — so this is not a
# regression against anything that works today.
from .stack import ADMIN_EMAIL

# The jobs the run-2 briefs refer to by name, in the state the briefs describe.
# `accepted` is what makes a job "delivered": the knowledge owner must be able
# to see that a rule change would move it, and the approver needs a baseline to
# diff against. Jobs still in planning are deliberately left un-accepted.
PORTFOLIO = [
    # named in the knowledge-owner brief: 5 m section, still in planning
    ("גדר רחוב הזית 3", [(0, 0, 0), (5000, 0, 0)], None, False),
    # named in the knowledge-owner brief: 22 m, accepted and delivered
    ("גדר שדרות הדקל", [(0, 0, 0), (22000, 0, 0)], None, True),
    ("גדר מגרש 12 — גבעת האלה", [(0, 0, 0), (6000, 0, 1000), (6000, 3000, 1000)],
     None, True),
    ("גדר מושב ניר גלים", [(0, 0, 0), (14600, 0, 0)], None, False),
    ("גדר רחוב הגפן 8", [(0, 0, 0), (7000, 0, 0)], "masonry_wall", False),
]


def sign_in(port: int, email: str = ADMIN_EMAIL) -> urllib.request.OpenerDirector:
    """Present an identity the way a browser tab does, and keep the cookie.

    Every route but a handful in `auth.EXEMPT_PATHS` — `/api/dev/identity`
    among them — 401s `no_identity` for a caller with no cookie. `stack.py`
    used to paper over that for this module specifically by handing the whole
    server process a `FENCEAI_DEV_USER` default, which authenticated every
    cookie-less caller, not just this one — including the browser's own first
    `GET /api/session`, before it ever reached the real sign-in form. That
    made the form's own sign-in redundant when it ran anyway, and the
    redundant sign-in was the thing racing the app's tab placement.
    Signing in for OURSELVES, the same way the browser does, means the server
    can go back to only trusting a cookie, which is what makes the browser's
    sign-in path exercised — and able to fail loudly — on every run.

    Returns an opener carrying the `fenceai_dev_user` cookie `POST
    /api/dev/identity` sets; every subsequent call this module makes must go
    through it, not through a bare `urlopen`.
    """
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    req = urllib.request.Request(
        f"http://localhost:{port}/api/dev/identity",
        data=json.dumps({"email": email}).encode(),
        method="POST", headers={"Content-Type": "application/json"},
    )
    opener.open(req, timeout=10).close()
    return opener


def _post(opener: urllib.request.OpenerDirector, port: int, path: str,
          body: dict | None = None, method: str = "POST"):
    data = json.dumps(body or {}).encode() if body is not None else b"{}"
    req = urllib.request.Request(
        f"http://localhost:{port}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    return json.load(opener.open(req, timeout=30))


def _topology(points: list[tuple[int, int, int]], surface: str | None) -> dict:
    nodes = [{"id": f"n{i+1}", "x_mm": x, "y_mm": y, "z_mm": z}
             for i, (x, y, z) in enumerate(points)]
    runs = []
    for i in range(len(nodes) - 1):
        run: dict = {"id": f"run{i+1}", "start_node_id": nodes[i]["id"],
                     "end_node_id": nodes[i + 1]["id"],
                     "point_events": [], "interval_events": []}
        if surface and i == 0:
            seg = abs(points[i + 1][0] - points[i][0]) or abs(
                points[i + 1][1] - points[i][1])
            anchor = lambda off: {  # noqa: E731
                "segment_index": 0, "offset_mm": off, "seg_len_at_authoring_mm": seg}
            run["interval_events"] = [{
                "id": f"ev_base{i+1}",
                "start_anchor": anchor(seg // 2), "end_anchor": anchor(seg),
                "payload": {"kind": "base", "surface": surface},
            }]
        runs.append(run)
    return {"nodes": nodes, "runs": runs}


def seed(port: int, *, email: str = ADMIN_EMAIL) -> list[dict]:
    """Create the portfolio, generate a strategy for each, quote the delivered
    ones and accept those quotes.

    An accepted quote is what makes a later change legible as a delta — without
    one there is no baseline to have moved away from. Jobs still in planning
    carry no accepted quote, which is exactly the distinction the knowledge
    owner has to be able to act on.
    """
    opener = sign_in(port, email)
    made = []
    for name, points, surface, accepted in PORTFOLIO:
        project = _post(opener, port, "/api/projects", {"name": name})
        _post(opener, port, f"/api/projects/{project['id']}/topology",
              _topology(points, surface), method="PUT")
        generated = _post(opener, port, f"/api/projects/{project['id']}/generate")
        run_id = generated["result"]["run"]["id"]
        entry = {"project_id": project["id"], "name": name, "run_id": run_id,
                 "accepted": accepted}
        if accepted:
            quote = _post(opener, port, f"/api/runs/{run_id}/quote",
                          {"label": f"הצעה ללקוח — {name}", "author": "seed"})
            _post(opener, port, f"/api/quotes/{quote['id']}/accept")
            entry["quote_id"] = quote["id"]
        made.append(entry)
    return made


def open_project(session: dict, project_id: str, *, expect_name: str = "") -> str:
    """Reload the tab and open a project, asserting the app really has it open.

    There is no job picker in the header any more, so this opens the project
    through the app's own `openProject` — the same module instance the page
    uses — and then asks the app which project is open. Reloading first still
    matters: the session cookie signs the reloaded page straight back in, and
    whatever the page had cached about projects before seeding is gone. Fails
    loudly rather than starting a persona in the wrong world.
    """
    from . import driver as driver_mod

    d = driver_mod.Driver(session)
    try:
        d._cmd("Page.navigate", url=f"http://localhost:{session['port']}/")
        for _ in range(40):
            if d._eval("document.documentElement.dataset.auth === 'in'"):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(
                "the reloaded page never signed back in — the persona would "
                "start on the login screen, not in its project"
            )
        known = d._eval(
            "fetch('/api/projects').then(r => r.json())"
            f".then(list => list.find(p => p.id === {project_id!r}) || null)"
        )
        if not known:
            raise RuntimeError(
                f"project {project_id} is not in the project list after reload — "
                "the persona would start in the wrong project"
            )
        value = d._eval(
            "import('./js/state.js').then(async m => {"
            f" await m.openProject({project_id!r});"
            " (await import('./js/tabs.js')).setTab('canvas');"
            " return m.state.projectId; })"
        )
        if value != project_id:
            raise RuntimeError(
                f"project {project_id} did not open — got {value!r}; "
                "the persona would start in the wrong project"
            )
        if expect_name:
            shown = f"{known.get('label') or ''} {known.get('name') or ''}"
            if expect_name not in shown:
                raise RuntimeError(f"project is called {shown.strip()!r}, expected {expect_name!r}")
        return value
    finally:
        d.close()


if __name__ == "__main__":
    import sys

    print(json.dumps(seed(int(sys.argv[1])), ensure_ascii=False, indent=2))
