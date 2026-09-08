# Amendment 008 — per-value provenance on authored geometry

```text
Status:     FILED PROPOSAL ONLY — no ratification, no changed obligation.
Against:    FROZEN contract v1.3, 2026-08-31.
Filed:      2026-09-06, Knowledge-side implementation proposal.
Posted:     2026-09-08, conversation.md T50 §1 — formally handed to Planning in the
            thread. Until that date this file had reached Planning only because they
            copied a directory (T49 §9b), which they correctly declined to treat as a
            filing. The disposition clock starts at T50, not at Filed.
Obligation: 6; §1.1 Provenance; delegated geometry definitions in knowledge-datamodel.md §3.
Trigger:    D — an obligation depends on an undefined numeric-owner association.
```

The frozen contract continues to govern. Neither this filing nor its synthetic example authorizes publication. Both teams' dispositions are pending. No frozen file or checksum was edited.

## Evidence

1. Frozen contract §1.1 (lines 102–104) defines Provenance with cites, source_class, curation_level and version_status. It explicitly excludes admitted_by, which is run output. Obligation 6 (lines 605–613) extends classification to every published value, not just parameter rows.
2. The delegated datamodel §2.4 says Provenance attaches to Member dimensions and other numeric values; its Joint, Member, Placement and PartRequirement definitions do not define a serialized association for multiple values with different sources. SpecField and ParameterTable rows already have an explicit provenance owner and remain unchanged.
3. The authored-model preflight previously returned only deepcopy(model) after receiving a private field_evidence map. That map held citations only, omitted the required classifications and did not cross with the returned model. This failure is reproduced and recorded in `workspace/reports/emblem-schema-review.md`. The unsafe success path is now refused as `consumer_numeric_provenance_mapping_unresolved`.
4. Actual consumer private parsers do not preserve unknown owner fields; the independently reproduced PostSlot example in `workspace/reports/emblem-public-adapter-boundary.md` demonstrates why a permissive parse or producer-side sidecar is no proof of preserved executable meaning.

## Exact proposed addition

Add the following binding paragraph to the delegated definition of supported numeric owners, referenced by obligation 6 without changing Quantity or Provenance:

> **Per-field provenance on authored geometry.** A Joint, Member, Placement, InfillSpec, PartRequirement, FixingRule or HeightSupport that carries an explicitly authored numeric semantic value carries `field_provenance: {<relative JSON pointer>: Provenance}`. Each pointer starts at that owner and targets the complete declared semantic value, including a complete Quantity where applicable. It never targets only amount_milli, raw lexemes, a schema identifier or provenance metadata. The consumer's supported schema declares the legal target paths and target value kinds. Every present supported numeric value must have exactly one association; dangling, duplicate, wrong-kind and undeclared targets are refused. No provenance record supplies a missing value or authorizes a consumer default.
>
> The map is part of the published, hashed model and must survive consumer ingestion. It carries the frozen Provenance fields only; admitted_by is computed on the run. A producer must not synthesize classifications from a human-review flag or choose a winning source-policy row at publication. Existing SpecField and ParameterTable row provenance remain unchanged and are not duplicated into this map.
>
> An unknown/null value retains its existing owning-field meaning and required Gap behavior. It is never converted to zero. Map absence is not permission to invoke a private default. Unsupported owner fields and variants remain explicit refusals until implemented; this rule alone does not authorize their semantics.

The exact target registry and round-trip behavior must be dispositioned and tested on both sides before acceptance. This filing proposes a representation; it does not claim that a literal JSON pointer vocabulary is already a registry addition authorized by the current contract.

## Quantified initial scope

For the bounded two-rail, one-board-pattern panel with one post requirement, one cap and two separately addressed U-channel fixing requirements:

| Owner | Proposed numeric targets | Potential target count |
| --- | --- | ---: |
| Four Joint owners: two rails, one Member, one post | channel_depth, insertion_margin, shared_host_gap | 12 |
| One Member | base_engagement, top_engagement, gap_after, face_offset | 4 |
| Two FromBottom/FromTop placements | offset | 2 |
| Seven PartRequirements: two rails, board, post, cap, two channels | qty, overlap | 14 |
| Two FixingRules | qty_per_basis | 2 |
| One InfillSpec | edge_margin | 1 |
| One single-height Discrete HeightSupport | heights/0 | 1 |
| **Total potential addresses for this bounded shape** | | **36** |

This counts typed association locations, **not 36 missing dimensions or manufacturer claims**. Null optional values are not numeric readings; unsupported post-host/shared-host behavior remains separately blocked. Quantity defaults such as one board per fitted repeat are authored values and need explicit association; a kit's board inventory must not become per-repeat qty. Continuous/distributed placement, multiple heights and variants require explicit target-registry extensions and coverage tests before supported use. Joint.kind, fitting policy tokens and length-rule names remain separately authored semantic choices; numeric provenance does not establish those choices by itself.

## Concrete review object

`workspace/reports/authored-geometry-provenance-example.json` contains a complete hypothetical Joint with separate provenance for a synthetic 25 mm depth and synthetic 1 mm margin, plus matching synthetic source_refs/source_docs. Its wrapper explicitly says not agreed, not publishable, not manufacturer evidence. Both fields are honestly ai_proposal, curation level 0, version_status unknown. No human review, manufacturer datum, source-policy admission or physical fit is claimed.

The proposed map lives on the Joint, not inside Quantity. Different owners may use the same representation without forcing all fields to share one classification. A JSON-pointer index can distinguish differently sourced discrete heights without inventing a wrapper around each Quantity.

## Cost and implementation obligations

Knowledge: resolve reviewed value records into complete classified owner maps; validate typed target coverage/source closure; hash those maps with the model and referenced Parts; preserve the unchanged original source readings.

Planning: preserve the maps through a lossless public adapter and stored run/model representation; apply source policy per addressed value at run time; refuse unsupported targets, missing coverage and lossy unknown-field parsing; expose resulting admitted_by on run output only.

Both: test positive round trips using synthetic evidence, and refusal controls for dropped maps, absent targets, duplicate associations, malformed pointers, incorrect value kinds, missing classifications, unsupported defaults, null-to-zero conversion and unresolvable SourceRefs. Real Emblem publication additionally needs manufacturer evidence and implemented post-host/board-fit semantics; this amendment does not waive those requirements.

## In-flight impact

No current Part or ParameterTable serialization changes. Published models remain empty under the current implementation. Existing private Emblem candidates stay private. No application may interpret this pending proposal as an accepted alternative wire format.

## What must be on the table when this is judged

Recorded 2026-09-08 with the posting, at Planning's request in T49 §9b — *"Neither of
us should disposition 008 without §1 on the table beside it."* Agreed, and named here
so the condition survives in the file rather than only in the thread. Three items, and
the third is new since this amendment was filed:

1. **T49 §1 — the consumer floors what this map would certify.** `Mm = int` on the
   Planning side, and `contract.md:112-117` requires a multiplied published value to be
   consumed in thousandths and rounded only at its output. A `field_provenance` entry
   that classifies a 88.9 mm centreline is a promise about a number the reader currently
   stores as 89. That does not make the map wrong, but it decides what the map is
   *for*: certifying a value the consumer then re-rounds is a weaker guarantee than
   either side has been describing, and both should say which they mean before
   accepting the representation.

2. **The map is per-value, and the rounding is per-value too.** Every one of the 36
   proposed target addresses in the scope table above is a place where a classification
   and a conversion meet. If a target's value survives ingestion but its precision does
   not, the association is intact and the guarantee is not. Whatever this amendment says
   about "must survive consumer ingestion" has to mean the value as well as the record.

3. **C17, and the measurement in T50 §3.** `max_span_mm` is published today inside
   `footing_schedule`'s `paired` value and is converted to whole millimetres at
   `parameters.py:327`. That is the same class of loss as item 1, already live in
   published data, and it is evidence about how a "must survive ingestion" clause
   actually behaves in this pair of systems. It should inform the wording here rather
   than be settled separately.

## Dispositions

- Knowledge team acceptance: **PENDING**. Filing is not acceptance or a fabricated reviewer decision. Posting it into the thread (T50) is not acceptance either.
- Planning team disposition: **PENDING** — accept / accept-modified / reject with reasoning. Formally handed over 2026-09-08 (T50 §1); before that date there was nothing for this side to disposition.
- Ratification/version cut: **NOT PERFORMED**. Follow AMENDING.md steps 3–5 if accepted; do not update frozen files or hashes as a side effect of implementation.
