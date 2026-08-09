"""SQLite persistence (ADR-0008): document-style tables behind thin repositories.

Domain code never touches SQL. Knowledge versions, generation runs, corrections and
the audit log are append-only; version content is immutable (only lifecycle status
may change, via a dedicated method that audits the transition).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from fenceai.fulfillment.fulfill import Inventory
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion
from fenceai.learning.model import Correction
from fenceai.project.model import Project
from fenceai.strategy.model import GenerationResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_versions (
    object_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
    doc TEXT NOT NULL, PRIMARY KEY (object_id, version));
CREATE TABLE IF NOT EXISTS generation_runs (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, created_at TEXT NOT NULL,
    doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS corrections (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inventories (project_id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS catalogs (id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, ref TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript("PRAGMA journal_mode=WAL;" + _SCHEMA)
        self._conn.commit()

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

    def insert_knowledge_version(self, v: KnowledgeVersion, actor: str = "system") -> None:
        self._conn.execute(
            "INSERT INTO knowledge_versions (object_id, version, status, doc) VALUES (?,?,?,?)",
            (v.object_id, v.version, v.status, v.model_dump_json()),
        )
        self._audit(actor, "insert_knowledge_version", v.ref)
        self._conn.commit()

    def update_knowledge_status(
        self, object_id: str, version: int, status: str, actor: str = "system"
    ) -> None:
        """The only mutation versions allow: lifecycle status (content is immutable)."""
        row = self._conn.execute(
            "SELECT doc FROM knowledge_versions WHERE object_id=? AND version=?",
            (object_id, version),
        ).fetchone()
        if row is None:
            raise KeyError(f"{object_id}@v{version}")
        v = KnowledgeVersion.model_validate_json(row[0])
        v.status = status  # type: ignore[assignment]
        self._conn.execute(
            "UPDATE knowledge_versions SET status=?, doc=? WHERE object_id=? AND version=?",
            (status, v.model_dump_json(), object_id, version),
        )
        self._audit(actor, f"knowledge_status:{status}", v.ref)
        self._conn.commit()

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

    def audit_entries(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT seq, at, actor, action, ref FROM audit_log ORDER BY seq DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"seq": r[0], "at": r[1], "actor": r[2], "action": r[3], "ref": r[4]}
            for r in rows
        ]
