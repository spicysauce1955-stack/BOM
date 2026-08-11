# The strategy's structure: layout and the items it consists of

Status: implemented · 2026-08-11 (see the plan for the task breakdown)

The generator already decides everything needed to build the fence, and the BOM already
prices it. What is missing is the document in between: **how the structure is laid out**
(where each post goes, how wide each bay is) and **what each piece of it consists of**.
Today a user sees a drawing, a warning list, a one-line summary, and an aggregate BOM —
never "bay B3 is 1200 mm wide, 1800 mm high, and takes 2 rails, 12 screws and 1 picket
pack".

## What the trade actually expects

From the practitioner sources (fence estimating vendors, contractor guides, permit-drawing
requirements, AIA dimensioning practice):

1. **A layout drawing beats prose.** "A simple layout drawing or shop drawing attached to
   the proposal eliminates more confusion than three pages of text" (dirtface, fence
   estimating). Every fence-quote checklist asks for: linear footage per fence line, type
   and height per section, **post type and spacing (line / corner / end)**, gate locations
   and sizes, and transition details where the height steps.
2. **Two levels of detail, on purpose.** The same vendors are explicit that a
   customer-facing proposal should *not* itemise every screw and bag of concrete — an
   itemised list invites "you used 812 screws, not 847, credit me the difference" — while
   the ordering/installing list must be complete (posts, rails, pickets, hardware,
   concrete). So the same data needs two presentations, not two computations.
3. **Schedules are keyed by tag.** Architectural practice tags each element in the drawing
   (like a window schedule) and puts the numbers in a table keyed by that tag. Fence
   drawings do the same with post/bay numbers.
4. **Dimensioning is minimal and purposeful** (AIA, *The lost art of dimensioning*): each
   element locatable from one string per direction, no duplicate dimensions, and the least
   critical dimension is the one that absorbs site tolerance. For a fence that means:
   centre-to-centre bay dimensions chained along the run, one overall run dimension, and
   the closing bay carrying the tolerance.
5. **Setting out is by running measurement from a known end.** Contractor guidance: measure
   the whole run, divide, and spread the remainder across all bays rather than leaving one
   short bay at the end — which is exactly what the equal-span layout already does. The
   crew then marks from one end, so they need **cumulative stations**, not just spacings.

Gaps this surfaces in our own model, none of which block the feature: we do not model gate
**swing direction**, footing **diameter** (only embedment depth), or labour. Swing
direction appears in every professional quote checklist and is the cheapest to add later.

## The shape of the thing

A **structure report**: a derived, read-only view over an existing generation run. It
introduces no new persisted state and no new authored data — regenerating the same run
produces the same report, because it is a pure function of what generation already
produced.

```
StructureReport { run_id, sections: [Section], totals: Totals }
Section  { run_id, tag ("A", "B", …), length_mm, height_mm?, base_surface, post_tilt,
           setting_out: [Station], bays: [Bay], gates: [GateRow] }
Station  { tag ("P1"), station_mm (cumulative from the section start),
           spacing_mm (centre-to-centre from the previous post), kind, sku,
           ground_z_mm, base_z_mm, mounting, tilt_deg }
Bay      { tag ("B1"), from_tag, to_tag, width_mm, height_mm, vertical, slope_len_mm,
           bottom_z_start_mm, bottom_z_end_mm, parts: [Part] }
GateRow  { tag ("G1"), from_tag, to_tag, opening_mm, kit_sku, parts: [Part] }
Part     { sku, qty, unit, cut_length_mm?, from_bar? }   # what this element consists of
Totals   { fence_length_mm, posts, bays, gates, height_range, per_sku: [{sku, qty, unit}] }
```

**Tags are derived, never stored.** `P1…Pn` in station order per section, `B1…Bn` for bays,
`G1…Gn` for gates, sections `A, B, C…` in chain order. Element ids stay exactly as they are
(`post@run1:1200`) — they are machine identity; tags are what a human says out loud on
site. Determinism follows from the ids being content-addressed already.

**Parts come from the pegs we already keep.** `RequirementLine.pegs` holds strategy element
ids and `BomLine.pegs` holds requirement ids, so element → requirements → BOM lines is a
pure inversion of data that exists today. For a divisible SKU the cut plan pegs each piece
to its requirement, so a bay's rail can even name the bar it is cut from. Nothing new is
computed: the parts breakdown and the BOM are the same numbers, grouped differently — which
is the property to test (Σ per-element parts ≡ BOM engineering quantities).

## Two presentations, one report

- **Installer / ordering view** — everything: every post with its station and spacing, every
  bay with its parts, cut lengths and bar provenance.
- **Customer view** — scope-level: sections with lengths, heights and styles, post count and
  spacing, gate openings, and materials described rather than itemised. This is the industry
  convention from (2) above, and it is a *filter over the same report*, not a second
  calculation. The existing quote snapshot is the natural place for it.

## Where it appears

1. **A "Structure" tab** (Hebrew-first like the rest): section cards, each with a setting-out
   table (tag · station · spacing · post type · SKU), a bay table (tag · width · height ·
   mode · parts), and a gate row. Clicking any row selects that element on the canvas and in
   the side view, and the inspector still explains *why* it is there — the schedule says
   *what*, the decision graph says *why*, and they stay separate.
2. **Tags on the drawings.** Post tags along the plan run and the side view; bay tags inside
   the panels. This is what makes a schedule usable — you find B3 in the table by seeing B3
   in the picture.
3. **Dimension strings in the side view** (AIA-minimal): one chained string of
   centre-to-centre bay dimensions, one overall run dimension, the closing bay marked as the
   tolerance-absorbing one.
4. **A printable sheet** — the drawing plus the schedules on one page, which is what actually
   goes to site. A print stylesheet, not a PDF pipeline.

## Non-goals

Labour lines, swing direction, footing diameters, and per-bay pricing. Pricing stays in the
BOM/quote, which already owns money; the structure report owns *quantities and positions*.

## The properties that must hold

- The report is a pure function of `(topology, strategy, requirements, bom)`; same run in,
  same report out, no persistence.
- Σ(parts across elements) ≡ BOM engineering quantities, per SKU. A part that belongs to no
  element (a rounding overage, a package remainder) must be reported as such, never hidden.
- Every station is cumulative from the section start and every spacing is the difference
  between consecutive stations — the two must agree, or the crew's tape and our table
  disagree on site.
- Tags are stable for a given run and re-derived, never stored.
- Every number renders in the user's display unit; every label exists in both locale
  bundles.
