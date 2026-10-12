"""What a person calls a stretch of the drawing.

A, B, … Z, AA, AB … Sections are NAMED, not numbered, so a bay tag (B3) never
reads like a section tag. The letter is the run's position in the drawing, so
it is a fact about the topology and nothing else — which is why it lives here
rather than in a read model: three readers letter sections (`report.sections`
before generation, `report.structure` after, and `project.changes` for a job's
history), and the history is in the People & work plane, which has no business
importing the engine's read models to learn the alphabet.

**One implementation.** Two private copies would agree on every job anybody has
drawn and disagree on the twenty-seventh run.
"""

from __future__ import annotations

_SECTION_TAGS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def section_tag(index: int) -> str:
    """The letter for the n-th stretch of a drawing."""
    tag = ""
    n = index
    while True:
        tag = _SECTION_TAGS[n % 26] + tag
        n = n // 26 - 1
        if n < 0:
            return tag
