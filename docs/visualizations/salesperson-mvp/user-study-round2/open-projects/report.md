# Open projects for the signed-sale fence editor

Access date for every external source: **2026-09-06**. Scope: transcribe an already signed sale, rough measured drawing, and WhatsApp promises/photos into a saved structured layout. Pricing, quotation, and office engineering are excluded.

**Recommendation: keep the existing vanilla JS/SVG editor.** Add source attachments, links from promises to fence elements, and an explicit submission revision. Three maintained open-source projects supply useful precedents: Konva, Excalidraw, and LibreCAD. A fourth, tldraw, is a useful source-available comparator but its current SDK license excludes unrestricted production use. None of the reviewed documentation establishes a ready-made signed-sale fence topology editor.

## Evidence boundaries

Research used Tavily search and page extraction, followed by direct official GitHub API reads to verify release dates. Official documentation, repositories, and license files were read; no competitor was installed or interactively tested, and no signup was performed. **Documented** means an official reference or example describes the behavior, not that this study verified it at runtime. **Inference/proposal** identifies our Fence AI application of that evidence. Marketing statements about speed or developer savings are not treated as evidence. No human task-success or completion-time claims are made.

Local code inspection confirms typed-distance entry and saving in [editor.js](../../references/repository/src/fenceai/web/static/js/editor.js.txt), particularly `commitTypedDot`, `commitTypedLength`, `finishDraft`, and the event popover. Gates are point events and height/model changes are interval events. The supplied brief establishes source attachments and explicit submission as missing; the existing [evidence.js](../../references/repository/src/fenceai/web/static/js/evidence.js.txt) describes fixture-backed technical source references, which does not establish a salesperson attachment-upload workflow. This report follows the current brief where the older sales specification includes pricing.

## Projects and adoption choices

Release dates below are GitHub `published_at` dates, in UTC, verified through the official API. Releases indicate ongoing maintenance, not support guarantees. Documentation follows moving branches and may include features beyond a stable release.

| Project | Verified maintenance | Documented core and custom boundary | License and fit judgment |
| --- | --- | --- | --- |
| **Konva** | 10.3.3 published **2026-09-04**. [Release](https://github.com/konvajs/konva/releases/tag/10.3.3), [API](https://api.github.com/repos/konvajs/konva/releases?per_page=3). | JavaScript canvas nodes, events, image rendering and selection transforms are core. The official transform example includes vanilla JS. Measured units, shared fence nodes, gate offsets, interval coverage and validation would remain custom application logic. [Transform example](https://konvajs.org/docs/select_and_transform/Basic_demo.html), [Image API example](https://konvajs.org/docs/shapes/Image.html). | **MIT**; preserve copyright and permission notices in distributed copies/substantial portions. [Actual license](https://github.com/konvajs/konva/blob/master/LICENSE). **Inference:** possible later canvas renderer or isolated photo-annotation tool; no React rewrite required, but replacing SVG would still require renderer and interaction migration. |
| **Excalidraw** | v0.18.1 published **2026-04-21**; the release is a security patch. [Release](https://github.com/excalidraw/excalidraw/releases/tag/v0.18.1), [API](https://api.github.com/repos/excalidraw/excalidraw/releases?per_page=3). | Whiteboard shapes, image support, arrows, Undo/Redo, PNG/SVG export and scene JSON are documented. Images can be restored through `initialData.files`. These are visual scene features; the reviewed docs do not establish physical units, persistent dimensional constraints or fence topology. [Repository](https://github.com/excalidraw/excalidraw), [Initial data](https://docs.excalidraw.com/docs/@excalidraw/excalidraw/api/props/initialdata). | **MIT**, with notice preservation. [Actual license](https://github.com/excalidraw/excalidraw/blob/master/LICENSE). Embedding requires React/React DOM and CSS/font asset integration. [Installation](https://docs.excalidraw.com/docs/@excalidraw/excalidraw/installation). **Inference:** optional later evidence sketchpad; poor replacement for the existing measured editor. |
| **LibreCAD** | Stable v2.2.1.5 published **2026-05-02**; separate rolling builds are marked prerelease. [Stable release](https://github.com/LibreCAD/LibreCAD/releases/tag/v2.2.1.5), [API](https://api.github.com/repos/LibreCAD/LibreCAD/releases/latest). | Assigned lengths/angles, polylines, dimension annotations and geometry property edits are documented CAD tools. Bitmap import is documented. Fence models, gate kits, interval properties and signed-source provenance are not established core entities. [Tools](https://docs.librecad.org/en/latest/ref/tools.html), [Import menu](https://docs.librecad.org/en/latest/ref/menu.html#file). | **GPLv2** for the application as a whole; its license also identifies separately licensed bundled resources. [Actual license](https://github.com/LibreCAD/LibreCAD/blob/master/LICENSE). Qt desktop application, not a drop-in browser library. [Repository](https://github.com/LibreCAD/LibreCAD). **Inference:** borrow interaction ideas; avoid a desktop CAD adoption or code port for this MVP. GPL code reuse has materially different distribution obligations from MIT. |
| **tldraw: comparator, not counted as open source here** | v5.4.0 published **2026-09-02**. [Release](https://github.com/tldraw/tldraw/releases/tag/v5.4.0), [API](https://api.github.com/repos/tldraw/tldraw/releases?per_page=3). | Custom shapes define validated properties, hit geometry, resize behavior and React rendering. Images reference separate asset records. Those extension points enable, but do not provide, a fence-domain constraint model. [Custom shape](https://tldraw.dev/examples/shapes/custom-shape), [Image asset example](https://tldraw.dev/examples/local-images). | Current repository license permits development but prohibits production under its default terms; trials and separate commercial agreements provide exceptions. License-key enforcement must not be disabled. [Actual license](https://github.com/tldraw/tldraw/blob/main/LICENSE.md). **Inference:** useful design reference, unsuitable as an unrestricted open-source MVP dependency; embedding also introduces React. |

## Five transferable patterns

### 1. Use numeric entry to create geometry; distinguish it from dimension text

**Documented:** LibreCAD offers lines created with an assigned length and angle, while its dimension tools separately add annotation to existing geometry. Its drawing setup guide specifies full-scale geometry, with output scaling handled separately. [Line and dimension tools](https://docs.librecad.org/en/latest/ref/tools.html#line), [Drawing scale](https://docs.librecad.org/en/latest/guides/dwg-setup.html#scale-and-dimensioning).

**Proposal:** retain Fence AI's click-start, aim, type distance, Enter interaction and visible units. Treat dimensions on screen as derived from stored measurements. Do not infer dimensions by measuring the photograph of a rough drawing. Known run lengths alone also do not establish exact corner angles or site position: preserve uncertainty where those were not measured.

**MVP fit/size:** keep existing capability; small work for a clearer measurement/source indicator. Persistent geometric constraint solving would be large and outside the present capture need. **Unknown:** reviewed LibreCAD references do not establish that editing dimension text solves connected geometry; dimensioning must not be presented as a parametric constraint engine.

### 2. Keep original evidence separate from its displayed position

**Documented:** tldraw creates an asset record and a separate image shape referring to its ID, expressly allowing the displayed image to resize without resizing the source asset. Excalidraw restores binary files separately from elements, and `getFiles()` may include unreferenced files. [tldraw image example](https://tldraw.dev/examples/local-images), [Excalidraw initial data](https://docs.excalidraw.com/docs/@excalidraw/excalidraw/api/props/initialdata), [Excalidraw file retrieval](https://docs.excalidraw.com/docs/@excalidraw/excalidraw/api/props/excalidraw-api#getfiles).

**Proposal:** add a source rail containing the signed contract, measured sketch and manually attached WhatsApp screenshots/photos. Store original attachment identity separately from crop/rotation/zoom settings. Let a note link to an attachment and optional page/region, plus a run or gate. A preview thumbnail is not the authoritative original.

**MVP fit/size:** medium, because upload/storage, persistent IDs, previews, errors and links cross UI/API/data boundaries. This does not require adopting either whiteboard. PDF rendering, WhatsApp ingestion and OCR are not supplied by these image APIs; keep automatic ingestion out of the first slice. A calibrated underlay is optional later and should never imply that an unscaled rough sketch is a survey.

### 3. Save fence data and rebuild the view from it

**Documented:** Konva recommends saving essential application state rather than serializing a complex canvas tree, noting problems with images and event listeners; its example implements history over state and reconstructs the view. [Serialization and Undo/Redo guidance](https://konvajs.org/docs/data_and_serialization/Best_Practices.html).

**Proposal:** preserve Fence AI's existing run/node/event model as the authoritative saved document. Add references and a revision identity there. Viewport, selection and image display transforms are presentation state. Verify that reopening a saved draft restores measured geometry, interval properties, gate data and evidence references; a PNG/SVG export alone is insufficient.

**MVP fit/size:** small-to-medium extension of the existing save path, subject to a focused schema/save review. A renderer replacement is large because all drawing and selection paths must be reconciled with existing domain state. This is architectural inference, not a Konva guarantee about Fence AI.

### 4. Constrain edits according to the selected object's meaning

**Documented:** Konva's generic Transformer changes `scaleX`/`scaleY`, not node width/height. tldraw custom shapes explicitly define properties, hit geometry and resize behavior. [Konva transform semantics](https://konvajs.org/docs/select_and_transform/Basic_demo.html), [tldraw shape behavior](https://tldraw.dev/examples/shapes/custom-shape).

**Proposal:** allow free image resizing, but keep gate width as a measured field and gate location as a distance along a run. Clicking the run chooses an approximate location; a numeric field confirms it. Preserve the kit already sold. Show the selected interval when height/base/model tools are active. Validate a gate against run bounds and other openings using domain data, not its visible bounding box.

**MVP fit/size:** medium for exact gate-offset entry and focused validation; selection feedback can be small. Existing gates and interval tools should be extended. **Boundary:** visual contact between lines or arrow binding is not proof of shared fence-node identity; a general transform handle does not maintain sold widths or interval coverage automatically.

### 5. Separate draft persistence from an explicit submitted revision

**Documented:** Excalidraw's repository distinguishes package features from hosted-app features such as browser autosave and collaboration. Its API offers scene updates, change subscriptions and explicit history-capture control. [Package versus hosted app](https://github.com/excalidraw/excalidraw#excalidrawcom), [Update/history API](https://docs.excalidraw.com/docs/@excalidraw/excalidraw/api/props/excalidraw-api#updatescene).

**Proposal:** retain draft saving, then add a Review action listing runs, gates, interval properties, linked promises and unresolved discrepancies. Submit saves a named revision of those records with attachment references and records the submitting person/time. Later edits create a new draft revision. Failed saves must not show Submitted. This submission behavior is a Fence AI design proposal, not a documented feature of these libraries.

**MVP fit/size:** medium: review UI, revision persistence and failure handling. Submission should capture unresolved source discrepancies explicitly; it must not imply office engineering approval. Multiplayer, approval routing, quotation generation and manufacturing checks are outside this slice.

## Concrete salesperson workflow

This is a proposed Fence AI workflow, not a tested competitor walkthrough. Values below are illustrative inputs.

1. Open the sold job. Click **Attach source**, select the signed contract, drawing photo and relevant WhatsApp screenshots/photos. Identify their source type. Open the drawing beside the editor. Attachment persistence is new work.
2. Select the existing unit setting. Click **Draw**, click the first corner, aim along the first stretch, type `420cm`, press Enter; aim along the return, type `280cm`, press Enter; finish the connected run sequence. Use only measured lengths, and record an unmeasured angle as uncertain. Typed lengths already exist.
3. Click **Gate**, then the applicable run. Select the sold kit and enter `100cm` opening width. In the proposed offset field, enter `150cm from start` and inspect the highlighted opening. Confirm the measurement reference used in the source; click Save. Gate selection/width exist; exact offset confirmation is the proposed extension.
4. Use the existing **Height**, **Base**, and **Model** tools on each relevant stretch. Enter the sold height, select what it sits on and the sold model, and inspect the highlighted interval before saving. Use side elevation to review the entered height/base changes.
5. Click the relevant run or gate, add the promised condition as a note, and link its screenshot/photo. For a source conflict, preserve both sources and mark the unresolved discrepancy. Do not silently replace signed information with a guessed interpretation. Notes exist; attachment linking is new.
6. Click **Review**. Inspect plan and side elevation alongside a compact list of runs, dimensions, gates, stretch properties and promises. Correct transcription mistakes with the existing edit tools and Undo/Redo. Confirm that originals can be reopened.
7. Click **Submit captured layout**. On successful persistence, show revision and submission status. Retain explicit unresolved items in that revision. Save/Submit is capture completion, not a fresh quote or engineering approval.

## Implementation judgment and limits

Sizes are relative engineering judgments, not calendar estimates or human performance findings: **small** = local UI/state work; **medium** = UI plus persisted schema/API changes; **large** = renderer/framework or geometry-engine migration.

**Keep now:** SVG, measured topology, connected runs, gate kit/width inputs, separate interval tools, notes, elevation and history. Add the evidence and submission path in medium-sized increments. There is no documented gap here that requires a new drawing framework.

**Adopt conditionally later:** Konva for a separately justified canvas requirement or photo annotation, after an isolated comparison against existing SVG. Excalidraw only for optional free-form evidence sketches that remain distinct from the measured layout. LibreCAD supplies useful numeric-entry precedents, but desktop CAD adoption introduces a second editing environment and custom transfer work. tldraw carries both integration work and a production licensing dependency.

**Unresolved:** no browser/device/RTL verification, benchmark, complete dependency-license audit or detailed save-schema audit was performed. The documentation does not establish automatic contract interpretation, WhatsApp integration, fence-specific constraints, or submission workflows for these projects. LibreCAD's latest manual warns that it is a work in progress for prerelease builds; its documented behavior is not asserted as verified in stable v2.2.1.5. [Manual caveat](https://docs.librecad.org/en/latest/ref/tools.html). Excalidraw extraction returned API text but its embedded live examples reported a rendering error, so those examples were not treated as executed evidence.

## Official help images

These are reference images for the numeric-input pattern, not screenshots from testing. Both links appear in the official tools reference and returned HTTP 200 with `image/png` on the access date. No image reuse rights are inferred from availability.

- Assigned line length/angle toolbar: https://docs.librecad.org/en/latest/_images/toLineAngle.png
- Dimension annotation toolbar: https://docs.librecad.org/en/latest/_images/toDimn.png
- Source page for both: https://docs.librecad.org/en/latest/ref/tools.html
