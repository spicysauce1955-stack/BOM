"""FastAPI application — composition root (04-backend.md API surface).

The API orchestrates persistence and the pure domain functions; no domain logic
lives here. AI adapters are selected once at startup (stub by default, ADR-0009).
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import ValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fenceai.core.env import load_dotenv

load_dotenv()  # .env in the working directory fills gaps; real env vars win

from fenceai.agent.run import run_task  # noqa: E402
from fenceai.agent.tasks import RANK_CHOICE_SET
from fenceai.agent.view import AgentView
from fenceai.ai.claude import build_interpreter
from fenceai.ai.stub import StubAgent, StubCritic, StubProposer
from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import (
    CATALOG_SCHEMA_VERSION, Catalog, Product, catalog_hash, purchase_price_cents,
)
from fenceai.core.errors import GenerationFailure, ReadRefused, RequestRefused
from fenceai.core.ids import new_id
from fenceai import commands
from fenceai.commands import CommandRefused
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
from fenceai.fulfillment.supply import SupplyResolution
from fenceai.fulfillment.supply_run import (
    SUPPLY_BEHAVIOR_VERSION, SupplyRun, inventory_hash, supply_id,
)
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.discovery_stub import SourceRefResolved, resolve_batch
from fenceai.knowledge.model import KnowledgeVersion
from fenceai.knowledge.snapshot import SnapshotRefused, ingest, load
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
from fenceai.report.flags import job_flags
from fenceai.report.handover import handover_gaps
from fenceai.report.readiness import readiness
from fenceai.report.sections import section_facts
from fenceai.project.model import (
    Annotation, Job, Project, Selection, SiteConditions, SiteContext, Stated,
)
from fenceai.report.annexe import WarningPlacement, place_for_plan
from fenceai.report.bom_groups import group_bom
from fenceai.report.section_decisions import decisions_for_section
from fenceai.report.structure import build_structure
from fenceai.identity.model import (
    Capacity, User, actor_ref, default_view, may_choose_view,
)
from fenceai.identity.dev import DEV_COOKIE
from fenceai.identity.provider import build_provider
from fenceai.api.auth import (
    EXEMPT_PATHS, REFUSAL_STATUS_CODES, current_user, dev_mode, make_gate,
    require_admin, resolve as auth_resolve,
)
from fenceai.project.queue import DEFAULT_LIMIT, QueueFilter, my_jobs, select_rows
from fenceai.store.db import Store
from fenceai.strategy.generator import DEFAULT_POLICY, LEGACY_MODEL_ID, generate
from fenceai.strategy.model import PartUse
from fenceai.strategy.overrides import Override
from fenceai.topology.model import Topology

WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "static"


class AppState:
    store: Store
    provider = None
    interpreter = None
    proposer = None
    critic = None
    agent = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.store = Store(os.environ.get("FENCEAI_DB", "fenceai.db"))
    state.provider = build_provider()
    # Loud, once. A machine running `dev` by accident should say so rather than
    # behave strangely — an impersonation switch nobody noticed is the one way
    # this arrangement fails silently.
    print(f"[fenceai] identity provider: {state.provider.provider_id}", flush=True)
    # `_DEV` was read at IMPORT (needed then, to decide route registration and
    # the docs switch, both of which must exist before any request can arrive).
    # `state.provider.provider_id` is read HERE, at startup, from the same
    # `FENCEAI_IDENTITY`. In a real process the two reads are nil apart and can
    # never disagree; a test that swaps the provider at the port (or changes the
    # environment between import and this call) can make them disagree, and the
    # failure mode is fail-OPEN in one direction — import saw `dev` and left
    # `/openapi.json` registered, while startup built `iap` and would otherwise
    # give no sign that the whole API surface is sitting behind a live URL. A
    # WARNING, not a raise: several tests deliberately construct exactly this
    # mismatch to exercise the `iap`-shaped path without reloading the module.
    if _DEV != (state.provider.provider_id == "dev"):
        print("[fenceai] WARNING: identity provider at import "
              f"({'dev' if _DEV else state.provider.provider_id!r}) disagrees "
              f"with identity provider at startup ({state.provider.provider_id!r}) "
              "— dev-only routes and the docs switch were fixed at import time "
              "and will not match this process's actual provider", flush=True)
    state.interpreter = build_interpreter()
    state.proposer = StubProposer()
    state.critic = StubCritic()
    state.agent = StubAgent()
    if state.store.load_catalog() is None:
        state.store.save_catalog(demo_catalog(), actor="seed")
    if not state.store.knowledge_base().versions:
        for v in demo_knowledge().versions:
            state.store.insert_knowledge_version(v, actor="seed")
    if not state.store.list_projects():
        state.store.save_project(_sample_project(), actor="seed")
    # The demo accounts are a DEV-MODE thing, and the condition is the whole
    # reason `FENCEAI_BOOTSTRAP_ADMIN` can ever fire: seeding `u_admin`
    # unconditionally put an admin row in every fresh database before the first
    # request arrived, which permanently disabled the bootstrap and left a real
    # company's first admin with no way in at all — in the slice that deletes
    # the password path. Dev mode never needs the bootstrap, because the picker
    # can become anybody; production never wants three inert strangers.
    if state.provider.provider_id == "dev":
        _seed_demo_accounts()
    # Unset is the SAFE state, and the normal one for every deployment past its
    # first admin — so this is a log line, not a refusal to boot. A deployment
    # that forgot the variable on its very first boot would otherwise seat
    # nobody and give the operator nothing to grep for; refusing to boot would
    # instead turn a legitimate, permanent configuration (bootstrap disabled
    # once an admin exists) into a restart loop under a supervisor.
    if not state.store.list_users() and not os.environ.get(
            "FENCEAI_BOOTSTRAP_ADMIN", "").strip():
        print("[fenceai] no users exist and FENCEAI_BOOTSTRAP_ADMIN is unset — "
              "nobody can sign in until it names the first admin's address",
              flush=True)
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


#: Default-deny, declared once rather than on seventy routes. A dependency on
#: the app covers every route the router serves — including one added tomorrow
#: by somebody who never read this file, which is the whole point. The closure
#: reads `state` at request time because the provider and the store are both
#: built in `lifespan`, after this line has run.
_gate = make_gate(lambda: state.provider, lambda: state.store)

#: `/openapi.json`, `/docs`, `/docs/oauth2-redirect` and `/redoc` are OUTSIDE
#: the gate and cannot be brought inside it: FastAPI registers them with
#: `Starlette.add_route`, so they are plain `Route`s rather than `APIRoute`s and
#: the router's dependencies never reach them. Left on, they hand the entire API
#: surface — including the account-administration routes — to anybody who
#: reaches the service, which is the exact thing verifying IAP's assertion
#: exists to stop. Off outside dev, where the convenience is worth nothing to a
#: stranger because there is nobody to be a stranger to.
_DEV = dev_mode()
app = FastAPI(title="Fence AI", version="0.1.0", lifespan=lifespan,
              dependencies=[Depends(_gate)],
              openapi_url="/openapi.json" if _DEV else None,
              docs_url="/docs" if _DEV else None,
              redoc_url="/redoc" if _DEV else None)


def _now_iso() -> str:
    """The clock, for anything a route stamps on a document.

    Here rather than inside `fenceai.commands`, because a command that read the
    clock itself could not be driven through every state it declares from a test
    without freezing time globally. The store keeps its own `_now` for the audit
    column, which is a different fact: when the row was WRITTEN, not when the
    thing it records happened.
    """
    return datetime.now(timezone.utc).isoformat()


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
    unchanged fence regenerates to the same id and `save_run`'s ON CONFLICT DO NOTHING
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
    must not put that line's warranty notice on a plan built to the old one.

    That is a claim about the REF and not about the bytes, and the difference is
    recorded rather than glossed: a run also stamps a `content_hash`, because a
    draft's content moves under a fixed `(id, version)`, and this resolves by ref
    alone. So editing a draft in place changes what a stored run says the
    manufacturer warned, with no `model_changed`. `report/assembly.py` compares
    refs only for the same reason and would need the same fix, so it is one item
    covering both read models in `plan/open-work.md` rather than a divergence
    introduced here. A ref the library can no longer answer is SKIPPED rather than
    refused: this is a warning surface, and losing the annexe is not a reason to
    take a working BOM away from somebody.
    """
    library = state.store.fence_model_library()
    refs, models, unreadable = [], [], 0
    for span in result.strategy.spans:
        ref = span.panel.model_ref if span.panel else ""
        if not ref or ref in refs:
            continue
        refs.append(ref)
        model = library.by_ref(ref)
        if model is None:
            # COUNTED, not swallowed. The architecture review's finding, and it
            # is right: skipping is the correct trade — a missing annexe is not a
            # reason to take a working BOM away from somebody — but skipping in
            # SILENCE means a plan built to a document that carries a safety
            # notice can print with no annexe and nothing saying why. The path is
            # reachable: a run may pin a draft version that was later discarded.
            unreadable += 1
            continue
        models.append(model)
    placement = place_for_plan(models,
                               skus=[line.sku for line in priced.requirements])
    placement.documents_unreadable = unreadable
    return placement


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
    # Who bought this fence, where, who sold it and when. Optional, because
    # every existing caller — the demo project created on first boot, the smoke
    # suite, the whole test suite — posts a name and nothing else.
    job: Job | None = None


@app.post("/api/projects")
def create_project(request: Request, body: ProjectCreate) -> Project:
    # Who created it, from the identity and never from the body: it is what puts
    # the job on that salesperson's home screen (`GET /api/my-jobs`), and a
    # creator a client could name would put jobs on somebody else's list.
    user = current_user(request)
    project = Project(id=new_id("proj"), name=body.name, job=body.job,
                      created_by=user.id)
    state.store.save_project(project, actor=_actor(request))
    return project


@app.put("/api/projects/{project_id}/job")
def put_job(request: Request, project_id: str, job: Job) -> Project:
    """Name the job, or finish naming it.

    The route that matters more than the create form. A salesperson enters this
    after the visit from paper notes: they start with a customer name, draw for
    twenty minutes, and only then find the address on the sketch. If creation
    were the only way to set this, finding the address would cost them the
    drawing.

    Unrevisioned, unlike `/site` and `/topology`. Those are INPUTS to generation,
    so a derived view must be able to tell whether it is stale against them;
    who bought the fence changes no quantity and invalidates nothing.
    """
    project = _project(project_id)
    project.job = job
    state.store.save_project(project, actor=_actor(request))
    return project


@app.put("/api/projects/{project_id}/stated")
def put_stated(request: Request, project_id: str, stated: Stated) -> Project:
    """Say what this job does not have.

    Unrevisioned, like `/job` and unlike `/site` and `/topology`. Those are
    INPUTS to generation, so a derived view must be able to tell whether it is
    stale against them; a claim that there are no gates changes no quantity.

    The claim is stored as given and never validated against the drawing —
    `handover_gaps` reports the disagreement instead. Refusing the claim here
    would mean the salesperson could not record what they believe, which is
    the one thing this field exists to capture.
    """
    project = _project(project_id)
    project.stated = stated
    state.store.save_project(project, actor=_actor(request))
    return project


@app.put("/api/projects/{project_id}/context")
def put_context(request: Request, project_id: str, context: SiteContext) -> Project:
    """The house, the street, the boundary — what makes the layout a PLACE.

    Unrevisioned, like `/job` and unlike `/topology` and `/site`. A landmark
    changes no quantity and no derived view can be stale against it; giving it a
    revision would imply otherwise and invite somebody to check against it.
    """
    project = _project(project_id)
    project.context = context
    state.store.save_project(project, actor=_actor(request))
    return project


# -- one door: commands --------------------------------------------------------
#
# Every change that MOVES a job — whose desk it is on, or what it commits to —
# comes through this one route (backoffice design §10). Field edits do not:
# typing an address is not a command, and forcing it to be one turns the design
# into ceremony.
#
# It was the FIRST gated route in this app and is no longer the only one: the
# app-level gate now resolves every caller to a capacity row before any route
# runs. What stays particular here is the CAPACITY check — "may this account
# perform this command on a job in this state" — which lives in
# `fenceai.commands` and is a different question from "may this person reach the
# API at all".


class CommandBody(BaseModel):
    kind: str
    payload: dict = {}
    #: Who PROPOSED it, when that is not who performed it. `actor` is always the
    #: session. Two names, because "Yossi accepted the agent's suggestion" and
    #: "Yossi decided this himself" must stay different rows in the log.
    origin: str = ""


#: Which HTTP status each refusal earns. `command_wrong_state` is a 409 rather
#: than a 403 because it is a conflict with the job as it stands now, not a
#: statement about the caller — somebody else moved the folder while this screen
#: was open, and the browser's answer is to reload rather than to give up. The
#: default is 403: this account may not do this, and trying again will not help.
_REFUSAL_STATUS = {"command_wrong_state": 409}


def _refuse_unknown_assignee(body: CommandBody) -> None:
    """A desk you can hand a job to has to exist.

    `commands/` cannot reach the store, so `AssignJob.user_id` is unchecked there
    and says so in a comment. Unchecked here too, a typo would put the job on a
    desk nobody has — off every list at once, with nothing refusing and nobody
    able to find it again except by reading the database. That is the failure the
    seam was left open for, and this is the side of the seam that knows who
    exists.
    """
    if body.kind != "assign_job":
        return
    user_id = (body.payload or {}).get("user_id")
    target = state.store.user(user_id) if user_id else None
    if target is None or not target.active:
        raise HTTPException(422, {
            "code": "assignee_unknown", "params": {"user_id": user_id or ""},
        })


def _command_precondition(kind: str, payload, project: Project) -> None:
    """The strict staleness guards, for the one command that freezes a decision.

    `commands/` is pure over a `Project` and may not reach the store, so what a
    row needs from the store is stated here and handed to `perform` as its
    `precondition` — the seam `CommandSpec`'s `assignee` comment names.

    `commit_plan` takes STRICTER guards than any working view, and stricter than
    `create_quote`'s (which checks the site, the catalog and unresolved supply but
    not the topology revision): a working view that renders something stale is a
    screen somebody re-reads, while a committed plan is read later by somebody who
    builds from it. Unresolved supply is NOT a refusal here — a design can be
    complete while the yard cannot fill it; that stays a readiness item and the
    quote stays the hard stop.
    """
    if kind != "commit_plan":
        return
    # Non-blank by the payload model (`CommitPlan.run_id`), which has already
    # parsed by the time a precondition is asked.
    #
    # A run nobody has ever stored and a run belonging to somebody else are ONE
    # fact from here: it is not this job's plan. `_run`'s bare 404 would reach
    # the office as "the action failed" (`state.js` has no code to render), and
    # would answer, to anybody allowed this far, which run ids exist.
    result = state.store.load_run(payload.run_id)
    if result is None or result.run.project_id != project.id:
        raise HTTPException(422, {
            "code": "run_not_on_this_job", "params": {"run_id": payload.run_id},
        })
    if project.topology.revision != result.run.topology_revision:
        raise HTTPException(409, {
            "code": "topology_changed",
            "run_topology_revision": result.run.topology_revision,
            "project_topology_revision": project.topology.revision,
        })
    _refuse_moved_site(project, result)
    # ...and the catalog, through the check every other reader of a stored run
    # makes. NOT `_priced`: pricing would drag the objective preset — a fact
    # about what it costs — into an act that commits the design and never a
    # price, and would refuse on fulfillment grounds one line under a comment
    # promising it does not.
    _fresh_catalog(result)


@app.post("/api/projects/{project_id}/actions")
def perform_command(request: Request, project_id: str, body: CommandBody) -> Project:
    """Perform one command against one job, or refuse it in a sentence.

    The three checks live in `fenceai.commands`, not here — a permission scattered
    across handlers is a permission half of which gets added later by somebody who
    did not know. This route contributes exactly what the pure half cannot have:
    the session, the store, and one activity row.

    The row is written only on success. A log that recorded every attempt would
    make "who did what" a list of things nobody did.
    """
    user = current_user(request)
    project = _project(project_id)
    _refuse_unknown_assignee(body)
    try:
        changed = commands.perform(
            body.kind, body.payload, project,
            actor=actor_ref(user), capacity=user.capacity, now=_now_iso(),
            # What only this layer can check — the run a `commit_plan` names, and
            # the drawing, catalog and site it was generated from. Asked by
            # `perform` AFTER capacity and state, so a salesperson who may not
            # commit is told that and learns nothing about which runs exist.
            precondition=_command_precondition,
        )
    except KeyError as unknown:
        raise HTTPException(404, {
            "code": "command_unknown", "params": {"kind": body.kind},
        }) from unknown
    except CommandRefused as refused:
        raise HTTPException(_REFUSAL_STATUS.get(refused.code, 403), {
            "code": refused.code, "params": refused.params,
        }) from refused
    except ValidationError as invalid:
        # A caller's mistake, not ours, and not a 500. The English list is
        # AUTHORING text — our finding about a payload somebody is holding — so
        # it carries no code of its own and is rendered for whoever can fix it,
        # exactly as `validate_model`'s errors are.
        raise HTTPException(400, {
            "code": "command_payload_invalid",
            "params": {"kind": body.kind},
            "errors": [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}"
                       for e in invalid.errors()[:10]],
        }) from invalid
    state.store.save_project(changed, actor=actor_ref(user))
    state.store.log(actor_ref(user), f"command:{body.kind}",
                       f"{project_id}|{body.origin}")
    return changed


def _readiness_supply(result) -> SupplyResolution | None:
    """What supply says about this run, or `None` when it cannot be asked.

    `None` is not silence: `readiness` turns it into `supply_unknown`, which is
    the honest answer for a run whose catalog or site has moved under it —
    reported here instead of raised, because the road is the screen people open
    to find out what is wrong with a job.

    The SITE is checked explicitly, because `_priced` does not: it checks the
    catalog alone. Without it step 5 read "the yard can fill this" for a run laid
    out under conditions the project no longer states, while step 7's quote door
    refuses that same run on `site_conditions_changed` — the road saying go and
    the next door saying no, with nothing on the road mentioning the site. The
    DRAWING is deliberately not checked: supply answers the demand this run
    already recorded, and a moved drawing is what `plan_stale` is for.
    """
    if result is None:
        return None
    try:
        _refuse_moved_site(_project(result.run.project_id), result)
        _, _, priced = _priced(result, _live_preset(result.run.project_id))
    except HTTPException:
        return None
    return SupplyResolution(requirements=priced.requirements,
                            unresolved=priced.unresolved)


def _readiness_for(project: Project, result=None):
    """`readiness(...)` over this project's latest run, and the run it read.

    Extracted because TWO routes need it — `/readiness` renders the office
    road's list and `/flags` places the same items on the drawing — and the
    loading below is not boilerplate: which run, which committed run, and the
    difference between "no id" and "an id naming no run of this job" each carry
    a comment explaining what goes wrong when it is done the other way. A second
    copy would be a second set of those decisions, drifting.

    `result` lets a caller that has already resolved a run (because the caller
    was asked for a specific one) hand it in rather than re-reading the latest.
    """
    runs = state.store.list_runs(project.id)
    if result is None:
        # The LATEST run, because that is the one the office is looking at. An
        # older one is a document somebody may still read, but "what is left to
        # do" is a question about the fence as it stands now.
        result = _run(runs[-1]["id"]) if runs else None
    _has_run = any(r["id"] == project.committed_run_id for r in runs)
    items = readiness(
        project,
        run=result.run if result else None,
        strategy=result.strategy if result else None,
        # Step 5 is about what the YARD can fill, which only the supply pass can
        # answer. Unwired, `readiness` reported `supply_unknown` on every job
        # with a run — "nobody worked it out", which was true and meant step 5
        # could never read done. It stays that way for a run too stale to price:
        # a moved drawing or catalog makes the question unanswerable rather than
        # answered, and this read model must never be the thing that 409s the
        # road on the screen somebody opened to find out what is wrong.
        supply=_readiness_supply(result),
        choice_sets=result.choice_sets if result else None,
        # The committed run is a DIFFERENT document from the latest one, and
        # `plan_stale` is a claim about the committed one alone (readiness.py):
        # handed the latest, it would judge the plan by a run that is not it.
        # `None` for an id this project has no run for — readiness reads that as
        # nothing committed, which is the honest answer and the one thing it
        # never does is stay silent.
        committed_run=(state.store.load_run(project.committed_run_id).run
                       if project.committed_run_id and _has_run else None),
        # ...and this says we LOOKED: an id naming no run of this job is nothing
        # committed, which is different from a caller that simply did not pass one.
        committed_missing=bool(project.committed_run_id) and not _has_run,
        quotes=state.store.list_quotes(project.id),
    )
    return items, result


@app.get("/api/projects/{project_id}/flags")
def get_flags(project_id: str, run_id: str = "") -> dict:
    """Every problem on this job, each carrying where it belongs on the drawing.

    The office job screen's second route. It finds nothing: `handover_gaps`,
    `readiness` and the stored run's own warnings found all of it, and this
    places them so a mark can be drawn at the thing each one is about.

    **It does not refuse a stale run, and that is the decision.**
    `/runs/{id}/structure` answers 409 `topology_changed` because it describes a
    fence laid out against a drawing that has since moved. This route is the
    screen that TELLS somebody that happened — `plan_stale` is one of the items
    it carries — so refusing here would hide the answer behind the very problem
    it exists to report.

    A `run_id` naming a run of a different job is 422 `run_not_on_this_job`,
    the same refusal the command door gives, rather than a bare 404: it is not
    that the run does not exist, it is that it is not this job's.
    """
    project = _project(project_id)
    result = None
    if run_id:
        result = state.store.load_run(run_id)
        if result is None or result.run.project_id != project.id:
            raise HTTPException(422, {
                "code": "run_not_on_this_job", "params": {"run_id": run_id},
            })
    items, result = _readiness_for(project, result)
    flags = job_flags(
        gaps=handover_gaps(project),
        items=items,
        # The STORED run's warnings, never re-evaluated: re-running the
        # evaluator would re-resolve to "current" (contract 3.2.1) and recompute
        # a quantity inside a read model (foundation §15).
        warnings=result.strategy.warnings if result else [],
        choice_sets=result.choice_sets if result else [],
    )
    return {"flags": [f.model_dump() for f in flags],
            # Which run this answer was read from — "" when there is none, so a
            # screen can tell "nothing has been generated" from "generated and
            # clean" instead of reading an empty list as either.
            "run_id": result.run.id if result else "",
            # ...and WHICH DRAWING that run was laid out against, beside the one
            # the reader is looking at. Without this pair the answer is unsafe:
            # a `strategy` flag's place is a STATION minted against the run's
            # topology, so after an edit the screen would draw a red `!` at
            # station 4000 of a run that is now 3000 mm long — confidently, at a
            # spot that does not exist.
            #
            # It is a pair of facts rather than a refusal on purpose (this route
            # must not 409 — it is how somebody finds out the drawing moved) and
            # rather than a boolean, because "stale" is the READER's conclusion
            # from two revisions and a screen that disagrees with the server
            # about which is which should be able to say so.
            #
            # `readiness`'s `plan_stale` does NOT cover this: it is a claim about
            # the COMMITTED run only, so in the ordinary office loop — generate,
            # edit the drawing, nothing committed yet — nothing else in this
            # answer mentions that the latest run no longer describes the fence.
            "run_topology_revision": result.run.topology_revision if result else 0,
            "topology_revision": project.topology.revision}


@app.get("/api/projects/{project_id}/readiness")
def get_readiness(project_id: str) -> dict:
    """What the OFFICE still has to do — the run-scoped sibling of `/handover`.

    Two read models and deliberately not one. `/handover` is a pure function of
    the PROJECT and must stay one: that is what lets it catch the silent 1800 mm
    height before a strategy exists to make it look decided. These questions are
    about a run, so folding them in would drag a run into a function whose whole
    value is not needing one.

    The road reads both and GROUPS them. It never recounts — three surfaces
    answering "what is left" and disagreeing is the defect this repo already
    paid for once.

    **Reads the STORED run and never re-evaluates.** No knowledge base is loaded
    here and `readiness()` takes none, so there is nothing in scope to resolve
    against: re-running the evaluator would re-resolve to "current" (contract
    3.2.1) and recompute a quantity in a read model (foundation §15).

    The loading lives in `_readiness_for` because `/flags` needs the same items
    to place them on the drawing, and the choices it makes — which run, which
    committed run — are decisions rather than boilerplate.
    """
    items, _ = _readiness_for(_project(project_id))
    return {"items": [i.model_dump() for i in items]}


@app.get("/api/projects/{project_id}/handover")
def get_handover(project_id: str) -> dict:
    """What the office still needs from the salesperson.

    A read model, derived and never stored — and derived from the PROJECT, not
    from a run: by the time a `Strategy` exists the silent defaults (1800 mm
    height, `soil` base) have already been applied and look decided, and
    catching them before that is the whole point.

    GET rather than a field on `/projects/{id}` because it is a computed view,
    and putting it on the aggregate would make every project read recompute it.
    """
    project = _project(project_id)
    gaps = handover_gaps(project)
    return {"gaps": [g.model_dump() for g in gaps],
            # The estimate is withheld while a BLOCKING item stands — a price
            # for a fence with no model chosen is a number with nothing behind
            # it. The handover itself is never withheld.
            "estimate_ready": not any(g.blocking for g in gaps)}


@app.get("/api/projects/{project_id}/sections")
def get_sections(project_id: str) -> dict:
    """What each stretch of this fence IS — length, what it stands on, the
    ground along it, whether anybody stated a height.

    The route the office job screen opens on, and the only per-stretch view in
    this app that **cannot go stale**. `/runs/{id}/structure` and
    `/runs/{id}/sections/{run_id}/decisions` both refuse with 409
    `topology_changed`, and they are right to: they describe a stored run that
    was generated from a drawing which has since moved. This describes the
    DRAWING. When the drawing moves it has a new answer, not a refusal — so
    there is nothing here to guard against and a guard would be a lie about
    what the reader is looking at.

    A job with nothing drawn answers `{"sections": []}` rather than a 404: a
    job nobody has drawn yet is a real state and the screen renders it.
    """
    return {"sections": [s.model_dump()
                         for s in section_facts(_project(project_id).topology)]}


@app.get("/api/projects")
def list_projects() -> list[dict]:
    """The PICKER's list — every project, three fields, unchanged.

    Deliberately not the queue. They answer different questions and want
    different rows: the picker is "which job am I looking at" and includes a
    salesperson's own drafts, while the queue is "what should I work on next"
    and hides drafts from everybody but their author. Folding them into one
    route meant changing this one's envelope from a list to an object, which
    broke five callers including the picker itself — the plan said "rebuilt
    rather than extended" and the rebuild turned out to be a second question,
    not a bigger answer.
    """
    return [{"id": p.id, "name": p.name, "label": p.display_name()}
            for p in state.store.list_projects()]


@app.get("/api/queue")
def queue(
    request: Request,
    bucket: str = "open",
    status: str = "",
    assignee: str = "",
    sold_by: str = "",
    submitted_from: str = "",
    submitted_to: str = "",
    has_open: bool | None = None,
    q: str = "",
    sort: str = "waiting",
    limit: int = DEFAULT_LIMIT,
    cursor: str = "",
) -> dict:
    """What should I work on next — or, in the finished bucket, what did we do.

    Paged from the first commit, because the open-question count is DERIVED per
    row: deriving it for twenty-five is free and for an unbounded list is what
    would make "read models are derived, never stored" unaffordable.
    """
    user = current_user(request)
    # `me` is resolved HERE and never passed through. `select_rows` refuses the
    # literal string on purpose: matched as an id it would return an empty page
    # that reads as "you have nothing to do", which is the most misleading answer
    # a queue can give.
    who = user.id if assignee == "me" else assignee
    try:
        f = QueueFilter(
            bucket=bucket,
            status=tuple(s for s in status.split(",") if s),
            assignee=who or None,
            sold_by=sold_by,
            submitted_from=submitted_from, submitted_to=submitted_to,
            has_open=has_open, q=q, sort=sort,
            for_capacity=user.capacity if user else None,
            limit=limit, cursor=cursor or None,
        )
        rows, next_cursor = select_rows(
            state.store.list_projects(), f, now=datetime.now(timezone.utc))
    except ValidationError as e:
        raise HTTPException(422, {"code": "queue_filter_invalid",
                                  "params": {"detail": e.errors()[0]["msg"]}})
    except ValueError as e:
        raise HTTPException(400, {"code": "queue_cursor_invalid",
                                  "params": {"detail": str(e)}})
    return {"rows": [_queue_row(r) for r in rows], "next_cursor": next_cursor}


@app.get("/api/my-jobs")
def my_jobs_route(request: Request) -> dict:
    """A salesperson's home screen: the jobs this account created, what the
    office has said about each, most urgent first.

    "My" has no answer for a caller nobody can name, which is why an unresolved
    request is refused by the gate rather than shown an empty list that reads as
    "you have no jobs".
    """
    user = current_user(request)
    rows = my_jobs(state.store.list_projects(), user.id)
    return {"rows": [r.model_dump() for r in rows]}


def _queue_row(row) -> dict:
    """One row, plus the two columns a pure function could not fill.

    `quote_total_cents` is looked up here because the store is here, and NOT
    stored on the job for the same reason the open-question count is not: it
    already lives somewhere, and a second copy is a second answer.
    """
    out = row.model_dump()
    if row.status in ("quoted", "delivered"):
        quotes = state.store.list_quotes(row.id)
        accepted = [q for q in quotes if q.status == "accepted"] or quotes
        out["quote_total_cents"] = accepted[-1].total_cents if accepted else None
    return out


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> Project:
    return _project(project_id)


@app.put("/api/projects/{project_id}/site")
def put_site_conditions(request: Request, project_id: str, site: SiteConditions) -> Project:
    """What kind of site this is. Revisioned like the topology, and bumped HERE
    rather than trusted from the client, for the same reason: the revision is
    what every derived view checks itself against, so a client that forgot to
    increment it would silently make a stale document look current."""
    project = _project(project_id)
    site.revision = project.site.revision + 1
    project.site = site
    state.store.save_project(project, actor=_actor(request))
    return project


@app.put("/api/projects/{project_id}/topology")
def put_topology(request: Request, project_id: str, topology: Topology) -> Project:
    project = _project(project_id)
    topology.revision = project.topology.revision + 1
    project.topology = topology
    state.store.save_project(project, actor=_actor(request))
    return project


# -- annotations & interpretation ---------------------------------------------

class AnnotationCreate(BaseModel):
    target_ref: str
    text: str


@app.post("/api/projects/{project_id}/annotations")
def add_annotation(request: Request, project_id: str, body: AnnotationCreate) -> Annotation:
    project = _project(project_id)
    # The author is the session, full stop — there is no client-supplied
    # `author` left to outrank (Task 7) — and the time is stamped: both are
    # what let a salesperson's list tell the office's notes from her own, and
    # let the handover tell a note made after she sent the job from the sale.
    annotation = Annotation(
        id=new_id("ann"), target_ref=body.target_ref, text=body.text,
        author=_actor(request), created_at=_now_iso(),
    )
    project.annotations.append(annotation)
    state.store.save_project(project, actor=_actor(request))
    return annotation


@app.post("/api/projects/{project_id}/annotations/{annotation_id}/interpret")
def interpret_annotation(request: Request, project_id: str, annotation_id: str):
    project = _project(project_id)
    annotation = next((a for a in project.annotations if a.id == annotation_id), None)
    if annotation is None:
        raise HTTPException(404, "annotation not found")
    record = state.interpreter.interpret(annotation)
    annotation.interpretations.append(record)
    state.store.save_project(project, actor=_actor(request))
    return record


class IntentConfirm(BaseModel):
    annotation_id: str
    run_id: str
    confirmed_by: str = "user"


@app.post("/api/projects/{project_id}/intents/{intent_id}/confirm")
def confirm_intent_route(request: Request, project_id: str, intent_id: str, body: IntentConfirm):
    project = _project(project_id)
    try:
        materialized = confirm_intent(
            project, body.annotation_id, intent_id, body.run_id, body.confirmed_by
        )
    except (StopIteration, ValueError) as e:
        raise HTTPException(400, str(e))
    state.store.save_project(project, actor=_actor(request))
    return {"materialized_id": materialized}


# -- overrides -----------------------------------------------------------------

@app.post("/api/projects/{project_id}/overrides")
def add_override(request: Request, project_id: str, override: Override) -> Override:
    project = _project(project_id)
    if not override.id:
        override.id = new_id("ov")
    project.overrides.append(override)
    state.store.save_project(project, actor=_actor(request))
    return override


@app.delete("/api/projects/{project_id}/overrides/{override_id}")
def delete_override(request: Request, project_id: str, override_id: str):
    project = _project(project_id)
    before = len(project.overrides)
    project.overrides = [o for o in project.overrides if o.id != override_id]
    if len(project.overrides) == before:
        raise HTTPException(404, "override not found")
    state.store.save_project(project, actor=_actor(request))
    return {"deleted": override_id}


# -- choices -------------------------------------------------------------------
# Deliberately its own group and not an extension of overrides: a choice is not
# an override. An override says the engine got this wrong HERE and patches an
# output at a station; a selection answers a question the data left open and is
# an INPUT to generation, anchored to a scope that outlives a redraw.

@app.put("/api/projects/{project_id}/choices")
def put_choice(request: Request, project_id: str, selection: Selection) -> Selection:
    """Upsert one selection by `(choice_set, scope)`.

    PUT and not POST because an answer is not an accumulation: choosing again
    replaces, or a project would carry two answers to one question and the
    generator would have to guess which is current. `asked=False` arrives on
    this same route — a pin is the same record with one flag."""
    project = _project(project_id)
    project.choices = [
        c for c in project.choices if c.key() != selection.key()
    ] + [selection]
    state.store.save_project(project, actor=_actor(request))
    return selection


@app.delete("/api/projects/{project_id}/choices/{choice_set}")
def delete_choice(request: Request, project_id: str, choice_set: str, scope: str):
    """The scope is a QUERY parameter, not a path segment: a real scope is
    `model:mfr/certainteed/rail` and a path segment cannot carry the slashes."""
    project = _project(project_id)
    before = len(project.choices)
    project.choices = [
        c for c in project.choices if c.key() != (choice_set, scope)
    ]
    if len(project.choices) == before:
        raise HTTPException(404, "choice not found")
    state.store.save_project(project, actor=_actor(request))
    return {"deleted": choice_set, "scope": scope}


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
            # A person's answers are an INPUT to generation, threaded like the
            # site and the parts — never a patch on its output.
            choices=project.choices,
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
    `save_supply_run`'s ON CONFLICT DO NOTHING does not write twice. Growth tracks real
    changes to the yard, not read volume, which is why no retention policy is
    needed yet (spec §7.2).
    """
    result = _run(run_id)
    preset = _live_preset(result.run.project_id)
    _, inventory, priced = _priced(result, preset)
    # the STORED row, not the one just built: on a repeat read ON CONFLICT DO NOTHING
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
    hashes facts, so regeneration returned the same id, `ON CONFLICT DO NOTHING` kept
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


@app.get("/api/runs/{run_id}/advice")
def get_advice(run_id: str):
    """What the agent would suggest about this run's open questions.

    Read-only and derived: nothing is stored, and a second call on unchanged
    inputs returns the same proposal ids because they are content-derived.
    """
    result = _run(run_id)
    project = _project(result.run.project_id)
    # Same refusal as `/structure`: advice about a layout laid over an edited
    # drawing is advice about a fence nobody drew.
    if project.topology.revision != result.run.topology_revision:
        raise HTTPException(409, {
            "code": "topology_changed",
            "run_topology_revision": result.run.topology_revision,
            "project_topology_revision": project.topology.revision,
        })
    view = AgentView(project, result)
    return run_task(RANK_CHOICE_SET, view, state.agent,
                    project_id=result.run.project_id)


# -- quotes (persisted BOM snapshots) ---------------------------------------------

class QuoteCreate(BaseModel):
    label: str = ""


@app.post("/api/runs/{run_id}/quote")
def create_quote(request: Request, run_id: str, body: QuoteCreate) -> Quote:
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
        _supply_run_for(result, preset, priced, inventory), actor=_actor(request))
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
    state.store.save_quote(quote, actor=_actor(request))
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
def accept_quote(request: Request, quote_id: str) -> Quote:
    try:
        return state.store.accept_quote(quote_id, actor=_actor(request))
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


@app.post("/api/projects/{project_id}/corrections")
def add_correction(request: Request, project_id: str, body: CorrectionCreate) -> Correction:
    _project(project_id)
    correction = Correction(
        id=new_id("corr"), project_id=project_id, author=_actor(request),
        **body.model_dump(),
    )
    state.store.save_correction(correction, actor=_actor(request))
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
    """No `reviewer` field, deliberately.

    Approving a candidate writes `attributed_to` on the version that becomes
    ACTIVE and generates every later project's fence — domain provenance, not
    just an audit fallback. A client-supplied reviewer let any caller sign a
    rule change as anyone, including another real account. The reviewer is the
    resolved caller, like every other actor in this app; a body that still
    sends one is ignored rather than rejected, because the field was never
    load-bearing for anything but the forgery.
    """

    action: str
    reason: str | None = None
    edited_scope: dict[str, str] | None = None


@app.post("/api/candidates/{object_id}/{version}/review")
def review_candidate(request: Request, object_id: str, version: int, body: ReviewBody):
    kb = state.store.knowledge_base()
    cand = next(
        (v for v in kb.versions if v.object_id == object_id and v.version == version), None
    )
    if cand is None or cand.status != "proposed":
        raise HTTPException(404, "candidate not found or not reviewable")
    actor = _actor(request)
    try:
        outcome = apply_review(cand, ReviewAction(**body.model_dump(), reviewer=actor))
    except ValueError as e:
        raise HTTPException(400, str(e))
    approved = outcome if outcome is not cand else None
    state.store.apply_review_outcome(cand, approved, actor=actor)
    return outcome


# -- knowledge -------------------------------------------------------------------

@app.get("/api/knowledge/snapshot")
def active_snapshot():
    """The published snapshot runs resolve against, and what it became.

    `loaded: false` is an ordinary state, not an error — this installation has
    authored knowledge and no published snapshot, which is how every one starts
    and how one works with the Knowledge Platform unreachable (§3.2.2).
    """
    snapshot = state.store.active_snapshot()
    if snapshot is None:
        return {"loaded": False, "history": state.store.snapshot_ids()}
    ingested = ingest(snapshot)
    return {
        "loaded": True,
        "snapshot_id": snapshot.snapshot_id,
        "contract_version": snapshot.contract_version,
        "regime": snapshot.regime,
        "tenant": snapshot.tenant,
        "versions": len(ingested.knowledge.versions),
        # The counts a person actually asks about: how much came in, how much
        # this engine declined to use, and how many holes were reported.
        "admitted": len(ingested.knowledge.admitted),
        "declined": {k: len(v) for k, v in ingested.knowledge.declined.items()},
        "gaps": len(ingested.gaps),
        "warnings": len(ingested.warnings),
        # Published spec values this run judged (item 7). A COUNT here and the
        # values themselves at `/api/knowledge/parts`: this response is the
        # numbers a person scans, and a snapshot may carry thousands of parts.
        "part_specs": len(ingested.part_specs),
        "part_defects": len(ingested.part_defects),
        "unconsumed": ingested.unconsumed,
        "history": state.store.snapshot_ids(),
    }


@app.get("/api/knowledge/parts")
def published_parts():
    """Every published spec value, with the documents behind it.

    The reviewer's question §1.2.1 names — *"which documents is this definition
    built from"* — answered per VALUE rather than per definition, because
    admissibility is decided per value (§2.4: a rail length is `derived`,
    marketing-grade OCR or PE-sealed depending which of eleven documents it came
    from).

    The Knowledge tab renders definitions including draft and retired parts.
    Definition visibility does not imply admission for generation. `defects` is authoring text for
    whoever holds the payload, so it is returned as-is and rendered escaped and
    LTR — never through the warning registry.
    """
    snapshot = state.store.active_snapshot()
    if snapshot is None:
        return {"loaded": False, "specs": [], "defects": [], "inactive": [],
                "definitions": [], "source_docs": []}
    ingested = ingest(snapshot)
    return {
        "loaded": True,
        "snapshot_id": snapshot.snapshot_id,
        "specs": ingested.part_specs,
        "defects": ingested.part_defects,
        "inactive": ingested.inactive_parts,
        # Inspection carries inactive definitions too; consumption still judges
        # active specs separately. Storage may materialize schema defaults.
        "definitions": [p.model_dump(mode="json", exclude_unset=True) for p in snapshot.parts],
        "source_docs": [d.model_dump(mode="json", exclude_unset=True) for d in snapshot.source_docs],
    }


@app.post("/api/knowledge/snapshot")
def load_snapshot(body: dict):
    """Load a published snapshot document, and make it the active one.

    Explicit, never automatic. A knowledge base that swapped itself under a
    project would change numbers with no action anyone took — the same reason
    generation sits behind a button rather than firing on edit.

    **The refusal is the important path here**, not the happy one. The first
    document anyone tries is `3ae88642`, which predates §1.1's typed `Date` and
    is refused by version — so `load()`'s one-sentence explanation is what a
    person meets first, and it reaches them as a typed 400 rather than a stack
    trace.
    """
    try:
        snapshot, gap_defects = load(body)
    except SnapshotRefused as refused:
        raise HTTPException(400, {
            "code": refused.code, "message": str(refused),
        }) from refused
    except ValidationError as invalid:
        # A payload that is not a snapshot at all. English, uncoded, addressed to
        # whoever is holding the document — `validate_model`'s own convention for
        # authoring text, and the same audience.
        raise HTTPException(400, {
            "code": "snapshot_malformed",
            "message": "this document does not parse as a Snapshot (§1.2)",
            "errors": [
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in invalid.errors()[:10]
            ],
        }) from invalid

    state.store.save_snapshot(snapshot, actor="user")
    ingested = ingest(snapshot, gap_defects=gap_defects)
    return {
        "snapshot_id": snapshot.snapshot_id,
        "versions": len(ingested.knowledge.versions),
        "admitted": len(ingested.knowledge.admitted),
        "gaps": len(ingested.gaps),
        # Published gaps we could not parse. Carried and counted rather than
        # dropped: "we were told 81 things and could read none of them" is a fact
        # the sender needs, and silence about it is the one thing that hides drift.
        "gap_defects": len(ingested.gap_defects),
        "warning_defects": len(ingested.warning_defects),
        # Judged spec values, and the parts whose own shapes contradict their
        # schema — the same split every other pair here has: what we could use,
        # and what needs an edit at the sender.
        "part_specs": len(ingested.part_specs),
        "part_defects": len(ingested.part_defects),
        "unconsumed": ingested.unconsumed,
    }


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


@app.post("/api/knowledge")
def upsert_knowledge(request: Request, body: KnowledgeCreate):
    """New version of a knowledge object; the previous active version is retired."""
    version_no = state.store.next_version(body.object_id)
    v = KnowledgeVersion(
        object_id=body.object_id, version=version_no,
        type=body.type,  # type: ignore[arg-type]
        title=body.title, scope=body.scope,
        condition=body.condition, actions=body.actions,  # type: ignore[arg-type]
        source_text=body.source_text, attributed_to=_actor(request),
        derived_from=[f"{body.object_id}@v{version_no - 1}"] if version_no > 1 else [],
        status="active",
    )
    state.store.replace_active_version(v, actor=_actor(request))
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
        status="draft",
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
def retire_knowledge(request: Request, object_id: str, version: int):
    try:
        state.store.update_knowledge_status(object_id, version, "retired", actor=_actor(request))
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
def create_fence_model(request: Request, model: FenceModel):
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
    state.store.save_fence_model(draft, actor=_actor(request))
    return {"model": draft, "invalid": _model_errors(draft)}


@app.put("/api/fence-models/{model_id}/draft")
def put_fence_model_draft(request: Request, model_id: str, model: FenceModel):
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
        state.store.save_fence_model(draft, actor=_actor(request))
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
def discard_fence_model_draft(request: Request, model_id: str, version: int):
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
    state.store.delete_fence_model_draft(model_id, version, actor=_actor(request))
    return {"discarded": model.ref}


@app.post("/api/fence-models/{model_id}/{version}/publish")
def publish_fence_model(request: Request, model_id: str, version: int):
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
    state.store.set_fence_model_status(model_id, version, "active", actor=_actor(request))
    return state.store.load_fence_model(model_id, version)


@app.post("/api/fence-models/{model_id}/{version}/status")
def set_fence_model_status(
    request: Request,
    model_id: str, version: int, status: Literal["active", "retired"],
):
    try:
        state.store.set_fence_model_status(model_id, version, status, actor=_actor(request))
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
def put_project_fence_model(request: Request, project_id: str, choice: FenceModelChoice | None = None) -> Project:
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
    state.store.save_project(project, actor=_actor(request))
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


#: One account per capacity, so a laptop and the browser smoke have somebody to
#: BE on a fresh database. Written only under `FENCEAI_IDENTITY=dev` (see
#: `lifespan`), so a real deployment never sees them and its first admin arrives
#: through `FENCEAI_BOOTSTRAP_ADMIN` instead.
DEMO_ACCOUNTS = [
    ("u_dana", "Dana", "dana@example.com", "sales"),
    ("u_yossi", "Yossi", "yossi@example.com", "backoffice"),
    ("u_admin", "Admin", "admin@example.com", "admin"),
]


def _seed_demo_accounts() -> None:
    """Only on an empty table, and only in dev. A company that has made its own
    accounts must never find three strangers in the list after an upgrade — and
    under `iap` it must never find them at all."""
    if state.store.list_users():
        return
    for uid, name, email, capacity in DEMO_ACCOUNTS:
        state.store.save_user(
            User(id=uid, name=name, email=email, capacity=capacity), actor="seed")


# -- who is asking -------------------------------------------------------------


def _actor(request: Request) -> str:
    """Who to write in the log.

    There is no unsigned case left: the gate resolved somebody before any
    route ran, so the resolved caller is the only answer. This used to take a
    `fallback` for the eleven `?author=`-style parameters that let a client
    NAME the actor instead — that was never an audit trail, and default-deny
    deleted the unsigned case `fallback` existed for, so it was already dead
    (unread in this body) before it was removed here along with the last of
    those parameters.
    """
    return actor_ref(current_user(request))


def _public(user: User) -> dict:
    """An account as a screen may see it.

    `subject` is Google's stable account id, and this function feeds two
    routes: `GET /api/session` (this account, to itself) and `GET /api/users`
    (every account, to any signed-in capacity — not only an admin). The second
    of those has no reason to hand a colleague's Google id to whoever asked;
    the people panel only needs to know WHETHER an address has completed a
    real Google sign-in, never which account it landed on. `subject_bound`
    answers that question and the raw id stays server-side, in the row
    `identity/binding.py` compares against.
    """
    data = user.model_dump(exclude={"subject"})
    data["subject_bound"] = bool(user.subject)
    return data


@app.get("/api/session")
def session(request: Request) -> dict:
    """Who am I, which view do I open on, and am I offered the selector.

    **The one route that answers without a capacity row.** A person IAP let
    through but nobody has granted anything reaches a screen telling them to ask
    an admin, and that screen has to be able to name them to the admin they are
    about to ask. Hence the exemption in `auth.EXEMPT_PATHS` and hence the
    `status` field: this route reports the refusal the rest of the API performs.

    The view is answered HERE rather than defaulted in the browser, which is the
    safe way to flip the default the salesperson MVP left at `all`: nobody edits
    a global setting, Dana lands on her own screen because of who she is.
    """
    principal = state.provider.principal(
        dict(request.headers), dict(request.cookies))
    if principal is None:
        return {"status": "no_identity", "code": "no_identity", "email": "",
                "user": None, "view": None, "may_choose_view": True}
    user, status = auth_resolve(state.store, principal)
    if status != "ok":
        # `code` rather than a second mapping in the browser: `status` is a
        # STATE for a screen and the code is the platform refusal a person may
        # read in a log, and the two differ for exactly one value
        # (`deactivated` / `account_deactivated`). `REFUSAL_STATUS_CODES` is
        # where that difference is decided; a copy of it in JavaScript would be
        # a second place to forget.
        return {"status": status, "code": REFUSAL_STATUS_CODES[status],
                "email": principal.email, "user": None,
                "view": None, "may_choose_view": True}
    return {"status": "ok", "code": None, "email": principal.email,
            "user": _public(user),
            "view": default_view(user.capacity),
            "may_choose_view": may_choose_view(user.capacity)}


class BecomeRequest(BaseModel):
    email: str


if _DEV:

    @app.post("/api/dev/identity", status_code=204)
    def become(body: BecomeRequest) -> Response:
        """Become somebody, with no credential, on a laptop.

        Registered ONLY under `FENCEAI_IDENTITY=dev`, so under `iap` this route
        does not exist to be found — which is why the condition is read here, at
        import, rather than checked inside the handler. It is an impersonation
        switch and is named as one: no secret, no session row, no expiry.
        """
        response = Response(status_code=204)
        response.set_cookie(DEV_COOKIE, body.email.strip().lower(),
                            httponly=True, samesite="lax",
                            max_age=30 * 24 * 3600)
        return response

    @app.delete("/api/dev/identity", status_code=204)
    def stop_being_dev() -> Response:
        """Stop being anybody, on a laptop. Registered on the same
        module-level condition as the POST above, for the same reason: under
        `iap` there is no cookie of ours to clear, and `js/session.js`'s
        `signOut()` already calls this inside a try/catch for exactly that
        case. `EXEMPT_PATHS` matches by path, not by method, so this needs no
        entry of its own."""
        response = Response(status_code=204)
        response.delete_cookie(DEV_COOKIE)
        return response


@app.get("/api/users")
def list_users(request: Request) -> list[dict]:
    """The people, for the assignee picker, the “sold by” filter and the
    admin's own panel."""
    # Belt and braces, and kept deliberately although the gate has already
    # resolved this caller: the day somebody adds a path to `EXEMPT_PATHS`, the
    # route that hands out every account in the company is the one that must not
    # quietly start answering. Nothing can assert this line while the gate
    # stands, which is the point of it.
    current_user(request)
    return [_public(u) for u in state.store.list_users()]


class GrantRequest(BaseModel):
    email: str
    name: str
    capacity: Capacity


class AmendRequest(BaseModel):
    capacity: Capacity | None = None
    active: bool | None = None


def _would_strand_the_admins(target: User, body: AmendRequest) -> bool:
    """Is this the edit that leaves nobody able to grant anything?

    Asked before the write, because after it the only cure is
    `FENCEAI_BOOTSTRAP_ADMIN` and a redeploy — and that variable is removed
    after the first deploy precisely so it is not a standing way in.
    """
    losing_admin = (body.capacity is not None and body.capacity != "admin") \
        or body.active is False
    if target.capacity != "admin" or not losing_admin:
        return False
    others = [u for u in state.store.list_users()
              if u.id != target.id and u.capacity == "admin" and u.active]
    return not others


@app.post("/api/users", status_code=201)
def grant_capacity(request: Request, body: GrantRequest) -> dict:
    """Give an address a capacity, before its owner has ever signed in.

    That order is the point: an admin grants Dana her capacity on Monday and
    Dana arrives on Tuesday, at which moment her Google `sub` binds to this row.
    """
    admin = require_admin(request)
    if state.store.user_by_email(body.email) is not None:
        raise HTTPException(409, {"code": "user_exists"})
    user = User(id=f"u_{uuid.uuid4().hex[:8]}", name=body.name,
                email=body.email, capacity=body.capacity)
    state.store.save_user(user, actor=actor_ref(admin))
    state.store.log(actor_ref(admin), "grant_capacity", user.id)
    return _public(user)


@app.patch("/api/users/{user_id}")
def amend_capacity(request: Request, user_id: str, body: AmendRequest) -> dict:
    """Change what somebody may do, or stop them doing anything.

    Deactivated, never deleted — the audit log names people who have left, so a
    row must keep resolving to a name for ever.
    """
    admin = require_admin(request)
    user = state.store.user(user_id)
    if user is None:
        raise HTTPException(404, {"code": "user_not_found"})
    if _would_strand_the_admins(user, body):
        raise HTTPException(409, {"code": "last_admin"})
    if body.capacity is not None:
        user.capacity = body.capacity
    if body.active is not None:
        user.active = body.active
    state.store.save_user(user, actor=actor_ref(admin))
    state.store.log(actor_ref(admin), "amend_capacity", user.id)
    return _public(user)


@app.get("/api/audit")
def audit(limit: int = 100):
    return state.store.audit_entries(limit)


# -- evidence viewer (Knowledge Discovery, fixture-backed) -----------------------

class SourceRefBatchRequest(BaseModel):
    ids: list[str]


class SourceRefBatchResponse(BaseModel):
    resolved: list[SourceRefResolved]
    # ids the fixture does not carry — never a per-id 404, since a queue
    # resolving fifty citations cannot afford one miss to fail the other 49.
    not_found: list[str] = []


@app.post("/api/source-refs:batch")
def resolve_source_refs(body: SourceRefBatchRequest) -> SourceRefBatchResponse:
    """Batch-resolve opaque `SourceRef.id` strings (core/gaps.py) into evidence
    a person can look at: a page crop, the quoted text beside it, and an
    honest provenance label.

    FIXTURE-BACKED, not a live call to fence-rag's Knowledge Platform: their
    Discovery API is design-only today (frontend design §3), so this resolves
    against a vendored copy of their own example fixture
    (`fenceai/knowledge/fixtures/source-ref-examples.json`, seven records
    built from real rows in their store). The request/response shape mirrors
    what a real Discovery API implementation could satisfy later — batched,
    because "ask for the batch call now, not later" (frontend design §3) — so
    the frontend does not have to change when fence-rag's endpoint ships.

    An id outside the seven-record fixture is not an error; it comes back in
    `not_found` rather than failing the whole batch, exactly the shape a
    review queue resolving many citations at once needs.
    """
    resolved, not_found = resolve_batch(body.ids)
    return SourceRefBatchResponse(resolved=resolved, not_found=not_found)


class _RevalidatedStaticFiles(StaticFiles):
    """The frontend, served so a browser ASKS before reusing a cached file.

    There is no build step (ADR-0010), so file names never change between
    versions. Without a `Cache-Control` a browser applies heuristic caching to
    each ES module separately, and after an update it can pair a fresh
    `app.js` with a stale `js/session.js`: the import of a name the old module
    does not export fails, `app.js` never runs, and the page stays blank. That
    is what a user saw the first time the login screen shipped. `no-cache`
    means revalidate, not "do not cache" — the ETag StaticFiles already sends
    makes an unchanged file a 304."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


if WEB_DIR.is_dir():
    app.mount("/", _RevalidatedStaticFiles(directory=str(WEB_DIR), html=True), name="web")
