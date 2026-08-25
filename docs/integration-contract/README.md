# The boundary contract — our copy

**This is a second byte-identical copy of the contract**, not a variant. The other
lives in `fence-rag/docs/integration/`. Both teams hold one so that either can work
with the other unreachable — the same reason a bundled default snapshot ships in
this repo — and the hash is what makes them provably the same.

```bash
sha256sum -c contract.sha256      # must print: contract.md: OK
```

**FROZEN at v1.0.** Do not edit `contract.md` here or there. Changing a BINDING
item requires a ratified amendment: [`AMENDING.md`](AMENDING.md) carries the four
triggers and the five steps. A hash mismatch means a copy drifted — find the edit
rather than regenerating the hash.

Everything else about the boundary — the data model, the asks, the four rounds of
audit that produced v1.0 — stays in `fence-rag/docs/integration/`. Only the contract
and its amendment procedure are duplicated, because only they are the promise.
