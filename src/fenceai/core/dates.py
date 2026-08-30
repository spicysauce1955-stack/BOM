"""`Date` — the contract's date type, and the one rule that makes it worth having.

Integration contract §1.1, BINDING, added in v1.2 by amendment 002:

```text
Date         { iso: str | null, value_raw: [str] }   iso is ISO-8601 YYYY-MM-DD
```

> `iso` is `null` when the source states no date, or states one that cannot be
> normalised without guessing. `"05/04/2023"` is ambiguous on its face, and a
> publisher resolving it by house convention has manufactured a fact rather than
> read one. **A `null` `iso` is never ordered, and never treated as earliest or
> latest.**

**Absent is the default path, not an edge case.** 72 of the 75 source documents in
the first published snapshot carry no `issue_date`, and 8 of its 16 parameter rows
carry no validity dates. Code written on the assumption that a date is usually
there will usually be wrong.

**Why the ordering helpers live here rather than at each call site.** The rule is
one sentence and it is easy to satisfy accidentally-wrongly: `a.iso < b.iso` with
`None` is a `TypeError`, `(a.iso or "")` silently makes absent the earliest date,
and `(a.iso or "9999-99-99")` silently makes it the latest. Both of those are
exactly what the BINDING clause forbids, both look reasonable in review, and
neither has a test that fails. So the comparison is a named function that returns
`None` for "not orderable" and callers must handle the third case.

This module holds no locale strings and no policy. What a caller DOES when two
dates cannot be ordered is the caller's decision — §1.4 moves to its next
criterion, `parameters.expand()` declines to judge a row lapsed. The type only
refuses to invent an answer.
"""

from __future__ import annotations

import datetime
import re

from pydantic import BaseModel, field_validator

# §1.1 says ISO-8601 `YYYY-MM-DD` — nothing wider. `datetime.date.fromisoformat`
# alone is too permissive for the contract's own wording (it accepts `20250424`
# and `2025-04-24T00:00` on 3.11+), and a bare regex is too weak: `2025-13-45` is
# well-shaped and is not a date. Both checks, so `iso` means what it says.
_ISO_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_iso_date(value: str) -> bool:
    """Whether `value` is a real ISO-8601 `YYYY-MM-DD` calendar date."""
    if not _ISO_SHAPE.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


class Date(BaseModel):
    """§1.1, field for field.

    `iso` is validated rather than trusted. The guard this replaces was a shape
    regex, and a shape regex says yes to `2025-13-45` — which then compares
    lexicographically against a real date perfectly happily and reports a row
    lapsed on the strength of a month that does not exist. A malformed `iso` is a
    payload defect, so it is refused **at the door, loudly**, the same way a
    `DocumentWarning` with no `text_raw` is: carrying it would mean every consumer
    downstream re-deciding whether to believe it.

    `value_raw` is a list for the same reason `Quantity.value_raw` is — a source
    can state a date twice and disagree with itself — and it is kept even when
    `iso` is null, which is the common case and the whole point: `"05/04/2023"`
    survives verbatim beside `iso: null`, so a curator can read what the document
    actually said and resolve it, and nobody has guessed.
    """

    iso: str | None = None
    value_raw: list[str] = []

    @field_validator("iso")
    @classmethod
    def _iso_is_really_iso(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not is_iso_date(v):
            raise ValueError(
                f"{v!r} is not an ISO-8601 YYYY-MM-DD date. `iso` is null when a "
                f"source states no date or one that cannot be normalised without "
                f"guessing (§1.1) — an unreadable date is null plus `value_raw`, "
                f"never a string that only looks like a date"
            )
        return v

    @property
    def orderable(self) -> bool:
        """Whether this date may take part in an ordering at all."""
        return self.iso is not None

    def raw(self) -> str:
        """What the source said, for display beside a null `iso`."""
        return self.value_raw[0] if self.value_raw else ""


def precedes(a: Date | None, b: Date | None) -> bool | None:
    """`a < b`, or **None when the pair cannot be ordered** (§1.1 BINDING).

    `None` is not "no" and callers must not read it as one. It means the question
    has no answer, and the contract's instruction for that case is to move to the
    next criterion or report — never to assume.
    """
    if a is None or b is None or a.iso is None or b.iso is None:
        return None
    return a.iso < b.iso


def all_orderable(dates: list[Date | None]) -> bool:
    """Whether **every** date in a set carries an `iso`.

    §1.4's tie-break says "later `issue_date` where both carry one". Applied
    pairwise across three or more candidates that rule is intransitive (see
    `amendments/005`), so the only reading of it that is a total order is
    all-or-skip: the date step fires when the whole tied set is dated, and is
    skipped otherwise. This function is that test, named so the reading is
    visible at the one call site that depends on it.
    """
    return bool(dates) and all(d is not None and d.iso is not None for d in dates)


def latest(dates: list[Date]) -> Date | None:
    """The latest of a set that is entirely dated, else None. Never guesses."""
    if not all_orderable(list(dates)):
        return None
    return max(dates, key=lambda d: d.iso or "")
