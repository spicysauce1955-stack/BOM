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
import urllib.request

# Four jobs a fencing company would plausibly have on the books: a straight run,
# an L with a corner, a climb, and a stretch sitting on a built wall.
PORTFOLIO = [
    ("גדר רחוב הזית 3", [(0, 0, 0), (12000, 0, 0)], None),
    ("גדר מגרש 12 — גבעת האלה", [(0, 0, 0), (6000, 0, 1000), (6000, 3000, 1000)], None),
    ("גדר מושב ניר גלים", [(0, 0, 0), (14600, 0, 0)], None),
    ("גדר רחוב הגפן 8", [(0, 0, 0), (7000, 0, 0)], "masonry_wall"),
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


def seed(port: int, *, accept_quotes: bool = True) -> list[dict]:
    """Create the portfolio, generate a strategy for each, and accept a quote.

    An accepted quote is what makes a later change legible as a delta — without
    one there is no baseline to have moved away from.
    """
    made = []
    for name, points, surface in PORTFOLIO:
        project = _post(port, "/api/projects", {"name": name})
        _post(port, f"/api/projects/{project['id']}/topology",
              _topology(points, surface), method="PUT")
        generated = _post(port, f"/api/projects/{project['id']}/generate")
        run_id = generated["result"]["run"]["id"]
        entry = {"project_id": project["id"], "name": name, "run_id": run_id}
        if accept_quotes:
            quote = _post(port, f"/api/runs/{run_id}/quote",
                          {"label": f"הצעה ראשונה — {name}", "author": "seed"})
            _post(port, f"/api/quotes/{quote['id']}/accept")
            entry["quote_id"] = quote["id"]
        made.append(entry)
    return made


if __name__ == "__main__":
    import sys

    print(json.dumps(seed(int(sys.argv[1])), ensure_ascii=False, indent=2))
