# Published Part inspection

Plane: **Engine** — see [00-overview.md](00-overview.md#three-planes).

The Knowledge tab exposes public Part definitions from the active source snapshot,
including drafts and retired definitions. `GET /api/knowledge/parts` returns `loaded`
and `snapshot_id`, the `definitions` (every published part, in every status) and the
typed `source_docs`, beside the judged `specs` (from **active** parts only), `defects`
and `inactive`. Visibility does not promote a Part or create a private FenceModel,
inventory item, or assembly binding.

Public Part versions accept positive integers and nonempty opaque strings. This
supports publisher content hashes without changing the private model version
scheme. Values, original strings, provenance, and source hash joins remain in the
typed receipt. The store keeps the typed `Snapshot` re-serialised, which
materializes schema defaults; unknown extension fields are not promised to survive
the existing typed loader. This is not a byte-preserving archive of the incoming
snapshot.

`published-parts.js` owns its own subtree, reads via the existing API, and receives
navigation, locale, and unit events through state.js. Source strings are escaped.
The read-only quantity formatter preserves public milli-unit precision instead
of using the geometry editor's integer-mm rounding. Evidence expands to typed
published JSON; direct PDF-page navigation is not implemented.

## Two Part families, one name

There are two `Part` types and nothing converts one into the other. The **private
library** — `fenceai.parts.model.Part` / `PartType` / `SpecField`, `version: int`,
`type` a plain key, served by `GET /api/parts` — is what fence models name and
generation resolves. The **published** types — `fenceai.knowledge.parts.Part` /
`PartType` / `SpecField`, `version: int | str`, `type` a `(namespace, key)` ref — are
the boundary contract's shapes, read only from the active snapshot.

## What `consume()` does

`knowledge/parts.py: consume()` runs inside the snapshot's `ingest`, beside parameter
expansion ([`knowledge-system.md`](knowledge-system.md#published-knowledge--the-snapshot)):

* it files each part's type by walking the published `part_types` parent chain to the
  shared spine — `post`, `post_cap`, `rail`, `bar`, `infill`, `reinforcement`,
  `bracket`, `fastener`, `anchor`, `gate_hardware`, plus the reserved, unimplemented
  `site_material`. A chain that ends anywhere else, or loops, is a defect;
* it skips any part whose `status` is not `active`, listing it in `inactive`;
* for each spec field of an active part, it checks the field's shape, joins its
  citations to `source_docs` by content hash, and judges it through the same §1.4
  source policy a parameter row gets;
* an admitted value becomes a `PublishedSpec`; a rejected or unjudgeable one becomes a
  gap; a payload contradicting its own schema becomes a `part_defects` line —
  authoring text, rendered escaped and LTR, never through the warning registry.

**Published spec values never reach generation or the BOM.** Every admitted spec also
emits a `published_spec_unapplied` gap that says so: nothing yet maps a published part
to a catalog product. Their only consumers are the counts on `GET` and
`POST /api/knowledge/snapshot` and this inspection route.

*The section below is a dated operations record of one import — not architecture. Its
snapshot id, counts, paths and open defect describe that day, not the system.*

## Emblem import — 2026-09-07

Imported fence-rag snapshot
`55bc6c769a933079f37e7b5795bd0042ee52a66d5beefe95c9a9d079dcc05bda`
from `/home/user/Workspace/fence-rag/workspace/snapshots/` into this checkout's
persistent `fenceai.db` through `POST /api/knowledge/snapshot`. All 24 typed Part
bodies matched after storage and retrieval. The three `emblem-noa22021705-*`
definitions remained drafts in the inactive list. They describe the pre-built
NOA drawing; exact SKU applicability remains unverified. Eight definitions match
"Emblem", including older family and SKU records. The snapshot carries no Models.

Preview: `http://localhost:8000`, the **Everything** view (`all` — a presentation
choice, not a role) → Knowledge → Published parts.
Search defaults to Emblem; `noa22021705` selects the three new drawing definitions.
The preview uses stub AI, the persistent database, and a detached local uvicorn
process. Port 8791 is an unrelated automated smoke server with a temporary DB.

Before import the active snapshot was `FIXTURE-not-a-real-snapshot`. A SQLite
backup, server log/PID, import receipt, browser check, and EN/HE screenshots are
under `/home/user/.local/state/fenceai-emblem/`. The import selects the new snapshot
for subsequent generation; stored runs retain their existing snapshot stamps.
No run was regenerated during this integration.

Validation actually run: 85 focused API/Part/locale tests, plus one Node-backed
precision test; frozen contract checksums passed. Browser checks exercised eight
Emblem matches, three drawing matches, exact mm/cm display, and Hebrew status.
The saved s17 project's generated canvas overlay raises a null-point error on
startup. Knowledge checks were repeated after clearing only the browser's
`state.result`; no saved project was changed. No full suite or broad browser
smoke was run by this integration task.
