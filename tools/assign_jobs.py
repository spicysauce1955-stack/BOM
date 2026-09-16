"""Give the jobs that predate `Project.created_by` an owner.

A job with no recorded creator is on nobody's home screen: `GET /api/my-jobs`
answers "the jobs YOUR account created", and before the create route wrote that
field there was no answer. The jobs are not lost — the office's queue lists every
job, whoever made it — but the salesperson cannot reach one from her own list.

Two sources of an owner, in order, and the order is the point:

  1. the audit log, which already records who saved a project. The FIRST `user:`
     actor on a job is the closest thing to a creator that exists in the data,
     and it is a fact rather than a guess.
  2. the account named on the command line, for the jobs the log cannot answer
     for — every job created before accounts existed was saved by `seed` or
     `system`, and no amount of reading will turn those into a person.

    uv run python tools/assign_jobs.py fenceai.db                    # report only
    uv run python tools/assign_jobs.py fenceai.db --to u_dana --write

Report-only by default, and `--to` is refused unless the account exists: an
owner id nobody can sign in as would move the jobs from one empty list to
another, which is harder to notice than leaving them alone.
"""

from __future__ import annotations

import argparse
import sys

from fenceai.store.db import Store


def owner_for(project_id: str, audit_actors: list[str], default_user_id: str) -> str:
    """The account to record as this job's creator, or `""` for "cannot say".

    Pure, so the choice is testable without a database. `actor` is `user:<id>`
    for a person, and `seed` / `system` / `agent:<id>` for everything else; only
    a person can own a job, and the earliest one wins because later saves are
    whoever edited it since.
    """
    for actor in audit_actors:
        if actor.startswith("user:"):
            return actor.split(":", 1)[1]
    return default_user_id


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db")
    ap.add_argument("--to", default="", metavar="USER_ID",
                    help="account to own the jobs the audit log cannot answer for")
    ap.add_argument("--write", action="store_true", help="write the owners (default: report)")
    ap.add_argument("--history", type=int, default=1_000_000, metavar="N",
                    help="how many audit rows to read back (default: all of them)")
    args = ap.parse_args()

    store = Store(args.db)
    if args.to and store.user(args.to) is None:
        known = ", ".join(f"{u.id} ({u.email})" for u in store.list_users()) or "none"
        print(f"no account {args.to!r} — accounts in this database: {known}")
        return 2

    # Oldest first: `audit_entries` answers newest-first (it is the ops view of
    # "what just happened"), and the EARLIEST person is the one we want.
    actors: dict[str, list[str]] = {}
    for entry in reversed(store.audit_entries(limit=args.history)):
        actors.setdefault(entry["ref"], []).append(entry["actor"])

    unowned = [p for p in store.list_projects() if not p.created_by]
    if not unowned:
        print("every job already has an owner.")
        return 0

    assigned, unanswerable = [], []
    for project in unowned:
        owner = owner_for(project.id, actors.get(project.id, []), args.to)
        (assigned if owner else unanswerable).append((project, owner))

    for project, owner in assigned:
        source = "audit log" if owner != args.to else "--to"
        print(f"{project.id}  {project.display_name()!r}  ->  {owner}  ({source})")
    for project, _ in unanswerable:
        print(f"{project.id}  {project.display_name()!r}  ->  nobody "
              f"(no user in the audit log; pass --to)")

    if not args.write:
        print(f"\n{len(assigned)} job(s) would be assigned, {len(unanswerable)} left alone. "
              f"Re-run with --write to apply.")
        return 0

    for project, owner in assigned:
        project.created_by = owner
        # `actor` is what the LOG records for this write, and it is not the new
        # owner: the person who ran the migration did it, not the salesperson it
        # names. Writing the owner here would forge a row in the one table whose
        # whole value is that nobody can.
        store.save_project(project, actor="migration:assign_jobs")
    print(f"\n{len(assigned)} job(s) assigned, {len(unanswerable)} left alone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
