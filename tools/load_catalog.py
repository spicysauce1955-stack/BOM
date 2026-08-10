"""Load a product catalog (and optional knowledge defaults) into the Fence AI DB.

    uv run python tools/load_catalog.py tools/catalogs/barrette.json --apply-knowledge

- Products are UPSERTED into the stored catalog (existing SKUs overwritten).
- With --apply-knowledge, each knowledge entry becomes a NEW ACTIVE VERSION of its
  object (previous active retired, normal versioning — nothing is deleted, and the
  change is previewable/revertible from the Knowledge tab like any other rule).
- Respects FENCEAI_DB / .env; defaults to ./fenceai.db. Idempotent: re-running
  with unchanged content skips knowledge versions whose active content matches.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fenceai.catalog.demo import demo_catalog  # noqa: E402
from fenceai.catalog.model import Product  # noqa: E402
from fenceai.core.env import load_dotenv  # noqa: E402
from fenceai.knowledge.demo import demo_knowledge  # noqa: E402
from fenceai.knowledge.model import KnowledgeVersion  # noqa: E402
from fenceai.store.db import Store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="catalog JSON file")
    parser.add_argument("--db", default=None, help="SQLite path (default: FENCEAI_DB or fenceai.db)")
    parser.add_argument("--apply-knowledge", action="store_true",
                        help="also activate the file's knowledge defaults (new versions)")
    args = parser.parse_args()

    import os
    load_dotenv()
    db = args.db or os.environ.get("FENCEAI_DB", "fenceai.db")
    data = json.loads(args.catalog.read_text(encoding="utf-8"))

    store = Store(db)
    catalog = store.load_catalog()
    if catalog is None:
        catalog = demo_catalog()
        print("seeded demo catalog (fresh database)")
    if not store.knowledge_base().versions:
        for v in demo_knowledge().versions:
            store.insert_knowledge_version(v, actor="seed")
        print("seeded demo knowledge (fresh database)")

    for raw in data.get("products", []):
        product = Product.model_validate(raw)
        verb = "updated" if product.sku in catalog.products else "added"
        catalog.products[product.sku] = product
        print(f"  product {verb}: {product.sku} — {product.name}")
    store.save_catalog(catalog, actor=f"load_catalog:{args.catalog.name}")

    if args.apply_knowledge:
        kb = store.knowledge_base()
        for raw in data.get("knowledge", []):
            object_id = raw["object_id"]
            current = next(
                (v for v in kb.versions if v.object_id == object_id and v.status == "active"),
                None,
            )
            version_no = store.next_version(object_id)
            candidate = KnowledgeVersion.model_validate(
                {**raw, "version": version_no, "status": "active",
                 "derived_from": [current.ref] if current else []}
            )
            if current is not None and current.actions == candidate.actions:
                print(f"  knowledge unchanged, skipped: {object_id} (v{current.version})")
                continue
            store.replace_active_version(candidate, actor=f"load_catalog:{args.catalog.name}")
            print(f"  knowledge activated: {candidate.ref} — {candidate.title}")
    elif data.get("knowledge"):
        print(f"  ({len(data['knowledge'])} knowledge defaults in file — rerun with --apply-knowledge to activate)")

    print(f"done → {db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
