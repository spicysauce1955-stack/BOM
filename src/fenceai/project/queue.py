"""What should I work on next — the backoffice's list of jobs.

`GET /api/projects` returned `id`, `name` and `label` for EVERY project with no
filter and no page, which is a picker, not a queue. A person choosing what to do
next asks a different question: who is waiting longest, whose desk is it on, and
is this one even worth opening yet.

**Pure, over already-loaded projects.** No store, no request — `fenceai/project/`
is in the `DOMAIN` tuple of `tests/architecture/test_fitness.py` and may not
reach the delivery mechanism or the database. The route loads, this decides, the
route serialises. That also makes every rule below testable without a client.

**The open-question count is `handover_gaps` and nothing else.** Not the office's
own readiness: a fresh job has a bay width to choose and a plan to commit BY
DEFINITION, so counting those would give every row the same number and tell the
reader nothing. The office's own list lives on its road, inside the job.

**Paging is a correctness requirement, not a nicety.** That count is DERIVED and
never stored (CLAUDE.md's rule for `report/`), so it is affordable for a page of
twenty-five and not for an unbounded list. Which is why sorting and filtering
here work over STORED columns only — a sort over the derived count would force
deriving it for everything and quietly undo the bound.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Callable, Literal

from pydantic import BaseModel, Field

from fenceai.core.units import Cents
from fenceai.project.lifecycle import FINISHED_STATES, is_open, sales_status
from fenceai.project.model import Project, is_office_note
from fenceai.report.handover import handover_gaps

#: A page. Big enough that the common desk is one screenful, small enough that
#: deriving twenty-five handover sheets is free.
DEFAULT_LIMIT = 25

#: The ceiling, and it REFUSES rather than clamps. A silently clamped `limit=500`
#: hands back a hundred rows with no way for the caller to tell that four hundred
#: were left behind — which is the same failure as an unpaged list, wearing a
#: page's clothes.
MAX_LIMIT = 100

#: Capacities that must never see a `drafting` job. A job the salesperson has not
#: submitted is not work anybody else can pick up, and showing it would invite
#: the office to start on a fence still being drawn.
#:
#: A closed set rather than `!= "sales"`, so a capacity added later (a foreman, a
#: fitter) has to be decided about rather than defaulted into seeing drafts.
DRAFTS_HIDDEN_FROM: frozenset[str] = frozenset({"backoffice"})

#: The route's word for the signed-in user, which it resolves to an id before
#: calling. Named here so the refusal below can say what went wrong.
_ME = "me"

#: The route's word for "nobody has taken it". A sentinel string rather than
#: `None`, because `None` is already taken by "do not filter on assignee at all"
#: and those are different questions — the whole reason a queue exists is the
#: first one.
UNASSIGNED = "none"


class QueueRow(BaseModel):
    """One line of the list.

    `id`, `name` and `label` are carried because this route is REBUILT, not
    replaced: the picker is not its only caller and something keyed on those
    must not silently start reading a customer's name instead.

    `customer` and `town` sit beside `label` rather than inside it because the
    queue is a table with its own columns where the picker was one string.
    """

    id: str
    name: str
    label: str
    customer: str = ""
    town: str = ""
    sold_by: str = ""
    sold_on: str = ""
    status: str
    # `None` is a real value here and means nobody has taken it — see UNASSIGNED.
    assignee: str | None = None
    submitted_at: str = ""
    # Seconds since submission, integer (ADR-0002: no floats at rest). Zero for a
    # job nobody submitted: its AGE is not its wait, and counting from creation
    # would float every abandoned draft above the customers actually waiting.
    waiting_seconds: int = 0
    open_questions: int = 0
    # The two Finished-bucket columns (spec §6), and `select_rows` CANNOT fill
    # them: `closed_at` has no field on `Project` yet and a quote total lives in
    # the store, which this layer may not import. They are declared here anyway
    # so the screen's row shape does not change when the store-backed half
    # lands — the route that holds the store fills them in on the way out.
    closed_at: str = ""
    quote_total_cents: Cents | None = None


class QueueFilter(BaseModel):
    """The question being asked of the list.

    Every field is a STORED column or a bucket over one. The single exception is
    `has_open`, and its comment says what it costs.
    """

    # Which of the two lists. Open asks *what should I work on next*; finished
    # asks *what did we do and what did it come to*. Defaulting to `open`
    # because a queue opens on the work, not on the archive.
    bucket: Literal["open", "finished"] = "open"
    # Narrow inside the bucket. A tuple rather than one value because "waiting or
    # returned" is a single question a person asks.
    status: tuple[str, ...] = ()
    # `None` = do not ask. `"none"` = nobody has taken it. Anything else = a user
    # id. `"me"` is the route's word and is refused here (see `_refuse_me`).
    assignee: str | None = None
    sold_by: str = ""
    # ISO dates (YYYY-MM-DD), inclusive at both ends, compared against the date
    # part of the stored timestamp.
    submitted_from: str = ""
    submitted_to: str = ""
    sold_on_from: str = ""
    sold_on_to: str = ""
    # The one filter over the DERIVED count, and therefore the one that costs a
    # handover sheet per candidate rather than per page. Kept because "show me
    # only the jobs that are ready to plan" is the reason the column exists at
    # all; named as expensive so nobody adds a second one by accident.
    has_open: bool | None = None
    q: str = ""
    sort: Literal["waiting", "newest", "customer"] = "waiting"
    # Who is reading. Not a permission — a capacity is checked on the server and
    # a view is never a permission — this only decides whether drafts belong on
    # the list somebody is looking at.
    for_capacity: str | None = None
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = None


def _town(address: str) -> str:
    """The town off a free-typed address: the part after the last comma.

    Addresses are typed from paper, so there is no structured town to read. A
    blank cell where there is no comma is honest; a guess — the last word, say —
    would put "12" or a street name in the column the office sorts its week by.
    """
    return address.rsplit(",", 1)[1].strip() if "," in address else ""


def _waiting_seconds(submitted_at: str, now: datetime) -> int:
    """How long this job has been on the queue.

    An unreadable or blank timestamp answers zero rather than raising. A queue
    that 500s because one row's timestamp is malformed hides every other job on
    it, and the cost of being wrong here is one row sorting last.
    """
    if not submitted_at:
        return 0
    try:
        at = datetime.fromisoformat(submitted_at)
    except (TypeError, ValueError):
        return 0
    if at.tzinfo is None:
        return 0
    return max(0, int((now - at).total_seconds()))


# --- sorting -----------------------------------------------------------------
#
# Each sort is a key over STORED columns plus its direction. The keys are lists
# of JSON primitives on purpose: the cursor below is one of these keys written
# down, and a tuple would come back from JSON as a list and stop comparing.
#
# The leading 0/1 in each key is where a BLANK goes, and it is chosen per sort so
# that a job with nothing in the column lands at the END under that sort's own
# direction. Get it wrong and every never-submitted job sits at the top of the
# list of who has waited longest.

def _waiting_key(p: Project) -> list:
    return [0 if p.submitted_at else 1, p.submitted_at]


def _newest_key(p: Project) -> list:
    return [1 if p.submitted_at else 0, p.submitted_at]


def _customer_key(p: Project) -> list:
    name = (p.job.customer if p.job else "") or p.display_name()
    return [0 if name else 1, name.casefold()]


#: name -> (key over stored columns, descending). The seam for a new column is
#: one row here; a sort over anything DERIVED does not belong in it.
_SORTS: dict[str, tuple[Callable[[Project], list], bool]] = {
    "waiting": (_waiting_key, False),   # oldest submission first = longest wait
    "newest": (_newest_key, True),
    "customer": (_customer_key, False),
}


def _encode_cursor(key: list, project_id: str) -> str:
    return base64.urlsafe_b64encode(
        json.dumps([key, project_id], separators=(",", ":")).encode()
    ).decode().rstrip("=")


def _decode_cursor(cursor: str) -> list:
    """The boundary this page starts after, as `[key, id]`.

    A cursor that cannot be read is REFUSED, not ignored. Ignoring it restarts
    the walk at page one, and a caller looping until the cursor comes back
    `None` would then page forever over the same twenty-five rows.
    """
    try:
        boundary = json.loads(
            base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except Exception as exc:  # noqa: BLE001 — every failure means the same thing
        raise ValueError(f"unreadable queue cursor: {cursor!r}") from exc
    if (not isinstance(boundary, list) or len(boundary) != 2
            or not isinstance(boundary[0], list)):
        raise ValueError(f"unreadable queue cursor: {cursor!r}")
    return boundary


# --- filtering ---------------------------------------------------------------

def _within(value: str, start: str, end: str) -> bool:
    """Is this stored date inside the window? Inclusive at both ends.

    A blank value is inside NO window. It has no date, so a report of last
    week's intake must not quietly include it — that is the difference between
    "nobody said" and "it happened then", which this repo keeps paying for
    elsewhere (`Stated`, `height_assumed`).
    """
    if not (start or end):
        return True
    if not value:
        return False
    return (not start or value >= start) and (not end or value <= end)


def _matches_text(p: Project, needle: str) -> bool:
    job = p.job
    haystack = " ".join(filter(None, (
        p.name, job.customer if job else "", job.address if job else "",
        job.sold_by if job else "")))
    return needle in haystack.casefold()


def _stored_match(p: Project, f: QueueFilter) -> bool:
    """Everything answerable without deriving anything."""
    if is_open(p.status) != (f.bucket == "open"):
        return False
    if p.status == "drafting" and f.for_capacity in DRAFTS_HIDDEN_FROM:
        return False
    if f.status and p.status not in f.status:
        return False
    if f.assignee is not None:
        if f.assignee == UNASSIGNED:
            if p.assignee is not None:
                return False
        elif p.assignee != f.assignee:
            return False
    job = p.job
    if f.sold_by and (job.sold_by if job else "").casefold() != f.sold_by.casefold():
        return False
    if not _within(p.submitted_at[:10], f.submitted_from, f.submitted_to):
        return False
    if not _within(job.sold_on if job else "", f.sold_on_from, f.sold_on_to):
        return False
    if f.q and not _matches_text(p, f.q.casefold()):
        return False
    return True


def select_rows(projects: list[Project], filter: QueueFilter, *,
                now: datetime) -> tuple[list[QueueRow], str | None]:
    """One page of the queue, and the cursor for the next one (`None` at the end).

    `now` is injected rather than read from the clock so that "waited nine days"
    is a fact a test can state instead of a wait it has to sit through — the same
    call `identity/session.py` makes.
    """
    if filter.assignee == _ME:
        # Matched literally, `me` finds no user, returns an empty page, and
        # reads on screen as "you have nothing to do" — a wrong answer shaped
        # exactly like a right one. The route resolves it against the session.
        raise ValueError(
            "assignee='me' must be resolved to a user id before it reaches "
            "select_rows; this layer has no session to resolve it against")

    candidates = [p for p in projects if _stored_match(p, filter)]

    # Derived, and therefore counted once per project and remembered. Without
    # `has_open` this runs for the twenty-five rows of the page; with it, for
    # every candidate — which is the cost that filter carries by its nature, and
    # why nothing else here is allowed to touch a derived value.
    gaps: dict[str, int] = {}

    def open_questions(p: Project) -> int:
        if p.id not in gaps:
            gaps[p.id] = len(handover_gaps(p))
        return gaps[p.id]

    if filter.has_open is not None:
        candidates = [p for p in candidates
                      if (open_questions(p) > 0) == filter.has_open]

    key_of, descending = _SORTS[filter.sort]
    # The project id is the tiebreak, and it is what makes the order TOTAL. Two
    # jobs submitted in the same second with no tiebreak can swap places between
    # two page requests, which is how a keyset cursor skips one row and repeats
    # another.
    ordered = sorted(candidates, key=lambda p: [key_of(p), p.id],
                     reverse=descending)

    if filter.cursor:
        boundary = _decode_cursor(filter.cursor)
        ordered = [p for p in ordered
                   if ([key_of(p), p.id] < boundary if descending
                       else [key_of(p), p.id] > boundary)]

    page = ordered[:filter.limit]
    next_cursor = (_encode_cursor(key_of(page[-1]), page[-1].id)
                   if len(ordered) > filter.limit else None)

    return [_row(p, open_questions(p), now) for p in page], next_cursor


def _row(p: Project, open_questions: int, now: datetime) -> QueueRow:
    job = p.job
    return QueueRow(
        id=p.id,
        name=p.name,
        label=p.display_name(),
        customer=job.customer if job else "",
        town=_town(job.address if job else ""),
        sold_by=job.sold_by if job else "",
        sold_on=job.sold_on if job else "",
        status=p.status,
        closed_at=p.closed_at,
        assignee=p.assignee,
        submitted_at=p.submitted_at,
        waiting_seconds=_waiting_seconds(p.submitted_at, now),
        open_questions=open_questions,
    )


class MyJobRow(BaseModel):
    """One job on a salesperson's home screen.

    `office_notes` and `office_latest` are the point of the list: what the
    office has said about this job, so she can see from the list which job needs
    her and what it asks — and then open it and find each note where it was
    pinned. The latest note is carried verbatim (immutable human text) and is
    rendered escaped and `dir="auto"`; it is never summarised here.
    """

    id: str
    label: str
    customer: str = ""
    town: str = ""
    status: str
    sales_status: str
    submitted_at: str = ""
    office_notes: int = 0
    office_latest: str = ""


#: The order her list is read in: what needs her first, then what she is still
#: writing, then what is out of her hands.
_ATTENTION = {"needs_info": 0, "draft": 1, "pending": 2, "accepted": 3, "rejected": 4}


def my_jobs(projects: list[Project], user_id: str) -> list[MyJobRow]:
    """The jobs this account created, most urgent first.

    Pure. Unpaged on purpose and bounded by the one person: the per-row work is
    a pass over that job's notes, not a handover sheet, so there is no derived
    cost that grows with the whole database. `created_by` is written by the
    create route from the session; a job created before that field was written
    has none and belongs to nobody's list.
    """
    rows: list[MyJobRow] = []
    for p in projects:
        if not user_id or p.created_by != user_id:
            continue
        office = [a for a in p.annotations if is_office_note(p, a)]
        latest = max(office, key=lambda a: a.created_at, default=None)
        job = p.job
        rows.append(MyJobRow(
            id=p.id, label=p.display_name(),
            customer=job.customer if job else "",
            town=_town(job.address if job else ""),
            status=p.status, sales_status=sales_status(p.status),
            submitted_at=p.submitted_at,
            office_notes=len(office),
            office_latest=latest.text if latest else "",
        ))
    rows.sort(key=lambda r: (_ATTENTION[r.sales_status], r.label.casefold(), r.id))
    return rows


#: Re-exported so a caller rendering the Finished bucket does not have to import
#: two modules to know which statuses it is looking at.
__all__ = ["DEFAULT_LIMIT", "MAX_LIMIT", "FINISHED_STATES", "UNASSIGNED",
           "MyJobRow", "QueueFilter", "QueueRow", "my_jobs", "select_rows"]
