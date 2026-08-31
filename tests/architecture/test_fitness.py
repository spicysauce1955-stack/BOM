"""Architecture fitness — the class of drift, rather than one instance of it.

Backend audit §5. Every finding it raised was a fact that had quietly stopped
being true: a doc counting 47 routes over a 51-route app, a layering rule kept by
habit, a table list nobody re-read. Each was fixed by hand and would have drifted
again by the next arc, because nothing was watching.

These tests watch. They assert STRUCTURE, never behaviour, so they cost nothing
to run and fail for exactly one reason: something moved and a statement about the
system did not move with it.

Deliberately not a lint pass. Each test below encodes a rule this project argued
itself into — the layering in `docs/architecture/04-backend.md`, ADR-0009's "no
AI inside deterministic computation", CLAUDE.md's read-model rule — and the
failure message says which.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "fenceai"
DOCS = Path(__file__).resolve().parents[2] / "docs" / "architecture"

# Everything that is NOT a delivery mechanism. The rules below are about what
# these may depend on; `api` and `web` are the outside and may depend on them.
DOMAIN = (
    "catalog", "core", "decisions", "demand", "fencemodel", "fulfillment",
    "knowledge", "learning", "parts", "project", "report", "strategy", "topology",
)


def _modules(package: str) -> list[Path]:
    return sorted((SRC / package).rglob("*.py"))


def _imports(path: Path) -> set[str]:
    """Every `fenceai.*` module this one imports, dotted and un-truncated.

    Full paths rather than top-level packages, because one of the rules below
    turns on a SUBMODULE: a domain module may name the shape of an AI record and
    may not reach an AI port.
    """
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        out |= {n for n in names if n.startswith("fenceai.")}
    return out


def _packages(path: Path) -> set[str]:
    return {name.split(".")[1] for name in _imports(path)}


# --- layering ----------------------------------------------------------------

def test_the_domain_does_not_import_the_delivery_mechanism():
    """`api` is a delivery mechanism and `web` is a folder of assets. A domain
    module importing either is the dependency that makes the domain untestable
    without a database and a client — which is the property
    `docs/architecture/04-backend.md` opens by claiming."""
    offenders = [
        f"{path.relative_to(SRC)} imports fenceai.{bad}"
        for package in DOMAIN for path in _modules(package)
        for bad in sorted(_packages(path) & {"api", "web"})
    ]
    assert not offenders, offenders


def test_no_domain_module_imports_the_store():
    """Persistence is the caller's business. A domain module that loaded its own
    data would decide WHICH data, and `generate()` would stop being a pure
    function of its arguments (ADR-0004)."""
    offenders = [
        f"{path.relative_to(SRC)} imports fenceai.store"
        for package in DOMAIN for path in _modules(package)
        if "store" in _packages(path)
    ]
    assert not offenders, offenders


# A domain module may name the SHAPE of an AI result and may not reach for the
# thing that produces one. `ai/records.py` is the vocabulary — `InterpretationRecord`
# is what an annotation stores, and `project/model.py` legitimately holds a list
# of them. `ai/ports.py` is the protocol, `ai/stub.py` and `ai/claude.py` are the
# adapters, and a domain module reaching any of those has put a model inside a
# computation that must be reproducible for ever.
_AI_BEHAVIOUR = ("fenceai.ai.ports", "fenceai.ai.stub", "fenceai.ai.claude")


def test_no_ai_inside_deterministic_computation():
    """ADR-0009 and CLAUDE.md: AI sits behind the ports in `fenceai/ai/`, and the
    whole system works offline with the stub. Only the composition root wires
    them, and only a route calls one."""
    offenders = [
        f"{path.relative_to(SRC)} imports {bad}"
        for package in DOMAIN for path in _modules(package)
        for bad in sorted(m for m in _imports(path) if m.startswith(_AI_BEHAVIOUR))
    ]
    assert not offenders, offenders


def test_a_read_model_never_reaches_for_the_things_that_decide():
    """"Read models are derived, never stored" (foundation §15) — and a read
    model that imported the generator could re-decide rather than re-read. The
    report package takes what it is given."""
    offenders = [
        f"{path.relative_to(SRC)} imports fenceai.{bad}"
        for path in _modules("report")
        for bad in sorted(_packages(path) & {"api", "store", "ai"})
    ]
    assert not offenders, offenders


# --- inventories: a statement about the system, kept true ---------------------

def _route_paths() -> set[str]:
    from fenceai.api.app import app
    return {r.path for r in app.routes
            if getattr(r, "methods", None) and str(r.path).startswith("/api")}


def _route_count() -> int:
    """METHOD + path pairs, which is what the doc has always counted: `GET/PUT
    /catalog/products` is two routes on one path, and the table writes it as one
    row. Counting unique paths instead made the doc look wrong when it was
    right — the first version of this test did exactly that."""
    from fenceai.api.app import app
    return sum(
        len({m for m in r.methods if m not in ("HEAD", "OPTIONS")})
        for r in app.routes
        if getattr(r, "methods", None) and str(r.path).startswith("/api")
    )


def test_the_doc_counts_the_routes_the_app_actually_has():
    """It said 47 while the app served 51 — and the number is the first thing a
    reader trusts. Counted, so it cannot drift again."""
    doc = (DOCS / "04-backend.md").read_text()
    claimed = int(re.search(r"^(\d+) routes\.", doc, re.M).group(1))
    assert claimed == _route_count(), (
        f"the doc says {claimed} routes and the app serves {_route_count()}")


def test_every_route_the_app_serves_is_in_the_doc_table():
    """A route nobody wrote down is a route nobody reviews. The table groups by
    what a route is FOR, so the test asks only that the path appears — the
    grouping stays a human judgement."""
    doc = (DOCS / "04-backend.md").read_text()
    missing = []
    for path in sorted(_route_paths()):
        # the table writes paths without the /api prefix and with {id} for the
        # resource's own id, so compare on the distinctive tail segments
        tail = [seg for seg in path.split("/") if seg and not seg.startswith("{")
                and seg != "api"]
        if tail and not all(seg in doc for seg in tail):
            missing.append(path)
    assert not missing, missing


def test_the_doc_counts_the_tables_the_store_actually_creates():
    from fenceai.store import db
    tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", db._SCHEMA))
    doc = (DOCS / "04-backend.md").read_text()
    claimed = re.search(r"(\w+) tables — ", doc)
    words = {"Eight": 8, "Nine": 9, "Ten": 10, "Eleven": 11, "Twelve": 12,
             "Thirteen": 13, "Fourteen": 14, "Fifteen": 15, "Sixteen": 16}
    assert claimed, "the backend doc no longer states a table count"
    assert words.get(claimed.group(1)) == len(tables), (
        f"the doc says {claimed.group(1)} tables and the schema creates "
        f"{len(tables)}: {sorted(tables)}")


def test_every_table_is_named_in_the_doc():
    from fenceai.store import db
    tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", db._SCHEMA))
    doc = (DOCS / "04-backend.md").read_text()
    assert not [t for t in sorted(tables) if t not in doc]


def test_every_ai_port_has_a_stub():
    """The stub is what keeps the whole system working offline (CLAUDE.md). A
    port with no stub implementation is a feature that needs a network.

    Each port is matched to a stub that actually CONFORMS to it — every method
    the protocol declares, present and callable on the stub class. It used to
    compare two COUNTS, `len(implemented) >= len(protocols)`, which any class
    whose name begins with "Stub" satisfies: adding a port with no stub beside a
    `class StubSomethingElse:` that implements nothing left this green, and the
    system it certifies as offline-capable would raise at the first call.
    """
    from fenceai.ai import ports, stub

    # `Protocol` itself is imported into that module; it is the mechanism, not a
    # port, and counting it made this test assert one port too many.
    protocols = {name: getattr(ports, name) for name in dir(ports)
                 if name[0].isupper() and name != "Protocol"
                 and hasattr(getattr(ports, name), "__protocol_attrs__")}
    assert protocols, "no ports found — this test has stopped looking at anything"
    stubs = {name: obj for name in dir(stub)
             if name.startswith("Stub") and isinstance(obj := getattr(stub, name), type)}
    assert stubs, "no stubs found — this test has stopped looking at anything"

    def conforms(candidate: type, protocol) -> bool:
        for attr in protocol.__protocol_attrs__:
            if not hasattr(candidate, attr):
                return False
            # ...and a method must be a method: the right NAME of the wrong kind
            # is not an implementation either
            if callable(getattr(protocol, attr, None)) and \
                    not callable(getattr(candidate, attr)):
                return False
        return True

    unstubbed = {name: sorted(protocol.__protocol_attrs__)
                 for name, protocol in protocols.items()
                 if not any(conforms(c, protocol) for c in stubs.values())}
    assert not unstubbed, (
        f"no stub implements these ports: {unstubbed}. "
        f"The stubs that exist are {sorted(stubs)} — a name is not an "
        f"implementation.")
