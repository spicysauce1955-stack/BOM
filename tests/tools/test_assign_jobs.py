"""Giving pre-account jobs an owner (tools/assign_jobs.py).

A job with no `created_by` is on nobody's home screen. The choice of owner is a
pure function over the audit log and one named fallback, so it is tested here
rather than by writing a database and reading it back.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from assign_jobs import owner_for  # noqa: E402


def test_the_first_person_in_the_audit_log_owns_the_job():
    """Later saves are whoever edited it since; the earliest person is the
    closest thing to a creator that the data holds."""
    assert owner_for("p", ["seed", "user:u_dana", "user:u_yossi"], "u_fallback") == "u_dana"


def test_machines_in_the_log_are_not_people():
    """Every job created before accounts existed was saved by `seed` or
    `system`, and an agent is not an owner either."""
    assert owner_for("p", ["seed", "system", "agent:a1"], "u_dana") == "u_dana"


def test_with_nobody_named_and_nobody_in_the_log_it_says_so():
    """`""` means "cannot say", and the tool leaves those jobs alone rather than
    inventing an owner — an owner nobody can sign in as would move the job from
    one empty list to another."""
    assert owner_for("p", ["system"], "") == ""
    assert owner_for("p", [], "") == ""
