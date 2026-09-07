# Amendment 001 — obligation 6 carries a clause §1.4 superseded

```text
Obligation   6 (§3.1)
Trigger      D — defect. The contract contradicts itself.
Filed by     Knowledge Platform, 2026-08-25, on the cold second pass before signature
Status       ACCEPTED IN FULL and applied. Cut as contract v1.1, 2026-08-25.
             v1.0 was never ratified. Ratification moves to audit/11.
```

## Evidence — the contract against itself

**Obligation 6, `contract.md` §3.1, final clause:**

> …Nothing reaches level 2 without a person having compared it to the source image, **and
> resolution honours the source policy, recording `admitted_by` on the winner.**

**§1.4, `contract.md`, the paragraph marked BINDING — CHANGED IN v0.4:**

> **Planning** applies the source policy, not this platform, and records `admitted_by`
> **on the run** rather than on the published row. […] a snapshot carries **every
> admissible row including the ones a policy will reject** […]
>
> *(Superseded wording, kept so the change is legible: resolution honoured the policy and
> the winning row recorded `admitted_by`…)*

The clause still binding in obligation 6 **is** the wording §1.4 marks as superseded, and
it contradicts §1.4 three separate ways:

| | Obligation 6 binds this platform to | §1.4 binds |
|---|---|---|
| Who applies the policy | this platform, at resolution | **Planning**, at run time |
| Where `admitted_by` is recorded | on the winning row | **on the run** |
| Whether a winner exists at publish | yes — "the winner" | **no** — every admissible row crosses, including rejected ones |

The third is the one that cannot be reconciled by reading charitably. `admitted_by` on
"the winner" presupposes that publishing selects one row per point; §1.4 makes selection a
property of a planning run and requires the snapshot to carry the losers deliberately, so
a decision graph can say *"a spec sheet was inadmissible for a structural parameter"*.
There is no winner at publish time for this platform to stamp.

"Resolution" is unambiguous here: §1.5 lists Resolution as this platform's API surface, and
obligation 6 sits under *"What Planning relies on this platform for."*

## Why this is not clarifying wording

`AMENDING.md` §2: *"If you cannot tell whether the meaning changed, it changed — treat it
as D."* Here it plainly changed. Enforced as written, obligation 6 requires this platform
to build the policy evaluator that §1.4 assigns to Planning, and to publish only winners —
which would delete exactly the visibility that v0.4 delta item 2 was accepted to create.

This is also not a disagreement. Both teams already agreed the substance twice, in
`06-review-of-v0.4.md` §2 and `07-delta-disposition.md` §2. Only the obligation text was
not updated when §1.4 was.

## Proposed text

Obligation 6, replacing the final clause:

```text
6. Every published value carries an honest `source_class`, `curation_level` and
   `version_status` — not only every parameter row. A rail length has the same
   admissibility problem as a footing depth. Nothing reaches level 2 without a person
   having compared it to the source image. This platform does not apply the source
   policy and does not select a winner: it publishes every row it holds, honestly
   classified, and Planning applies the policy at run time per §1.4.
```

`version_status` is added because §1.4's second BINDING paragraph makes it a policy axis
and obligation 6 is where the per-row honesty duties are listed; without it, the axis is
binding on Planning to use and on nobody to supply. If that reads as widening the
amendment beyond the defect, drop it and we will file it separately — we would rather the
scope argument than the silent hole.

## Cost if this lands

**Planning:** none. It is the behaviour §1.4 already binds and `07-delta-disposition.md`
§2 already accepted.

**Knowledge:** none, and it removes work — no policy evaluator on this side.

## In-flight

Nothing. No published snapshot exists on either side, so no work is building against the
superseded reading. This is the cheapest possible moment for it.

## Disposition — Planning & BOM, 2026-08-25

**ACCEPTED IN FULL, including `version_status`. Cut as v1.1.**

**The defect is real and it is ours.** When §1.4 changed in v0.4 we rewrote the BINDING
block and never checked whether any obligation restated the old rule. Obligation 6 did,
verbatim. Your three-way table is exactly right, and the third row is the one that settles
it: `admitted_by` on *"the winner"* presupposes a selection that v0.4 deliberately moved to
run time. There is no winner at publish for this platform to stamp.

**On `version_status` — keep it in, and thank you for flagging it rather than sliding it
in.** You are right that without it the axis is binding on Planning to use and on nobody to
supply, and obligation 6 is where per-row honesty duties live. It is the same clause, not
an adjacent one. Filing it separately would have been more procedurally pure and less
correct.

**Why we cut v1.1 rather than ratifying v1.0 with 001 pending.** You declined to make that
choice unilaterally and you were right to. Signing v1.0 would mean both sides putting their
name to a document that binds this platform to build a policy evaluator both teams have
twice agreed it should not build. That is not a reservation, it is a known-false promise,
and *"documented"* does not fix it. Cost of the alternative: nothing. No snapshot exists on
either side, nothing is in flight, and you named it as the cheapest possible moment.

**One gap in AMENDING.md this exposed**, fixed alongside: the procedure was written for
amendments filed against a *ratified* version and said nothing about one filed against an
unratified freeze. §3a now covers it — an amendment filed before ratification is cut
immediately rather than batched, because there is no in-flight work to protect and nothing
to be gained from signing a version both sides intend to supersede.

**Status:** accepted, applied, `contract.md` is v1.1. Ratification moves to
`audit/11-ratification-v1.1.md`.
