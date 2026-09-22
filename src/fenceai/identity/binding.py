"""Is this arrival the same Google account the row was bound to?

One pure function with three answers, kept out of the gate so the decision can
be read and tested without a request. The gate turns `"mismatch"` into a 403 and
persists the row on `"bound"`.
"""

from __future__ import annotations

from typing import Literal

from fenceai.identity.model import User
from fenceai.identity.ports import Principal

Outcome = Literal["ok", "bound", "mismatch"]


def bind(user: User, principal: Principal) -> Outcome:
    """`"bound"` means the caller must SAVE the row; `"ok"` means it must not.

    A principal with no subject binds nothing. `DevIdentity` has no Google
    behind it, and writing its empty string as a subject would make the real
    person's first arrival a `mismatch` against a value nobody set.
    """
    if not principal.subject:
        return "ok"
    if not user.subject:
        user.subject = principal.subject
        return "bound"
    return "ok" if user.subject == principal.subject else "mismatch"
