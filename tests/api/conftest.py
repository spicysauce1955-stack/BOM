"""Every API test gets its own database, whether it remembered to ask or not.

This is the suite-wide version of a fix that has now been made twice in one file
each time, and the trap it closes is recorded in `plan/open-work.md` §Traps:

> A gate that only goes green on state another test left behind is not testing
> what it claims. `test_s17_1b` passed for months because it was the one gate
> file driving the API without pinning its own database; two agents reported it
> failing and were told it passed. Its red was not evidence, and neither was its
> green.

It bit again while build-order item 8 was being built. `Store.seed_fence_models`
is keyed on `(model_id, version)` and never overwrites — which is right, because
reopening a store must leave an expert's edits and a retirement exactly as they
were found — so a database seeded before a built-in model gained a field keeps
the document from before. Four assertions about a warning on M-LEGACY therefore
passed or failed on the age of a file in the working directory, and the file in
question was 141 MB of accumulated development state.

`autouse`, so a new API test cannot opt out by forgetting. A test that wants a
database of its own with particular contents still sets `FENCEAI_DB` itself in
its own fixture; `monkeypatch` is function-scoped and the later setting wins, so
this makes the floor safe without taking the choice away.

Deliberately NOT a guard that fails when `FENCEAI_DB` is unset. That would have
been a test about tests, and it would have gone red in exactly the situation
where a fresh contributor is least able to read it — while leaving the ambient
database one forgotten fixture away from being read again.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "api-test.db"))
    # The stub AI port too, for the same reason: a test that reaches an
    # interpretation must not depend on what the ambient environment configured.
    # `fenceai/ai/` keeps the whole system working offline and the stub is what
    # makes that true (CLAUDE.md), so it is the honest default here.
    monkeypatch.setenv("FENCEAI_AI", "stub")
