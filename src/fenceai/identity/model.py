"""An account, what it may do, and how the log names it.

**This is the first PERMISSION in the repo, and it is deliberately a different
word from the one next to it.** `web/static/js/view.js` insists twice that its
`view` is "a PRESENTATION preference, emphatically not a permission" — hiding is
CSS, anybody can edit `localStorage`, and nothing there protects anything. A
`capacity` is the other half of that sentence: it is what an account may DO, it
is read on the server, and no screen decides it.

Three words, three meanings, no overlap (`view.js` carries the same paragraph):

    view      what is SHOWN            sales | backoffice | all
    capacity  what an account may DO   sales | backoffice | admin
    role      what a part is FOR       rail | screw | post | …

`default_view` and `may_choose_view` below are the ONE place the two touch, and
they touch in one direction only: a capacity decides which view you open on and
whether you are offered the selector. Nothing may run the arrow backwards and
ask a view what somebody is allowed to do.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, field_validator

Capacity = Literal["sales", "backoffice", "admin"]

#: Every capacity an account may be issued with. A tuple rather than a set so
#: the order is the order a picker offers them, narrowest first.
CAPACITIES: tuple[str, ...] = ("sales", "backoffice", "admin")

#: What wrote a row when nobody was signed in — a seed, a migration, a test.
#: Every store method already defaults its actor to this string; accounts give
#: the column something better to say, they do not change what it means when
#: there is nobody to name.
SYSTEM = "system"

# An id may not contain the separator `actor_ref` builds with, or it could spell
# another KIND of actor. See `_no_colon`.
_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


class User(BaseModel):
    """A person with an account.

    **Deactivated, never deleted.** The audit log names people who have left the
    company, so a row has to keep resolving to a name for ever. `active=False`
    is what a company does instead, and `api/auth.py`'s gate refuses it — the
    two halves of that decision belong together or deactivating becomes a label
    somebody still signs in behind.

    **There is no credential here.** Google holds the identity; this row holds
    what that identity may DO. `subject` records which Google account it was
    bound to and is never used to find the row.
    """

    id: str
    name: str
    email: str
    # No default. There is no safe one: the narrowest silently locks somebody
    # out, the widest silently lets them in, and both failures are quiet.
    capacity: Capacity
    #: Google's stable `sub` claim, bound on this person's first arrival and
    #: never used to FIND them. Rows are created by email, because an admin
    #: grants Dana her capacity before Dana has ever signed in. This is the
    #: field that then answers "is this still the same Google account?" —
    #: see `identity/binding.py`. Empty means nobody has arrived yet.
    subject: str = ""
    active: bool = True

    @field_validator("email")
    @classmethod
    def _normalised(cls, v: str) -> str:
        """Stripped and lower-cased HERE, so there is one spelling of an address
        in the system.

        An address is not case-sensitive to the person typing it. Normalising at
        the call sites instead means the store can write one casing and look up
        another — which is how an account becomes unreachable from the very
        machine that created it, and it is exactly what happened the first time
        this was written. `Job._strip` makes the same move for the same reason:
        two jobs for "Dana Levy" and "Dana Levy " are one customer.
        """
        return v.strip().lower()

    @field_validator("id")
    @classmethod
    def _no_colon(cls, v: str) -> str:
        """`actor_ref` builds `user:<id>`, so an id carrying a colon could spell
        `user:agent:ranker`, which reads as an agent to anything splitting on the
        first colon. Refused where an id is MADE rather than everywhere one is
        read — the same argument `Topology` makes for refusing duplicate ids at
        the model boundary instead of downstream."""
        if not _ID_RE.fullmatch(v):
            raise ValueError(
                f"user id must be letters, digits, _ . or -, got {v!r}")
        return v


def actor_ref(user: User) -> str:
    """What the log writes for this person.

    `user:<id>` rather than a bare id, because one column carries three kinds of
    actor and a reader — or a filter — has to be able to tell a person from an
    agent without a lookup.
    """
    return f"user:{user.id}"


def is_agent(actor: str) -> bool:
    """Was this performed by an agent rather than a person?

    The reason the prefix exists. `actor` says who PERFORMED; a separate
    `origin` says who proposed — so "Yossi accepted the agent's suggestion" and
    "Yossi decided this himself" stay two different rows, which is the only way
    to ever measure whether the agent is worth listening to.
    """
    return actor.startswith("agent:")


def default_view(capacity: str) -> str:
    """The view an account opens on.

    This is the safe way to flip the default the salesperson MVP deliberately
    deferred: it would not make `sales` the default because that "would change
    what 307 passing browser-smoke checks are looking at, in the same commit
    that introduces the mechanism". With accounts nobody has to choose a global
    default — Dana opens on her view because of who she is, and the smoke signs
    in as an admin and keeps seeing today's app.
    """
    return {"sales": "sales", "backoffice": "backoffice"}.get(capacity, "all")


def may_choose_view(capacity: str) -> bool:
    """Is this account offered the view selector at all?

    Only an admin, who can "play" each role to see what it looks like.

    **This gates a selector, and nothing else.** It is a presentation question:
    hiding is CSS, `localStorage` is editable, and a backoffice account that
    forces itself into the sales view has changed what it SEES and none of what
    it may DO. Anything that decides whether an action is allowed reads
    `capacity` on the server; if you find yourself reaching for this function to
    guard a mutation, the thing you wanted was a capacity check.
    """
    return capacity == "admin"
