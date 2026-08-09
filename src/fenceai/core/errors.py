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
