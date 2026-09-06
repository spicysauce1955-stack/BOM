# Parent Verification and Synthesis

Date: 2026-09-06. These source checks followed the four independent UI sessions. They are engineering verification, not extra participants or another usability trial. No application files were changed.

## S01. Length Corrections Affect Connected Measurements

The returning agent observed street 8,000 -> 8,400 mm, side 5,000 -> 5,016 mm and gate offset 2,000 -> 2,100 mm after one edit. Undo and Redo restored the corresponding sets of values. [Session evidence](returning/report.md).

Screenshot review: `05-street-change-side-effect.png` still shows the pre-edit 8,000/5,000 mm layout, despite its filename. It is not visual proof of the completed change. The HTML uses [07-redo.png](returning/07-redo.png), which visibly shows 8,400/5,016 mm. The original agent report remains intact; this note qualifies its screenshot reference.

`commitTypedLength` in [editor.js](../references/repository/src/fenceai/web/static/js/editor.js.txt), around line 1046, changes the run's end node. Connected runs deliberately share that node. `stationOfAnchor` in [geom.js](../references/repository/src/fenceai/web/static/js/geom.js.txt), around line 170, scales an ordinary anchor proportionally when its segment length changes; rigid anchoring preserves the offset. These mechanisms explain the observation. They are not evidence of random coordinate corruption.

Design implication: make the fixed endpoint and affected dimensions explicit. Choosing the shared corner instead preserves this example's side length by moving the other start point; it is a tradeoff, not a universal constraint solution. The HTML comparison illustrates that choice and independently compares gate anchoring policies. It is not production functionality.

## S02. Height Save Adds Another Instruction

The returning agent saw both 1,800 and 1,600 mm height events covering the same 0-5,000 mm range, then removed the old event. [Session evidence](returning/report.md).

The `height` branch of `openEventPopover.save` in [editor.js](../references/repository/src/fenceai/web/static/js/editor.js.txt), around line 960, calls `addIntervalEvent` without removing overlapping height events. The nearby base and model branches have explicit replacement logic. This corroborates the duplicate-instruction observation. The session did not establish every downstream consumer's precedence behavior, so the finding is not stated as a proven wrong final BOM.

Design implication: separate adding a range from editing an existing value; make replacement or overlap resolution explicit.

## S03. Gate Station Is Not Editable in the Encountered Form

The novice saved 1,992 rather than 2,000 mm; the Hebrew-first agent saved 201.4 rather than 200 cm. The returning agent succeeded using fine pointer coordinates, adding a replacement and deleting the old gate. That does not establish easy human mouse precision. [Novice](novice/report.md), [Hebrew](hebrew/report.md), [returning](returning/report.md).

`openEventPopover` in [editor.js](../references/repository/src/fenceai/web/static/js/editor.js.txt), around lines 823-840, renders station as text and width as an input. Its save branch uses the station supplied by the click. This confirms the missing numeric station field in that form. The separate pointer-hint/dialog discrepancy is observed, but its exact cause was not diagnosed here.

Design implication: identify the run start, expose a numeric offset, and provide an edit-existing-gate interaction.

## S04. Height Reference Must Be Clear

The Hebrew agent entered 180 cm height on a 40 cm wall and observed a 140 cm panel. It interpreted the requested height as the fence above the wall. [Session evidence](hebrew/report.md).

`_span_height` in [generator.py](../references/repository/src/fenceai/strategy/generator.py.txt), around line 4074, explicitly reduces height intent by base-top height on a built base. The result matches that logic. This is a mismatch in communicated meaning, not a proven subtraction bug or a decision that the generator's current semantics should be reversed.

Design implication: distinguish total height from panel height above the base, and show both alongside the elevation before confirmation.

## S05. Hint Text Defects

The Hebrew session found an example saying 420 cm equals 42 m and raw `hint.house`, `hint.street` and `hint.model` text. The novice independently encountered raw hint keys. Both locale files have the same incorrect `hint.draw_cm` example at line 432: [English](../references/repository/src/fenceai/web/static/i18n/en.json.txt), [Hebrew](../references/repository/src/fenceai/web/static/i18n/he.json.txt).

`updateStatus` in [editor.js](../references/repository/src/fenceai/web/static/js/editor.js.txt), around line 108, supplies `ex_mm: 4200`, displayed as 420 in cm mode. The correct metre equivalent is 4.2, not 42. Neither locale file defines the three tool hint keys. These are confirmed text defects, not a failure of actual centimetre entry; the 600 cm run was correctly recorded.

## S06. Resume and Save Confidence

The novice's reload selected the sample project. Re-selecting the customer job restored its drawing, specifications and note. That is a navigation-continuity observation, not evidence of deleted data. The role-label inconsistency was independently reproduced by multiple agents and already appears as B04 in the earlier audit.

The novice's first job-details save also needed a retry. Entry occurred immediately after project creation; no causal diagnosis or repetition across users was established. Retain this as a lower-confidence timing hypothesis, not a confirmed lost-save bug.

## Handover Is Still a Product Boundary

The office agent recovered scope and promises but could not establish the signed source, submitted version or office acceptance. Its saved clarification was attached to a technical decision conversation. No recipient or delivery confirmation to sales was established. These independently encountered limitations corroborate existing source-package and transfer gaps; they are not counted as newly discovered backend failures.

The app cannot compare a gate against a signed measurement it never received. The readiness problem is that its broad wording is easily confused with matching the agreement or actual receipt. A saved comment is likewise not a delivered clarification, and a ready banner is not office acceptance.

## Proposed Priority

1. Fix the earlier false-readiness defects before treating the checklist as trustworthy.
2. Make numeric gate entry, height replacement/reference and connected-edit consequences reliable and clear.
3. Define source attachment, submitted snapshot, recipient acknowledgement and clarification ownership for this after-sale MVP.
4. Improve active-job restoration, role vocabulary, hints and selected-stretch review.

Preserve typed drawing, Undo/Redo, context, event inspection, notes and side views. All four sessions found useful parts of the existing path. The evidence supports focused improvement, not a demonstrated need to replace the editor.
