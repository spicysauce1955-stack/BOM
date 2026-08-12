"""Which fence model a stretch of fence is built to.

A *choice* is a reference plus the option values chosen against it — never a
model. It is deliberately its own tiny module with no imports beyond pydantic:
`topology/model.py` and `project/model.py` both need to say "this fence is built
to that model", and neither may depend on the resolver, the catalog or the
knowledge AST that `fencemodel/model.py` pulls in.

`version_pin` is the difference between "build it the way we build it now" and
"build it the way run X built it". None follows the newest active version;
an integer freezes it, and keeps freezing it even after that version is retired
(`FenceModelLibrary.resolve`), because a stored run must stay reproducible.
"""

from __future__ import annotations

from pydantic import BaseModel


class FenceModelChoice(BaseModel):
    model_id: str
    version_pin: int | None = None
    # axis key -> chosen value. Inert until W3 reads PanelContext.options; carried
    # from here on so a run generated today records what was asked for.
    options: dict[str, str | int] = {}

    def key(self) -> tuple:
        """Deterministic identity for memoising resolution within one generation."""
        return (self.model_id, self.version_pin, tuple(sorted(self.options.items())))
