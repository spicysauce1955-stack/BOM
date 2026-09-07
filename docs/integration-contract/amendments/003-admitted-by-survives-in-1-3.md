# Amendment 003 — `admitted_by` survives amendment 001 in §1.3's row annotation

```text
Obligation   §1.3 (ParameterTable, the rows[] block) against §1.1 and §1.4
Trigger      D — defect. The contract contradicts itself, in the same way and about
             the same field that amendment 001 was accepted to fix.
Filed by     Planning & BOM, 2026-08-30, while building item 6 against §1.4
Status       FILED. Governs nothing until ratified (AMENDING.md §3 step 2).
```

## The gap

Amendment 001 found `admitted_by` bound to the published row in obligation 6, and
was accepted in full: this platform does not select a winner, and `admitted_by` is
an output of a run. **The same clause survives in a third place.**

**`contract.md:250`, inside `ParameterTable.rows[]`:**

```text
  rows [ { conditions       { exposure_category: "C", hvhz: false }
           condition_basis  stated | assumed
           value            Quantity | Token    conforming to value_type
           provenance       Provenance          class, level, admitted_by, cites
```

**`contract.md:71`, §1.1, the `Provenance` definition it points at:**

```text
Provenance   { cites: [SourceRef], source_class, curation_level,
               version_status: active | superseded | unknown }
             # admitted_by is NOT here — it is an output of a RUN, see §1.4
```

The annotation on `rows[].provenance` enumerates the fields of a type whose own
definition, nine lines earlier in the same document, says one of those four fields is
not among them. Read left to right, §1.3 tells an implementer that a published
`ParameterTable` row carries `admitted_by`; §1.1 and §1.4 tell them it cannot.

## Why this is not clarifying wording

`AMENDING.md` §2: *"If you cannot tell whether the meaning changed, it changed."* Here
it plainly does. This is the exact three-way defect 001's own evidence table set out —
who applies the policy, where `admitted_by` is recorded, and whether a winner exists at
publish — reproduced in the type annotation that a builder of `ParameterTable` reads
first, because §1.3 is where `ParameterTable` is specified and §1.1 is not.

**It is not hypothetical, and it is not the other side's problem.** Planning built
`fenceai/knowledge/parameters.py` field-for-field from §1.3. The `Provenance` model
there carries four fields and a test (`tests/knowledge/test_parameters.py:129-133`)
asserts `"admitted_by" not in Provenance.model_fields`, citing §1.1. That test exists
because a previous reader of this repo had to choose between two sentences in one
frozen document and wrote down which one they picked. A contract that requires a
consumer to pick has not decided the thing it exists to decide.

**Why it survived 001.** 001's disposition named the cause: *"When §1.4 changed in v0.4
we rewrote the BINDING block and never checked whether any obligation restated the old
rule."* The check that followed covered obligations. It did not cover **type
annotations inside §1–2**, which is where this one was.

## Proposed text

`contract.md:250`, replacing the annotation only. The field list is unchanged; four
words come off it.

```text
           provenance       Provenance          class, level, status, cites
```

`admitted_by` is removed and `status` added, because `version_status` is the fourth
field `Provenance` actually carries and amendment 001 made it a per-row honesty duty
under obligation 6. The annotation then enumerates exactly the type it names.

## Also worth checking in the same pass, and not proposed here

We swept `contract.md` for other survivals of the pre-v0.4 wording and found none —
`admitted_by` appears six times, and the other five are correct (§1.1's exclusion note,
§1.4's BINDING rank sentence, §1.4's v0.4 delta paragraph, the superseded-wording block
kept deliberately for legibility, and obligation 6 as amended by 001). This is the last
one. We are stating the sweep rather than only the find, so the disposition does not
have to repeat it.

## Cost if this lands

**Knowledge:** none. No published shape changes; `3ae88642` already publishes
`Provenance` without `admitted_by`, correctly.

**Planning:** none. Already built to §1.1, with the test that says so.

This is a documentation-only correction to a frozen document, which is exactly the
category `AMENDING.md` exists to route rather than to allow as a quiet edit.

## In-flight

Nothing. Both implementations already follow §1.1; only a future reader is at risk, and
they are the reason to fix it.

---

## Disposition — Knowledge Platform

**ACCEPT, as proposed. 2026-08-30.**

Read left to right, `contract.md:250` and `:71` do give an implementer two
sentences to pick between in one frozen document, which is exactly what
001 was accepted to close everywhere obligation 6 restated the old rule —
this is the one occurrence that sweep missed, in a type annotation rather
than an obligation. `status` for `admitted_by` is the correct swap; it's
the field `Provenance` actually carries.

Cost as stated: zero. `3ae88642` already publishes `Provenance` without
`admitted_by`, so nothing we've shipped moves.
