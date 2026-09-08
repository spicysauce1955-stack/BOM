"""The S20 published-limit fence, as a fixture two suites share.

Not a test module. It exists because the shape S20 pins — a span maximum that
arrived as thousandths and does NOT sit on a whole millimetre — cannot be built
from `demo_knowledge()`: every rule this repo authored is integer millimetres, so
`max_span_milli` is always `max_span * 1000` and the remainder ceiling is always exactly
`max_span`. Nothing authored can put a bay a fraction over its own maximum, which
is why the second authorized exception in `docs/scenarios/golden-scenarios.md`
went twelve commits with no scenario behind it.

So the maximum comes from a published `paired(...)` row in the shape and
provenance the vendored real snapshots use — the same shape as
`tests/knowledge/test_published_precision.py`'s, deliberately, so the two suites
cannot drift onto two different sets of numbers for one behaviour.

`K-MAXSPAN` is REMOVED rather than out-specified: two hard maximums at the same
authority is `resolve_param`'s conflict path, which is a different scenario (S13)
and would make this one about tie-breaking rather than about precision.
"""

from __future__ import annotations

from fenceai.core.gaps import SourceRef
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeBase
from fenceai.knowledge.parameters import (
    ParameterRow, ParameterTable, Provenance, Quantity, expand,
)
from fenceai.knowledge.source_policy import SHIPPED_DEFAULT

ROUNDED = "span_rounded_over_published_limit"

# 56 in x 25.4, exactly — a whole inch, not a conversion artefact, which is why a
# publisher will keep sending numbers like it.
PUBLISHED_LIMIT_MILLI = 1422400
PUBLISHED_MAX_MM = 1422        # `to_mm` of the above: what every clamp compares
PUBLISHED_CEIL_MM = 1423       # `remainder_ceiling_mm()`: widest whole mm it admits
RUN_MM = 4267                  # three bays under the true limit, four under 1422
EXACT_RUN_MM = 4266            # one mm shorter: the residue vanishes

# 75 in is 1905.000 mm — the one magnitude of the ACTIVE snapshot's six that is
# whole, so the control is made against real data rather than an authored rule.
WHOLE_LIMIT_MILLI = 1905000
WHOLE_RUN_MM = 9000


def span_table(milli: int, lexeme: str) -> ParameterTable:
    """One `paired` row in the shape and provenance the real snapshot uses, so
    §1.4 admits it and it lands as knowledge rather than as a gap.

    The parameter this table NAMES is `footing_schedule`; the parameter it BINDS
    is `max_span_mm`, inside `value_type`. That is where the breach hid — a scan
    enumerating `ParameterTable.parameter` never sees the span limit at all —
    and it is why this fixture publishes the pair rather than a bare maximum.
    """
    return ParameterTable(
        parameter="footing_schedule", task="structural_parameter",
        value_type="paired(footing_depth_mm:mm, max_span_mm:mm)",
        rows=[ParameterRow(
            provenance=Provenance(
                cites=[SourceRef(id="doc-1", belongs_to="doc-1")],
                source_class="sealed_approval", curation_level=2),
            value=[[Quantity(amount_milli=609600, unit="mm", value_raw=['24"']),
                    Quantity(amount_milli=milli, unit="mm", value_raw=[lexeme])]])],
    )


def published_knowledge(milli: int = PUBLISHED_LIMIT_MILLI,
                        lexeme: str = '56"') -> KnowledgeBase:
    """The demo knowledge base with its authored maximum replaced by a published
    one at `milli` thousandths."""
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-MAXSPAN"]
    versions, gaps, _ = expand(span_table(milli, lexeme), policy=SHIPPED_DEFAULT)
    assert gaps == [], "the fixture's own row must land as knowledge, not as a gap"
    kb.versions.extend(versions)
    return kb


# Module-level and shared, like `EXPOSURE_KB` beside it: the invariant battery
# identifies its published fixture by this object, so the limit it checks against
# is the one this file states rather than a number copied into two places.
PUBLISHED_KB = published_knowledge()
