# The boundary contract — our copy

**This is a second byte-identical copy of the contract**, not a variant. The other
lives in `fence-rag/docs/integration/`. Both teams hold one so that either can work
with the other unreachable — the same reason a bundled default snapshot ships in
this repo — and the hash is what makes them provably the same.

```bash
# run from THIS directory — the paths inside the file are relative to it
sha256sum -c contract.sha256      # must print: contract.md: OK
```

**FROZEN at v1.3.** Do not edit `contract.md` here or there. Changing a BINDING
item requires a ratified amendment: [`AMENDING.md`](AMENDING.md) carries the four
triggers and the five steps. A hash mismatch means a copy drifted — find the edit
rather than regenerating the hash.

[`amendments/`](amendments/) holds the filed amendments the version header at the
top of `contract.md` cites by number — the record of how v1.0 became v1.3, plus
`CANDIDATES.md`, the waiting room for items not yet cut into a version. Nothing
in it governs anything until ratified.

[`conversation.md`](conversation.md) is the append-only thread between the two
teams: every amendment above was filed, argued, and dispositioned in a numbered
turn there, and the version header cites those turns. It is copied between both
repos like the contract is — append to it, never rewrite it, and copy the whole
file across rather than merging halves.

Everything else about the boundary — the data model, the asks, the four rounds of
audit that produced it — stays in `fence-rag/docs/integration/`. The contract, its
amendment procedure, the amendments themselves and the thread are duplicated,
because those are the promise and the record of how it changed; the rest is theirs.
