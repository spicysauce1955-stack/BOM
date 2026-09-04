"""Which surfaces each company role sees (static/js/role.js).

Fence AI serves three people (`docs/superpowers/specs/2026-09-04-sales-mvp-design.md`):
a **salesperson** who is explicitly non-technical, an **office person** who holds
the inventory and the installation knowledge, and a **super user** who alters and
customises. The repo's older roster in `tools/persona_lab` is engineering-shaped
— `expert`, `knowledge-owner`, `topology-author`, `fulfillment`, `approver` — and
contains nobody non-technical, which is the likeliest reason the UI drifted into
naming stations and spans at a person who sells fences.

Hiding is CSS keyed on `<html data-role>`, so `role.js` holds only the LIST. That
is what makes it testable here instead of by aiming a browser at it.

**The assertion that earns this file** is `test_every_hidden_selector_exists`. A
hide-list is the one kind of list that fails silently: rename `#section-decisions`
tomorrow and sales mode simply starts showing the decision graph to a salesperson,
with every test still green and nothing on screen looking broken. So the list is
checked against the real `index.html` rather than against itself.
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
import { ROLES, SALES_TABS, hiddenFor } from "./js/role.js";

const out = {};
out.roles = ROLES;
out.sales = hiddenFor("sales");
out.all = hiddenFor("all");
out.office = hiddenFor("office");
out.unknown = hiddenFor("nonsense-not-a-role");
out.sales_tabs = SALES_TABS;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    # `-e` with cwd=STATIC, matching test_base_top_module.py: an ES module
    # resolves its imports against its OWN url, so a script written to tmp_path
    # cannot see `./js/` however the cwd is set.
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)



def _live_ids() -> set[str]:
    """Every id the running app actually has: the ones in `index.html`, plus the
    ones a module CREATES.

    `#choices` is the case that forced this. `choices.js` owns its own host and
    inserts it — deliberately, because index.html is not that module's file and
    reaching into another module's subtree is what the module map forbids. So an
    id can be perfectly real and absent from the HTML.

    Scanning the JS for the assignment rather than exempting the id by name keeps
    the check total: rename the host in `choices.js` and this still notices.
    """
    ids = set(re.findall(r'id="([^"]+)"', (STATIC / "index.html").read_text()))
    for mod in (STATIC / "js").glob("*.js"):
        src = mod.read_text()
        ids |= set(re.findall(r'\.id\s*=\s*"([^"]+)"', src))
        ids |= set(re.findall(r'"id":\s*"([^"]+)"', src))
        ids |= set(re.findall(r'\bid:\s*"([^"]+)"', src))
    return ids


def test_the_three_roles_are_the_company_s_and_not_the_pipeline_s(out):
    """`sales` / `office` / `all` name people in the company. Deliberately NOT
    the `persona_lab` roster, which names positions in our pipeline — the two
    lists answer different questions and merging them would put a salesperson on
    a ladder beside `knowledge-owner`."""
    assert out["roles"] == ["sales", "office", "all"]


def test_the_widest_role_hides_nothing(out):
    """`all` must be exactly today's app. It is the default, so a mistake here
    is a feature disappearing for everybody rather than a mode being wrong."""
    assert out["all"] == []


def test_an_unknown_role_hides_nothing_rather_than_everything(out):
    """A stored preference from a future version, or a typo, must degrade to the
    full app. Hiding on an unrecognised role would present a stranger with a
    stripped UI and no way to tell why."""
    assert out["unknown"] == []


def test_sales_is_shown_no_surface_that_decides_how_the_fence_IS_BUILT(out):
    """The line the MVP draws. A salesperson records what was SOLD; bay widths,
    post placement, cut plans, the decision graph and the knowledge behind it are
    the office person's and the super user's work.

    `#gaps` is on the list for a reason worth keeping: a gap is not about this
    job at all — it reports what the knowledge behind EVERY job cannot answer, so
    to a salesperson it reads as a fault in the sale they just made.
    """
    sales = set(out["sales"])
    for selector in ("#tool-pin", "#override-list", "#section-decisions",
                     "#choices", "#inspector", "#gaps"):
        assert selector in sales, selector


def test_sales_keeps_every_surface_that_records_what_was_SOLD(out):
    """The other half, and the one that makes the mode useful rather than merely
    small. What it sits on, how tall, which model, where the gates go, and the
    side view that shows the ground — all of that IS the sale."""
    sales = set(out["sales"])
    for selector in ("#profile", "#model-row", "#site-conditions", "#warnings",
                     "#tool-base", "#tool-height", "#tool-model", "#tool-gate",
                     "#run-events", "#btn-generate"):
        assert selector not in sales, selector


def test_a_promise_made_during_the_sale_keeps_a_home(out):
    """Annotations stay. `Annotation.target_ref` already accepts `run:<id>`, so
    *"a post clear of that window"* — a real thing to promise a customer — can be
    recorded as a note without giving a salesperson post placement.

    It is a NOTE and not an override on purpose: an override is a technical
    instruction that survives into generation, and a promise is a sentence the
    office person has to read and decide about.
    """
    assert '[data-tab="annotations"]' not in set(out["sales"])
    assert "annotations" in out["sales_tabs"]


def test_office_still_hides_the_knowledge_bench(out):
    """`office` is not `all`. The office person holds the inventory and the
    items; authoring RULES is the super user's bench. This is the weakest of the
    three definitions and the one most likely to be wrong — it is asserted so
    that changing it is a decision rather than a drift."""
    assert '[data-tab="knowledge"]' in set(out["office"])
    assert '[data-tab="bom"]' not in set(out["office"])


def test_every_hidden_selector_exists(out):
    """The assertion that earns this file.

    A hide-list naming a selector nothing matches hides nothing, breaks no test,
    and looks fine on screen — sales mode would just quietly start showing a
    salesperson the decision graph. So every selector is resolved against the
    real page.

    Only id and `[data-tab=...]` forms are checked, because those are the two the
    list is allowed to use; a selector in any other shape fails here rather than
    being skipped, which is what keeps the check total.
    """
    ids = _live_ids()
    tabs = set(re.findall(r'data-tab="([^"]+)"',
                          (STATIC / "index.html").read_text()))
    for role in ("sales", "office"):
        for selector in out[role]:
            if selector.startswith("#"):
                assert selector[1:] in ids, f"{role}: no element {selector}"
            elif selector.startswith('[data-tab='):
                name = selector[len('[data-tab="'):-len('"]')]
                assert name in tabs, f"{role}: no tab {selector}"
            else:
                pytest.fail(f"{role}: selector {selector!r} is neither an id "
                            f"nor a [data-tab=...] — this check cannot verify it")


def test_sales_tabs_and_the_hidden_tabs_partition_the_page(out):
    """Every tab is either shown to a salesperson or hidden from one. A tab
    added tomorrow and forgotten would otherwise default to VISIBLE, which is the
    wrong default for a mode whose entire purpose is subtraction."""
    tabs = set(re.findall(r'data-tab="([^"]+)"',
                          (STATIC / "index.html").read_text()))
    hidden = {s[len('[data-tab="'):-len('"]')] for s in out["sales"]
              if s.startswith("[data-tab=")}
    assert set(out["sales_tabs"]) | hidden == tabs
    assert not (set(out["sales_tabs"]) & hidden)
