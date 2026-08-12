from __future__ import annotations


class FenceAiError(Exception):
    """Base class for domain errors."""


class GenerationFailure(FenceAiError):
    """A hard constraint cannot be satisfied and no authorized exception exists.

    Distinct from a Conflict (which is surfaced but survivable) — see knowledge-system.md.
    """

    def __init__(self, message: str, *, constraint_refs: list[str] | None = None):
        super().__init__(message)
        self.constraint_refs = constraint_refs or []


class InvalidTopology(FenceAiError):
    pass


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
