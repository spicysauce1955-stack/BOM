# Fence-product workflows for signed-job transcription

Access date for every external source below: **2026-09-06**. Research only; no application changes.

## Decision

Keep Fence AI's existing exact-length, connected-run editor. The strongest transferable additions are explicit gate offsets/orientation, source attachments linked to the relevant stretch, a readable scope legend, and a review-to-submission step. These are design recommendations inferred from the evidence, not measured usability findings.

Scope: the sale is already signed. The salesperson transcribes the contract, rough measured drawing, and WhatsApp promises/photos into a saved structured layout. Quoting, repricing, new signatures, material engineering, and installation design are excluded.

## Evidence and coverage

Tavily search discovered sources; Tavily extract returned article bodies and the ArcSite training transcript, which were read. No competitor was operated or tested. No account, signup, payment, or downloaded-code installation was used. Independent searches ran concurrently; this session exposed no agent-spawning tool. No human completion-time or success-rate claims are made.

| Product | Evidence actually read | Relevance and limits |
| --- | --- | --- |
| ArcSite | Official fence training, published 2023-04-12, plus current help articles. [Training](https://www.youtube.com/watch?v=5_Kd6x_D7Zc), [fence bundles](https://support.arcsite.com/en/articles/11759343-how-to-create-your-bundles-fence). | Substantive drawing workflow: run geometry, product assignment, gate positioning, dimensions, photos. Training is older and includes estimating; only drawing behavior is transferred. |
| Draw A Fence | Official step-by-step layout and drawing-sheet tutorial. [Tutorial](https://www.drawafence.com/support-resources/tutorials/how-to-use-our-fence-layout-tool). | Substantive second product: symbols, gate rotation, labels, notes, preview and PDF. The vendor explicitly describes the layout as **not to scale**; image export does not establish a structured geometric model. |
| Betafence simulator | Official section-by-section instructions. [Instructions](https://www.betafence.com/en/fence-configurator-tool). | Length then fence-system selection, positioning on a photo, repeat and save. Useful corroboration, but photo perspective adjustment is not evidence of dimensional validation. |
| Fence Cloud | Official feature page and workflow tips. [Features](https://fence.cloud/features), [tips](https://fence.cloud/articles/fence-cloud/how-to-increase-efficiency-with-fence-cloud). | Mostly marketing for this question. Tips document template creation and estimate duplication; exact stretch-entry, gate-offset and orientation controls remain unknown from the pages read. |

FenceSoft searches did not yield a primary, substantive drawing tutorial in this pass. Targeted Fence Genius searches likewise did not yield suitable official workflow documentation. Neither is counted as a documented comparator; absence from search is not absence of functionality. Generic SketchUp/magicplan research was excluded.

## Six transferable patterns

### 1. Sketch geometry, then enter the authoritative dimension

**Documented:** ArcSite exposes individual line and continuous-line modes. Select an object, tap its dimension or angle, enter a precise value, then accept with the checkmark. An arrow identifies which end lengthens/shortens; the direction control switches it. [Draw lines](https://support.arcsite.com/en/articles/7258148-draw-lines), [manual dimensions](https://support.arcsite.com/en/articles/7258187-edit-lengths-angles-manually), [edit direction](https://support.arcsite.com/en/articles/7258189-change-line-or-wall-segment-direction).

**MVP inference:** preserve typed lengths. Label endpoints A/B/C and make the fixed endpoint visible when correcting a connected stretch. Distinguish typed measured length from approximate sketch direction; entering one exact dimension does not verify the entire layout. **Size:** small for a visible anchor indicator if existing edit semantics suffice; medium if changing the fixed endpoint must move connected runs and their events.

### 2. A gate needs a reference position as well as a width

**Documented training:** ArcSite searches gate products, places a gate shape, then permits editing a relative dimension, illustrated as a gate ten feet from the house. This documents placement relative to another object, not the physical definition of a clear opening. [Fence training](https://www.youtube.com/watch?v=5_Kd6x_D7Zc).

**Documented:** Draw A Fence supplies single, double and sliding gate symbols that can be rotated and resized. [Layout tutorial](https://www.drawafence.com/support-resources/tutorials/how-to-use-our-fence-layout-tool).

**MVP inference:** after clicking the run, enter opening width, kit, and distance from a named endpoint to the opening's near edge. Show that offset on the drawing. Record hinge side and swing toward yard/street, or slide direction, when promised; offer an explicit unknown state. Rotation of a competitor's symbol does **not** prove it stores those semantics. **Size:** medium: form, event fields, SVG glyphs, persistence and Undo/Redo; offset conversion must respect whether the current station denotes center or edge.

### 3. Assign the sold product to the selected stretch

**Documented training:** ArcSite selects fence lines, opens Attributes, adds a product and saves. Its fence library represents fence runs as lines and gates/posts as shapes. [Training](https://www.youtube.com/watch?v=5_Kd6x_D7Zc), [bundle types](https://support.arcsite.com/en/articles/11759343-how-to-create-your-bundles-fence).

**Documented corroboration:** Betafence's sequence is section length, fence system, position on the photo, then repeat for other sections. [Section instructions](https://www.betafence.com/en/fence-configurator-tool).

**MVP inference:** retain the existing interval model/height/base tools; highlight exactly the interval being edited. A compact selected-stretch summary can expose all three values together. For a product change within a straight run, enter the boundary distance and assign the new model only beyond it. Do not imply ArcSite's whole-line assignment proves equivalent interval behavior. **Size:** small for a summary; medium for coordinated editing across existing interval operations.

### 4. Give each promise/photo a place in the layout

**Documented:** ArcSite's help sequence is Site Data, Photo, tap a drawing location, take/import a photo, then optionally annotate it. [Photo instructions](https://support.arcsite.com/en/articles/7258153-add-location-based-photos-with-annotations).

**Marketing only:** Fence Cloud advertises uploaded files, cloud storage and image markup; that page does not establish linking a file to a particular fence interval. [Features](https://fence.cloud/features).

**MVP inference:** attach the signed contract and measured sketch to the job; attach a WhatsApp screenshot/photo and transcribed promise to the relevant run, gate or interval. Store the original source and a locator such as page/message date. Mark transcription as unconfirmed until reviewed. Manual upload is sufficient; automatic WhatsApp integration or OCR is not implied by these sources. **Size:** medium-to-large: storage, project authorization, upload lifecycle, metadata and links, beyond a canvas icon.

### 5. Make the drawing checkable with labels and a derived legend

**Documented:** ArcSite creates a product legend via the top-right control and provides a separate refresh action. Draw A Fence recommends labeled points such as A/B/C and provides text labels. [Legend instructions](https://support.arcsite.com/en/articles/3616865-diagram-legend-key), [layout tutorial](https://www.drawafence.com/support-resources/tutorials/how-to-use-our-fence-layout-tool).

**MVP inference:** derive a legend from current model assignments, heights and gates; show both text and visual styles. Selecting an entry should highlight its interval. Add house/street labels and an explicit viewing side for side elevation, so “left hinge” has a reference. Review plan and elevation against the same saved data. Legend generation is documented; automatic freshness, viewing-side semantics and this review interaction are proposed. **Size:** small-to-medium, primarily derived UI plus orientation metadata.

### 6. Separate editable work from a checked deliverable

**Documented:** Draw A Fence saves the canvas as an image, uploads it into a drawing-sheet form with project details/notes, generates a preview, then exports PDF after checking. [Drawing-sheet tutorial](https://www.drawafence.com/support-resources/tutorials/how-to-use-our-fence-layout-tool).

**MVP inference:** provide Review, then Submit layout, recording the saved revision, author, timestamp and unresolved questions. Keep drafts saveable with unknowns. Submission can explicitly carry unresolved items; it must not silently label them complete. An export button is not evidence of a competitor's immutable revision or approval lifecycle. **Size:** medium-to-large: durable status and revision semantics, failure handling and later edits, as well as UI.

## Proposed salesperson click/input sequence

This is a Fence AI proposal, not a tested competitor sequence. Example values below are illustrative.

1. Open the sold job. Choose **Attach source** and upload the signed contract, measured sketch and relevant WhatsApp files. Label each source and keep it visible beside the layout.
2. Add house/street reference labels. Draw A-B, type **8.00 m**; continue B-C, type **5.00 m**. Use the sketch for direction; flag an unspecified angle instead of treating visual alignment as a measurement.
3. Select A-B. Choose the signed model, set height **1.80 m**, and record the base condition from the source. Repeat for B-C. Leave absent information unknown rather than accepting an unnoticed default.
4. Where B-C changes product, choose its interval from **3.00 m to 5.00 m**, apply the second model, and confirm the highlighted portion. Use the height/base tools separately for changes supported by the source.
5. Choose Gate, click A-B, enter **1.00 m** opening and the sold kit. Set the near opening edge **2.00 m from A**. Confirm hinge at the A-side jamb and swing toward yard, or mark orientation unknown. The displayed opening should occupy **2.00-3.00 m from A**.
6. Select the gate or stretch, choose **Link source**, attach the relevant WhatsApp photo/message, and transcribe its promise. A conflict with the signed drawing becomes a visible unresolved item; do not automatically prefer the newest message.
7. Choose Review. Compare each labeled run, gate offset/width, model interval, height/base, plan orientation and side elevation with its source. Show source links and unknowns beside the corresponding item. Any total must state whether it includes gate openings.
8. Save draft or **Submit layout**. On submission, show the persisted revision and unresolved-item count. A later correction creates an identifiable new revision; a failed save must not produce a submitted indicator. The endpoint is saved sales scope, not a new quote or engineering approval.

## Fit, exclusions and implementation judgment

The supplied baseline already covers the central drawing tasks. A limited read of [editor.js](../../references/repository/src/fenceai/web/static/js/editor.js.txt#L798) confirms gate kit/width handling and interval tools. [handover.js](../../references/repository/src/fenceai/web/static/js/handover.js.txt#L61) renders gaps/estimate information; this does not establish an explicit submission lifecycle. The existing [evidence.js](../../references/repository/src/fenceai/web/static/js/evidence.js.txt#L1) is a fixture-backed knowledge-source viewer, not demonstrated customer-contract/WhatsApp upload storage. These reads inform sizing, not a complete architecture audit.

| Adopt for this MVP | Defer or exclude |
| --- | --- |
| Named endpoints; precise gate offset; clear physical orientation; selected interval summary; current legend. | New CAD engine, freeform design environment, photorealistic simulation, satellite-derived measurements. |
| Job/source attachments, linked promises, unknown/conflict states, source comparison. | Automatic WhatsApp ingestion, OCR-to-layout and resolving contractual conflicts automatically. |
| Draft persistence, explicit review/submission, revision identity and visible save errors. | New proposals, price alternatives, payment/signature collection, engineering approval. |
| Existing catalog model and gate-kit choices. | Full supplier bundle authoring, post/fastener calculations and fabrication outputs. |

ArcSite explicitly documents both full component bundles and a simplified library without material breakdowns. This supports keeping product choice conceptually separate from component engineering; its simplified option still includes pricing, which Fence AI does not need for this workflow. [Library approaches](https://support.arcsite.com/en/articles/11518114-two-ways-to-set-up-a-fence-library).

Overall judgment: **medium effort for the editor/review improvements; medium-to-large for the complete workflow**, driven by attachments and durable submission. Sizes are relative engineering judgments, not schedules. Before implementation, inspect run-station semantics, connected-run edits, undo serialization, existing persistence and project access controls. No dependency installation or replacement drawing engine is justified by this research.

## Limitations and visual reference

- Documentation shows intended behavior, not usability, reliability or measured task outcomes. The 2023 training transcript may contain transcription errors and older control names; recent text help was preferred where available.
- ArcSite's help-linked [fencing onboarding URL](https://www.arcsite.com/onboarding/fencing) returned a Not Found page in extraction. The separately extracted official training video was usable as a transcript; the video was not watched or interactively reproduced.
- Draw A Fence supplies strong tutorial evidence but its layout is schematic. Betafence's photo positioning is not a substitute for the signed measured drawing. Cross-device behavior, offline sync, exact gate-width semantics and transactional submission remain unverified.
- Official help image: [ArcSite dimension-entry number pad](https://arcsite-e780de917482.intercom-attachments-1.com/i/o/709730308/9e4bb3c1da4af91f4482674d/numberpad.png?expires=1788691500&signature=bc6588b7fae1ad2b12e25ce8e728dd929f56177253f917a3e319378f22c81d1f&req=cyAuEcp%2BnoFXFb4f3HP0gBhOKoThk47NyvUiLwVeMKLVkzIu96VCZcNgmz0D%0A0wbkMRs09fehCz1GqQ%3D%3D%0A), extracted from [manual dimensions help](https://support.arcsite.com/en/articles/7258187-edit-lengths-angles-manually). This is the exact supplied image URL, not an invented asset; its signed query may expire. It was collected as a reference, not independently visually inspected. Use the parent help page if the image link expires.
