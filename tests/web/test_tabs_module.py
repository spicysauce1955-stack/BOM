"""One path switches a tab (static/js/tabs.js).

`road.js` has to activate the annotations panel, and the only way to do that
today is `.click()` on a button — which, once `#tabs` is hidden for sales, is a
module reaching into a subtree it does not own to poke an invisible element.

So the switch becomes an export, and the click handler calls it. This test holds
the property that makes the export worth having: there is ONE place that moves
the `active` class, so the road and the strip can never disagree about which
panel is showing.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"


def test_tabs_exports_a_programmatic_switch():
    src = (STATIC / "js" / "tabs.js").read_text()
    assert re.search(r"^export function setTab\(", src, re.M), (
        "road.js needs a way to switch panels that is not a click on a hidden "
        "button")


def test_only_set_tab_moves_the_active_class():
    """A second site that adds `.active` to a `.tab` is a second answer to
    which panel is showing. The click handler must delegate, not duplicate."""
    for mod in (STATIC / "js").glob("*.js"):
        src = mod.read_text()
        for line_no, line in enumerate(src.splitlines(), 1):
            if 'classList.add("active")' not in line:
                continue
            assert mod.name == "tabs.js", f"{mod.name}:{line_no} moves .active"
    body = (STATIC / "js" / "tabs.js").read_text()
    set_tab = body[body.index("export function setTab("):]
    set_tab = set_tab[:set_tab.index("\n}\n") + 1]
    assert set_tab.count('classList.add("active")') == 2, (
        "setTab activates exactly the button and its panel")


def test_the_click_handler_delegates_to_set_tab():
    src = (STATIC / "js" / "tabs.js").read_text()
    init = src[src.index("export function initTabs("):]
    init = init[:init.index("\n}\n") + 1]
    assert "setTab(" in init, "initTabs must call setTab, not repeat it"
    assert 'emit("tab-changed"' not in init, (
        "the emit belongs to setTab, or a programmatic switch is silent")


def test_an_unknown_panel_name_is_inert():
    """Spec invariant 8. A step naming a panel that does not exist must be a
    no-op, not a thrown error that stops the road rendering the other five."""
    src = (STATIC / "js" / "tabs.js").read_text()
    set_tab = src[src.index("export function setTab("):]
    set_tab = set_tab[:set_tab.index("\n}\n") + 1]
    assert re.search(r"if \(!btn \|\| !panel\) return;", set_tab), (
        "setTab must guard both lookups before touching anything")
