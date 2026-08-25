"""Rule impact preview: "what would this knowledge change do to my projects?"

The single highest-value review feature (Research D): before approving a candidate
or saving a new rule version, regenerate every project under the hypothetical
knowledge base and diff strategy + BOM against the current one. Pure
regenerate-and-diff (ADR-0006 impact philosophy) — no incremental patching.

Pure functions over explicit inputs; the API layer supplies the cases.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.core.errors import GenerationFailure
from fenceai.core.units import Cents
from fenceai.fulfillment.fulfill import Inventory
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import FenceModel
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion
from fenceai.parts.model import PartLibrary
from fenceai.project.model import SiteConditions
from fenceai.strategy.generator import generate
from fenceai.strategy.model import Strategy
from fenceai.strategy.overrides import Override
from fenceai.topology.model import Topology


class ImpactFailure(BaseModel):
    """Why the hypothetical knowledge base cannot generate, as `code + params`.

    User-visible text is rendered from the code by the reader's locale bundle
    (`impact.failure.<code>`); `message` is the raw engine string, a diagnostic
    fallback only — never the thing a Hebrew reader is shown.
    """

    code: str
    params: dict[str, str | int] = {}
    message: str = ""


class ImpactCase(BaseModel):
    """One project to evaluate the hypothetical change against."""

    project_id: str
    project_name: str = ""
    topology: Topology
    overrides: list[Override] = []
    inventory: Inventory = Inventory()
    accepted_quote_cents: Cents | None = None  # latest accepted quote, if any
    # the project's default model, for the same reason project_id is bound as a
    # scope dimension: a preview that regenerates a job under a DIFFERENT model
    # from the one it is built to reports the delta of two changes at once, and
    # attributes both to the rule being previewed
    fence_model: FenceModelChoice | None = None
    # ...and its SITE, for the same reason again, and this one bites hardest: a
    # preview that regenerates under no site conditions evaluates every
    # `site.*`-conditioned rule as not-applicable, so a rule that relays the
    # entire fence reports `bom_delta_cents: 0` on the screen a curator approves
    # from. `SiteConditions()` — all dimensions unset — rather than None, so the
    # namespace is always BOUND and `_assert_namespaces_bound` can tell "nobody
    # answered" from "nobody asked".
    site: SiteConditions = SiteConditions()
    # and its policy, for the same reason: `objective_preset` decides which
    # product supply resolution buys, so previewing under DEFAULT_POLICY reports
    # a delta the real run would never produce
    policy: dict = {}


class ProjectImpact(BaseModel):
    project_id: str
    project_name: str = ""
    changed: bool = False
    generation_failure: ImpactFailure | None = None  # hypothetical KB cannot generate
    # the project could not generate BEFORE the change either, so there is no
    # delta to report and this row is not evidence about the change. Distinct
    # from `generation_failure` alone, which means the change broke it.
    baseline_failed: bool = False
    posts_added: int = 0
    posts_removed: int = 0
    posts_modified: int = 0  # same station, different sku/kind/mounting/reinforced
    spans_before: int = 0
    spans_after: int = 0
    bom_before_cents: Cents = 0
    bom_after_cents: Cents = 0
    bom_delta_cents: Cents = 0
    warnings_before: int = 0
    warnings_after: int = 0
    # vs the project's ACCEPTED quote (the number the customer actually saw)
    accepted_quote_cents: Cents | None = None
    vs_accepted_delta_cents: Cents | None = None


class ImpactReport(BaseModel):
    hypothetical_ref: str
    projects_checked: int = 0
    projects_affected: int = 0
    impacts: list[ProjectImpact] = []  # every checked project, changed flag per row


def activated_copy(candidate: KnowledgeVersion) -> KnowledgeVersion:
    """The version a candidate WOULD become on approval (mirrors review promotion:
    candidate type -> heuristic, next version number, active status)."""
    return candidate.model_copy(
        update={
            "version": candidate.version + 1,
            "type": "heuristic" if candidate.type == "candidate" else candidate.type,
            "status": "active",
        }
    )


def hypothetical_kb(kb: KnowledgeBase, hypothetical: KnowledgeVersion) -> KnowledgeBase:
    """A copy of the KB with the hypothetical version active and any currently
    active version of the same object retired (matching replace_active_version)."""
    versions = []
    for v in kb.versions:
        if v.object_id == hypothetical.object_id and v.status in ("active", "proposed"):
            v = v.model_copy(update={"status": "retired"})
        versions.append(v)
    versions.append(hypothetical.model_copy(update={"status": "active"}))
    return KnowledgeBase(versions=versions)


def _post_key(post) -> tuple:
    return (post.run_ref, post.station_mm)


def _post_signature(post) -> tuple:
    return (post.sku, post.kind, post.mounting, post.reinforced)


def _diff_strategies(before: Strategy, after: Strategy, impact: ProjectImpact) -> None:
    b = {_post_key(p): _post_signature(p) for p in before.posts}
    a = {_post_key(p): _post_signature(p) for p in after.posts}
    impact.posts_added = len(a.keys() - b.keys())
    impact.posts_removed = len(b.keys() - a.keys())
    impact.posts_modified = sum(1 for k in b.keys() & a.keys() if b[k] != a[k])
    impact.spans_before = len(before.spans)
    impact.spans_after = len(after.spans)
    impact.warnings_before = len(before.warnings)
    impact.warnings_after = len(after.warnings)


def _failure(e: GenerationFailure) -> ImpactFailure:
    """The engine's English sentence is not a user-facing message. Report the
    structure a reader can act on — which knowledge blocked generation — and keep
    the raw text only as a diagnostic."""
    if e.constraint_refs:
        return ImpactFailure(
            code="generation_failed_refs",
            params={"refs": ", ".join(e.constraint_refs)},
            message=str(e),
        )
    return ImpactFailure(code="generation_failed", message=str(e))


def _spine(topology, kb, catalog, overrides, inventory, project_id="",
           models=None, default_model=None, policy=None, parts=None,
           site=None):
    # project_id is a bound scope dimension during generation — a project-scoped
    # rule must behave in the preview exactly as it will in the real run. `parts`
    # travels for the same reason: a slot's products come from the part it names,
    # so a preview regenerating without the library is pricing a different fence
    # from the one Generate would build.
    result = generate(topology, kb, catalog, overrides=overrides, project_id=project_id,
                      models=models, default_model=default_model, policy=policy,
                      parts=parts, site=site)
    # the SAME pipeline the read routes run, not a fourth hand-rolled copy of it:
    # a preview that priced a job differently from /bom would be worse than no
    # preview at all
    priced = price_strategy(
        result.strategy, catalog, inventory,
        demand_skus=result.run.demand_skus, preset=result.run.objective_preset,
    )
    return result.strategy, priced.bom


def hypothetical_library(
    library: FenceModelLibrary, hypothetical: FenceModel
) -> FenceModelLibrary:
    """The library as it would be with this model version published.

    Any currently active version of the same model id is retired, mirroring what
    publishing does — otherwise `latest_active` could still return the old one and
    the preview would report no change. A version PINNED by a project is left
    reachable by `resolve`, which is the whole point of a pin: those projects
    correctly show no impact.
    """
    models = [
        m.model_copy(update={"status": "retired"})
        if m.id == hypothetical.id and m.status == "active" else m
        for m in library.models
    ]
    models = [m for m in models
              if not (m.id == hypothetical.id and m.version == hypothetical.version)]
    models.append(hypothetical.model_copy(update={"status": "active"}))
    return FenceModelLibrary(models=models)


def preview_model_impact(
    hypothetical: FenceModel,
    library: FenceModelLibrary,
    kb: KnowledgeBase,
    catalog: Catalog,
    cases: list[ImpactCase],
    parts: PartLibrary | None = None,
) -> ImpactReport:
    """"This change would affect N of your projects", for a fence model.

    `FenceModel` is catalog-side rather than a knowledge object, so it inherits
    none of knowledge's versioning, review and preview machinery for free —
    and editing a model's slat gap is a portfolio-wide change that foundation
    §11 requires to be exposed BEFORE it is made. Same regenerate-and-diff, with
    the library swapped instead of the knowledge base.
    """
    return _preview(
        hypothetical.ref, kb, kb, catalog, cases,
        library, hypothetical_library(library, hypothetical), parts,
    )


def preview_impact(
    hypothetical: KnowledgeVersion,
    kb: KnowledgeBase,
    catalog: Catalog,
    cases: list[ImpactCase],
    library: FenceModelLibrary | None = None,
    parts: PartLibrary | None = None,
) -> ImpactReport:
    """Regenerate every case under (current KB) vs (KB with the hypothetical
    version active) and report per-project diffs. Deterministic; read-only."""
    library = library or FenceModelLibrary()
    return _preview(
        hypothetical.ref, kb, hypothetical_kb(kb, hypothetical), catalog, cases,
        library, library, parts,
    )


def _preview(
    ref: str,
    kb_before: KnowledgeBase,
    kb_after: KnowledgeBase,
    catalog: Catalog,
    cases: list[ImpactCase],
    library_before: FenceModelLibrary,
    library_after: FenceModelLibrary,
    parts: PartLibrary | None = None,
) -> ImpactReport:
    """One regenerate-and-diff, whichever of the two inputs is the hypothesis.

    Knowledge and models are both things a change to which silently reprices
    every open job, and both must be previewable the same way; two copies of this
    loop would be two chances for one of them to answer differently."""
    report = ImpactReport(hypothetical_ref=ref)
    for case in cases:
        if not case.topology.runs:
            continue  # nothing to compare on an empty project
        report.projects_checked += 1
        impact = ProjectImpact(project_id=case.project_id, project_name=case.project_name)
        try:
            strategy_before, bom_before = _spine(
                case.topology, kb_before, catalog, case.overrides, case.inventory,
                case.project_id, library_before, case.fence_model, case.policy,
                parts, case.site,
            )
        except (GenerationFailure, ValueError) as e:
            # The project cannot generate as it STANDS — a broken rule, a SKU
            # somebody deleted. That is not this change's doing and there is no
            # delta to report, but it must not take the portfolio preview down
            # with it: one unbuildable job used to 500 the whole "what would this
            # affect" answer, which is the moment a user most needs an answer.
            impact.generation_failure = _failure(e) if isinstance(
                e, GenerationFailure) else ImpactFailure(
                    code="generation_failed", message=str(e))
            impact.baseline_failed = True
            report.impacts.append(impact)
            continue
        impact.bom_before_cents = bom_before.total_cents
        try:
            strategy_after, bom_after = _spine(
                case.topology, kb_after, catalog, case.overrides, case.inventory,
                case.project_id, library_after, case.fence_model, case.policy,
                parts, case.site,
            )
        except GenerationFailure as e:
            impact.generation_failure = _failure(e)
            impact.changed = True
            report.projects_affected += 1
            report.impacts.append(impact)
            continue
        _diff_strategies(strategy_before, strategy_after, impact)
        impact.bom_after_cents = bom_after.total_cents
        impact.bom_delta_cents = bom_after.total_cents - bom_before.total_cents
        if case.accepted_quote_cents is not None:
            impact.accepted_quote_cents = case.accepted_quote_cents
            impact.vs_accepted_delta_cents = bom_after.total_cents - case.accepted_quote_cents
        impact.changed = (
            strategy_before.model_dump() != strategy_after.model_dump()
            or bom_before.model_dump() != bom_after.model_dump()
        )
        if impact.changed:
            report.projects_affected += 1
        report.impacts.append(impact)
    return report
