"""ID helpers.

User-authored entities get random ids (stable once created, stored).
Generated strategy elements get content-derived ids (`post@run:station`) so identical
regeneration yields identical ids — but nothing may *reference* them across runs
(overrides anchor to topology coordinates instead, ADR-0004).
"""

from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def element_id(kind: str, run_ref: str, station_mm: int | tuple[int, int]) -> str:
    if isinstance(station_mm, tuple):
        return f"{kind}@{run_ref}:{station_mm[0]}-{station_mm[1]}"
    return f"{kind}@{run_ref}:{station_mm}"
