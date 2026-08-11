"""tools/cdp.py owns the CDP transport so persona stacks and the smoke suite
can each drive their own Chrome on their own port."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def test_cdp_is_importable_from_its_own_module():
    from cdp import Cdp

    assert inspect.isclass(Cdp)


def test_cdp_port_and_out_dir_are_constructor_arguments():
    from cdp import Cdp

    params = inspect.signature(Cdp.__init__).parameters
    assert params["cdp_port"].default == 9333
    assert params["out_dir"].default is None


def test_ui_smoke_no_longer_defines_its_own_cdp():
    source = (TOOLS / "ui_smoke.py").read_text(encoding="utf-8")
    assert "class Cdp" not in source
    assert "from cdp import Cdp" in source
