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
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import Inventory, fulfill
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion
from fenceai.strategy.generator import generate
from fenceai.strategy.model import Strategy
from fenceai.strategy.overrides import Override
from fenceai.topology.model import Topology


class ImpactCase(BaseModel):
    """One project to evaluate the hypothetical change against."""

    project_id: str
    project_name: str = ""
    topology: Topology
    overrides: list[Override] = []
    inventory: Inventory = Inventory()


class ProjectImpact(BaseModel):
    project_id: str
    project_name: str = ""
    changed: bool = False
    generation_failed: str | None = None  # hypothetical KB cannot generate at all
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


def _spine(topology, kb, catalog, overrides, inventory):
    result = generate(topology, kb, catalog, overrides=overrides)
    bom = fulfill(derive_requirements(result.strategy, catalog), catalog, inventory)
    return result.strategy, bom


def preview_impact(
    hypothetical: KnowledgeVersion,
    kb: KnowledgeBase,
    catalog: Catalog,
    cases: list[ImpactCase],
) -> ImpactReport:
    """Regenerate every case under (current KB) vs (KB with the hypothetical
    version active) and report per-project diffs. Deterministic; read-only."""
    kb_after = hypothetical_kb(kb, hypothetical)
    report = ImpactReport(hypothetical_ref=hypothetical.ref)
    for case in cases:
        if not case.topology.runs:
            continue  # nothing to compare on an empty project
        report.projects_checked += 1
        impact = ProjectImpact(project_id=case.project_id, project_name=case.project_name)
        strategy_before, bom_before = _spine(
            case.topology, kb, catalog, case.overrides, case.inventory
        )
        impact.bom_before_cents = bom_before.total_cents
        try:
            strategy_after, bom_after = _spine(
                case.topology, kb_after, catalog, case.overrides, case.inventory
            )
        except GenerationFailure as e:
            impact.generation_failed = str(e)
            impact.changed = True
            report.projects_affected += 1
            report.impacts.append(impact)
            continue
        _diff_strategies(strategy_before, strategy_after, impact)
        impact.bom_after_cents = bom_after.total_cents
        impact.bom_delta_cents = bom_after.total_cents - bom_before.total_cents
        impact.changed = (
            strategy_before.model_dump() != strategy_after.model_dump()
            or bom_before.model_dump() != bom_after.model_dump()
        )
        if impact.changed:
            report.projects_affected += 1
        report.impacts.append(impact)
    return report
