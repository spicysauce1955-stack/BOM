"""Give this checkout its own ports.

`tools/persona_lab/stack.py` binds a real port, and it used to bind the SAME real
port for everybody. Two checkouts running `pytest` at once — two worktrees, two
agents, a developer beside CI — collided there and produced 22 errors that read
exactly like genuine failures on a suite where nothing was wrong with either
copy. It cost an afternoon to recognise, which is the real argument: the failure
does not look like a collision, it looks like a bug in whatever you just wrote.

The base is derived from the CHECKOUT PATH rather than randomised, so a rerun in
one worktree lands on the same ports and a stale process is still caught by
`_port_free` instead of being silently stepped around.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

# Room for the persona roster above each base, and clear of 8000 (the dev
# server), 8791 (the browser smoke) and 9333 (its CDP port).
_SPAN = 20
_LOW, _HIGH = 8900, 9200


@pytest.fixture(scope="session", autouse=True)
def _ports_for_this_checkout():
    root = str(Path(__file__).resolve().parents[2])
    digest = int(hashlib.sha256(root.encode()).hexdigest()[:8], 16)
    base = _LOW + (digest % ((_HIGH - _LOW) // _SPAN)) * _SPAN
    os.environ.setdefault("FENCEAI_LAB_PORT_BASE", str(base))
    os.environ.setdefault("FENCEAI_LAB_CDP_BASE", str(base + 10_000))
    yield
