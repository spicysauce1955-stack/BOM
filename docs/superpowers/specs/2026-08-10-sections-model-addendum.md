# Addendum: sections as the unit of differentiation (user feedback, 2026-08-10)

User direction (verbatim intent): the ground side-view belongs to the **entire fence**,
not per-selected-section fiddling; wall sections may differ in elevation/height but the
UI must be simpler; **base surface applies to a whole section** — "we are choosing
sections to differentiate between angles, base surfaces, …".

This is a mental-model statement: **drawing a new section IS the act of expressing a
change** (of direction, of base, of wall). Per-section properties must therefore be
one-choice simple, and cross-section things (the ground) must be edited once, fence-wide.

## Changes

1. **Ground elevation lives on nodes** (`Node.z_mm`, backend commit fcb7c12).
   A corner shared by two sections has exactly one height; the fence-wide ground
   profile is continuous by construction. Interior `elevation_sample` events remain
   for mid-section refinement; explicit endpoint events still override (compat).
2. **Side view shows the whole fence unrolled**: all sections chained in walking
   order (orientation-corrected; disconnected pieces after a gap), one continuous
   ground polyline, section boundary ticks. Node dots are the primary ground handles —
   dragging a corner moves both adjacent sections' ground.
3. **Wall tops stay per-section** (linear start→end; steps = draw two sections), with
   click-the-band → type two numbers editing (drag retained for fine-tuning).
4. **Base surface is a whole-section choice**: the base tool asks only for the surface;
   one base per section (re-choosing replaces it). Mid-section base intervals remain
   supported by the API/domain (S05 unchanged) but are no longer authored by the UI.

## What did NOT change

Domain semantics: interval events, anchors, S01–S14 behavior, the generator, BOM.
The UI now writes a stricter subset of what the model allows.
