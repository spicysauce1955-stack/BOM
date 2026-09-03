"""Every smoke case that exists actually runs.

`tools/ui_smoke.py` is a 4000-line `main()`, so cases live in `_smoke_*(c)`
functions registered in `_CHOICE_CASES`. Four agents added cases concurrently
and two merges collided on that list — one resolution produced TWO assignments,
the second shadowing the first, which parses cleanly and silently drops the
cases it shadows.

A dropped case is worse than a deleted one: the file still contains the
function, a reader still sees it, and the check it makes simply never runs. This
is the cheapest possible guard, and it does not need a browser.
"""

from __future__ import annotations

import ast
from pathlib import Path

SMOKE = Path(__file__).resolve().parents[2] / "tools" / "ui_smoke.py"


def _tree() -> ast.Module:
    return ast.parse(SMOKE.read_text())


def test_the_registration_list_is_assigned_exactly_once():
    """Two assignments parse fine and the later one wins."""
    tree = _tree()
    assigns = [n for n in tree.body
               if (isinstance(n, ast.AnnAssign)
                   and getattr(n.target, "id", "") == "_CHOICE_CASES")
               or (isinstance(n, ast.Assign)
                   and any(getattr(t, "id", "") == "_CHOICE_CASES"
                           for t in n.targets))]
    assert len(assigns) == 1, f"{len(assigns)} assignments — a later one shadows"


def test_every_case_function_defined_is_also_run():
    tree = _tree()
    defined = {n.name for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name.startswith("_smoke_")}
    assigns = [n for n in tree.body
               if (isinstance(n, ast.AnnAssign)
                   and getattr(n.target, "id", "") == "_CHOICE_CASES")]
    registered = {e.id for e in assigns[0].value.elts}
    assert defined == registered, {"defined_not_run": sorted(defined - registered),
                                    "run_not_defined": sorted(registered - defined)}
