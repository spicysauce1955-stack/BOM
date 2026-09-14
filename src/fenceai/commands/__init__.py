"""What may be DONE to a job — the closed, typed, permission-checked table.

The table itself (`model.py`, `registry.py`) is a pure leaf: stdlib and pydantic,
nothing else. It has to be, because both ends of the system reach it. A route
performs a row; an agent proposes one. If the table could import either, one of
them would end up owning it again — which is exactly where it came from.

The ROWS are allowed to know what they change. `desk.py` moves a `status` and
writes an `Annotation`, so it names `fenceai.project`; what it may never name is
`fenceai.api` or `fenceai.agent`, the two ends above.

Importing this package registers the desk rows. That is deliberate: `spec_for`
answering `KeyError` for `claim_job` depending on which module a caller happened
to import first is the kind of order-dependent emptiness this table exists to
rule out.
"""

from fenceai.commands import desk as desk  # noqa: F401  — registers the six rows
from fenceai.commands.model import CommandRefused, CommandSpec
from fenceai.commands.registry import all_kinds, parse_payload, register, spec_for
from fenceai.commands.run import perform

__all__ = ["CommandRefused", "CommandSpec", "all_kinds", "parse_payload",
           "perform", "register", "spec_for"]
