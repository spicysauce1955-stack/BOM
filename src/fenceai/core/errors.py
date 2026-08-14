from __future__ import annotations


class FenceAiError(Exception):
    """Base class for domain errors."""


class GenerationFailure(FenceAiError):
    """A hard constraint cannot be satisfied and no authorized exception exists.

    Distinct from a Conflict (which is surfaced but survivable) — see knowledge-system.md.

    `code` + `params` are OPTIONAL and carry the same contract as `ReadRefused`:
    when present, the route sends them instead of the English sentence and the
    reader's locale bundle renders `error.<code>`. They are set for the failures
    a USER can cause from the editors — a knowledge rule naming a SKU nobody
    stocks is the whole strategy refused, and "the action failed (422)" tells
    that user neither which SKU nor that a SKU is even the problem. A failure
    only an author of internal data can cause stays a plain sentence.
    """

    def __init__(
        self,
        message: str,
        *,
        constraint_refs: list[str] | None = None,
        code: str | None = None,
        **params: str | int,
    ):
        super().__init__(message)
        self.constraint_refs = constraint_refs or []
        self.code = code
        self.params: dict[str, str | int] = params


class InvalidTopology(FenceAiError):
    pass


class RequestRefused(FenceAiError, ValueError):
    """The REQUEST names something the model does not have — as `code + params`.

    Distinct from `ReadRefused`, which is about stored data that can no longer be
    served: here nothing is wrong with what is stored, the caller asked for a
    part the panel cannot be built from. That is a different answer (422: fix
    your request, not 400/409: regenerate), and a route that told the two apart
    by inspecting the code would be a second list of codes drifting quietly out
    of step with this one.

    Subclasses ValueError for the same reason `ReadRefused` does: every existing
    `except ValueError` around the panel pipeline keeps catching it, so a caller
    that does not care about the code is unchanged.
    """

    def __init__(self, code: str, message: str, **params: str | int):
        super().__init__(message)
        self.code = code
        self.params: dict[str, str | int] = params


class ReadRefused(FenceAiError, ValueError):
    """A stored run cannot be read, as `code + params` rather than a sentence.

    User-visible text is rendered from the code by the reader's locale bundle
    (`error.<code>`); the message is the raw engine string, a diagnostic
    fallback only — never the thing a Hebrew reader is shown. Subclasses
    ValueError so the existing `except ValueError` at every read site keeps
    catching it, and so a caller that does not care about the code is unchanged.
    """

    def __init__(self, code: str, message: str, **params: str | int):
        super().__init__(message)
        self.code = code
        self.params: dict[str, str | int] = params
