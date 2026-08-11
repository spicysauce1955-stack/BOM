"""Seed a stack with a portfolio of finished projects.

Two of the run-2 roles are cross-project by nature: the knowledge owner asks
"would this rule change break work I already did?", and the approver asks "what
moved since I accepted?". Against a single project both questions are empty, so
run 1 could not have tested either.

Everything goes through the HTTP API rather than the store, so the seeded state
is reachable exactly the way a user's own work would be.
"""

from __future__ import annotations

import json
import time
import urllib.request

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


def _post(port: int, path: str, body: dict | None = None, method: str = "POST"):
    data = json.dumps(body or {}).encode() if body is not None else b"{}"
    req = urllib.request.Request(
        f"http://localhost:{port}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=30))


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


def seed(port: int) -> list[dict]:
    """Create the portfolio, generate a strategy for each, quote the delivered
    ones and accept those quotes.

    An accepted quote is what makes a later change legible as a delta — without
    one there is no baseline to have moved away from. Jobs still in planning
    carry no accepted quote, which is exactly the distinction the knowledge
    owner has to be able to act on.
    """
    made = []
    for name, points, surface, accepted in PORTFOLIO:
        project = _post(port, "/api/projects", {"name": name})
        _post(port, f"/api/projects/{project['id']}/topology",
              _topology(points, surface), method="PUT")
        generated = _post(port, f"/api/projects/{project['id']}/generate")
        run_id = generated["result"]["run"]["id"]
        entry = {"project_id": project["id"], "name": name, "run_id": run_id,
                 "accepted": accepted}
        if accepted:
            quote = _post(port, f"/api/runs/{run_id}/quote",
                          {"label": f"הצעה ללקוח — {name}", "author": "seed"})
            _post(port, f"/api/quotes/{quote['id']}/accept")
            entry["quote_id"] = quote["id"]
        made.append(entry)
    return made


def open_project(session: dict, project_id: str, *, expect_name: str = "") -> str:
    """Reload the tab and select a project, asserting the selection took.

    The app builds its project list at load time. Seeding after the page has
    loaded leaves the new options absent, so assigning `select.value` silently
    does nothing and the persona lands on the seeded demo instead — which is
    exactly what contaminated the first wave of run 2. Reload first, then
    verify, and fail loudly rather than starting a persona in the wrong world.
    """
    from . import driver as driver_mod

    d = driver_mod.Driver(session)
    try:
        d._cmd("Page.navigate", url=f"http://localhost:{session['port']}/")
        time.sleep(4)
        value = d._eval(
            "(() => { const s = document.getElementById('project-select');"
            f" s.value = {project_id!r};"
            " s.dispatchEvent(new Event('change')); return s.value; })()"
        )
        if value != project_id:
            raise RuntimeError(
                f"project {project_id} is not in the selector after reload — "
                f"got {value!r}; the persona would start in the wrong project"
            )
        time.sleep(2)
        if expect_name:
            shown = d._eval(
                "(() => { const s = document.getElementById('project-select');"
                " return s.selectedOptions.length ? s.selectedOptions[0].text : ''; })()"
            )
            if expect_name not in (shown or ""):
                raise RuntimeError(f"selector shows {shown!r}, expected {expect_name!r}")
        return value
    finally:
        d.close()


if __name__ == "__main__":
    import sys

    print(json.dumps(seed(int(sys.argv[1])), ensure_ascii=False, indent=2))
