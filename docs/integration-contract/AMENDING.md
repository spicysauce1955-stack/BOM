# Amending the contract

```text
Governs:  contract.md, which is FROZEN at v1.0.
Holds in: both repositories. Byte-identical copies, verified by hash.
Rule:     the contract is never edited. An amendment produces a NEW version.
```

## Why there is a procedure at all

The contract went through six revisions in a single working session. Every one was
justified — measured evidence, a falsified premise, a defect — and the result was still
that neither team could point at a stable document and say *"this is what we are building
against."* Two of those revisions changed obligations while the other team was mid-review
of the previous ones.

So the fix is not fewer changes. It is that **changes land in batches, at a version, with
both sides' agreement, and never as a side effect of some other work.**

This is the same discipline the contract itself demands of knowledge: versions are
immutable, a consumer pins a hash, and a change produces a new object rather than mutating
the old one. It would be odd for the document mandating that to be the one thing edited in
place.

---

## 1 · The frozen copy

Both teams hold `contract.md` and `contract.sha256`, byte-identical.

```bash
sha256sum -c contract.sha256      # both lines must print OK
```

The manifest covers **`contract.md` and this file**. A procedure that protects a frozen
document while being itself unprotected can have its protection edited away silently —
which was true of this one until ratification, and is the kind of hole that only shows up
when you write down what you are signing.

**If that fails, stop.** Someone edited a frozen document, or the copies have drifted.
Neither side should build against an unverified contract, and the fix is to find which copy
moved rather than to regenerate the hash.

Both sides keep a copy rather than one side holding the original, for the same reason a
bundled default snapshot ships inside the Planning repo: each team can work with the other
unreachable, and the hash is what makes the two provably the same.

---

## 2 · When an amendment is admissible

Four triggers. Anything else is not an amendment.

| # | Trigger | Test |
|---|---|---|
| **A** | **Falsification** | Measured evidence contradicts a binding item. A document and page, or a file and line. All four rounds ran on this and it is the one that must never be obstructed. |
| **B** | **Unimplementable** | A binding item cannot be built as written. Requires the attempt, not the intuition — name the mechanism that fails. |
| **C** | **Scope change** | Something parked comes in. Gates, `Combination`, site materials, stock-length-constrains-layout, `soil_class`. Each is named in `where-we-stand.md` with what would reopen it. |
| **D** | **Defect** | The contract contradicts itself, or an obligation depends on something it does not define. |

### What is NOT an amendment

- **Registry additions.** New part types, warning codes, condition dimensions, source
  classes. The contract already says adding an entry is never a breaking change; that
  property is what lets the two teams move at different speeds, and routing it through
  ratification would destroy it.
- **Anything internal.** Pipeline shape, extraction strategy, storage, read models,
  curation workflow. If it does not change what crosses, it is not the contract's business.
- **Clarifying wording that changes no meaning.** File it as a note in the round's
  disposition. If you cannot tell whether the meaning changed, it changed — treat it as D.

---

## 3 · How an amendment is made

Five steps, and the first four change nothing.

**1 · File it.** `amendments/NNN-short-slug.md`, next number, either team:

```text
Amendment NNN
  Obligation     which BINDING item, by number
  Trigger        A falsification | B unimplementable | C scope | D defect
  Evidence       document + page, or file + line. Not an argument — a citation.
  Proposed text  the exact replacement wording
  Cost           what the other side has to change if this lands
  In-flight      what breaks for work already building against v1.0
```

**2 · It governs nothing.** The frozen contract still holds. Both teams keep building
against v1.0 while the amendment sits.

**3 · The other side dispositions it.** Accept / accept-modified / reject, with reasoning
in the same file. Same standard as every round so far: a gap per item, with the document
and page.

**4 · Batch.** Amendments accumulate. They are cut into a version together, not one at a
time — because a document that moves under a reviewer is the failure this procedure exists
to prevent.

**5 · Ratify and cut.** When both teams have recorded acceptance:

```bash
# both repos, identically:
#   1. apply the accepted text, bump the version, date it
#   2. sha256sum contract.md AMENDING.md > contract.sha256
#   3. commit both, one commit, message naming every amendment in the batch
#   4. verify the other repo's hash matches before either side builds on it
```

The amendment files stay. They are the reasoning, and the reasoning has been worth more
than the conclusions every round so far.

---

## 4 · When to cut a version

**Cut when a batch is ready and neither side is mid-review.** Not on a schedule, not per
amendment.

Two cases force a cut:

- **A trigger-A falsification of a binding item.** Someone is currently building against
  something measurably untrue. That is not batched; cut it.
- **A trigger-B item blocking work.** Waiting to batch it means waiting to build.

Everything else waits for the batch.

---

## 5 · What must not happen, and it is worth naming

**Editing `contract.md` as a side effect of other work.** This is the failure mode that
produced the procedure, and it does not feel like a violation while it is happening — it
feels like keeping the document current. The signal is the absence of an amendment file.
If you are changing a binding item and there is no `amendments/NNN`, stop.

**Regenerating the hash to make a verification failure go away.** The hash failing is the
mechanism working. Find the edit.

**Ratifying by inference.** *"They did not object"* is not acceptance. Both sides record
it, in writing, in the amendment file.

---

## 6 · A note for whoever picks this up in a later session

Assume you do not remember this document. The contract's header says FROZEN and points
here; that banner is the only thing standing between a good-faith improvement and six more
undocumented revisions.

Nothing here forbids changing the contract. It forbids changing it **quietly**. If a
binding item is wrong, the four triggers exist precisely so that saying so is cheap — every
one of the four rounds behind v1.0 was one side telling the other that something they wrote
was false, and every one of those rounds improved it.
