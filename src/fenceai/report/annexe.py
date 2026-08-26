"""Where each quoted warning lands — and the annexe, which is where most of them do.

Contract §3.3.5 is the obligation this closes, and it is worth quoting because it
names the failure rather than the feature:

> Render a warning where its `attaches_to.kind` says: on the step, at the head of
> the procedure, on the BOM line group, or — for `document`, `warranty` and
> `maintenance` — once in the plan's **annexe** and never on a line. A
> document-scoped warning shown on every line is noise that trains a reader to
> ignore warnings.

So this module is not a formatter. It is the single place that decides where a
sentence somebody else published is allowed to appear, and every surface reads
its own bucket out of one answer:

| `attaches_to.kind`                     | bucket       | rendered              |
|----------------------------------------|--------------|-----------------------|
| `step`                                 | `step`       | on that step          |
| `procedure`                            | `procedure`  | head of the procedure |
| `product`, `model`                     | same names   | once per line group   |
| `document`, `warranty`, `maintenance`  | `annexe`     | once, never on a line |

**The freeze-thaw footnote is the case to hold in mind.** It is printed at the
foot of fourteen pages and resolves to 83 instances of one sentence. It becomes
ONE annexe entry carrying `instances=83`, and refusing to attribute it to step 10
costs nothing — nobody ever needed to be told about frost heave while fitting a
rail. Collapsing happens by `DocumentWarning.identity()`, so the same sentence
cited to two different documents stays two entries: which document said it is
half of what a reader needs to go and check it.

**What `instances` counts, said carefully, because the first version of it lied.**
It counts identical warnings among the ones THIS PLAN carries — not printings in a
document. The two are the same number when one publisher repeats itself and
different when two of a company's own product lines each say a thing once: §1.1
forbids this side from minting a `SourceRef`, so every authored warning is
uncited, `identity()` maps an absent citation to the empty one, and two
in-house documents saying the same sentence therefore collapse — correctly, since
a reader wants it once — with `instances=2`. The locale string used to render that
as "the document prints this 2 times", which no document did. It now says what
the number is: how many times this appears across the documents this fence is
built to.

**The invariant, and it is deliberately the same shape as the two beside it.**
`report/assembly.py` says every member is placed by exactly one step or reported
`unplaced`; `report/structure.py` says `Σ(parts) ≡ BOM`. Here:

    Σ instances + not_in_plan  ≡  the warnings handed in

Every warning is placed, counted as belonging to another plan, or reported
unplaceable. None is dropped, and the arithmetic is checkable from the returned
object alone — which is what stops a future surface from quietly filtering a
kind it does not know how to draw.

**`not_in_plan` is quiet on purpose, and `unplaceable` is not.** A warning about
a sku this fence does not buy is not a problem — it belongs to another job, and
listing it would put a stranger's safety notice on this plan. A warning attached
to a `procedure` this engine does not hold IS a problem: §1.2 publishes
`procedures` as step sequences that own no panel, this engine models none, and
saying so is how that gap stays visible instead of becoming a silent filter.

**`instances` is a count and not a quantity**, which matters because a read model
here may never recompute one (foundation §15). It counts the identical warnings
this function was handed — there is no other record of how many times a document
printed a sentence, and nothing downstream buys anything with it. Every number
that reaches a purchase still comes from `resolve_supply` by way of an inverted
peg, exactly as it does on the setting-out sheet.

**Nothing here is localized, and that is the whole discipline.** A quoted warning
carries `text_raw` and `lang`; this module moves it and never touches it. The
codes and sentences in `i18n/{en,he}.json` are for the platform's own warnings —
see `core/warnings.py` for the split and why CLAUDE.md's rule now names it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel

from fenceai.core.warnings import ANNEXE_SCOPES, DocumentWarning
from fenceai.fencemodel.model import FenceModel

# Where a warning ended up. Five places a reader can look, plus the honest sixth.
Bucket = Literal["step", "procedure", "product", "model", "annexe", "unplaceable"]


class PlacedWarning(BaseModel):
    """One warning, and the one place it renders.

    `ref` is the step key, sku or model ref it landed on — empty for the annexe,
    which is the point of the annexe. `instances` is how many identical warnings
    collapsed into this one entry: 1 almost everywhere, 83 for a footnote at the
    foot of fourteen pages, and never 0.

    `instances` counts identical warnings across the documents THIS PLAN carries,
    which is not the same claim as "printed N times in one document" — see the
    module docstring.

    `owner` is the document the sentence came OUT of, and it is here because a
    step key is model-local. Both reviewers of this slice found the same hole
    from opposite ends: `rails`, `cure` and `frame` are generic keys, so a plan
    built to two product lines placed manufacturer A's warning on ref `rails`
    and any surface drawing step warnings would show it on manufacturer B's
    `rails` step. That is obligation 10's misattribution reached by a third
    route, and it was latent only because the one surface drawing that bucket
    previews a single model — a fact about today's UI, not about the model.

    So a model-local bucket is keyed by `(owner, ref)` and a global one by `ref`
    alone. `product` and `model` refs are global identifiers and need no owner to
    disambiguate; the annexe deliberately ignores it, so one footnote two
    documents quote from the same source doc is still one entry.
    """

    warning: DocumentWarning
    where: Bucket
    ref: str = ""
    instances: int = 1
    owner: str = ""


class WarningPlacement(BaseModel):
    """Every quoted warning of a plan, each in exactly one place.

    One list rather than a field per bucket, so a surface that renders three of
    them cannot disagree with one that renders two about what the fourth
    contained — and so the invariant above is one sum over one list.
    """

    placements: list[PlacedWarning] = []
    # Warnings that belong to another job: a sku this fence does not buy, a step
    # of a document it is not built to. COUNTED, not listed — see the module
    # docstring. A surface may say "4 warnings belong to other documents"; it
    # must not print a stranger's safety notice on this plan.
    not_in_plan: int = 0
    # Documents this plan was built to that could not be READ back, so whatever
    # they warn is not in the list above. Not a placement and not a gap in the
    # document — a hole in what this plan can say about itself.
    #
    # The caller counts them (`api/app.py::_quoted_warnings`), because only the
    # caller knows which library it asked. Carried here rather than dropped for
    # the reason the module docstring gives for `unplaceable`: an annexe that
    # renders nothing because a document went missing is indistinguishable, to
    # the person holding the sheet, from a document that warns nothing.
    documents_unreadable: int = 0

    def at(self, where: Bucket, ref: str | None = None) -> list[PlacedWarning]:
        """The bucket a surface renders, optionally narrowed to one target.

        `ref=None` is every ref, which is what the annexe and a procedure head
        want; `ref="rails"` is what one step wants. A caller filtering the list
        itself would be a second placement rule the moment it got a condition
        wrong, so the filter lives here.
        """
        return [p for p in self.placements
                if p.where == where and (ref is None or p.ref == ref)]

    def carried(self) -> int:
        """How many warnings this placement accounts for, instances and all.

        The left-hand side of the invariant. A test asserts it against the input;
        a surface uses it to say how many it is not showing.
        """
        return sum(p.instances for p in self.placements) + self.not_in_plan


def place_warnings(
    warnings: Iterable[DocumentWarning],
    *,
    steps: Iterable[str] = (),
    skus: Iterable[str] = (),
    model_refs: Iterable[str] = (),
    procedures: Iterable[str] = (),
    owner: str = "",
) -> WarningPlacement:
    """`(the warnings, and what this plan actually holds)` -> where each one goes.

    Pure, and pure over its ARGUMENTS rather than over a run: the panel sheet
    knows its steps, the BOM knows its skus, and neither knows the other's. A
    caller passes what it holds; a bucket it did not describe comes back as
    `not_in_plan` rather than as a placement onto nothing.

    **Pass every vocabulary you can, even the ones you do not draw.** The
    structure sheet renders only the annexe, but it is handed the step keys
    anyway, because then it can say "and 4 warnings are shown on the panel
    sheet" instead of silently counting them as somebody else's. That is the same
    present-and-unrendered discipline `AssemblyStep.scope` keeps for `run` and
    `site`: dropping a fact at the boundary of a surface loses it, and saying how
    many were withheld does not.

    `procedures` is empty at every call site today and the parameter exists
    anyway — it is the seam. §1.2 publishes procedures as step sequences that own
    no panel; when this engine models one, a `procedure`-scoped warning stops
    being unplaceable here and nothing else changes.
    """
    placements: list[PlacedWarning] = []
    # first-seen wins, so authored order survives: a front safety box is printed
    # first because it is read first, and sorting the annexe would lose that.
    index: dict[tuple, int] = {}
    not_in_plan = _place_into(
        placements, index, warnings, owner=owner, steps=steps, skus=skus,
        model_refs=model_refs, procedures=procedures)
    return WarningPlacement(placements=placements, not_in_plan=not_in_plan)


def _place_into(
    placements: list[PlacedWarning],
    index: dict[tuple, int],
    warnings: Iterable[DocumentWarning],
    *,
    owner: str,
    steps: Iterable[str],
    skus: Iterable[str],
    model_refs: Iterable[str],
    procedures: Iterable[str],
) -> int:
    """One document's worth of warnings, appended to a placement being built.

    Split out of `place_warnings` so `place_for_plan` can walk several documents
    into ONE list with ONE dedup index: the step vocabulary has to be checked per
    document (a step key is model-local) while the annexe has to collapse across
    documents (a footnote two product lines quote from one source doc is one
    entry). Doing it as a merge of separate placements would lose the second;
    doing it as one pooled vocabulary lost the first, which is what both reviews
    found.

    Returns the number of warnings that belong to another job. Mutates its first
    two arguments, which is the whole reason it is private.
    """
    step_keys = set(steps)
    sku_set = set(skus)
    model_set = set(model_refs)
    procedure_set = set(procedures)
    not_in_plan = 0

    for warning in warnings:
        target = warning.attaches_to
        if target.kind in ANNEXE_SCOPES:
            where: Bucket = "annexe"
            ref = ""
        elif target.kind == "step":
            if target.ref not in step_keys:
                not_in_plan += 1
                continue
            where, ref = "step", target.ref
        elif target.kind == "product":
            if target.ref not in sku_set:
                not_in_plan += 1
                continue
            where, ref = "product", target.ref
        elif target.kind == "model":
            if target.ref not in model_set:
                not_in_plan += 1
                continue
            where, ref = "model", target.ref
        else:  # procedure
            if not target.ref:
                # "the procedure of the document this warning came with" — the
                # head of its own assembly sheet, which is a surface we have.
                # An authored warning can take no other form: `validate_model`
                # refuses a named procedure, because the ids are the platform's.
                where, ref = "procedure", ""
            elif target.ref in procedure_set:
                where, ref = "procedure", target.ref
            else:
                # A `target.ref in model_set` branch used to live here, reading a
                # model ref as its own procedure's id. Removed: a model ref is
                # never a procedure id, so it could not have fired on real data,
                # and it made an empty ref look like one case of two.
                # A published `Procedure` that owns no panel. We hold none, so
                # this is reported rather than filed under somebody else's job:
                # `not_in_plan` would say "not yours", and the truth is "yours,
                # and this engine has nowhere to put it".
                where, ref = "unplaceable", target.ref

        # Three things beyond the text make two warnings different warnings, and
        # each is here because collapsing on less loses something a reader needs:
        #
        # `ref` — one sentence attached to two steps is two placements. Drop it
        #   and the second step silently loses its warning while the invariant
        #   still balances, because the loss becomes an `instances` count. That
        #   is the module's own "carried and never rendered" failure arriving
        #   through the collapse instead of through the target.
        # `target.kind` — all three annexe kinds share one bucket, so a warranty
        #   condition and a maintenance note that happen to read the same would
        #   otherwise merge, and a reader would lose which of the two they were
        #   being told.
        # `owner`, for the model-local buckets only — see `PlacedWarning.owner`.
        #   The annexe, and a global sku or model ref, must NOT carry it, or one
        #   footnote quoted by two product lines becomes two entries.
        #
        # `identity()` deliberately excludes the target (see its docstring), so
        # the target is added here, whole.
        scope = owner if where in ("step", "procedure") else ""
        key = (where, ref, scope, target.kind, *warning.identity())
        if key in index:
            placements[index[key]].instances += 1
            continue
        index[key] = len(placements)
        placements.append(PlacedWarning(warning=warning, where=where, ref=ref,
                                        owner=owner))

    return not_in_plan


def place_for_plan(
    models: Iterable[FenceModel], skus: Iterable[str] = (),
) -> WarningPlacement:
    """Every quoted warning of every document this plan is built to, placed.

    The one call every surface makes, and it exists to stop a surface choosing
    its own vocabularies. A route that passed `skus` and forgot `steps` would
    turn every step-scoped warning into `not_in_plan` — "belongs to another job"
    — which is the exact misattribution obligation 10 replaced the old rule to
    avoid, arrived at from the other direction. Here the vocabularies are read
    off the documents themselves, so forgetting one is not expressible.

    A plan is built to more than one document more often than it looks: a run
    with two sections can carry two product lines, and a boundary post between
    them belongs to both. So this takes a LIST, dedups the annexe across all of
    them (one shared footnote, cited to one source doc, is one entry), and leaves
    `skus` to the caller because what a fence buys is fulfillment's answer and
    never a document's.
    """
    models = list(models)
    skus = list(skus)
    refs = [model.ref for model in models]
    placements: list[PlacedWarning] = []
    index: dict[tuple, int] = {}
    not_in_plan = 0
    # PER DOCUMENT, because a step key is model-local — `rails` and `cure` are
    # generic, and pooling the vocabularies put one manufacturer's warning on
    # another's step. `model_refs` stays the whole plan's: a document may only
    # warn about ITSELF (`validate_model` enforces that), and passing one ref at
    # a time would say nothing different while making the argument look local.
    #
    # One `index` across the loop, so the annexe still collapses across
    # documents: two product lines quoting one source doc's footnote is one
    # entry, and that property has a test.
    for model in models:
        not_in_plan += _place_into(
            placements, index, model.warnings,
            owner=model.ref,
            steps=[step.key for step in model.assembly],
            skus=skus,
            model_refs=refs,
            procedures=(),
        )
    return WarningPlacement(placements=placements, not_in_plan=not_in_plan)
