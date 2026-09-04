"""The role hide-list exists twice, and these two copies must agree.

`js/role.js` holds the list so it can be reasoned about and tested; `style.css`
holds it again because CSS cannot read a JavaScript array and the hiding has to
be CSS — a module that reached into other modules' subtrees to hide them would
break the one rule the frontend map is built on.

Two copies of a list is a defect generator, and this one fails in the direction
that is hardest to notice: add a surface to `role.js` and forget the stylesheet,
and a salesperson simply keeps seeing it. Every test stays green, the page looks
right, and the mode quietly does not do its job.

So: the sets must be EQUAL, not merely overlapping. A selector in the CSS that
`role.js` does not know about is just as wrong — it hides something no test
describes, and nothing would explain why it vanished.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { ROLES, hiddenFor } from "./js/role.js";
const out = {};
for (const r of ROLES) out[r] = hiddenFor(r);
console.log(JSON.stringify(out));
"""


def _from_js() -> dict[str, set[str]]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return {k: set(v) for k, v in json.loads(proc.stdout).items()}


def _from_css() -> dict[str, set[str]]:
    """Every `html[data-role="X"] <selector>` in the stylesheet, per role.

    `#tabs button[data-tab="x"]` is normalised back to `[data-tab="x"]`: the CSS
    needs the descendant path to beat the tab bar's own rules, and `role.js`
    names the tab. Normalising here rather than making `role.js` carry a CSS
    path keeps the JS list about MEANING and the stylesheet about specificity.
    """
    css = (STATIC / "style.css").read_text()
    out: dict[str, set[str]] = {}
    for role, selector in re.findall(
            r'html\[data-role="(\w+)"\]\s+([^,{\n]+)', css):
        out.setdefault(role, set()).add(
            selector.strip().replace("#tabs button", "").strip())
    return out


@pytest.mark.parametrize("role", ["sales", "office"])
def test_the_stylesheet_hides_exactly_what_the_module_says(role):
    js, css = _from_js(), _from_css()
    assert css.get(role, set()) == js[role], (
        f"{role}: role.js and style.css disagree — "
        f"only in role.js: {js[role] - css.get(role, set())}, "
        f"only in style.css: {css.get(role, set()) - js[role]}")


def test_the_widest_role_has_no_rules_at_all():
    """`all` is today's app. A single `html[data-role="all"]` rule would mean a
    surface disappears for everybody in the default mode, which is the one
    failure of this mechanism that reaches every user at once."""
    assert "all" not in _from_css()
