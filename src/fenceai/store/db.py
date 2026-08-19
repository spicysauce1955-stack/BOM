"""SQLite persistence (ADR-0008): document-style tables behind thin repositories.

Domain code never touches SQL. Knowledge versions, generation runs, corrections and
the audit log are append-only; version content is immutable (only lifecycle status
may change, via a dedicated method that audits the transition).
"""

from __future__ import annotations

import functools
import inspect
import json
import sqlite3
import threading
from datetime import datetime, timezone

from fenceai.fencemodel.demo import demo_model_versions
from fenceai.parts.demo import demo_parts
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import FenceModel
from fenceai.fulfillment.fulfill import Inventory
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion
from fenceai.learning.model import Correction
from fenceai.parts.model import Part, PartLibrary
from fenceai.project.model import Project
from fenceai.strategy.model import GenerationResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_versions (
    object_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
    doc TEXT NOT NULL, PRIMARY KEY (object_id, version));
CREATE TABLE IF NOT EXISTS fence_models (
    model_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
    doc TEXT NOT NULL, PRIMARY KEY (model_id, version));
CREATE TABLE IF NOT EXISTS parts (
    part_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
    doc TEXT NOT NULL, PRIMARY KEY (part_id, version));
CREATE TABLE IF NOT EXISTS generation_runs (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, created_at TEXT NOT NULL,
    doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS corrections (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inventories (project_id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS catalogs (id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quotes (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, ref TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialized(cls):
    """One connection, one caller at a time — enforced for every public method.

    FastAPI runs sync endpoints in a threadpool, so one process serves several
    requests at once through the SINGLE `sqlite3.Connection` this store opens
    with `check_same_thread=False`. That connection is not safe for interleaved
    statements, and the damage is not only a 500: half of these methods are
    read-then-write sequences (`set_fence_model_status` SELECTs the document
    then UPDATEs it, `accept_quote` supersedes then inserts), and another
    thread's `commit()` landing in the middle of one commits a transaction
    nobody finished.

    Measured before this existed: 48 failures in ~540 overlapping requests, and
    a browser session that 500'd on `GET /inventory` while a fence-model draft
    was being saved. It was found by a client that briefly saved on a 250 ms
    debounce; that client no longer does, but the hazard was never the client's
    — any two overlapping requests reach it, and the model editor merely made
    the odds routine enough to catch.

    A connection per THREAD is not the alternative: every test constructs
    `Store(":memory:")`, where per-thread connections mean per-thread
    DATABASES, and the suite would be testing empty ones. So the invariant is
    serialization, and it lives here rather than as a `with self._lock` to be
    remembered at each of ~35 call sites — the one that gets forgotten is the
    one that corrupts a transaction. Re-entrant, because public methods call
    each other (`__init__` -> `seed_fence_models` -> `save_fence_model`).

    SCOPE: this makes each store CALL atomic, not each route. A route that reads
    and then writes through two calls (`publish_fence_model` loads, checks the
    status and sets it; `put_fence_model_draft` reads the library, computes the
    next version and saves) is still a TOCTOU window. Closing that needs a
    transaction spanning the sequence, which is a different change; ADR-0008
    says so rather than letting this docstring imply more than it delivers.
    """
    for name, member in list(vars(cls).items()):
        if name.startswith("_"):
            continue
        if not inspect.isfunction(member):
            # Refused rather than skipped. A `property` is not callable, so a
            # filter on `callable` would leave it UNGUARDED with nothing
            # failing; a `staticmethod` IS callable and would be wrapped and
            # handed a bogus `self`. Both are silent, and this decorator only
            # protects what it can see.
            if callable(member) or isinstance(member, (property, staticmethod, classmethod)):
                raise TypeError(
                    f"{cls.__name__}.{name} is a {type(member).__name__}, which "
                    "@_serialized cannot guard — give it a leading underscore or "
                    "widen the decorator deliberately"
                )
            continue    # plain class attributes (_STATUS_TRANSITIONS and friends)

        def guard(fn):
            @functools.wraps(fn)
            def wrapper(self, *args, **kwargs):
                with self._lock:
                    return fn(self, *args, **kwargs)
            return wrapper

        setattr(cls, name, guard(member))
    return cls


@_serialized
class Store:
    def __init__(self, path: str = ":memory:"):
        # `check_same_thread=False` only silences sqlite3's guard; it does not
        # make the connection safe. FastAPI runs sync endpoints in a threadpool,
        # so two overlapping fetches interleaved statements on one cursor and
        # raised `InterfaceError: bad parameter or other API misuse` straight out
        # of a route — a real 500 in the browser that NO pytest test can see,
        # because TestClient serialises requests. The browser smoke suite was the
        # only detector, and it was red here while green on main.
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript("PRAGMA journal_mode=WAL;" + _SCHEMA)
        self._conn.commit()
        # Parts BEFORE models: a seeded model names a part_id, and a store whose
        # models arrived first would, for the length of one call, hold a published
        # model that resolves to nothing. Nothing reads the store between the two
        # lines today, and the ordering is the cheap way to keep that true.
        self.seed_parts()
        self.seed_fence_models()

    def close(self) -> None:
        self._conn.close()

    def _audit(self, actor: str, action: str, ref: str) -> None:
        self._conn.execute(
            "INSERT INTO audit_log (at, actor, action, ref) VALUES (?,?,?,?)",
            (_now(), actor, action, ref),
        )

    # -- projects -------------------------------------------------------------

    def save_project(self, project: Project, actor: str = "system") -> None:
        self._conn.execute(
            "INSERT INTO projects (id, doc) VALUES (?,?) "
            "ON CONFLICT(id) DO UPDATE SET doc=excluded.doc",
            (project.id, project.model_dump_json()),
        )
        self._audit(actor, "save_project", project.id)
        self._conn.commit()

    def load_project(self, project_id: str) -> Project | None:
        row = self._conn.execute(
            "SELECT doc FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        return Project.model_validate_json(row[0]) if row else None

    def list_projects(self) -> list[Project]:
        rows = self._conn.execute("SELECT doc FROM projects ORDER BY id").fetchall()
        return [Project.model_validate_json(r[0]) for r in rows]

    # -- knowledge (append-only versions) --------------------------------------

    # lifecycle transitions a version may take; anything else is a caller bug
    _STATUS_TRANSITIONS = {
        "draft": {"active", "retired"},
        "active": {"retired"},
        "proposed": {"retired", "rejected"},
    }

    def insert_knowledge_version(self, v: KnowledgeVersion, actor: str = "system") -> None:
        self._insert_version_nocommit(v, actor)
        self._conn.commit()

    def _insert_version_nocommit(self, v: KnowledgeVersion, actor: str) -> None:
        self._conn.execute(
            "INSERT INTO knowledge_versions (object_id, version, status, doc) VALUES (?,?,?,?)",
            (v.object_id, v.version, v.status, v.model_dump_json()),
        )
        self._audit(actor, "insert_knowledge_version", v.ref)

    def update_knowledge_status(
        self, object_id: str, version: int, status: str, actor: str = "system"
    ) -> None:
        """The only mutation versions allow: lifecycle status (content is immutable)."""
        self._update_status_nocommit(object_id, version, status, actor)
        self._conn.commit()

    def _update_status_nocommit(
        self, object_id: str, version: int, status: str, actor: str
    ) -> None:
        row = self._conn.execute(
            "SELECT doc FROM knowledge_versions WHERE object_id=? AND version=?",
            (object_id, version),
        ).fetchone()
        if row is None:
            raise KeyError(f"{object_id}@v{version}")
        v = KnowledgeVersion.model_validate_json(row[0])
        if status not in self._STATUS_TRANSITIONS.get(v.status, set()):
            raise ValueError(f"illegal status transition {v.status} -> {status} for {v.ref}")
        v.status = status  # type: ignore[assignment]
        v = KnowledgeVersion.model_validate(v.model_dump())  # re-validate the Literal
        self._conn.execute(
            "UPDATE knowledge_versions SET status=?, doc=? WHERE object_id=? AND version=?",
            (status, v.model_dump_json(), object_id, version),
        )
        self._audit(actor, f"knowledge_status:{status}", v.ref)

    def replace_active_version(self, v: KnowledgeVersion, actor: str = "system") -> None:
        """Atomically retire the object's active version(s) and insert the new one —
        a crash can never leave a retired rule without its successor (final
        architecture review, finding 6)."""
        try:
            rows = self._conn.execute(
                "SELECT version FROM knowledge_versions WHERE object_id=? AND status='active'",
                (v.object_id,),
            ).fetchall()
            for (prev_version,) in rows:
                self._update_status_nocommit(v.object_id, prev_version, "retired", actor)
            self._insert_version_nocommit(v, actor)
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    def apply_review_outcome(
        self,
        candidate: KnowledgeVersion,
        approved: KnowledgeVersion | None,
        actor: str,
    ) -> None:
        """Atomically persist a review: candidate status change + optional approved
        version in one transaction."""
        try:
            self._update_status_nocommit(
                candidate.object_id, candidate.version, candidate.status, actor
            )
            if approved is not None:
                self._insert_version_nocommit(approved, actor)
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    def knowledge_base(self) -> KnowledgeBase:
        rows = self._conn.execute(
            "SELECT doc FROM knowledge_versions ORDER BY object_id, version"
        ).fetchall()
        return KnowledgeBase(versions=[KnowledgeVersion.model_validate_json(r[0]) for r in rows])

    def next_version(self, object_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(version) FROM knowledge_versions WHERE object_id=?", (object_id,)
        ).fetchone()
        return (row[0] or 0) + 1

    # -- fence models (drafts mutable, published versions frozen) ---------------

    _FENCE_MODEL_STATUSES = ("draft", "active", "retired")

    def save_fence_model(self, model: FenceModel, actor: str = "system") -> None:
        """A draft may be rewritten in place — that is what makes authoring
        bearable. Anything published is frozen: a run stamps `(id, version)` and
        re-reading it must give back the panel that run priced. The refusal
        belongs here and not in a route, because it is the invariant, not a
        validation of one caller."""
        row = self._conn.execute(
            "SELECT status FROM fence_models WHERE model_id=? AND version=?",
            (model.id, model.version),
        ).fetchone()
        if row is not None and row[0] != "draft":
            raise ValueError(
                f"{model.ref} is {row[0]}; its content is immutable "
                "(publish a new version, or change only its status)"
            )
        self._conn.execute(
            "INSERT INTO fence_models (model_id, version, status, doc) VALUES (?,?,?,?) "
            "ON CONFLICT(model_id, version) DO UPDATE SET "
            "status=excluded.status, doc=excluded.doc",
            (model.id, model.version, model.status, model.model_dump_json()),
        )
        self._audit(actor, "save_fence_model", model.ref)
        self._conn.commit()

    def load_fence_model(self, model_id: str, version: int) -> FenceModel | None:
        row = self._conn.execute(
            "SELECT doc FROM fence_models WHERE model_id=? AND version=?",
            (model_id, version),
        ).fetchone()
        return FenceModel.model_validate_json(row[0]) if row else None

    def fence_model_library(self) -> FenceModelLibrary:
        rows = self._conn.execute(
            "SELECT doc FROM fence_models ORDER BY model_id, version"
        ).fetchall()
        return FenceModelLibrary(models=[FenceModel.model_validate_json(r[0]) for r in rows])

    def set_fence_model_status(
        self, model_id: str, version: int, status: str, actor: str = "system"
    ) -> None:
        """The only mutation a published model allows. The status lives on the
        document as well as on the row, so both are rewritten together —
        resolution reads documents, and a doc lagging its row would let a
        retired model keep resolving as the latest active one."""
        if status not in self._FENCE_MODEL_STATUSES:
            raise ValueError(f"unknown fence model status {status!r}")
        model = self.load_fence_model(model_id, version)
        if model is None:
            raise KeyError(f"{model_id}@v{version}")
        model.status = status  # type: ignore[assignment]
        model = FenceModel.model_validate(model.model_dump())  # re-validate the Literal
        self._conn.execute(
            "UPDATE fence_models SET status=?, doc=? WHERE model_id=? AND version=?",
            (status, model.model_dump_json(), model_id, version),
        )
        self._audit(actor, f"fence_model_status:{status}", model.ref)
        self._conn.commit()

    def delete_fence_model_draft(
        self, model_id: str, version: int, actor: str = "system"
    ) -> None:
        """Discard a draft. The refusal lives HERE, not in the route: an
        immutable document that any route could delete is not immutable, and a
        stored run or an accepted quote may name a published version."""
        model = self.load_fence_model(model_id, version)
        if model is None:
            raise KeyError(f"{model_id}@v{version}")
        if model.status != "draft":
            raise ValueError(f"{model.ref} is {model.status}, not a draft")
        self._conn.execute(
            "DELETE FROM fence_models WHERE model_id=? AND version=?",
            (model_id, version),
        )
        self._audit(actor, "fence_model_discard", model.ref)
        self._conn.commit()

    def next_fence_model_version(self, model_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(version) FROM fence_models WHERE model_id=?", (model_id,)
        ).fetchone()
        return (row[0] or 0) + 1

    def seed_fence_models(self, actor: str = "seed") -> None:
        """A fresh database is never empty, so the compatibility path is data
        rather than a special case in the generator. Keyed on (id, version) and
        never an overwrite: reopening a store must leave an expert's edits, and
        a retirement, exactly as they were found."""
        for model in demo_model_versions():
            present = self._conn.execute(
                "SELECT 1 FROM fence_models WHERE model_id=? AND version=?",
                (model.id, model.version),
            ).fetchone()
            if present:
                continue
            # The column follows the DOCUMENT. It used to force "active" so that
            # a seeded model nobody could select could not happen, which held
            # while every built-in was the only version of its line; a built-in
            # that ships a second version cannot be seeded that way, because
            # `latest_active` is what an unpinned project resolves and the newer
            # document would take over every existing job at the next generation
            # without anyone publishing anything. Each line still seeds an active
            # version — `demo_model_versions()` is what guarantees it — and a
            # draft beside it is work an author can open, not a model nobody can
            # select.
            self._conn.execute(
                "INSERT INTO fence_models (model_id, version, status, doc) VALUES (?,?,?,?)",
                (model.id, model.version, model.status, model.model_dump_json()),
            )
            self._audit(actor, "seed_fence_model", model.ref)
        self._conn.commit()

    def seed_parts(self, actor: str = "seed") -> None:
        """The library the built-in models name, seeded on the same terms as they
        are: keyed on (id, version), never an overwrite.

        A part is EDITABLE — that is the whole point of the shared entity — so
        re-seeding one would undo an expert's published fix on every restart, and
        `save_part` would refuse it anyway once the version is active. The check is
        here so a reopened store is silent rather than raising."""
        for part in demo_parts():
            present = self._conn.execute(
                "SELECT 1 FROM parts WHERE part_id=? AND version=?",
                (part.id, part.version),
            ).fetchone()
            if present:
                continue
            self._conn.execute(
                "INSERT INTO parts (part_id, version, status, doc) VALUES (?,?,?,?)",
                (part.id, part.version, part.status, part.model_dump_json()),
            )
            self._audit(actor, "seed_part", part.ref)
        self._conn.commit()

    # -- parts (drafts mutable, published versions frozen) ---------------------

    def save_part(self, part: Part, actor: str = "system") -> None:
        """A draft may be rewritten in place; anything published is frozen.

        The refusal belongs here and not in a route, because it is the invariant
        rather than a validation of one caller — the same reason `save_fence_model`
        carries it. A run stamps `(part_id, version)` and re-reading it must give
        back the spec that run resolved.

        `Part.status` DEFAULTS to `"active"`, so this method is a second door into
        the state `set_part_status` guards, and it has to carry the same two
        invariants or the guard is decorative:

        * **one active version per id.** `set_part_status` retires the predecessor
          precisely so `latest_active` is never ambiguous; saving `x@v2` as active
          beside an active `x@v1` leaves two, and `latest_active`'s `max(version)`
          then hides the older one instead of reporting the contradiction.
          Refused rather than silently retiring the predecessor here: a save is not
          a publication, and retiring a version is a lifecycle act with its own
          audit line.
        * **a published part earns its refusals now.** Same moment and same voice as
          `set_part_status`, for the reason `validate_part`'s docstring gives: a part
          that publishes cleanly and reports `no_eligible_item` on every bay of every
          job has told the author nothing.
        """
        row = self._conn.execute(
            "SELECT status FROM parts WHERE part_id=? AND version=?",
            (part.id, part.version),
        ).fetchone()
        if row is not None and row[0] != "draft":
            raise ValueError(
                f"{part.ref} is {row[0]}; its content is immutable "
                "(publish a new version, or change only its status)"
            )
        if part.status == "active":
            others = [
                v for (v,) in self._conn.execute(
                    "SELECT version FROM parts WHERE part_id=? AND status='active'",
                    (part.id,),
                ).fetchall()
                if v != part.version
            ]
            if others:
                raise ValueError(
                    f"{part.ref} would be a second active version beside "
                    f"{', '.join(f'{part.id}@v{v}' for v in sorted(others))} — save "
                    "it as a draft and activate it, so its predecessor is retired"
                )
        self._refuse_invalid_part(part)
        self._conn.execute(
            "INSERT INTO parts (part_id, version, status, doc) VALUES (?,?,?,?) "
            "ON CONFLICT(part_id, version) DO UPDATE SET "
            "status=excluded.status, doc=excluded.doc",
            (part.id, part.version, part.status, part.model_dump_json()),
        )
        self._audit(actor, "save_part", part.ref)
        self._conn.commit()

    def load_part(self, part_id: str, version: int) -> Part | None:
        row = self._conn.execute(
            "SELECT doc FROM parts WHERE part_id=? AND version=?", (part_id, version),
        ).fetchone()
        return Part.model_validate_json(row[0]) if row else None

    def part_library(self) -> PartLibrary:
        rows = self._conn.execute(
            "SELECT doc FROM parts ORDER BY part_id, version"
        ).fetchall()
        return PartLibrary(parts=[Part.model_validate_json(r[0]) for r in rows])

    def next_part_version(self, part_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(version) FROM parts WHERE part_id=?", (part_id,),
        ).fetchone()
        return (row[0] or 0) + 1

    def set_part_status(
        self, part_id: str, version: int, status: str, actor: str = "system"
    ) -> None:
        """Activating retires the predecessor, so `latest_active` is never ambiguous.

        Wrapped in the same try/except/rollback as `replace_active_version` and
        `apply_review_outcome`, and for the identical reason: this is a
        MULTI-statement write behind one `commit()`. If the final write raised, the
        retires above it sat uncommitted on the connection and the NEXT store call's
        `commit()` landed them — an id left with ZERO active versions, and every
        model naming that part failing generation with nothing in the audit log to
        say which call did it.
        """
        part = self.load_part(part_id, version)
        if part is None:
            raise ValueError(f"{part_id}@v{version} not found")
        if status not in self._STATUS_TRANSITIONS.get(part.status, set()):
            raise ValueError(
                f"illegal status transition {part.status} -> {status} for {part.ref}"
            )
        if status == "retired":
            # A published model naming this part would resolve to nothing at its next
            # generation. Refused here rather than in a route, because it is the
            # invariant — the same placement `save_fence_model`'s immutability refusal
            # argues for. Note it checks ACTIVE models only: a draft naming a part it
            # is about to stop naming must not block the retirement.
            #
            # The question is asked of the ID, not of this version, because that is
            # what a model names: `part_id` is unpinned and resolution takes
            # `latest_active`. So retiring one version while ANOTHER stays active
            # takes nothing away from any slot — which is the ordinary way an
            # abandoned draft is discarded, and refusing it left every draft of an
            # in-use part stuck forever, `draft -> {active, retired}` being the only
            # transitions it has.
            leaves_none = not any(
                v != version for (v,) in self._conn.execute(
                    "SELECT version FROM parts WHERE part_id=? AND status='active'",
                    (part_id,),
                ).fetchall()
            )
            naming = self._models_naming_part(part_id) if leaves_none else []
            if naming:
                raise ValueError(
                    f"{part.ref} is still named by {', '.join(naming)} — retiring it "
                    "would leave those slots with nothing eligible"
                )
        if status == "active":
            # Same moment and same voice as `save_part`: what a part earns at
            # authoring time it must earn at the one act that makes it the answer
            # every model naming its id resolves to.
            self._refuse_invalid_part(part.model_copy(update={"status": status}))
        try:
            if status == "active":
                for row in self._conn.execute(
                    "SELECT version FROM parts WHERE part_id=? AND status='active'",
                    (part_id,),
                ).fetchall():
                    if row[0] != version:
                        self._set_part_status_nocommit(part_id, row[0], "retired", actor)
            self._set_part_status_nocommit(part_id, version, status, actor)
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    def _refuse_invalid_part(self, part: Part) -> None:
        """The authoring refusals a PUBLISHED part earns, at the moment it publishes.

        `validate_part`'s docstring promises "refusals a part earns at authoring
        time" and design §3.3 promises the same, but its only caller was
        `validate_model` — i.e. GENERATION, which hands the author a 422 on a job
        they were pricing instead of a refusal on the part they were writing.

        A draft is exempt by `validate_part` itself: that is what lets an author
        write a spec before the item exists. No catalog means no answer rather than
        a wrong one — the same `library is None` bargain `validate_model` strikes,
        for a store that has not been seeded yet.
        """
        if part.status == "draft":
            return
        catalog = self.load_catalog()
        if catalog is None:
            return
        from fenceai.parts.validate import validate_part

        errors = validate_part(part, catalog)
        if errors:
            raise ValueError("; ".join(errors))

    def _models_naming_part(self, part_id: str) -> list[str]:
        from fenceai.parts.resolve import part_requirements
        return sorted(
            m.ref for m in self.fence_model_library().models
            if m.status == "active"
            and any(r.part_id == part_id for _key, r in part_requirements(m))
        )

    def _set_part_status_nocommit(
        self, part_id: str, version: int, status: str, actor: str
    ) -> None:
        part = self.load_part(part_id, version)
        part.status = status  # type: ignore[assignment]
        part = Part.model_validate(part.model_dump())  # re-validate the Literal
        self._conn.execute(
            "UPDATE parts SET status=?, doc=? WHERE part_id=? AND version=?",
            (status, part.model_dump_json(), part_id, version),
        )
        self._audit(actor, f"part_status:{status}", part.ref)

    # -- generation runs (append-only) -----------------------------------------

    def save_run(self, result: GenerationResult, actor: str = "system") -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO generation_runs (id, project_id, created_at, doc) "
            "VALUES (?,?,?,?)",
            (result.run.id, result.run.project_id, _now(), result.model_dump_json()),
        )
        self._audit(actor, "save_run", result.run.id)
        self._conn.commit()

    def load_run(self, run_id: str) -> GenerationResult | None:
        row = self._conn.execute(
            "SELECT doc FROM generation_runs WHERE id=?", (run_id,)
        ).fetchone()
        return GenerationResult.model_validate_json(row[0]) if row else None

    def list_runs(self, project_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, created_at FROM generation_runs WHERE project_id=? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        return [{"id": r[0], "created_at": r[1]} for r in rows]

    # -- corrections (append-only) ----------------------------------------------

    def save_correction(self, c: Correction, actor: str = "system") -> None:
        self._conn.execute(
            "INSERT INTO corrections (id, project_id, doc) VALUES (?,?,?)",
            (c.id, c.project_id, c.model_dump_json()),
        )
        self._audit(actor, "save_correction", c.id)
        self._conn.commit()

    def list_corrections(self, project_id: str | None = None) -> list[Correction]:
        if project_id:
            rows = self._conn.execute(
                "SELECT doc FROM corrections WHERE project_id=? ORDER BY id", (project_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT doc FROM corrections ORDER BY id").fetchall()
        return [Correction.model_validate_json(r[0]) for r in rows]

    # -- inventory ---------------------------------------------------------------

    def save_inventory(self, project_id: str, inv: Inventory, actor: str = "system") -> None:
        self._conn.execute(
            "INSERT INTO inventories (project_id, doc) VALUES (?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET doc=excluded.doc",
            (project_id, inv.model_dump_json()),
        )
        self._audit(actor, "save_inventory", project_id)
        self._conn.commit()

    def load_inventory(self, project_id: str) -> Inventory:
        row = self._conn.execute(
            "SELECT doc FROM inventories WHERE project_id=?", (project_id,)
        ).fetchone()
        return Inventory.model_validate_json(row[0]) if row else Inventory()

    # -- quotes (append-only content; lifecycle status only) ---------------------

    def save_quote(self, quote: "Quote", actor: str = "system") -> None:
        quote.created_at = quote.created_at or _now()
        self._conn.execute(
            "INSERT INTO quotes (id, project_id, status, created_at, doc) VALUES (?,?,?,?,?)",
            (quote.id, quote.project_id, quote.status, quote.created_at,
             quote.model_dump_json()),
        )
        self._audit(actor, "save_quote", quote.id)
        self._conn.commit()

    def load_quote(self, quote_id: str) -> "Quote | None":
        from fenceai.fulfillment.quote import Quote

        row = self._conn.execute(
            "SELECT doc FROM quotes WHERE id=?", (quote_id,)
        ).fetchone()
        return Quote.model_validate_json(row[0]) if row else None

    def list_quotes(self, project_id: str) -> list["Quote"]:
        from fenceai.fulfillment.quote import Quote

        rows = self._conn.execute(
            "SELECT doc FROM quotes WHERE project_id=? ORDER BY created_at, id",
            (project_id,),
        ).fetchall()
        return [Quote.model_validate_json(r[0]) for r in rows]

    def latest_accepted_quote(self, project_id: str) -> "Quote | None":
        quotes = [q for q in self.list_quotes(project_id) if q.status == "accepted"]
        return quotes[-1] if quotes else None

    def accept_quote(self, quote_id: str, actor: str = "system") -> "Quote":
        """Atomically accept a quote and supersede the project's previously
        accepted quote (mirrors the knowledge-version lifecycle discipline)."""
        from fenceai.fulfillment.quote import QUOTE_STATUS_TRANSITIONS, Quote

        quote = self.load_quote(quote_id)
        if quote is None:
            raise KeyError(quote_id)
        if "accepted" not in QUOTE_STATUS_TRANSITIONS.get(quote.status, set()):
            raise ValueError(f"illegal quote transition {quote.status} -> accepted")
        try:
            rows = self._conn.execute(
                "SELECT id, doc FROM quotes WHERE project_id=? AND status='accepted'",
                (quote.project_id,),
            ).fetchall()
            for qid, doc in rows:
                prev = Quote.model_validate_json(doc)
                prev.status = "superseded"
                self._conn.execute(
                    "UPDATE quotes SET status=?, doc=? WHERE id=?",
                    ("superseded", prev.model_dump_json(), qid),
                )
                self._audit(actor, "quote_status:superseded", qid)
            quote.status = "accepted"
            self._conn.execute(
                "UPDATE quotes SET status=?, doc=? WHERE id=?",
                ("accepted", quote.model_dump_json(), quote_id),
            )
            self._audit(actor, "quote_status:accepted", quote_id)
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise
        return quote

    # -- catalog -----------------------------------------------------------------

    def save_catalog(self, catalog: "Catalog", actor: str = "system") -> None:
        self._conn.execute(
            "INSERT INTO catalogs (id, doc) VALUES ('default',?) "
            "ON CONFLICT(id) DO UPDATE SET doc=excluded.doc",
            (catalog.model_dump_json(),),
        )
        self._audit(actor, "save_catalog", "default")
        self._conn.commit()

    def load_catalog(self) -> "Catalog | None":
        from fenceai.catalog.model import Catalog

        row = self._conn.execute("SELECT doc FROM catalogs WHERE id='default'").fetchone()
        return Catalog.model_validate_json(row[0]) if row else None

    # -- audit -------------------------------------------------------------------

    def log(self, actor: str, action: str, ref: str) -> None:
        """Public audit hook for domain events the store doesn't itself perform
        (e.g. a BOM computed against an inventory snapshot)."""
        self._audit(actor, action, ref)
        self._conn.commit()

    def audit_entries(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT seq, at, actor, action, ref FROM audit_log ORDER BY seq DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"seq": r[0], "at": r[1], "actor": r[2], "action": r[3], "ref": r[4]}
            for r in rows
        ]
