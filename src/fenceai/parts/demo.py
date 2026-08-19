"""The demo models' inline requirements, as library parts.

`SLAT-100` backed an infill member in M-SLAT@v1 and again in M-SLAT@v2, and
`SCREW-S10` a fixing in both, as separate acts of authoring. Here each is one part,
and editing it edits both — which is the entity's whole reason for being shared
rather than copied.

Two slots that name the same SKU are still two parts when they declare DIFFERENT
facts about it. `rail-rail-3000` and `rail-rail-3000-40` are both RAIL-3000: the
second adds `thickness_mm == 40`, because M-SLAT@v2's top rail draws that face and
M-SLAT@v1's rail draws none. Collapsing them would write 40 onto a slot that had
declared nothing, and an undeclared band is rendered `declared=False` rather than as
a measured number — so the merge would change a drawing, not just a document.

**Two demo slots are deliberately absent**, and both refusals are load-bearing:

* **M-LEGACY's rail and screw.** Its eligibility is not authored at all — it is
  rebuilt at generation from the run's resolved `demand_skus`, so a knowledge
  `DefaultComponent` still reaches the BOM (`generator._pick_model`). A part would
  overwrite that with a fixed SKU and silently outrank the rule.
* **M-VINYL's post and cap.** Their predicates agree with a fact about the BAY
  (`item.routed_at_mm == panel.rail_positions_mm`, `item.fits_face_mm ==
  post.face_width_mm`), and a `SpecField` is always `item.<key> <agree> <literal>`.
  A part cannot declare where this panel puts its rails, so the spec vocabulary
  cannot express these and they keep their authored predicate.

Both slots name no part (`PartRequirement.part_id == ""`), which is the documented
meaning of the empty default rather than an oversight.
"""

from __future__ import annotations

from fenceai.parts.model import Part, SpecField


def demo_parts() -> list[Part]:
    """One part per distinct `(type, sku list, width, thickness)` the demo models
    drew, plus ONE part that was not migrated from anything.

    A migrated part's spec is only what the slot authored: the SKU list as `among`,
    and a `width_mm` / `thickness_mm` `==` row where the slot carried the number.
    **No `type ==` row** — `type` is a fact on the entity, and an agreement on it
    would match nothing until slice 2 authors item types, so every migrated slot
    would resolve to no eligible item. The gate would not move, it would collapse.
    """
    return [
        # -- migrated: the slot named one SKU, so the SKU list IS the spec --------
        Part(id="rail-rail-3000", version=1, type="rail",
             name_i18n={"en": "Rail stock 3000 mm", "he": 'מוט מסילה 3000 מ"מ'},
             spec=[SpecField(key="sku", value=["RAIL-3000"], agree="among")]),
        Part(id="rail-rail-3000-40", version=1, type="rail",
             name_i18n={"en": "Rail stock 3000 mm (40 mm face)",
                        "he": 'מוט מסילה 3000 מ"מ (פאה 40)'},
             spec=[SpecField(key="sku", value=["RAIL-3000"], agree="among"),
                   SpecField(key="thickness_mm", value=40, agree="==", unit="mm")]),
        Part(id="rail-channel-3000", version=1, type="rail",
             name_i18n={"en": "U-channel 3000 mm", "he": 'תעלת U 3000 מ"מ'},
             spec=[SpecField(key="sku", value=["CHANNEL-3000"], agree="among"),
                   SpecField(key="thickness_mm", value=60, agree="==", unit="mm")]),
        Part(id="rail-rail-v-3000", version=1, type="rail",
             name_i18n={"en": "Channelled vinyl rail 3000 mm",
                        "he": 'מסילת PVC מחורצת 3000 מ"מ'},
             spec=[SpecField(key="sku", value=["RAIL-V-3000"], agree="among"),
                   SpecField(key="thickness_mm", value=60, agree="==", unit="mm")]),
        Part(id="infill-slat-100", version=1, type="infill",
             name_i18n={"en": "Slat 100 mm", "he": 'שלב 100 מ"מ'},
             spec=[SpecField(key="sku", value=["SLAT-100"], agree="among"),
                   SpecField(key="width_mm", value=100, agree="==", unit="mm")]),
        Part(id="infill-slat-v-150", version=1, type="infill",
             name_i18n={"en": "Vinyl slat 150 mm", "he": 'שלב PVC 150 מ"מ'},
             spec=[SpecField(key="sku", value=["SLAT-V-150"], agree="among"),
                   SpecField(key="width_mm", value=150, agree="==", unit="mm")]),
        Part(id="screw-screw-s10", version=1, type="screw",
             name_i18n={"en": "Screw S10", "he": "בורג S10"},
             spec=[SpecField(key="sku", value=["SCREW-S10"], agree="among")]),
        # -- NOT a migration -----------------------------------------------------
        # Authored by spec, and it admits more than one product on purpose. Every
        # demo slot naming exactly one product is what made the drawer's
        # alternatives untested last arc — `buttons == len(options) - 1` was
        # `0 == 0`, and deleting the offer button passed eighteen tests. One part
        # must admit several, so `RAIL-V-3600` exists in the catalog beside
        # `RAIL-V-3000` for this part to choose between.
        #
        # It names no model slot. Wiring it into `slat_model`'s rail would swap a
        # 3000 mm aluminium rail for a vinyl one in every M-SLAT bay ever
        # generated — a BOM move, which the compatibility gate forbids. A part the
        # library holds and no model yet names is an ordinary state of a shared
        # entity, and it is the state the Parts tab is built to show.
        Part(id="rail-38-vinyl", version=1, type="rail",
             name_i18n={"en": "38 mm vinyl rail", "he": 'שלב ויניל 38 מ"מ'},
             spec=[SpecField(key="width_mm", value=38, agree="==", unit="mm"),
                   SpecField(key="material", value="vinyl", agree="=="),
                   SpecField(key="length_mm", agree="supplies", unit="mm")]),
    ]
