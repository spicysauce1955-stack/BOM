"""FastAPI application — composition root (system-design.md API surface).

The API orchestrates persistence and the pure domain functions; no domain logic
lives here. AI adapters are selected once at startup (stub by default, ADR-0009).
"""

from __future__ import annotations

import hashlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fenceai.core.env import load_dotenv

load_dotenv()  # .env in the working directory fills gaps; real env vars win

from fenceai.ai.claude import build_interpreter  # noqa: E402
from fenceai.ai.stub import StubCritic, StubProposer
from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import Product
from fenceai.core.errors import GenerationFailure
from fenceai.core.ids import new_id
from fenceai.decisions.explain import explain_element
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import Inventory, fulfill
from fenceai.fulfillment.quote import Quote
from fenceai.fulfillment.supply import resolve_supply
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeVersion
from fenceai.learning.impact import (
    ImpactCase,
    ImpactReport,
    activated_copy,
    preview_impact,
)
from fenceai.learning.model import Correction, ReviewAction
from fenceai.learning.review import apply_review
from fenceai.project.intents import confirm_intent
from fenceai.project.model import Annotation, Project
from fenceai.report.structure import build_structure
from fenceai.store.db import Store
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import Override
from fenceai.topology.model import Topology

WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "static"


class AppState:
    store: Store
    interpreter = None
    proposer = None
    critic = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.store = Store(os.environ.get("FENCEAI_DB", "fenceai.db"))
    state.interpreter = build_interpreter()
    state.proposer = StubProposer()
    state.critic = StubCritic()
    if state.store.load_catalog() is None:
        state.store.save_catalog(demo_catalog(), actor="seed")
    if not state.store.knowledge_base().versions:
        for v in demo_knowledge().versions:
            state.store.insert_knowledge_version(v, actor="seed")
    if not state.store.list_projects():
        state.store.save_project(_sample_project(), actor="seed")
    yield
    state.store.close()




def _sample_project() -> Project:
    """Seeded example fence: an L with a gate, a slope, and a wall section — new
    users land in a working project, never a blank grid (template-as-onboarding)."""
    from fenceai.topology.model import (
        BasePayload, BaseTopPayload, BaseTopPoint, GatePayload, IntervalEvent,
        Node, PointEvent, Run, Topology,
    )

    def anchor(seg_len, offset):
        return {"segment_index": 0, "offset_mm": offset, "seg_len_at_authoring_mm": seg_len}

    topology = Topology(
        nodes=[
            Node(id="n1", x_mm=0, y_mm=0),
            Node(id="n2", x_mm=9000, y_mm=0),
            Node(id="n3", x_mm=9000, y_mm=6000, z_mm=600),
        ],
        runs=[
            Run(id="run1", start_node_id="n1", end_node_id="n2", point_events=[
                PointEvent(id="ev_gate", anchor=anchor(9000, 3000),
                           payload=GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000")),
            ]),
            Run(id="run2", start_node_id="n2", end_node_id="n3", interval_events=[
                IntervalEvent(id="ev_base", start_anchor=anchor(6000, 0),
                              end_anchor=anchor(6000, 6000),
                              payload=BasePayload(surface="masonry_wall")),
                IntervalEvent(id="ev_top", start_anchor=anchor(6000, 0),
                              end_anchor=anchor(6000, 6000),
                              payload=BaseTopPayload(points=[
                                  BaseTopPoint(pos_permille=0, z_mm=300),
                                  BaseTopPoint(pos_permille=1000, z_mm=300),
                              ])),
            ]),
        ],
    )
    return Project(id=new_id("proj"), name="פרויקט לדוגמה", topology=topology)


app = FastAPI(title="Fence AI", version="0.1.0", lifespan=lifespan)


def _project(project_id: str) -> Project:
    p = state.store.load_project(project_id)
    if p is None:
        raise HTTPException(404, f"project {project_id} not found")
    return p


def _run(run_id: str):
    r = state.store.load_run(run_id)
    if r is None:
        raise HTTPException(404, f"run {run_id} not found")
    return r


@app.get("/api/health")
def health():
    return {"ok": True, "interpreter": state.interpreter.interpreter_id}


# -- projects ------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str


@app.post("/api/projects")
def create_project(body: ProjectCreate) -> Project:
    project = Project(id=new_id("proj"), name=body.name)
    state.store.save_project(project)
    return project


@app.get("/api/projects")
def list_projects() -> list[dict]:
    return [{"id": p.id, "name": p.name} for p in state.store.list_projects()]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> Project:
    return _project(project_id)


@app.put("/api/projects/{project_id}/topology")
def put_topology(project_id: str, topology: Topology) -> Project:
    project = _project(project_id)
    topology.revision = project.topology.revision + 1
    project.topology = topology
    state.store.save_project(project)
    return project


# -- annotations & interpretation ---------------------------------------------

class AnnotationCreate(BaseModel):
    target_ref: str
    text: str
    author: str = "user"


@app.post("/api/projects/{project_id}/annotations")
def add_annotation(project_id: str, body: AnnotationCreate) -> Annotation:
    project = _project(project_id)
    annotation = Annotation(
        id=new_id("ann"), target_ref=body.target_ref, text=body.text, author=body.author
    )
    project.annotations.append(annotation)
    state.store.save_project(project)
    return annotation


@app.post("/api/projects/{project_id}/annotations/{annotation_id}/interpret")
def interpret_annotation(project_id: str, annotation_id: str):
    project = _project(project_id)
    annotation = next((a for a in project.annotations if a.id == annotation_id), None)
    if annotation is None:
        raise HTTPException(404, "annotation not found")
    record = state.interpreter.interpret(annotation)
    annotation.interpretations.append(record)
    state.store.save_project(project)
    return record


class IntentConfirm(BaseModel):
    annotation_id: str
    run_id: str
    confirmed_by: str = "user"


@app.post("/api/projects/{project_id}/intents/{intent_id}/confirm")
def confirm_intent_route(project_id: str, intent_id: str, body: IntentConfirm):
    project = _project(project_id)
    try:
        materialized = confirm_intent(
            project, body.annotation_id, intent_id, body.run_id, body.confirmed_by
        )
    except (StopIteration, ValueError) as e:
        raise HTTPException(400, str(e))
    state.store.save_project(project)
    return {"materialized_id": materialized}


# -- overrides -----------------------------------------------------------------

@app.post("/api/projects/{project_id}/overrides")
def add_override(project_id: str, override: Override) -> Override:
    project = _project(project_id)
    if not override.id:
        override.id = new_id("ov")
    project.overrides.append(override)
    state.store.save_project(project)
    return override


@app.delete("/api/projects/{project_id}/overrides/{override_id}")
def delete_override(project_id: str, override_id: str):
    project = _project(project_id)
    before = len(project.overrides)
    project.overrides = [o for o in project.overrides if o.id != override_id]
    if len(project.overrides) == before:
        raise HTTPException(404, "override not found")
    state.store.save_project(project)
    return {"deleted": override_id}


# -- generation, decisions, BOM -------------------------------------------------

@app.post("/api/projects/{project_id}/generate")
def generate_route(project_id: str):
    project = _project(project_id)
    catalog = state.store.load_catalog()
    kb = state.store.knowledge_base()
    try:
        result = generate(
            project.topology, kb, catalog,
            overrides=project.overrides, policy=project.policy, project_id=project.id,
        )
    except GenerationFailure as e:
        raise HTTPException(422, f"generation failed: {e}")
    state.store.save_run(result)
    critique = state.critic.critique(result)
    return {"result": result, "critique": critique}


@app.get("/api/projects/{project_id}/runs")
def list_runs(project_id: str):
    return state.store.list_runs(project_id)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return _run(run_id)


@app.get("/api/runs/{run_id}/bom")
def get_bom(run_id: str):
    result = _run(run_id)
    catalog = state.store.load_catalog()
    inventory = state.store.load_inventory(result.run.project_id)
    try:
        requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    except ValueError as e:
        raise HTTPException(400, str(e))
    resolution = resolve_supply(requirements, catalog, inventory,
                                preset=result.run.objective_preset)
    requirements = resolution.requirements
    bom = fulfill(requirements, catalog, inventory)
    bom.warnings = resolution.warnings
    # the BOM is what a customer gets quoted on: record which inventory state
    # produced it so a later recomputation is distinguishable (final review, #5)
    inventory_hash = hashlib.sha256(inventory.model_dump_json().encode()).hexdigest()[:16]
    state.store.log("system", "fulfill", f"{run_id}:inv={inventory_hash}")
    return {"requirements": requirements, "bom": bom, "inventory_hash": inventory_hash}


@app.get("/api/runs/{run_id}/structure")
def get_structure(run_id: str):
    """How the fence is laid out and what each element consists of — a derived view
    over the run, persisted nowhere (docs/superpowers/specs/2026-08-11-structure...)."""
    result = _run(run_id)
    project = _project(result.run.project_id)
    # The setting out is measured on the topology — so it must be THE topology the
    # run was generated from. Laying a stored strategy over an edited drawing
    # invents stations for posts nobody placed, and that document goes to site.
    if project.topology.revision != result.run.topology_revision:
        raise HTTPException(409, {
            "code": "topology_changed",
            "run_topology_revision": result.run.topology_revision,
            "project_topology_revision": project.topology.revision,
        })
    catalog = state.store.load_catalog()
    inventory = state.store.load_inventory(result.run.project_id)
    try:
        requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    except ValueError as e:
        raise HTTPException(400, str(e))
    resolution = resolve_supply(requirements, catalog, inventory,
                                preset=result.run.objective_preset)
    requirements = resolution.requirements
    bom = fulfill(requirements, catalog, inventory)
    bom.warnings = resolution.warnings
    report = build_structure(project.topology, result.strategy, requirements, bom,
                             run_id=run_id)
    # The layout is a function of the run alone, but the PARTS name the bars a
    # piece is cut from, and those depend on the inventory that was on hand.
    # Stamp it, exactly as /bom does, so two sheets that differ are explainable.
    report.inventory_hash = hashlib.sha256(
        inventory.model_dump_json().encode()).hexdigest()[:16]
    # A bay with a part nothing can supply must still say so on the setting-out
    # sheet, not just on /bom — stamped the same way as inventory_hash, since
    # build_structure() itself stays a pure function of its four inputs.
    report.warnings = resolution.warnings
    return report


# -- quotes (persisted BOM snapshots) ---------------------------------------------

class QuoteCreate(BaseModel):
    label: str = ""
    author: str = "user"


@app.post("/api/runs/{run_id}/quote")
def create_quote(run_id: str, body: QuoteCreate) -> Quote:
    """Snapshot the run's BOM as an immutable quote document."""
    result = _run(run_id)
    catalog = state.store.load_catalog()
    inventory = state.store.load_inventory(result.run.project_id)
    try:
        requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    except ValueError as e:
        raise HTTPException(400, str(e))
    resolution = resolve_supply(requirements, catalog, inventory,
                                preset=result.run.objective_preset)
    requirements = resolution.requirements
    bom = fulfill(requirements, catalog, inventory)
    bom.warnings = resolution.warnings
    quote = Quote(
        id=new_id("quote"), project_id=result.run.project_id, run_id=run_id,
        label=body.label,
        inventory_hash=hashlib.sha256(inventory.model_dump_json().encode()).hexdigest()[:16],
        knowledge_snapshot_hash=result.run.snapshot_hash,
        requirements=requirements, bom=bom, total_cents=bom.total_cents,
    )
    state.store.save_quote(quote, actor=body.author)
    return quote


@app.get("/api/projects/{project_id}/quotes")
def list_quotes(project_id: str):
    _project(project_id)
    return [
        {"id": q.id, "label": q.label, "created_at": q.created_at, "status": q.status,
         "total_cents": q.total_cents, "run_id": q.run_id}
        for q in state.store.list_quotes(project_id)
    ]


@app.get("/api/quotes/{quote_id}")
def get_quote(quote_id: str) -> Quote:
    q = state.store.load_quote(quote_id)
    if q is None:
        raise HTTPException(404, f"quote {quote_id} not found")
    return q


@app.post("/api/quotes/{quote_id}/accept")
def accept_quote(quote_id: str, author: str = "user") -> Quote:
    try:
        return state.store.accept_quote(quote_id, actor=author)
    except KeyError:
        raise HTTPException(404, f"quote {quote_id} not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/runs/{run_id}/explain/{element_id}")
def explain(
    run_id: str,
    element_id: str,
    lang: Literal["en", "he"] = "en",
    units: Literal["mm", "cm"] = "mm",   # display unit only; the graph stores mm
):
    result = _run(run_id)
    lines = explain_element(result.graph, element_id, lang=lang, units=units)
    if not lines:
        raise HTTPException(404, f"no decisions reference {element_id}")
    return {"element_id": element_id, "explanation": lines}


@app.get("/api/runs/{run_id}/impact/{object_id}")
def knowledge_impact(run_id: str, object_id: str):
    """Which decisions in this run depend on a knowledge object (impact analysis)."""
    result = _run(run_id)
    nodes = result.graph.dependents_of_knowledge(object_id)
    return {"object_id": object_id, "decisions": nodes}


# -- corrections & learning ------------------------------------------------------

class CorrectionCreate(BaseModel):
    generation_run_id: str
    decision_ref: str | None = None
    element_ref: str | None = None
    before: dict = {}
    after: dict = {}
    comment: str | None = None
    author: str = "expert"


@app.post("/api/projects/{project_id}/corrections")
def add_correction(project_id: str, body: CorrectionCreate) -> Correction:
    _project(project_id)
    correction = Correction(id=new_id("corr"), project_id=project_id, **body.model_dump())
    state.store.save_correction(correction, actor=body.author)
    return correction


@app.post("/api/projects/{project_id}/propose-knowledge")
def propose_knowledge(project_id: str):
    corrections = state.store.list_corrections(project_id)
    proposals = state.proposer.propose(corrections)
    stored = []
    existing = {v.object_id for v in state.store.knowledge_base().versions}
    for cand in proposals:
        if cand.object_id in existing:
            continue  # rejected/handled candidates are never re-proposed
        state.store.insert_knowledge_version(cand, actor=f"proposer:{state.proposer.interpreter_id}")
        stored.append(cand)
    return stored


@app.get("/api/candidates")
def list_candidates():
    kb = state.store.knowledge_base()
    return [v for v in kb.versions if v.status == "proposed"]


class ReviewBody(BaseModel):
    action: str
    reviewer: str
    reason: str | None = None
    edited_scope: dict[str, str] | None = None


@app.post("/api/candidates/{object_id}/{version}/review")
def review_candidate(object_id: str, version: int, body: ReviewBody):
    kb = state.store.knowledge_base()
    cand = next(
        (v for v in kb.versions if v.object_id == object_id and v.version == version), None
    )
    if cand is None or cand.status != "proposed":
        raise HTTPException(404, "candidate not found or not reviewable")
    try:
        outcome = apply_review(cand, ReviewAction(**body.model_dump()))
    except ValueError as e:
        raise HTTPException(400, str(e))
    approved = outcome if outcome is not cand else None
    state.store.apply_review_outcome(cand, approved, actor=body.reviewer)
    return outcome


# -- knowledge -------------------------------------------------------------------

@app.get("/api/knowledge")
def list_knowledge():
    return state.store.knowledge_base().versions


class KnowledgeCreate(BaseModel):
    object_id: str
    type: str
    title: str = ""
    scope: dict[str, str] = {}
    condition: dict | None = None
    actions: list[dict] = []
    source_text: str | None = None
    author: str = "user"


@app.post("/api/knowledge")
def upsert_knowledge(body: KnowledgeCreate):
    """New version of a knowledge object; the previous active version is retired."""
    version_no = state.store.next_version(body.object_id)
    v = KnowledgeVersion(
        object_id=body.object_id, version=version_no,
        type=body.type,  # type: ignore[arg-type]
        title=body.title, scope=body.scope,
        condition=body.condition, actions=body.actions,  # type: ignore[arg-type]
        source_text=body.source_text, attributed_to=body.author,
        derived_from=[f"{body.object_id}@v{version_no - 1}"] if version_no > 1 else [],
        status="active",
    )
    state.store.replace_active_version(v, actor=body.author)
    return v


# -- impact preview ---------------------------------------------------------------

def _impact_cases() -> list[ImpactCase]:
    cases = []
    for p in state.store.list_projects():
        accepted = state.store.latest_accepted_quote(p.id)
        cases.append(ImpactCase(
            project_id=p.id, project_name=p.name, topology=p.topology,
            overrides=p.overrides, inventory=state.store.load_inventory(p.id),
            accepted_quote_cents=accepted.total_cents if accepted else None,
        ))
    return cases


@app.post("/api/knowledge/preview-impact")
def preview_knowledge_impact(body: "KnowledgeCreate") -> ImpactReport:
    """What would saving this knowledge version change, across all projects?"""
    hypo = KnowledgeVersion(
        object_id=body.object_id,
        version=state.store.next_version(body.object_id),
        type=body.type,  # type: ignore[arg-type]
        title=body.title, scope=body.scope,
        condition=body.condition, actions=body.actions,  # type: ignore[arg-type]
        attributed_to=body.author, status="draft",
    )
    return preview_impact(hypo, state.store.knowledge_base(), state.store.load_catalog(),
                          _impact_cases())


@app.post("/api/candidates/{object_id}/{version}/preview")
def preview_candidate_impact(object_id: str, version: int) -> ImpactReport:
    """What would approving this candidate change, across all projects?"""
    kb = state.store.knowledge_base()
    cand = next(
        (v for v in kb.versions if v.object_id == object_id and v.version == version), None
    )
    if cand is None or cand.status != "proposed":
        raise HTTPException(404, "candidate not found or not reviewable")
    return preview_impact(activated_copy(cand), kb, state.store.load_catalog(),
                          _impact_cases())



@app.post("/api/knowledge/{object_id}/{version}/retire")
def retire_knowledge(object_id: str, version: int, author: str = "user"):
    try:
        state.store.update_knowledge_status(object_id, version, "retired", actor=author)
    except KeyError:
        raise HTTPException(404, f"{object_id}@v{version} not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"retired": f"{object_id}@v{version}"}


# -- catalog & inventory ----------------------------------------------------------

@app.get("/api/catalog")
def get_catalog():
    return state.store.load_catalog()


@app.put("/api/catalog/products")
def upsert_product(product: Product):
    catalog = state.store.load_catalog()
    catalog.products[product.sku] = product
    state.store.save_catalog(catalog)
    return product


@app.get("/api/projects/{project_id}/inventory")
def get_inventory(project_id: str) -> Inventory:
    _project(project_id)
    return state.store.load_inventory(project_id)


@app.put("/api/projects/{project_id}/inventory")
def put_inventory(project_id: str, inventory: Inventory) -> Inventory:
    _project(project_id)
    state.store.save_inventory(project_id, inventory)
    return inventory


@app.get("/api/audit")
def audit(limit: int = 100):
    return state.store.audit_entries(limit)


if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
