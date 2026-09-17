"""A `Store` on whichever backend this run is testing.

Closed afterwards, because a Postgres connection left open holds the schema
that `pg_dsn` is about to DROP CASCADE, and the drop would block.
"""

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
