"""Tiny .env loader — no dependency, no magic.

Loads KEY=VALUE lines from a .env file in the working directory (or an explicit
path) into os.environ. Real environment variables always win: the file only
fills gaps, so `FENCEAI_AI=stub uv run ...` still overrides the file.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> dict[str, str]:
    """Returns the variables actually applied (for logging/tests)."""
    file = Path(path)
    applied: dict[str, str] = {}
    if not file.is_file():
        return applied
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied
