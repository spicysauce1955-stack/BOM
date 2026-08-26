"""FastAPI application — composition root (04-backend.md API surface).

The API orchestrates persistence and the pure domain functions; no domain logic
lives here. AI adapters are selected once at startup (stub by default, ADR-0009).
"""

from __future__ import annotations

import json
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
from fenceai.catalog.model import (
    CATALOG_SCHEMA_VERSION, Catalog, Product, catalog_hash, purchase_price_cents,
)
from fenceai.core.errors import GenerationFailure, ReadRefused, RequestRefused
from fenceai.core.ids import new_id
from fenceai.decisions.explain import explain_element
from fenceai.decisions.supply import with_supply_decisions
from fenceai.fencemodel.library import ModelListing
from fenceai.fencemodel.model import FenceModel, unknown_skus, validate_model
from fenceai.fencemodel.preview import (
    BayPreviewRequest,
    PanelPreview,
    PreviewRequest,
    bay_preview_plan,
    preview_panel,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fencemodel.vocabulary import vocabularies
from fenceai.fulfillment.fulfill import Inventory
from fenceai.fulfillment.pipeline import PricedRun, price_strategy
from fenceai.fulfillment.quote import Quote
from fenceai.fulfillment.supply_run import (
    SUPPLY_BEHAVIOR_VERSION, SupplyRun, inventory_hash, supply_id,
)
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
from fenceai.project.model import Annotation, Project, SiteConditions
from fenceai.report.annexe import WarningPlacement, place_for_plan
from fenceai.report.bom_groups import group_bom
from fenceai.report.section_decisions import decisions_for_section
from fenceai.report.structure import build_structure
from fenceai.store.db import Store
from fenceai.strategy.generator import DEFAULT_POLICY, LEGACY_MODEL_ID, generate
from fenceai.strategy.model import PartUse
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
    # The SHAPE first, because it explains a mismatch the content check would
    # otherwise blame on a price edit that never happened. A run stamped under an
    # older Product schema cannot be compared against today's hash at all — the
    # two are hashes of different questions.
    if (result.run.catalog_schema_version
            and result.run.catalog_schema_version != CATALOG_SCHEMA_VERSION):
        raise HTTPException(409, {
            "code": "catalog_schema_changed",
            "message": (
                f"this run was generated when the catalog recorded "
                f"{result.run.catalog_schema_version!r}; it now records "
                f"{CATALOG_SCHEMA_VERSION!r}. Generate again to read it."
            ),
            "stamped": result.run.catalog_schema_version,
            "current": CATALOG_SCHEMA_VERSION,
        })
    current = catalog_hash(catalog, result.run.catalog_skus or None)
    if result.run.catalog_hash and current != result.run.catalog_hash:
        raise HTTPException(409, {
            "code": "catalog_changed",
            "run_catalog_hash": result.run.catalog_hash,
            "current_catalog_hash": current,
        })
    return catalog


def _live_preset(project_id: str) -> str:
    """The objective in force NOW, from the project's policy.

    NOT `result.run.objective_preset`. A stored run's preset is frozen at its
    FIRST generation: since digest-v3 the preset is not a digest input, so an
    unchanged fence regenerates to the same id and `save_run`'s INSERT OR IGNORE
    keeps the first document for ever. Reading the preset off it would price
    every later read under an objective the user has since changed, silently and
    with no way to see it. The preset is a supply input, sourced from now,
    exactly as inventory is.
    """
    project = state.store.load_project(project_id)
    policy = project.policy if project else {}
    return policy.get("objective_preset", DEFAULT_POLICY["objective_preset"])


def _priced(result, preset: str) -> tuple[Catalog, Inventory, PricedRun]:
    """The read path every BOM-shaped view shares: check the catalog is the one
    the run was generated against, then run the single domain pipeline, then
    convert its refusals into HTTP.

    The preset is a REQUIRED argument rather than something this helper reads off
    the run, so that no caller can quietly fall back to the frozen stored value —
    see `_live_preset`.

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
            preset=preset,
        )
    except ReadRefused as e:
        # code + params, not a raw English sentence: a run generated before the
        # fence-model change surfaced as untranslated text in a Hebrew-first UI
        raise HTTPException(400, {"code": e.code, "params": e.params, "message": str(e)})
    except ValueError as e:
        raise HTTPException(400, str(e))
    return catalog, inventory, priced


def _quoted_warnings(result, priced: PricedRun) -> WarningPlacement:
    """Every quoted warning of every document this run is built to, placed.

    One helper, two callers (/bom and /structure), for the reason `_priced` and
    `_supply_run_for` are one each: two collections of "which documents is this
    fence built to" is how the annexe on the setting-out sheet and the notices on
    the BOM would come to disagree about what the manufacturer said.

    The documents come off the RUN — every bay's `panel.model_ref` — and not off
    the project. A project that has since been pointed at another product line
    must not put that line's warranty notice on a plan built to the old one; the
    run stamped its refs precisely so a reader can go back to the document it was
    built from. A ref the library can no longer answer is SKIPPED rather than
    refused: this is a warning surface, and losing the annexe is not a reason to
    take a working BOM away from somebody.
    """
    library = state.store.fence_model_library()
    refs, models = [], []
    for span in result.strategy.spans:
        ref = span.panel.model_ref if span.panel else ""
        if not ref or ref in refs:
            continue
        model = library.by_ref(ref)
        if model is not None:
            refs.append(ref)
            models.append(model)
    return place_for_plan(models, skus=[line.sku for line in priced.requirements])


def _supply_run_for(result, preset: str, priced: PricedRun,
                    inventory: Inventory) -> SupplyRun:
    """One construction, two callers (/bom and /quote).

    Two copies of a digest's inputs is how the quote path and the BOM path would
    come to name different supply runs for the same fence — the same
    four-copies-of-a-pipeline shape `fulfillment/pipeline.py`'s own docstring
    exists to warn about.
    """
    inv_hash = inventory_hash(inventory)
    return SupplyRun(
        id=supply_id(result.run.id, inv_hash, result.run.catalog_hash, preset),
        design_id=result.run.id,
        inventory_hash=inv_hash,
        catalog_hash=result.run.catalog_hash,
        objective_preset=preset,
        supply_version=SUPPLY_BEHAVIOR_VERSION,
        requirements=priced.requirements,
        unresolved=priced.unresolved,
        bom=priced.bom,
    )


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


@app.put("/api/projects/{project_id}/site")
def put_site_conditions(project_id: str, site: SiteConditions) -> Project:
    """What kind of site this is. Revisioned like the topology, and bumped HERE
    rather than trusted from the client, for the same reason: the revision is
    what every derived view checks itself against, so a client that forgot to
    increment it would silently make a stale document look current."""
    project = _project(project_id)
    site.revision = project.site.revision + 1
    project.site = site
    state.store.save_project(project)
    return project


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
            # threaded in, never read from inside: `generate()` is pure (ADR-0004)
            parts=state.store.part_library(),
            site=project.site,
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
    """Resolve supply for this design against today's yard, and return the SupplyRun.

    This is deliberately not a pure read any more. It used to be one, and that
    was the defect: /bom read LIVE inventory, so one run id printed two different
    BOMs with `GET /api/runs/{id}` byte-identical between them, and the
    inventory_hash that would have explained the difference was computed on every
    read and written only to the audit log. It entered no identity, no stored
    document and no quote, so a reader holding two printouts could not tell which
    yard each was priced against — and neither could the system.

    Writing here is safe because the id IS the content: the same design against
    the same inventory, catalog and preset digests to the same `supply_id` and
    `save_supply_run`'s INSERT OR IGNORE does not write twice. Growth tracks real
    changes to the yard, not read volume, which is why no retention policy is
    needed yet (spec §7.2).
    """
    result = _run(run_id)
    preset = _live_preset(result.run.project_id)
    _, inventory, priced = _priced(result, preset)
    # the STORED row, not the one just built: on a repeat read INSERT OR IGNORE
    # keeps the first, and echoing our own object would report a `created_at` the
    # database does not have — making two reads of an unchanged fence differ
    supply = state.store.save_supply_run(_supply_run_for(result, preset, priced, inventory))
    # the audit action keeps its name and gains the supply id: the ref used to be
    # the only place the inventory hash was recorded, and is now a pointer to a
    # row that holds it
    state.store.log("system", "fulfill",
                    f"{run_id}:inv={supply.inventory_hash}:{supply.id}")
    # routing an unresolved line out of `requirements` (so a blank sku can never
    # reach fulfill()/the ledger) must not make it disappear from this view —
    # /bom is a working view, so it reports the gap rather than refusing.
    # The same demand, grouped by what CAUSED it. Derived here rather than in the
    # client because the pegs are a backend fact and a second inversion of them
    # in JS is how the two views would come to disagree about which bay bought a
    # rail. Deliberately NOT topology-dependent: /bom stays readable when the
    # drawing has moved on, which is why it groups by `run_ref` and leaves the
    # section TAGS to `js/structure-data.js`, the single tag source.
    return {"requirements": priced.requirements, "unresolved": priced.unresolved,
            "bom": priced.bom, "inventory_hash": supply.inventory_hash,
            "supply": supply,
            # What the documents warn, placed. This view renders the `product`
            # and `model` buckets — "on the BOM lines using it, once per line
            # group" (§3.3.5) — and carries the rest so the tab can say how many
            # are in the annexe instead of dropping them at the edge of a screen.
            "quoted_warnings": _quoted_warnings(result, priced),
            "grouped": group_bom(result.strategy, priced.requirements, priced.bom,
                                 priced.decisions, priced.unresolved)}


def _refuse_moved_site(project: Project, result) -> None:
    """The `topology_changed` failure through a door that guard cannot watch.

    Compares the FACTS, not the revision. A revision counts saves, so guarding on
    it meant that re-saving identical site conditions bricked the run: the digest
    hashes facts, so regeneration returned the same id, `INSERT OR IGNORE` kept
    the stored document with the old counter, and no user action could repair it.

    It names the dimensions that moved, because "the site conditions changed" on
    a five-field form sends the reader to compare them by eye.
    """
    was, now = result.run.site_facts, project.site.facts()
    if was == now:
        return
    moved = sorted(k for k in set(was) | set(now) if was.get(k) != now.get(k))
    raise HTTPException(409, {
        "code": "site_conditions_changed",
        "changed": ", ".join(moved),
        "run_site_revision": result.run.site_revision,
        "project_site_revision": project.site.revision,
    })


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
    # The SAME failure through a door the guard above cannot watch. Site
    # conditions are not part of `topology`, so changing a project from Exposure
    # B to C moves the span limit, moves the posts — and this document would
    # render the old layout without complaint. That document goes to site.
    _refuse_moved_site(project, result)
    preset = _live_preset(result.run.project_id)
    catalog, inventory, priced = _priced(result, preset)
    report = build_structure(project.topology, result.strategy, priced.requirements,
                             priced.bom, run_id=run_id, catalog=catalog)
    # The layout is a function of the run alone, but the PARTS name the bars a
    # piece is cut from, and those depend on the inventory that was on hand — so
    # the sheet goes through the SAME supply run /bom and /quote do. Two ids here
    # would mean the sheet was cut against a different yard than the BOM was
    # priced against, which is this defect in its most expensive form; one
    # construction and an idempotent digest make that unrepresentable.
    supply = state.store.save_supply_run(
        _supply_run_for(result, preset, priced, inventory))
    report.inventory_hash = supply.inventory_hash
    report.supply_id = supply.id
    # A bay with a part nothing can supply must still say so on the setting-out
    # sheet, not just on /bom — stamped the same way as inventory_hash, since
    # build_structure() itself stays a pure function of its inputs.
    report.warnings = priced.warnings
    report.unresolved = priced.unresolved
    # The annexe: stamped here rather than computed in `build_structure`, which is
    # handed the topology, the strategy and the numbers and deliberately not the
    # library the fence models live in.
    report.quoted_warnings = _quoted_warnings(result, priced)
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
    # ...and the SITE staleness check, by the same argument one line up. /bom and
    # /structure stay permissive because they are working views; a quote is the
    # one endpoint that freezes an immutable commercial document, so a quote
    # priced under Exposure B while the project now says C is signed and sent.
    # (This is a staleness guard, unlike `topology_changed` next door, which
    # exists because /structure MIXES a stored run with a live topology.)
    _refuse_moved_site(_project(result.run.project_id), result)
    preset = _live_preset(result.run.project_id)
    _, inventory, priced = _priced(result, preset)
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
    # the same digest /bom computes, from the same inputs — so a quote and the
    # BOM read that preceded it name ONE supply run rather than two. Saved here
    # as well because a quote may be the first thing a project ever asks for, and
    # the document it stands behind must exist.
    supply = state.store.save_supply_run(
        _supply_run_for(result, preset, priced, inventory), actor=body.author)
    quote = Quote(
        id=new_id("quote"), project_id=result.run.project_id, run_id=run_id,
        label=body.label,
        inventory_hash=supply.inventory_hash,
        knowledge_snapshot_hash=result.run.snapshot_hash,
        # which catalog priced this document, beside which knowledge shaped it —
        # the two inputs that decide what the customer was quoted
        catalog_hash=result.run.catalog_hash,
        # and WHICH supply run it froze — the thing that was missing, and the
        # reason two quotes of one run against two yards used to be
        # indistinguishable except by their totals
        supply_id=supply.id,
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
        _, _, priced = _priced(result, _live_preset(result.run.project_id))
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


@app.get("/api/runs/{run_id}/sections/{section_id}/decisions")
def section_decisions(
    run_id: str,
    section_id: str,
    lang: Literal["en", "he"] = "en",
    units: Literal["mm", "cm"] = "mm",   # display unit only; the graph stores mm
):
    """Only the decisions that settled something about ONE section.

    It REFUSES a moved topology, exactly as /structure does and for the same
    reason: a section is a topology object, so "the decisions for section A" is
    a false sentence once A may no longer be the stretch the reader is looking
    at. /explain is per ELEMENT and needs no topology, which is why it does not
    refuse — the asymmetry is the difference between the two questions, not an
    inconsistency.
    """
    result = _run(run_id)
    project = _project(result.run.project_id)
    if project.topology.revision != result.run.topology_revision:
        raise HTTPException(409, {
            "code": "topology_changed",
            "run_topology_revision": result.run.topology_revision,
            "project_topology_revision": project.topology.revision,
        })
    # The SAME failure through a door the guard above cannot watch. Site
    # conditions are not part of `topology`, so changing a project from Exposure
    # B to C moves the span limit, moves the posts — and this document would
    # render the old layout without complaint. That document goes to site.
    _refuse_moved_site(project, result)
    graph = result.graph
    try:
        _, _, priced = _priced(result, _live_preset(result.run.project_id))
    except HTTPException:
        # a stale catalog must not cost the reader every other decision — the
        # same trade /explain makes one route up
        priced = None
    if priced is not None:
        graph = with_supply_decisions(graph, priced.decisions)
    return decisions_for_section(graph, result.strategy, project.topology,
                                 section_id, lang=lang, units=units)


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


@app.get("/api/projects/{project_id}/corrections")
def list_corrections(
    project_id: str,
    decision_ref: str | None = None,
    element_ref: str | None = None,
    generation_run_id: str | None = None,
):
    """The conversation, read back.

    There was no GET here at all: a correction went in, the UI alerted, and
    nothing in the app could show it again — a suggestion box rather than a
    conversation. `Store.list_corrections` already existed and had exactly one
    caller, the knowledge proposer.

    The filters are the three anchors a `Correction` carries. They are AND-ed,
    and an unknown ref returns an empty list rather than a 404: a decision with
    nothing said about it is a real and ordinary state, not a missing resource.

    Note what a caller must NOT read into a `decision_ref` across runs. Node ids
    are generated per run (`core/ids.py`), so a ref means what it means only
    within its `generation_run_id` — which is why every correction carries one
    and why this route lets you filter by it.
    """
    _project(project_id)   # 404 for a project that does not exist
    if decision_ref is not None and generation_run_id is None:
        # A decision node id is POSITIONAL — `d0007` is the seventh node the
        # builder emitted, and inserting one gate event renumbers everything
        # after it (`decisions/graph.py`, `core/ids.py`). Asking for a
        # `decision_ref` across runs therefore mixes comments about different
        # decisions that happen to share an ordinal. The unsafe read is made
        # unrepresentable rather than warned about in a docstring nobody has to
        # read; ask for the whole project's conversation instead if that is
        # genuinely what you want.
        raise HTTPException(422, {
            "code": "decision_ref_needs_run",
            "decision_ref": decision_ref,
        })
    out = state.store.list_corrections(project_id)
    if decision_ref is not None:
        out = [c for c in out if c.decision_ref == decision_ref]
    if element_ref is not None:
        out = [c for c in out if c.element_ref == element_ref]
    if generation_run_id is not None:
        out = [c for c in out if c.generation_run_id == generation_run_id]
    return out


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
            # ...and the SITE, or the preview regenerates a project built to
            # Exposure C as if nobody had said, and reports the rule that
            # decides it as costing nothing
            site=p.site,
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
                          _impact_cases(), state.store.fence_model_library(),
                          state.store.part_library())


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
                          _impact_cases(), state.store.fence_model_library(),
                          state.store.part_library())



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
    # With the library, because three of `validate_model`'s rules read numbers a
    # slot no longer carries — they arrive from the part it names, and the authored
    # document is not the document a bay is built from.
    errors = validate_model(model, state.store.load_catalog(), state.store.part_library())
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
        state.store.load_catalog(), _impact_cases(), state.store.part_library(),
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


def _refusal(e: ValueError) -> HTTPException:
    """The panel pipeline's refusals as HTTP, in one place — every path into it
    answers the same way."""
    if isinstance(e, RequestRefused):
        # 422, not 400: nothing stored is wrong — the body named a product this
        # slot cannot be supplied by, or a slot this panel has not got, and the
        # fix is to the request. Checked first because it is also a ValueError.
        return HTTPException(422, {"code": e.code, "params": e.params, "message": str(e)})
    if isinstance(e, ReadRefused):
        return HTTPException(400, {"code": e.code, "params": e.params, "message": str(e)})
    return HTTPException(400, str(e))


def _preview_or_refuse(
    model: FenceModel, bay: PreviewRequest,
    catalog: Catalog | None = None, preset: str = "least_cost",
    part_snapshot: list[PartUse] | None = None,
) -> PanelPreview:
    """`catalog` and `preset` are arguments rather than lookups because a bay of
    a stored run is priced against the catalog that run was generated with and
    under the objective preset it was generated under — see `preview_run_bay`.
    A model-scoped preview has neither, and asks the library for both.

    `part_snapshot` is the third of the same kind: the part VERSIONS a stored run
    resolved. Absent, the preview resolves `latest_active`, which is the right
    answer for a question about a model and the wrong one about a bay."""
    try:
        return preview_panel(
            model, bay,
            catalog if catalog is not None else state.store.load_catalog(),
            preset=preset,
            part_library=state.store.part_library(),
            part_snapshot=part_snapshot,
        )
    except ValueError as e:
        raise _refusal(e)


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


@app.post("/api/runs/{run_id}/bays/{element_id}/panel-preview")
def preview_run_bay(run_id: str, element_id: str, body: BayPreviewRequest) -> PanelPreview:
    """What ONE BAY of a stored run is made of, and what a change to it would do.

    The route above answers a question about a MODEL, at whatever height and
    width the caller names, under the default preset and against today's
    catalog. Asking it about a bay of an existing fence and reading the answer as
    that bay is how the drawer came to mark one product "chosen" while the run
    had bought another: the run resolved the bay with its vertical mode, its rail
    cut basis, its company-resolved rail and screw counts and its option values,
    then priced it under `objective_preset` against a FROZEN catalog.

    So this route supplies all of that from the run — the model document the run
    stamped for the bay (never `latest_active`), the context
    `bay_preview_plan` rebuilds, the run's preset — and then calls the same
    `preview_panel` the model-scoped route calls. One preview implementation,
    two ways of saying which bay.

    Inherits the catalog staleness 409 through `_fresh_catalog`, exactly as /bom
    and /structure do: a run whose catalog has moved cannot be re-priced as
    itself, and a bay of it is no more re-priceable than the whole.

    Inventory is deliberately not passed. Stock on hand is consumed across the
    WHOLE run, so handing it to a single bay would let every bay previewed spend
    the same remnant — the panel cost here is what this bay costs to build, the
    same question `/api/fence-models/.../preview` answers.
    """
    result = _run(run_id)
    try:
        plan = bay_preview_plan(result, element_id, body)
    except ValueError as e:
        raise _refusal(e)
    if plan is None:
        # before the staleness check: an element that is not a bay of this run is
        # the wrong request whatever the catalog has done since
        raise HTTPException(404, f"{element_id} is not a bay of run {run_id}")
    catalog = _fresh_catalog(result)
    model = state.store.load_fence_model(plan.model_id, plan.version)
    if model is None:
        raise HTTPException(404, f"{plan.model_id}@v{plan.version} not found")
    return _preview_or_refuse(model, plan.request, catalog, _live_preset(result.run.project_id),
                              result.run.part_snapshot)


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
    """The catalog, with what ONE purchase unit costs already worked out.

    `purchase_price_cents` is derived, never stored: a flat-priced product carries
    its own `price_cents` and a rate-priced one carries a rate and a bar length,
    and turning the second into the first is `catalog.purchase_price_cents` —
    which its own docstring calls THE rounding point for rate pricing, the one
    place that rounds, because two call sites differing by a cent total the same
    BOM two ways.

    A client comparing two candidate products for one slot needs exactly that
    number, and the drawer had been recomputing it in JavaScript. Identical today
    and a divergence waiting for the first minimum charge or waste factor, so the
    server answers it instead. Sent alongside the product rather than replacing
    its fields: the raw price and the pricing basis are still what an editor
    edits.
    """
    catalog = state.store.load_catalog()
    return {
        **catalog.model_dump(),
        "purchase_price_cents": {
            sku: purchase_price_cents(product)
            for sku, product in catalog.products.items()
        },
    }


_LOCALE_BUNDLES: dict[str, dict[str, str]] = {}


def _locale_bundle(lang: str) -> dict[str, str]:
    """The frontend's own `i18n/<lang>.json`, read once per process and cached.

    A second reader is expected, not a duplication: the browser and this backend
    are different runtimes, and a label the server derives (a part type nobody
    stocked before) needs the same bundle the browser renders everything else
    from.
    """
    if lang not in _LOCALE_BUNDLES:
        path = Path(__file__).resolve().parents[1] / "web" / "static" / "i18n" / f"{lang}.json"
        _LOCALE_BUNDLES[lang] = json.loads(path.read_text(encoding="utf-8"))
    return _LOCALE_BUNDLES[lang]


def _part_type_labels(key: str) -> dict[str, str]:
    labels = {}
    for lang in ("en", "he"):
        bundle = _locale_bundle(lang)
        labels[lang] = bundle.get(f"part_type.{key}", key)
    return labels


@app.get("/api/parts")
def list_parts() -> dict:
    """The part library, for the Models editor's picker.

    Each part's spec travels with it: an author choosing "38mm vinyl rail" should be
    able to see WHY it is that, not only its name. Read-only — creating and editing
    parts is the arc that builds an editor for them.
    """
    library = state.store.part_library()
    return {"parts": [p.model_dump() for p in
                      sorted(library.parts, key=lambda p: (p.type, p.id, p.version))]}


@app.get("/api/vocabularies")
def list_vocabularies() -> dict:
    """The vocabularies a client may OFFER, so the editor offers exactly them.

    Read-only, project-independent and free of stored state — the same shape as
    /api/part-types above, and for the same reason: the browser cannot derive
    what the schema accepts, so it either asks or it keeps a second copy, and the
    second copy is the defect. A value the editor offers and the schema rejects
    is a save that 422s; one the schema has and the editor lacks is a product
    line nobody can author. Both halves are fixed by there being one list.

    Names only, no labels — unlike /api/part-types, whose types come from stored
    data the browser has never seen. These are rendered through `model.basis.*`
    and `model.length_rule.*`, keys the browser's own bundle already holds, so
    sending a label here would be a SECOND answer to "what is this called" that
    goes stale on the locale toggle without a refetch.
    """
    return vocabularies()


@app.get("/api/part-types")
def list_part_types() -> dict:
    """The types actually in use, with a label per language.

    `PartType` exists as a model and nothing instantiates it, so a route over stored
    type data would return an empty list. These are derived from the library, which
    is the honest amount of vocabulary this arc needs; a stored, editable type
    library belongs to the arc where a NEW part must be given a type.

    The label comes from `part_type.<key>` in the locale bundles and falls back to
    the raw key, so a company that stocks something new gets a working picker before
    anyone writes it a word.
    """
    library = state.store.part_library()
    keys = sorted({p.type for p in library.parts})
    return {"types": [{"key": k, "label_i18n": _part_type_labels(k)} for k in keys]}


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
