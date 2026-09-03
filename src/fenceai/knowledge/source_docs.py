"""`SourceDoc` — §1.1's provenance definition, and the target of every join.

It lived inside `snapshot.py` while `Snapshot` was its only consumer. Item 7
gave it a second one: a `SpecField` inside a published `Part` carries the same
`Provenance` a `ParameterTable` row does, so `knowledge/parts.py` has to resolve
citations to documents too — and `snapshot.py` has to hold `Part`s, which would
make the two files import each other.

So the type moves down to a module both can sit above, unchanged. It stays
importable from `snapshot` as well, because that is where every existing caller
looks for it and a move is not a reason to break them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.core.dates import Date


class SourceDoc(BaseModel):
    """§1.1 — the provenance definition every `SourceRef.belongs_to` joins to.

    Typed at last, and the two date fields are why it had to be: §1.4's tie-break
    reads `issue_date`, and until this existed there was no path from a published
    document to the policy that ranks it. `version_status` and `superseded_by`
    matter for the same reason — the first real snapshot contains an approval and
    the approval that supersedes it, both backing structural rows, and a run that
    cannot see the relation cannot tell them apart.

    Unknown fields are tolerated rather than refused: the real payload carries
    `also_filed_as`, which is theirs to add and not ours to have an opinion about
    (§2 — a registry addition is never a breaking change).
    """

    content_hash: str
    source_class: str = ""
    version_status: Literal["active", "superseded", "unknown"] = "unknown"
    version_status_basis: str = ""
    issue_date: Date | None = None
    expiration_date: Date | None = None
    superseded_by: list[str] = []
