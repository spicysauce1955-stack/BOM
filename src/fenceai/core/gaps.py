"""`Gap` — what is missing, said addressably (integration contract §1.2.1).

One type whether the Knowledge Platform publishes it or a planning run produces
it. That is the contract's wording and it is the reason this lives in `core/`
rather than under `knowledge/` or `strategy/`: a gap arriving in a snapshot and a
gap discovered while laying out a fence are the same fact seen from two sides,
and a curator's queue has to be able to hold both without a translation step.

**A gap is not a failure and not a warning.** A failure means the run stops; a
warning is a note on an answer. A gap is a hole in what we were told, carried
alongside an answer that was produced anyway — contract §3.2.4: *never fail a run
over a gap; warned, named, unfulfilled lines instead.* Every gap here is paired
with a `StrategyWarning` so the hole is visible on the drawing, and with a `gap`
node in the decision graph so it is traceable to the line it affected.

The fields are the contract's, unrenamed. Two are BINDING and are the reason the
type is worth having at all:

* `would_close` — one sentence naming what would resolve it. *"a footing row for
  exposure C, non-HVHZ, at 6 ft"* is a work item; *"footing depth is missing"*
  sends a curator hunting.
* `closes_by` — WHO can close it. Two kinds (`unmodellable_entity`,
  `unmapped_part_kind`) close by a schema change in THIS repo and by nothing a
  curator can do, and a review queue that shows a curator work only an engineer
  can perform is a queue whose items are not actionable.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

GapKind = Literal[
    "unmodellable_entity",       # the corpus describes something no type fits
    "uncovered_condition",       # a domain point no row covers
    "unsatisfiable_requirement", # nothing can fill a slot
    "unquantified",              # stated in prose, never given a number
    "missing_value",             # a field that should exist and does not
    "unmapped_part_kind",        # a part-kind no counting rule can produce
    "disputed",                  # two admissible readings disagree — carries `on`
    "illegible_source",          # the source states it; we cannot read it
]

# The two kinds a curator cannot close: they need a schema change here.
PLANNING_CLOSES: frozenset[str] = frozenset({"unmodellable_entity", "unmapped_part_kind"})


class GapSubject(BaseModel):
    """WHAT is missing, addressably — the contract's `EntityRef | SlotRef | ParamRef`.

    A discriminated ref rather than three types, because every consumer wants the
    same two things (which kind, which name) and a union of three one-field models
    buys a queue nothing but three code paths.
    """

    kind: Literal["entity", "slot", "param"]
    ref: str


class SourceRef(BaseModel):
    """Evidence, where there is any — contract §1.1, verbatim.

    ```text
    SourceRef    { id, belongs_to }        belongs_to = content_hash -> SourceDoc
    ```

    > **BINDING.** `SourceRef` is opaque to Planning in every respect except
    > `belongs_to`. That one field exists because a source ref resolves only on
    > the Discovery surface, which §3.2.2 forbids Planning from calling during a
    > run — so without it an opaque id carries **zero admissibility bits into a
    > pinned snapshot**, and a run cannot tell that three of a definition's five
    > citations are superseded approvals.

    So `belongs_to` is the whole point of the type and the one field this side is
    allowed to read. `id` is opaque and stays opaque: do not parse it, do not
    build one, do not infer a page number from it.

    A run-produced gap usually cites nothing — the evidence for *"no row covers
    this"* is the absence itself — so `cites` is empty far more often on this
    side than on a published gap. That is exactly why this type has to be right
    anyway: the direction it is NOT exercised in is the direction it will first
    be handed real data.
    """

    id: str
    belongs_to: str = ""  # content_hash -> SourceDoc; "" only where none was given


class Gap(BaseModel):
    id: str
    kind: GapKind
    # WHICH half of a `disputed` subject is in dispute — required by that kind and
    # meaningless on the other seven, so it is optional here and enforced below.
    #
    # Not a detail to flatten away: the contract records that **33.3% of the
    # platform's human-gated facts** carry a note that readers did not agree on
    # the applicability bracket — *the value is certain and the conditions are
    # not*. Dropping `on` turns that into an undifferentiated "somebody
    # disagreed" and discards the half that says where to look.
    on: Literal["value", "conditions"] | None = None
    subject: GapSubject
    # `code` + `params` render in both locales; `message` is an English fallback
    # only, exactly as StrategyWarning carries them.
    code: str
    params: dict[str, str | int] = {}
    message: str = ""
    cites: list[SourceRef] = []
    would_close: str
    closes_by: Literal["knowledge", "planning"] = "knowledge"
    severity: Literal["warns_line", "informational"] = "warns_line"

    def model_post_init(self, _ctx) -> None:
        # The one invariant worth enforcing in the type: the two schema-change
        # kinds cannot claim a curator can close them. Getting this wrong is not
        # a rendering bug, it is a work item nobody can action.
        if self.kind in PLANNING_CLOSES and self.closes_by != "planning":
            raise ValueError(
                f"a {self.kind} gap closes by a schema change in Planning, "
                f"not by {self.closes_by}"
            )
        # `disputed{ on: value | conditions }` is how the contract writes it: the
        # discriminator is part of the kind, not an optional embellishment.
        if self.kind == "disputed" and self.on is None:
            raise ValueError("a disputed gap must say what is disputed: value | conditions")
        if self.kind != "disputed" and self.on is not None:
            raise ValueError(f"`on` is meaningless on a {self.kind} gap")
