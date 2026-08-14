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
from fenceai.catalog.model import Catalog, Product, catalog_hash
from fenceai.core.errors import GenerationFailure, ReadRefused
from fenceai.core.ids import new_id
from fenceai.decisions.explain import explain_element
from fenceai.decisions.supply import with_supply_decisions
from fenceai.fencemodel.library import ModelListing
from fenceai.fencemodel.model import FenceModel, unknown_skus, validate_model
from fenceai.fencemodel.preview import PanelPreview, PreviewRequest, preview_panel
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.fulfill import Inventory
from fenceai.fulfillment.pipeline import PricedRun, price_strategy
from fenceai.fulfillment.quote import Quote
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeVersion
from fenceai.learning.impact import (
    ImpactCase,
    ImpactReport,
    activated_copy,
    preview_impact,
    preview_model_impact,
)
from fenceai.learning.model import Correction, ReviewAction
from fenceai.learning.review import apply_review
from fenceai.project.intents import confirm_intent
from fenceai.project.model import Annotation, Project
from fenceai.report.structure import build_structure
from fenceai.store.db import Store
from fenceai.strategy.generator import LEGACY_MODEL_ID, generate
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


def _fresh_catalog(result):
    """A stored run re-read against a different catalog would re-resolve supply
    and name a different product with nobody told (structure review A2). Stamping
    inventory_hash on the response is not the same as checking it — this is the
    check: refuse rather than silently reprice/resupply a run's read views."""
    catalog = state.store.load_catalog()
    # over the SAME set the run stamped, or the comparison is between two
    # different questions. An empty set means the run predates the narrowing and
    # is only comparable against the whole-catalog hash it was stamped with.
    current = catalog_hash(catalog, result.run.catalog_skus or None)
    if result.run.catalog_hash and current != result.run.catalog_hash:
        raise HTTPException(409, {
            "code": "catalog_changed",
            "run_catalog_hash": result.run.catalog_hash,
            "current_catalog_hash": current,
        })
    return catalog


def _priced(result) -> tuple[Catalog, Inventory, PricedRun]:
    """The read path every BOM-shaped view shares: check the catalog is the one
    the run was generated against, then run the single domain pipeline, then
    convert its refusals into HTTP.

    This exists because the four copies of that sequence had already diverged —
    `create_quote` called `load_catalog()` directly, so the one endpoint that
    freezes an immutable commercial document was the ONLY one exempt from the
    staleness check (BOM 409, structure 409, quote 200). One helper, four
    callers, no way to be the odd one out.
    """
    catalog = _fresh_catalog(result)
    inventory = state.store.load_inventory(result.run.project_id)
    try:
        priced = price_strategy(
            result.strategy, catalog, inventory,
            demand_skus=result.run.demand_skus,
            preset=result.run.objective_preset,
        )
    except ReadRefused as e:
        # code + params, not a raw English sentence: a run generated before the
        # fence-model change surfaced as untranslated text in a Hebrew-first UI
        raise HTTPException(400, {"code": e.code, "params": e.params, "message": str(e)})
    except ValueError as e:
        raise HTTPException(400, str(e))
    return catalog, inventory, priced


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
            models=state.store.fence_model_library(),
            default_model=project.fence_model,
        )
    except GenerationFailure as e:
        # code + params when the failure carries them, exactly as the read routes
        # do for ReadRefused: a 422 whose only content is an English sentence is
        # rendered by the client as "the action failed (422)", which tells a user
        # who mistyped a SKU neither which SKU nor that a SKU is the problem —
        # after losing the strategy they were working on.
        if e.code:
            raise HTTPException(422, {
                "code": e.code, "params": e.params, "message": str(e),
            })
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
    _, inventory, priced = _priced(result)
    # the BOM is what a customer gets quoted on: record which inventory state
    # produced it so a later recomputation is distinguishable (final review, #5)
    inventory_hash = hashlib.sha256(inventory.model_dump_json().encode()).hexdigest()[:16]
    state.store.log("system", "fulfill", f"{run_id}:inv={inventory_hash}")
    # routing an unresolved line out of `requirements` (so a blank sku can never
    # reach fulfill()/the ledger) must not make it disappear from this view —
    # /bom is a working view, so it reports the gap rather than refusing.
    return {"requirements": priced.requirements, "unresolved": priced.unresolved,
            "bom": priced.bom, "inventory_hash": inventory_hash}


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
    catalog, inventory, priced = _priced(result)
    report = build_structure(project.topology, result.strategy, priced.requirements,
                             priced.bom, run_id=run_id, catalog=catalog)
    # The layout is a function of the run alone, but the PARTS name the bars a
    # piece is cut from, and those depend on the inventory that was on hand.
    # Stamp it, exactly as /bom does, so two sheets that differ are explainable.
    report.inventory_hash = hashlib.sha256(
        inventory.model_dump_json().encode()).hexdigest()[:16]
    # A bay with a part nothing can supply must still say so on the setting-out
    # sheet, not just on /bom — stamped the same way as inventory_hash, since
    # build_structure() itself stays a pure function of its inputs.
    report.warnings = priced.warnings
    report.unresolved = priced.unresolved
    return report


# -- quotes (persisted BOM snapshots) ---------------------------------------------

class QuoteCreate(BaseModel):
    label: str = ""
    author: str = "user"


@app.post("/api/runs/{run_id}/quote")
def create_quote(run_id: str, body: QuoteCreate) -> Quote:
    """Snapshot the run's BOM as an immutable quote document."""
    result = _run(run_id)
    # via _priced, so the catalog staleness check applies here TOO. It did not
    # before: this was the only one of the four sites that loaded the catalog
    # directly, which made the one endpoint producing an immutable commercial
    # document the one endpoint that would happily freeze a stale one.
    _, inventory, priced = _priced(result)
    if priced.unresolved:
        # An immutable commercial document must not silently price a job that's
        # missing a part — refuse rather than freeze a quote that under-prices it
        # (get_bom/get_structure are working views and stay permissive; a quote
        # is the one place this becomes a hard stop).
        raise HTTPException(400, {
            "code": "unresolved_supply",
            "unresolved": [
                {"requirement_id": r.id, "role": r.role, "slot_key": r.slot_key,
                 "pegs": r.pegs}
                for r in priced.unresolved
            ],
        })
    quote = Quote(
        id=new_id("quote"), project_id=result.run.project_id, run_id=run_id,
        label=body.label,
        inventory_hash=hashlib.sha256(inventory.model_dump_json().encode()).hexdigest()[:16],
        knowledge_snapshot_hash=result.run.snapshot_hash,
        # which catalog priced this document, beside which knowledge shaped it —
        # the two inputs that decide what the customer was quoted
        catalog_hash=result.run.catalog_hash,
        requirements=priced.requirements, bom=priced.bom,
        total_cents=priced.bom.total_cents,
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
    # The supply choice is made in fulfillment, which has no graph builder, so
    # its nodes are derived here from the same pipeline the money views run.
    # Without this, /explain cannot say why one eligible product was bought
    # instead of another — the decision most worth explaining.
    graph = result.graph
    try:
        _, _, priced = _priced(result)
    except HTTPException:
        # a stale catalog or an unreadable run must not cost the reader the
        # explanation of everything else in the graph
        priced = None
    if priced is not None:
        graph = with_supply_decisions(graph, priced.decisions)
    lines = explain_element(graph, element_id, lang=lang, units=units)
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
            fence_model=p.fence_model, policy=p.policy,
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
                          _impact_cases(), state.store.fence_model_library())


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
                          _impact_cases(), state.store.fence_model_library())



@app.post("/api/knowledge/{object_id}/{version}/retire")
def retire_knowledge(object_id: str, version: int, author: str = "user"):
    try:
        state.store.update_knowledge_status(object_id, version, "retired", actor=author)
    except KeyError:
        raise HTTPException(404, f"{object_id}@v{version} not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"retired": f"{object_id}@v{version}"}


# -- fence models -----------------------------------------------------------------

def _model_errors(model: FenceModel) -> dict | None:
    """Load-time validation as the API reports it: `code + params`, so a Hebrew
    UI renders a sentence rather than English authoring text. The unknown-sku case
    gets its own code because it is the one a user causes by typing, and it names
    what they typed."""
    errors = validate_model(model, state.store.load_catalog())
    if not errors:
        return None
    missing = unknown_skus(model, state.store.load_catalog())
    if missing:
        return {"code": "fence_model_unknown_sku",
                "params": {"skus": ", ".join(missing), "model_ref": model.ref,
                           "n": len(missing)},
                "errors": errors}
    return {"code": "fence_model_invalid",
            "params": {"model_ref": model.ref, "errors": "; ".join(errors),
                       "n": len(errors)},
            "errors": errors}


def _reserved(model_id: str) -> None:
    """M-LEGACY is the compatibility path, not a model anybody authors.

    Its eligibility is rebuilt per run from the resolved demand SKUs, because a
    stored document naming RAIL-3000 would quietly outrank a DefaultComponent
    rule that changed the rail — so a published v2 would be offered by the
    picker, priced by the preview and reported on by the impact preview, and then
    ignored at generation. One version, for ever, enforced where a version could
    otherwise be minted.
    """
    if model_id == LEGACY_MODEL_ID:
        raise HTTPException(409, {
            "code": "fence_model_reserved",
            "params": {"model_id": model_id},
        })


@app.get("/api/fence-models")
def list_fence_models() -> list[ModelListing]:
    return state.store.fence_model_library().listing()


@app.get("/api/fence-models/{model_id}/{version}")
def get_fence_model(model_id: str, version: int) -> FenceModel:
    model = state.store.load_fence_model(model_id, version)
    if model is None:
        raise HTTPException(404, f"{model_id}@v{version} not found")
    return model


@app.post("/api/fence-models")
def create_fence_model(model: FenceModel, author: str = "user"):
    """A new model always arrives as a draft at the next free version.

    A draft may be saved INVALID, and its errors are returned rather than
    refused. Authoring is iterative — a panel half-built is invalid by
    definition, and a save that refuses until the whole thing is coherent is a
    save nobody can use. The gate is `publish`, and `_validate_resolved_model`
    still refuses to GENERATE from an invalid model, so an invalid draft can
    never quietly become a fence.
    """
    _reserved(model.id)
    draft = model.model_copy(update={
        "version": state.store.next_fence_model_version(model.id),
        "status": "draft",
    })
    state.store.save_fence_model(draft, actor=author)
    return {"model": draft, "invalid": _model_errors(draft)}


@app.put("/api/fence-models/{model_id}/draft")
def put_fence_model_draft(model_id: str, model: FenceModel, author: str = "user"):
    _reserved(model_id)
    library = state.store.fence_model_library()
    # the HIGHEST draft, which is the one `listing()` reports and therefore the
    # one the editor is showing. Taking the first would write the user's edits
    # into a different version from the one on their screen whenever two drafts
    # exist — the two disagreed, and the disagreement was silent.
    drafts = [m for m in library.models if m.id == model_id and m.status == "draft"]
    existing = max(drafts, key=lambda m: m.version, default=None)
    version = existing.version if existing else state.store.next_fence_model_version(model_id)
    draft = model.model_copy(update={"id": model_id, "version": version, "status": "draft"})
    try:
        state.store.save_fence_model(draft, actor=author)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"model": draft, "invalid": _model_errors(draft)}


@app.post("/api/fence-models/{model_id}/preview-impact")
def preview_fence_model_impact(model: FenceModel) -> ImpactReport:
    """What would publishing this model version change, across all projects?

    Editing a model's slat gap is a portfolio-wide change, and foundation §11
    requires impact to be exposed before it. `FenceModel` is catalog-side rather
    than a knowledge object, so it does not inherit /api/knowledge/preview-impact
    for free — without this, the authoring feature would ship a change nobody
    could preview.
    """
    return preview_model_impact(
        model, state.store.fence_model_library(), state.store.knowledge_base(),
        state.store.load_catalog(), _impact_cases(),
    )


@app.delete("/api/fence-models/{model_id}/{version}")
def discard_fence_model_draft(model_id: str, version: int, author: str = "user"):
    """Throw a draft away. ONLY a draft.

    Without this, every abandoned attempt stayed in the library for ever — and
    the editor's first design saved on every keystroke, so a half-typed id left a
    row behind for each character. A published version is never deletable: a
    stored run or an accepted quote may name it, and deleting one would make an
    immutable commercial document refer to nothing.
    """
    _reserved(model_id)
    model = state.store.load_fence_model(model_id, version)
    if model is None:
        raise HTTPException(404, f"{model_id}@v{version} not found")
    if model.status != "draft":
        raise HTTPException(409, {
            "code": "fence_model_not_a_draft",
            "params": {"model_ref": model.ref, "status": model.status},
        })
    state.store.delete_fence_model_draft(model_id, version, actor=author)
    return {"discarded": model.ref}


@app.post("/api/fence-models/{model_id}/{version}/publish")
def publish_fence_model(model_id: str, version: int, author: str = "user"):
    """Freeze a draft. This is the gate a draft save deliberately is not: from
    here the document is immutable and projects may select it."""
    model = state.store.load_fence_model(model_id, version)
    if model is None:
        raise HTTPException(404, f"{model_id}@v{version} not found")
    if model.status != "draft":
        raise HTTPException(409, f"{model.ref} is not a draft")
    invalid = _model_errors(model)
    if invalid:
        raise HTTPException(422, invalid)
    state.store.set_fence_model_status(model_id, version, "active", actor=author)
    return state.store.load_fence_model(model_id, version)


@app.post("/api/fence-models/{model_id}/{version}/status")
def set_fence_model_status(
    model_id: str, version: int, status: Literal["active", "retired"],
    author: str = "user",
):
    try:
        state.store.set_fence_model_status(model_id, version, status, actor=author)
    except KeyError:
        raise HTTPException(404, f"{model_id}@v{version} not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return state.store.load_fence_model(model_id, version)


def _preview_or_refuse(model: FenceModel, bay: PreviewRequest) -> PanelPreview:
    try:
        return preview_panel(model, bay, state.store.load_catalog())
    except ReadRefused as e:
        raise HTTPException(400, {"code": e.code, "params": e.params, "message": str(e)})
    except ValueError as e:
        raise HTTPException(400, str(e))


class DocumentPreviewRequest(BaseModel):
    """A model that need not exist yet, and the bay to imagine it into."""

    model: FenceModel
    bay: PreviewRequest = PreviewRequest()


@app.post("/api/fence-models/preview")
def preview_fence_model_document(body: DocumentPreviewRequest) -> PanelPreview:
    """What one panel of THIS DOCUMENT is made of — stored or not.

    The editor's reason for existing. `preview_panel` was always a pure function
    of a `FenceModel` object; only the route below insisted on a store lookup, and
    that accident of signature is what made a live preview and a save-on-demand
    editor look mutually exclusive. It is not a real constraint: the impact
    preview two routes up has taken an unsaved document in its body since W3.

    Charging a keystroke to the database to see its effect is the alternative,
    and it is a bad one — it writes a library row per typed character of a model
    id, an audit row per pause, and it turns "a draft may be saved invalid" (a
    permission about CONTENT) into a licence to save when the user did not ask.
    Stores nothing, is not quotable, and refuses nothing a draft may hold.
    """
    return _preview_or_refuse(body.model, body.bay)


@app.post("/api/fence-models/{model_id}/{version}/preview")
def preview_fence_model(model_id: str, version: int, body: PreviewRequest) -> PanelPreview:
    """What one panel of this STORED model is made of, at this height and width.

    Deliberately available BEFORE a project has a topology, and for a version
    that is still a draft: the point is to see what a model builds while deciding
    whether to build it. It stores nothing and it is not quotable.
    """
    model = state.store.load_fence_model(model_id, version)
    if model is None:
        raise HTTPException(404, f"{model_id}@v{version} not found")
    return _preview_or_refuse(model, body)


@app.put("/api/projects/{project_id}/fence-model")
def put_project_fence_model(project_id: str, choice: FenceModelChoice | None = None) -> Project:
    """The project's default model. Refused at the boundary rather than at
    generation: a typo that only fails when someone presses Generate has already
    cost them the strategy they were working on."""
    project = _project(project_id)
    if choice is not None:
        if state.store.fence_model_library().resolve(
                choice.model_id, choice.version_pin) is None:
            raise HTTPException(422, {
                "code": "fence_model_not_found",
                "params": {"model_id": choice.model_id,
                           "version_pin": choice.version_pin
                           if choice.version_pin is not None else ""},
            })
    project.fence_model = choice
    state.store.save_project(project)
    return project


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
