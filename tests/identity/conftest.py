from __future__ import annotations

import pytest

from fenceai.store.db import Store


@pytest.fixture()
def store(dsn):
    s = Store(dsn)
    try:
        yield s
    finally:
        s.close()
