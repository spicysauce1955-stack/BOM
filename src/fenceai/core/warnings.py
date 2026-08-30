"""A warning QUOTED from a document — verbatim, attributed, and never translated.

Integration contract §1.2 (`Snapshot.warnings`) and obligation 10. This is the
other half of a split that runs through the whole warning surface, and the split
is the point of the module:

* **A platform warning** is `StrategyWarning` (or `Gap`, or a refusal): a closed
  `code` + `params` this engine emits, whose sentence lives in
  `web/static/i18n/{en,he}.json` and is enforced present in BOTH bundles by
  `tests/web/test_locale_bundles.py`. We wrote the code, so we owe the sentence.
* **A quoted warning** is this type: text somebody else published, carried
  through untouched. There is no key to look up, because the text IS the
  content. Zero of the corpus's 81,794 elements are Hebrew, and translating a
  manufacturer's liability sentence and publishing it as theirs manufactures a
  claim they never made. So it renders in the language it was written in, marked
  as quoted, and no surface offers to translate it.

CLAUDE.md's rule — "user-visible warnings carry `code + params`" — is the first
rule, and it is now scoped to the first list. It failed precisely where it was
most confidently applied: a `message`/`text` fallback is *by definition* the case
with no code, so "every code in both bundles" can never say anything about it.

**Why this is not a paragraph of prose on a step.** The audit's census of all
81,794 elements found 1,038 warning instances resolving to 226 distinct warnings,
and only **19.9% sit inside a step that does something**. About 68% are
document-scoped — the front safety box, "BEFORE YOU BEGIN", a freeze-thaw
footnote printed at the foot of fourteen pages — 9.4% product- or
certification-scoped, and 2.7% warranty-scoped. v0.1 of the contract said "a
warning is attached to its step"; enforced literally that publishes one warning
in five and misattributes the rest, which is why obligation 10 replaced it with
"every warning declares what it attaches to, and its text is primary".

`attaches_to` is therefore not metadata. It is what decides whether a reader sees
this sentence once, in the plan's annexe, or eighty-three times on eighty-three
lines — and `report/annexe.py` is the one function that decides.

**Two authors, one type.** A `DocumentWarning` reaches this engine two ways: a
published `Snapshot` carries them (`knowledge/snapshot.py`, typed and consumed
rather than counted), and a curator authors them on a `FenceModel` in the model
editor. Neither is privileged and both place through the same function. Nothing
has been published through the first door yet, which is exactly why the second
one must not grow its own placement rule: two placement rules is how a warning
comes to land in the annexe when it arrives over the wire and on every line when
a curator types it.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal

from pydantic import BaseModel

from fenceai.core.gaps import SourceRef

# What a warning can be about. Seven kinds, and the grouping that matters is not
# alphabetical: `step`/`procedure` are places in an instruction, `product`/`model`
# are things on a list, and `document`/`warranty`/`maintenance` are about the
# whole job. `report/annexe.py` renders the three groups in three places.
WarningScope = Literal[
    "step", "procedure", "document", "product", "model", "warranty", "maintenance",
]

# The kinds that belong in the annexe: about the document, not about a line.
# Named here rather than in the read model because it is a fact about the
# vocabulary — a `warranty` warning is not a per-line warning under any
# rendering — and a surface that re-derived the set could differ from the one
# that placed it.
ANNEXE_SCOPES: frozenset[str] = frozenset({"document", "warranty", "maintenance"})


class WarningTarget(BaseModel):
    """What this warning attaches to: a kind, and a reference where one applies.

    `ref` names the object the kind is about — a step key, a procedure, a sku, a
    model ref, and for the ANNEXE kinds **the document itself**: a `content_hash`
    into the snapshot's `source_docs`.

    This docstring used to say `ref` "is EMPTY for the annexe kinds", and the
    first real published snapshot falsified it in the most emphatic way
    available: 276 of its 289 warnings are annexe-scoped with a ref (274
    `document`, 2 `warranty`), and every one of those refs is the content hash of
    the source doc the sentence was quoted from — all 276 resolve. That is not a
    warning claiming a line. It is the only thing that lets an annexe group 274
    quoted sentences by the guide they came from, which is half of what a reader
    needs in order to go and check one.

    The scope rule the old claim was reaching for is real and survives, narrowed
    to what it can actually justify: an annexe-scoped ref must name a DOCUMENT.
    Naming something that is not one of the documents in hand is the defect —
    see `warning_errors`.

    An empty `ref` on `procedure` means "the procedure of the document this
    warning came with" — the head of its own assembly sheet. That is a local
    convention for the AUTHORED path and not §1.2's, which publishes procedures
    as first-class entities with their own ids and says nothing about an empty
    ref; it is defensible because a curator has no procedure id to name, and it
    is written down here so the next reader does not mistake it for the
    contract's. A PUBLISHED ref naming a procedure this engine does not hold is
    reported as unplaceable rather than dropped, because this engine models none
    of them yet.
    """

    kind: WarningScope
    ref: str = ""


class DocumentWarning(BaseModel):
    """Somebody else's sentence, carried without being improved.

    Every field here is either required-and-unnormalised or absent, and the two
    that look like conveniences are the ones with the sharpest reasons:

    `severity_lexeme` is the publisher's own word and is NOT mapped onto our
    `info | warning | error`. `CAUTION` and `WARNING` are terms of art with
    different legal weight in North American product literature, and a mapping
    that made them interchangeable would be this engine editing a liability
    notice. Shown verbatim beside the text, or not shown.

    `code` + `params` are an OPTIONAL OVERLAY and never the rendered sentence:
    142 of the 226 distinct warnings in the corpus appear exactly once, and only
    3 recur with different values, so a code pays off almost nowhere. Where a
    publisher does send one it is theirs, not ours — it is not in our closed
    registry, it gets no locale entry, and `text_raw` is still what renders. It
    is for grouping and filtering, which is the only thing it is good for.

    `cites` is where this side had to depart from its own spec, and the departure
    is recorded rather than smoothed over. `docs/superpowers/specs/
    2026-08-23-bom-engine-design.md` declared `cites` REQUIRED. It cannot be, on
    this side: contract §1.1 makes `SourceRef.id` opaque to Planning — "do not
    parse it, do not build one" — so a curator authoring a warning in the model
    editor has no way to mint one, and the Discovery surface that would hand them
    a real one (`GET /source-refs/{id}`) is designed and unimplemented. So it is
    optional here, an UNATTRIBUTED warning is rendered as unattributed, and the
    count of them is evidence for the team still designing the door they come in
    by. Requiring the field would have been enforced by fabricating ids, which is
    how a hypothesis becomes a fact nobody checked.

    `cites` is a LIST, not the single optional ref this side first modelled it
    as: a warning printed on fourteen pages of two documents genuinely cites
    several, and 76 of 282 of the Knowledge team's published warnings do. Their
    review of the conforming fixture is what caught the singular field here.

    `lang_basis` says how `lang` was arrived at — `measured` if a person or a
    verified process confirmed it, `assumed` otherwise. Every warning either side
    holds today is `assumed`: nothing in this engine's own text is script-detected
    or reviewed for language, so a reader trusting `lang` alone would be trusting
    an assertion nobody verified.

    `severity_lexeme` is `None` where the publisher gave no lexeme at all, kept
    distinct from `""`: absent-and-unknown is a different fact from
    present-and-empty, and the Knowledge team's corpus carries both.
    """

    text_raw: str
    lang: str
    lang_basis: Literal["measured", "assumed"] = "assumed"
    attaches_to: WarningTarget
    cites: list[SourceRef] = []
    severity_lexeme: str | None = None
    code: str | None = None
    params: dict[str, str | int] = {}

    def identity(self) -> tuple:
        """What makes two of these THE SAME warning rather than two warnings.

        The freeze-thaw footnote is printed at the foot of fourteen pages and
        resolves to 83 instances of one sentence; the annexe holds it once. So
        identity is the whole quoted payload — text, language, attribution,
        the publisher's severity word and their code — and NOT the target,
        which the read model has already grouped by.

        Text and text alone would collapse the same sentence cited to two
        different documents into one entry, and which document a warning came
        from is the half a reader needs in order to go and check it.
        """
        return (self.text_raw, self.lang,
                tuple((c.id, c.belongs_to) for c in self.cites),
                self.severity_lexeme or "", self.code or "")


def warning_errors(
    warnings: list[DocumentWarning],
    *,
    where: str,
    known_docs: Collection[str] | None = None,
) -> list[str]:
    """Every reason a quoted warning cannot be carried, as English for the author.

    Shared by `validate_model` (a curated document) and by snapshot ingestion (a
    published one), because the rules are properties of the TYPE and not of the
    door: a warning with no text says nothing, a warning with no language cannot
    be rendered in the direction it was written, and `params` without a `code`
    has nothing to interpolate into.

    These are authoring errors and carry no `code + params` themselves —
    `validate_model`'s own convention, and doubly right here: the reader of this
    string is the person holding the document.

    **`known_docs`, and why the annexe-ref rule now needs it.** This function
    used to refuse ANY annexe-scoped warning that carried a ref, on the reasoning
    that such a warning "belongs to the whole job" so a ref could only be it
    naming a line. That reasoning was wrong about what the ref names, and it
    passed for as long as it did because the only data it had ever been run
    against was `fixtures/snapshot-example.json` — a fixture this side authored,
    with empty refs. The first real published snapshot flagged 276 of its 289
    warnings; in all 276 the ref is the source doc's own `content_hash` and it
    resolves (543 `SourceRef.belongs_to` across that payload, 0 dangling). A rule
    that fails on 95% of the first real input is not catching a defect.

    Contract §3.3.5 is the only binding text here and it constrains WHERE such a
    warning renders — "once in the plan's annexe and never on a line" — not
    whether a ref may be present. `report/annexe.py` satisfies §3.3.5 on its own
    by discarding the ref when it buckets an annexe kind, so nothing downstream
    ever depended on the emptiness. The rule was ours, and its cited basis was a
    docstring.

    What is left is the narrowest thing that is still checkable: an annexe-scoped
    ref names a DOCUMENT, so pass the content hashes in hand and a ref that
    resolves to none of them is reported — the same class of defect as a step
    warning naming a step this model has not got, which `validate_model` already
    refuses one function over. Pass nothing and NOTHING is checked, deliberately:
    a curator authoring in the model editor holds no `source_docs` list, and a
    caller with no way to resolve a ref has no standing to call it dangling.
    Silence there is the honest answer, and it is the answer the old rule refused
    to give.

    `None` and an EMPTY collection are therefore different arguments, the same
    distinction `severity_lexeme` keeps between absent and blank: `None` is "I
    cannot resolve refs", and `set()` is "I can, and there are no documents" —
    a snapshot that ships annexe warnings with no `source_docs` to hang them on,
    where every ref really does dangle.
    """
    resolvable = known_docs if known_docs is None else frozenset(known_docs)
    errors: list[str] = []
    for i, w in enumerate(warnings):
        label = f"{where} warning {i}"
        if not w.text_raw.strip():
            errors.append(
                f"{label}: a quoted warning IS its text, and this one has none")
        if not w.lang.strip():
            errors.append(
                f"{label}: no lang. The text renders verbatim in the language it "
                f"was written in, so the language is what tells a reader — and a "
                f"right-to-left surface — which language that is")
        if w.params and not w.code:
            errors.append(
                f"{label}: params with no code. `params` are values for a code's "
                f"sentence, and the text of a quoted warning is never "
                f"interpolated — it is quoted")
        if w.attaches_to.kind in ANNEXE_SCOPES and w.attaches_to.ref \
                and resolvable is not None \
                and w.attaches_to.ref not in resolvable:
            errors.append(
                f"{label}: attaches to the {w.attaches_to.kind} and names "
                f"{w.attaches_to.ref!r}, which is not one of the documents that "
                f"came with it. An annexe-scoped ref names the document the "
                f"sentence was quoted from, so one that resolves to nothing "
                f"leaves the annexe unable to say who said it")
        if w.attaches_to.kind not in ANNEXE_SCOPES \
                and w.attaches_to.kind != "procedure" and not w.attaches_to.ref:
            errors.append(
                f"{label}: attaches to a {w.attaches_to.kind} and names none. "
                f"Without a ref there is no line to put it on, so it would be "
                f"carried and never rendered")
    return errors
