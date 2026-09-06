# Round 2 Synthesis

Date: 2026-09-06. This report distinguishes independent salesperson observations, parent source verification, documented external patterns and design proposals. No production features were implemented.

## R2-F01: Saved Height Can Differ From Effective Height

**High priority; observed in the amendment session.** The agent added 1400 mm over stations 3000-8000 to an 8000 mm run that already had 1800 mm over its full length. Both events persisted. Calculation succeeded, but solid panels remained 1800 mm while a lower dashed intent line appeared. See [settled calculated view](sales-edit/06-calculated-side-events.png) and [full session](sales-edit/report.md).

This strengthens round 1's duplicate-height observation: it establishes a visible effective-result mismatch in this case, not only competing saved instructions. The agent recovered the intended disjoint ranges by deleting the full-run event and entering 1800 mm over 0-3000 separately.

**Parent verification:** [editor.js](../references/repository/src/fenceai/web/static/js/editor.js.txt), height save branch around line 960, appends the interval. [generator.py](../references/repository/src/fenceai/strategy/generator.py.txt), `_interval_at` around line 4061, returns the first covering event; `_span_height` uses that selected height. The old full-run event therefore has precedence in the inspected path. This is source corroboration, not an additional user simulation.

**Proposed correction:** explicitly replace an existing value or split the selected interval while preserving untouched portions. Highlight the interval and its effective height in the inspector, plan and elevation. Avoid requiring a salesperson to discover event precedence or manually reconstruct the complement. The HTML example demonstrates a single-property split/preserve operation, not production geometry or structural validation.

## R2-F02: Reload Can Restore an Outdated Result

**High priority; observed in the amendment session.** Once the height ranges were corrected, the selected vinyl configuration could not calculate. Reload restored the earlier successful strategy and estimate beside the newly saved height events. The captured page showed no visible stale-result warning. See [reloaded side and events](sales-edit/09-reloaded-side-events.png).

**Parent verification:** [state.js](../references/repository/src/fenceai/web/static/js/state.js.txt), `saveTopology` around line 75, clears the current result in memory. `openProject`, around lines 62-65, fetches the last saved generation for the project without checking whether it matches the current topology in that function. This is consistent with the observed stale restoration. The source check does not claim a comprehensive audit of all generation lineage or caching paths.

**Proposed correction:** bind the displayed result to the current saved input revision. If it is from an older revision, label it explicitly as historical or hide it from the current review. A failed regeneration must not leave an old layout appearing to represent new sold facts.

## R2-D01: Capture and Buildability Are Different Responsibilities

**Product/UX decision, not a proven catalog bug.** The amendment agent recorded the requested available vinyl model and 1400 mm height. After overlap correction, a native alert reported that the selected model's factory-routed post holes did not match the rails at that height. The agent preserved the signed values instead of inventing another model, height or post.

The validation is useful. Its suggested rail/post changes exceed the authority and knowledge supplied to this salesperson. The resulting experience needs to distinguish recorded sales scope from technical compatibility requiring review. Do not conceal the incompatibility, force a guessed substitution, or let an older result imply it is resolved. The native alert text is recorded in the report; it was not captured as a screenshot.

## R2-G01: Preserve the Meaning of Source Material

**Workflow gap and useful existing capability.** The source-entry agent retained the agreed 1800 mm height on both stretches and saved the later 1600 mm request as explicitly unapproved text linked to run2. Four source-attributed notes survived reopening. This is evidence that scoped notes can preserve the distinction, not that the app recognizes contractual approval. See [reopened notes](sales-entry/07-reopened-notes.png) and [session report](sales-entry/report.md).

The gate was saved at 1991 rather than 2000 mm. The agent recorded the discrepancy in a run1 note. The checklist did not surface that text discrepancy or the pending request; it requested missing house/street geometry. No original file retention or point-level driveway link was established. This repeats the known exact-gate and attachment limitations but adds evidence about the limits of treating all source information as undifferentiated free text.

**Important limits:** the agent accepted the gate form's default kit even though the supplied packet did not specify hardware; that selection must not be treated as a verified sold kit. The photo was described, not supplied. Automation also mis-targeted numeric fields and entered notes too quickly during retries; final corrected values and four notes were verified, but those intermediate failures are not classified as human data-loss findings.

**Proposal:** show source kind, agreed value, requested change and review state as separate information. Retain original files and plain source text. Add source-to-element links before trying automatic interpretation. A source link improves traceability but does not prove authenticity or agreement.

## R2-U01: Resume Must Show the Right Job and Saved Values

**Observed continuity and verification friction, not cross-job data corruption.** The resume agent created the same customer at two addresses, with 6000/1800 and 4000/1600 mm length/height combinations. Heights, models and notes remained separate after reload and switching. A run-scoped clarification preserved the original. Reload from the first site nevertheless opened the second site. See [resume report](sales-resume/report.md) and [retained scoped notes](sales-resume/09-first-resumed-notes.png).

On the second site, reopening Height showed 1800 mm and Model showed Legacy despite saved events showing 1600 mm and M-SLAT. The agent canceled those forms without changing the recorded values. **Parent verification:** `openEventPopover` in [editor.js](../references/repository/src/fenceai/web/static/js/editor.js.txt), around lines 865-887, seeds a new height event with 1800 and builds model choices without selecting the effective saved model. These are authoring forms, not reliable saved-value inspectors. The UI should make Add versus Edit explicit and expose the effective current values directly.

`loadProjects` in [state.js](../references/repository/src/fenceai/web/static/js/state.js.txt), around line 43, chooses the first listed project when no current ID exists. This supports the observed failure to restore the active site. A customer's address is an important persistent identity signal, not just secondary dropdown text.

**Limits:** explicit soil and some site context were added after the reload, then checked through switching, not a second reload. The first original note appears twice because an automation recovery repeated Add; this is not an app-duplication finding. No larger job list, cross-device sync, unsaved-draft-switch behavior or data-race test was performed.

## What the External Research Supports

The researchers used Tavily search and extraction of official pages. They did not operate competing products. The parent additionally extracted and read the Draw A Fence layout tutorial, ArcSite photo-placement guide, Fieldwire Photos guide and Konva state-serialization guide. The Fieldwire reference image was downloaded and visually inspected; it is attributed in the HTML.

- **Draw A Fence:** named points, gate symbols and a reviewed drawing sheet are useful presentation precedents. Its documented layout is not to scale; it is not evidence of a measured domain model. [Tutorial](https://www.drawafence.com/support-resources/tutorials/how-to-use-our-fence-layout-tool).
- **ArcSite:** editable dimensions with direction feedback, product legends and location-based photos suggest focused improvements to the current editor. Whole-object selection is not proof of safe interval replacement. [Dimensions](https://support.arcsite.com/en/articles/7258187-edit-lengths-angles-manually), [photo placement](https://support.arcsite.com/en/articles/7258153-add-location-based-photos-with-annotations).
- **magicplan:** dimension locks and imported reference plans provide useful patterns, but its room/partial-wall concepts do not directly model arbitrary fence height intervals. Use only scale-appropriate source images for calibrated tracing. [Locks](https://help.magicplan.app/how-to-lock-and-unlock-dimensions), [partial-wall limits](https://help.magicplan.app/partial-wall-vs.-partition-wall).
- **Fieldwire and CompanyCam:** originals, attachments and links support a source-aware capture design. Generic upload does not establish WhatsApp integration, source authenticity or contractual approval. [Fieldwire originals/links](https://help.fieldwire.com/hc/en-us/articles/211358926-Introduction-to-the-Photos-Tab), [CompanyCam documents](https://help.companycam.com/en/articles/6828384-uploading-files).
- **Konva, Excalidraw, LibreCAD and tldraw:** useful state, asset and selection precedents, but no documented drop-in fence editor. Keep existing measured domain data authoritative. Adoption requires separate integration and license evaluation; source availability alone is insufficient. [Konva state guidance](https://konvajs.org/docs/data_and_serialization/Best_Practices.html), [project/license comparison](open-projects/report.md).

## Proposed Next Checkpoint

Test one salesperson correction through the existing app: replace a partial height range, preserve every unaffected fact, and review the current saved specification with a current or explicitly unavailable result. Add no new CAD framework.

Treat source upload/linking as a separate coherent slice: original material, stable identity, selected-stretch links, failed-upload state and resume. It is more than a paperclip icon. Manual message capture is sufficient initially; automatic chat ingestion, OCR geometry and live pricing are out of scope.

The older MVP specification distinguishes completeness from accuracy. For this capture workflow, the useful boundary is **transcription fidelity versus engineering validation**: a complete set of fields that silently changes the signed measurement is not a faithful sales record. This is a product recommendation, not a change to the specification.

## Open Policy Choices

1. Can captured scope with a known technical incompatibility be sent for review, while remaining explicitly unapproved for construction?
2. Which missing sources and unapproved requests prevent a completed transcription, versus travelling as named unresolved items?
3. What is the physical reference for height and gate direction, and how is that reference shown from both plan and side view?
4. When a run is split, deleted or renumbered, how do its source links and location-specific promises remain traceable?

The research reports differ on whether unresolved items block submission. That policy is not established by competitor guides and is not silently resolved here. The source packet's unapproved height request must not be treated as an approved amendment merely because it is newer.
