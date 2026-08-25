"""The vocabularies a client may OFFER, in one place, because the editor must
not keep a second copy of them.

`panel-model.js` used to carry hand-written arrays of the fixing bases and the
length rules, pinned to `model.py` by a test. That pin is a person: a value the
schema gains and the array does not is a product line nobody can author, and a
value the array keeps and the schema drops is a save that 422s — and BOTH stay
green until somebody re-reads the JS. So the browser asks instead, through
`GET /api/vocabularies`.

**This module is the seam**, and it has already earned that description once.
It was written against the `Literal`s that used to define these three
vocabularies, predicting that when the handler registries of
`docs/superpowers/specs/2026-08-25-engine-architecture.md` §4 landed the three
functions would become registry lookups "and nothing above them changes: not the
route, not the editor, not the tests." The registries landed, and that is exactly
what it cost — the imports below and three function bodies.

ORDER IS DECLARATION ORDER, never sorted — hence `declared()` rather than
`names()`. These reach a select, and the sequence they are declared in is an
editorial judgement: `clear_between_posts` first because it is what most rails
are, `per_panel` last because it is the coarsest. `Registry.names()` is sorted
because IT answers "what could you have meant?" after a mistake, where a stable
order is the point; this answers "what may I choose?" before one, where the
author's ordering is information. Asking the wrong one of the two silently
reorders a dropdown, which is a regression the registry refactor shipped and this
distinction caught.

Every member is user-visible, so every member needs a word in BOTH locale
bundles; `tests/web/test_locale_bundles.py` reads the lists from here and refuses
one that has none. What the UI does with an unlabelled member is decided in
`panel-inspector.js` (it shows the raw token, never a dotted key).
"""

from __future__ import annotations

from fenceai.fencemodel.bases import FIXING_BASES as _BASES
from fenceai.fencemodel.lengths import LENGTH_RULES as _RULES
from fenceai.fulfillment.presets import PRESETS as _PRESETS

# The three names the API and the editor agree on. Kept as constants rather than
# spelled at each call site, because a typo in one of them is a vocabulary that
# silently arrives empty.
LENGTH_RULES = "length_rules"
FIXING_BASES = "fixing_bases"
OBJECTIVE_PRESETS = "objective_presets"


def length_rules() -> list[str]:
    """How a member's cut length is measured. Slot- and member-level."""
    return _RULES.declared()


def fixing_bases() -> list[str]:
    """What a fixing rule counts — crossings, members, gaps, panels."""
    return _BASES.declared()


def objective_presets() -> list[str]:
    """The lexicographic objectives supply resolution ranks candidates under
    (ADR-0007). Not offered by the panel editor — the objective is a PROJECT
    policy, not a property of a panel — but it is the third vocabulary the seam
    covers, it is authorable (`project.policy["objective_preset"]`), and the
    picker that will offer it is exactly the surface that would otherwise invent
    its own list. Three lines now against the same defect later.
    """
    return _PRESETS.declared()


def vocabularies() -> dict[str, list[str]]:
    """Everything a client may offer, as one document."""
    return {
        LENGTH_RULES: length_rules(),
        FIXING_BASES: fixing_bases(),
        OBJECTIVE_PRESETS: objective_presets(),
    }
