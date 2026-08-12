"""Without slot_key, a shadowbox panel's front and back members — same SKU, same
length, differing only in face offset — merge into one row, and clicking a slat
in the drawing cannot say which part it is."""

from fenceai.demand.derive import RequirementLine
from fenceai.fulfillment.fulfill import Bom
from fenceai.report.structure import _merge_parts, _parts_by_element


def _line(id_, slot_key):
    return RequirementLine(id=id_, sku="SLAT-90", engineering_qty=10, unit="cut",
                           cut_length_mm=1600, role="infill", slot_key=slot_key,
                           pegs=["span@run1:0-1500"])


def test_two_slots_with_the_same_sku_stay_two_rows():
    ledger = _parts_by_element([_line("req0001", "slat_front"),
                                _line("req0002", "slat_back")], Bom())
    parts = _merge_parts(ledger.per_element["span@run1:0-1500"])
    assert {p.slot_key for p in parts} == {"slat_front", "slat_back"}
    assert len(parts) == 2


def test_the_same_slot_twice_still_merges():
    ledger = _parts_by_element([_line("req0001", "slat"), _line("req0002", "slat")],
                               Bom())
    parts = _merge_parts(ledger.per_element["span@run1:0-1500"])
    assert len(parts) == 1 and parts[0].qty == 20
