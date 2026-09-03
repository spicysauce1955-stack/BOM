"""Item 7 — `Provenance` on a `SpecField`, and the `source_docs` join.

Obligation 6's other half. The parameter side of it has been live since
`knowledge/parameters.py` learned to judge a row's citations; this is the same
mechanism applied to the other place a number read off a page arrives — a
`SpecField` inside a published `Part` (`knowledge-datamodel.md` §2.4: *"a
Chesterfield rail length is `derived`, marketing-grade OCR, or PE-sealed
depending on which of the eleven documents it came from — exactly the same
admissibility problem as a parameter row"*).

**What this module's tests are about, and what they deliberately are not.** They
are about a published spec value being JUDGED (§1.4), JOINED to the documents
behind it (§1.2.1), and reported honestly where this engine cannot yet act on
it. They are not about the value reaching a bill of materials: nothing in this
repo can say which catalog product `shared/bt-rail-pr-3rail-white` is, and
inventing that mapping here would be the fourth instance of the pattern
`conversation.md` T42 §5 names — a private convenience standing in for an
agreement nobody made. Every admitted value therefore reports
`published_spec_unapplied` against us, which is what `test_every_admitted_value_
reports_that_nothing_can_apply_it_yet` pins.
"""

from __future__ import annotations

from fenceai.core.dates import Date
from fenceai.core.gaps import SourceRef
from fenceai.knowledge.parameters import Provenance, Quantity, Token
from fenceai.knowledge.parts import (
    Part, PartType, PartTypeRef, SpecField, consume, task_for,
)
from fenceai.knowledge.source_docs import SourceDoc
from fenceai.knowledge.source_policy import SHIPPED_DEFAULT, SourcePolicyRow

MANUAL = "aa" * 32
SECOND = "bb" * 32
UNKNOWN = "cc" * 32
INSTALL = "manufacturer_installation_instruction"


def _docs(*docs: SourceDoc) -> dict[str, SourceDoc]:
    return {d.content_hash: d for d in docs}


def _doc(content_hash: str = MANUAL, source_class: str = INSTALL,
         **kw) -> SourceDoc:
    return SourceDoc(content_hash=content_hash, source_class=source_class, **kw)


def _length(*, cites: tuple[str, ...] = (MANUAL,), source_class: str = INSTALL,
            curation_level: int = 0, key: str = "nominal_length_mm",
            agree: str = "==", value=None) -> SpecField:
    """The real published shape: `16 foot lengths` as a `Quantity` (T42/T43)."""
    if value is None:
        value = Quantity(amount_milli=4876800, unit="mm",
                         value_raw=["16 foot lengths"])
    return SpecField(
        key=key, agree=agree, value=value,
        provenance=Provenance(
            cites=[SourceRef(id=f"ref-{h[:4]}", belongs_to=h) for h in cites],
            source_class=source_class, curation_level=curation_level),
    )


def _rail(*spec: SpecField, part_id: str = "shared/bt-rail-pr-3rail-white",
          type_key: str = "rail", namespace: str = "shared",
          status: str = "active") -> Part:
    return Part(id=part_id, status=status, spec=list(spec),
                type=PartTypeRef(key=type_key, namespace=namespace))


def _consume(*parts: Part, part_types: list[PartType] | None = None,
             docs: dict[str, SourceDoc] | None = None,
             policy: list[SourcePolicyRow] | None = None):
    return consume(list(parts), part_types or [],
                   docs=_docs(_doc()) if docs is None else docs,
                   policy=SHIPPED_DEFAULT if policy is None else policy)


# -- the verdict ----------------------------------------------------------------

def test_a_published_dimension_is_judged_for_the_component_dimension_task():
    """§1.4 is applied by the PLANNER, and only the planner knows the task. A
    `SpecField` carries no task of its own, so choosing one is ours: a
    `Quantity` on a part is a component dimension, which is the row the shipped
    default table already has for exactly this ("Component dimension | …
    Install instruction 4 …", and 3 after the revision)."""
    out = _consume(_rail(_length()))

    assert len(out.specs) == 1
    spec = out.specs[0]
    assert spec.task == "component_dimension"
    assert spec.admitted_by is not None
    assert spec.admitted_by.rank == 3
    assert spec.admitted_by.source_class == INSTALL
    assert spec.value.amount_milli == 4876800
    assert spec.value.value_raw == ["16 foot lengths"]


def test_a_colour_is_judged_as_a_product_description_not_a_dimension():
    """The case that made `Quantity | Token` the right shape (T42 §2): a colour
    is not a dimension, and judging it against the dimension row would hold a
    brochure's word for a colour to the bar for a measurement."""
    colour = _length(key="colour", value=Token(key="sierra_blend",
                                                value_raw=["Sierra Blend"]))
    out = _consume(_rail(colour))

    assert task_for(colour) == "product_description"
    assert [s.task for s in out.specs] == ["product_description"]


def test_a_source_the_policy_refuses_produces_a_gap_and_no_value():
    """The refusal is the point of the mechanism, not an edge of it: a
    marketing-grade reading of a rail's length is inadmissible for a component
    dimension, and the gap has to name the part and the field so somebody can
    go and find a better document."""
    out = _consume(_rail(_length(source_class="marketing")),
                    docs=_docs(_doc(source_class="marketing")))

    assert out.specs == []
    refusals = [g for g in out.gaps if g.because.code == "source_inadmissible"]
    assert len(refusals) == 1
    gap = refusals[0]
    assert gap.because.params["part"] == "shared/bt-rail-pr-3rail-white"
    assert gap.because.params["parameter"] == "nominal_length_mm"
    assert gap.closes_by == "knowledge"


def test_a_reading_below_the_curation_bar_says_so_rather_than_refusing_outright():
    """Two codes because they send a person to different work — the distinction
    `explain_rejection` exists to keep. Reachable only under an operator's own
    policy: the shipped default sets `min_curation: 0` on every
    `component_dimension` row, so this is a table an operator edited."""
    strict = [SourcePolicyRow(task="component_dimension", source_class=INSTALL,
                              admissible=True, rank=3, min_curation=2)]
    out = _consume(_rail(_length()), policy=strict)

    assert out.specs == []
    assert [g.because.code for g in out.gaps] == ["source_below_min_curation"]


def test_a_source_class_this_policy_has_no_row_for_is_not_judged():
    """§2: a registry may grow without an amendment, so an unregistered class
    may not fail a load — and a value nobody judged has to say so, or it is
    indistinguishable from one that passed."""
    out = _consume(_rail(_length(source_class="carrier_pigeon")),
                    docs=_docs(_doc(source_class="carrier_pigeon")))

    assert out.specs == []
    assert [g.because.code for g in out.gaps] == ["source_class_unrecognised"]


def test_two_documents_tied_on_every_criterion_are_ordered_by_content_hash():
    """§1.4's own terminator since amendment 005, and the real data lands
    exactly here: both documents behind the 16 ft rail are
    `manufacturer_installation_instruction`, both `unknown`, both undated. With
    a non-total key the winner was whichever the caller listed first."""
    out = _consume(_rail(_length(cites=(SECOND, MANUAL))),
                    docs=_docs(_doc(MANUAL), _doc(SECOND)))

    assert out.specs[0].admitted_by.content_hash == MANUAL


def test_the_issue_date_comes_from_the_document_not_the_field():
    """A `SpecField`'s provenance carries no date — §1.4's third criterion lives
    on the `SourceDoc`, which is the whole reason the join has to happen before
    the judgement rather than after it."""
    out = _consume(
        _rail(_length(cites=(MANUAL, SECOND))),
        docs=_docs(_doc(MANUAL, issue_date=Date(iso="2019-01-01",
                                                 value_raw=["01/01/2019"])),
                   _doc(SECOND, issue_date=Date(iso="2025-04-24",
                                                 value_raw=["04/24/2025"]))))

    assert out.specs[0].admitted_by.issue_date.iso == "2025-04-24"
    assert out.specs[0].admitted_by.content_hash == SECOND


# -- the join -------------------------------------------------------------------

def test_the_join_resolves_every_citation_to_the_document_behind_it():
    """§1.2.1's closure rule is what makes this possible inside a pinned run:
    §3.2.2 forbids calling Discovery during one, so the documents have to be in
    the snapshot or the citations carry no admissibility bits at all."""
    out = _consume(_rail(_length(cites=(MANUAL, SECOND))),
                    docs=_docs(_doc(MANUAL), _doc(SECOND, source_class="spec_sheet")))

    assert [d.content_hash for d in out.specs[0].sources] == [MANUAL, SECOND]
    assert [d.source_class for d in out.specs[0].sources] == [INSTALL, "spec_sheet"]


def test_a_citation_that_resolves_to_no_document_is_not_invented():
    """The value is still judged — obligation 3 makes an uncited value a payload
    defect, and refusing to judge it would make it MORE admissible than a cited
    one. The dangling ref itself is reported once, snapshot-wide, by
    `Snapshot.dangling_refs()`; inventing a second report here would double-count
    the same hole the way 32 gaps once counted 16."""
    out = _consume(_rail(_length(cites=(UNKNOWN,))))

    assert out.specs[0].sources == []
    assert out.specs[0].admitted_by is not None


def test_a_document_class_disagreeing_with_the_fields_own_claim_is_reported():
    """The check the join makes possible, and the one that matters most: without
    it a payload can upgrade its own admissibility by claiming a class its
    cited document does not have.

    Reported rather than refused, and judged on the field's own claim, because
    `knowledge-datamodel.md` §2.5 records the honest reason a mismatch may be
    legitimate — one SHA-256 filed four times under four manufacturers has four
    `source_class` values, and `belongs_to` names one of them. Their §8 N-obs-1
    owns resolving that; ours is to make it visible rather than silently pick a
    side."""
    out = _consume(_rail(_length(source_class="sealed_approval")),
                    docs=_docs(_doc(source_class="marketing")))

    assert out.specs[0].admitted_by.source_class == "sealed_approval"
    assert any("sealed_approval" in d and "marketing" in d for d in out.defects), \
        out.defects


# -- what this engine cannot do with it yet -------------------------------------

def test_every_admitted_value_reports_that_nothing_can_apply_it_yet():
    """The honest half of consuming these. A judged value with a resolvable
    citation still reaches no bill of materials, because no product in this
    engine can claim to be a published `Part` — and an operator reading "2
    values admitted" would otherwise believe the plan had changed.

    Same call, same kind and same `closes_by` as `parameter_paired_unsupported`:
    the publisher is correct, the mechanism is missing here, and the
    `would_close` names the work rather than the symptom."""
    out = _consume(_rail(_length()))

    unapplied = [g for g in out.gaps
                 if g.because.code == "published_spec_unapplied"]
    assert len(unapplied) == 1
    gap = unapplied[0]
    assert gap.kind == "unmodellable_entity"
    assert gap.closes_by == "planning"
    assert "nominal_length_mm" in gap.because.params["parameter"]
    assert "product" in gap.would_close


def test_a_draft_part_is_carried_and_not_consumed():
    """§3.1 gives a `Part` a status, and a draft is a definition somebody is
    still writing. Judging its spec would put a value nobody published into a
    verdict that reads exactly like a published one."""
    out = _consume(_rail(_length(), status="draft"))

    assert out.specs == []
    assert out.inactive == ["shared/bt-rail-pr-3rail-white"]


def test_a_retired_part_is_not_consumed_either():
    out = _consume(_rail(_length(), status="retired"))

    assert out.specs == []
    assert out.inactive == ["shared/bt-rail-pr-3rail-white"]


# -- the shapes the delegated document specifies --------------------------------

def test_a_supplies_field_carries_no_value_and_asks_for_no_verdict():
    """§2.2: *"`agree = supplies` carries no value"* — the rule is about a CUT
    length and compiles to `item.stock_length_mm >= 0`, a question about whether
    a product has enough material rather than a measurement to admit."""
    out = _consume(_rail(SpecField(key="nominal_length_mm", agree="supplies",
                                    provenance=Provenance(source_class=INSTALL))))

    assert out.specs == []
    assert out.gaps == []
    assert out.defects == []


def test_a_supplies_field_carrying_a_value_is_a_defect_at_the_sender():
    """A payload contradicting its own schema closes by an edit at the sender,
    not by a curator adding knowledge — so this is authoring text, in the
    convention `warning_defects` and `gap_defects` already use, and not a gap."""
    out = _consume(_rail(_length(agree="supplies")))

    assert out.specs == []
    assert any("supplies" in d for d in out.defects), out.defects


def test_a_valued_field_with_no_value_is_a_defect():
    out = _consume(_rail(SpecField(key="nominal_length_mm", agree="==")))

    assert out.specs == []
    assert any("nominal_length_mm" in d for d in out.defects), out.defects


def test_contributing_sources_accepts_a_hash_or_a_whole_document():
    """The roll-up §1.2.1 calls *"for the reviewer's benefit"*. The delegated
    document writes it `[SourceDoc]` and the real payload sends content hashes;
    both parse, and only the join key is kept, because `source_docs` is the
    authority and a second copy of a document's fields here would be a second
    authority over the same facts.

    Accepting both rather than the one we happened to receive is the direct
    lesson of T42 §5: three shapes the contract permits have been rejected by a
    narrower type of ours, each time with the symptom pointing at the sender."""
    by_hash = Part(id="p1", type=PartTypeRef(key="rail"),
                   contributing_sources=[MANUAL])
    by_doc = Part(id="p2", type=PartTypeRef(key="rail"),
                  contributing_sources=[{"content_hash": MANUAL,
                                          "source_class": INSTALL}])

    assert by_hash.contributing_sources == [MANUAL]
    assert by_doc.contributing_sources == [MANUAL]


# -- filing a part: the spine, and extensions -----------------------------------

def test_a_published_extension_whose_parent_is_a_spine_key_files_cleanly():
    """§2.1 BINDING: *"Every extension's parent chain terminates in the shared
    spine."* The five extensions in the first snapshot that carries parts all
    do, and this is the pass case — verified here rather than trusted, because
    the check is a chain walk and the failure is a part nothing can place."""
    picket = PartType(key="picket", namespace="mfr/certainteed",
                       parent=PartTypeRef(key="infill", namespace="shared"))
    out = _consume(_rail(_length(), type_key="picket",
                          namespace="mfr/certainteed"),
                    part_types=[picket])

    assert out.defects == []
    assert len(out.specs) == 1


def test_a_part_whose_type_is_neither_spine_nor_published_extension_is_a_defect():
    """A type this engine cannot file is a part that can never produce a BOM
    line (§2.2's mechanical test). Its spec value is still judged: the
    admissibility of a number and the filing of the part it describes are two
    separate questions, and answering neither because we cannot answer one
    would hide a real verdict behind an unrelated omission."""
    out = _consume(_rail(_length(), type_key="gate_kit",
                          namespace="mfr/certainteed"))

    assert any("gate_kit" in d for d in out.defects), out.defects
    assert len(out.specs) == 1


def test_an_extension_chain_that_does_not_terminate_in_the_spine_is_a_defect():
    orphan = PartType(key="picket", namespace="mfr/certainteed",
                       parent=PartTypeRef(key="nonesuch",
                                           namespace="mfr/certainteed"))
    out = _consume(_rail(_length(), type_key="picket",
                          namespace="mfr/certainteed"),
                    part_types=[orphan])

    assert any("nonesuch" in d for d in out.defects), out.defects


def test_a_cycle_in_the_part_type_chain_terminates():
    """A payload is not trusted to be acyclic, and a walk that assumes it is
    hangs the load rather than reporting a defect."""
    a = PartType(key="a", namespace="mfr/x",
                  parent=PartTypeRef(key="b", namespace="mfr/x"))
    b = PartType(key="b", namespace="mfr/x",
                  parent=PartTypeRef(key="a", namespace="mfr/x"))
    out = _consume(_rail(_length(), type_key="a", namespace="mfr/x"),
                    part_types=[a, b])

    assert any("mfr/x/a" in d for d in out.defects), out.defects


def test_the_reserved_spine_key_is_not_a_place_to_file_a_part():
    """§2.1: `site_material` is *"reserved and unimplemented — concrete and
    gravel are out of scope for now, and the id is held so it cannot be
    reused."* Held means held: a part filed there is not a part this engine can
    place, and admitting it would quietly implement a scope decision."""
    out = _consume(_rail(_length(), type_key="site_material"))

    # Named as RESERVED specifically. "Neither spine nor published" would also
    # mention the key while sending the reader to publish a `PartType` that
    # nobody may publish — a work item impossible to action.
    assert any("RESERVED" in d and "site_material" in d for d in out.defects), \
        out.defects
