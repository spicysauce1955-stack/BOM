# Fence AI round 2: source capture after a signed sale

Access date for all external sources: **2026-09-06**. Method: Tavily search followed by Tavily extraction and reading official help-page content. Products: magicplan, CompanyCam, Fieldwire. This is documentation research, not hands-on competitor testing or a product ranking. No accounts, purchases, installations, or app implementation. Independent product searches ran concurrently.

**Recommendation:** add a job-level source tray, links from sources to runs/gates/intervals, and a resumable draft with explicit submission. Keep the original signed material visible while the salesperson enters exact values using the existing drawing tools. A rough sketch is evidence of intended layout; its photographed proportions should not silently determine dimensions.

Scope and existing drawing capabilities come from the study brief: the sale is already signed; typed lengths, connected runs, gate placement, interval height/base/model tools, notes, elevation and Undo/Redo already exist. Quotation, pricing, contract signing and office engineering are excluded.

## Six supported patterns

### 1. Store original documents alongside the structured drawing

**Documented:** magicplan accepts project files through Project Dashboard > Files > + > Import; its mobile scanner saves paper pages as PDFs. Files are accessible in the app and cloud, with upload date/time available. Images belong in its separate Photos section. [Official procedure](https://help.magicplan.app/magicplan-files-section).

CompanyCam also supports direct job attachments: Project > Documents > + Document > Upload From Computer, or mobile Documents > + > Add Files > Upload/Scan. Its scanner can collect multiple pages into a PDF; individual files are limited to 100 MB. [Official procedure](https://help.companycam.com/en/articles/6828384-uploading-files).

**Fence AI adaptation, inference:** start with three source categories: signed contract, measured sketch, and messages/site photos. Preserve the imported original and its filename; use separate previews and annotations. Assign each file a stable source ID. Uploading a signed document does not itself establish that the salesperson's transcription matches it.

**MVP fit:** high. **Size:** medium for upload, preview, metadata and persistence; larger if durable file storage is absent. Do not copy CompanyCam's reusable template-file library: that separate feature is web-only and administered by Admins/Managers, unlike direct job uploads. [Library limitation](https://help.companycam.com/en/articles/8345636-uploading-and-managing-project-files).

### 2. Use the imported sketch as a reference, with explicit scale assumptions

**Documented:** magicplan's mobile Import and draw takes a camera/library image, asks the user to position a scale over a known measurement and enter its dimension, then allows drawing rooms over it. The background can be shown or hidden. Its documentation warns that scale cannot be changed after creating the plan. [Official procedure](https://help.magicplan.app/import-and-digitalize-an-existing-floor-plan).

**Fence AI adaptation, inference:** first provide a zoomable source viewer beside the canvas on desktop, or a source/drawing switch on mobile. The salesperson reads the written measurements and types exact run lengths. A photographed freehand sketch may be distorted or deliberately out of proportion, so tracing is optional reference work, not measurement extraction.

**MVP fit:** high for reference viewing; optional later for an underlay. **Size:** small-to-medium for a viewer after attachment storage exists; medium for persistent underlay positioning, rotation and opacity. Defer perspective correction, automatic tracing, room scanning and pixel-derived fence lengths. The magicplan article documents a room workflow, not fence-specific topology.

### 3. Capture message context manually and distinguish its dates

**Documented:** CompanyCam lets a user choose existing photos manually on web/mobile; mobile path is Project > Photos + > Upload Photos > Select Photos Manually > Upload Photos. If EXIF exists, the displayed date uses its creation date; otherwise it defaults to the upload day. [Official upload and date behavior](https://help.companycam.com/en/articles/6828411-upload-existing-photos).

magicplan supports typed notes and photo-library uploads on selected floors, rooms, walls or objects. [Official photos/notes procedure](https://help.magicplan.app/add-information-and-photos-on-floor-level).

**Fence AI adaptation, inference:** upload already-saved WhatsApp photos/screenshots using the ordinary picker; paste the relevant promise into a plain-text source entry. Record sender and message date as manually supplied context, allow unknown dates, and link text to its screenshot when available. Store upload time separately. Mark pasted text as a manual transcription, not a verified conversation record. Keep the salesperson's interpretation in a separate field.

**MVP fit:** high. **Size:** small-to-medium after attachments. These docs support generic uploads and text entry; they do **not** establish WhatsApp scraping, chat parsing, automatic import, conversation completeness or sender verification. No such integration is assumed. CompanyCam's camera-roll share extension is documented for iOS only, so a universal share-to-app flow is also not assumed. [Platform limitation](https://help.companycam.com/en/articles/6828411-upload-existing-photos).

### 4. Link photos to an element or a location without creating an office task

**Documented:** magicplan offers a movable Photo annotation object: +Insert > Object > Annotation > Photo, position it, then open its details and add photos. [Official location-pin procedure](https://help.magicplan.app/restoration-documentation).

Fieldwire's mobile plan link tool includes a camera option for attaching photos to a plan sheet; its help explicitly treats these photo hyperlinks as documentation and distinguishes them from action-tracking tasks. [Official mobile attachment tools](https://help.fieldwire.com/hc/en-us/articles/360049713811-Introduction-to-the-Plan-View-and-Markup-Tools-Mobile).

**Fence AI adaptation, inference:** select a run, gate or interval > paperclip > choose a source > optional caption. A source thumbnail shows its linked element; selecting the link highlights that element. Use an optional plan pin for context that lacks a suitable element, such as access beside the fence. Leave general contract pages at job level.

**MVP fit:** high for element links; optional for free-position pins. **Size:** medium. Persist links by stable element ID, not screen coordinates. Splitting/deleting a run needs an explicit policy for its links, including a visible unlinked state. Defer assignees, deadlines, punch lists and task boards.

### 5. Keep the original, its annotation and the interpreted value distinct

**Documented:** Fieldwire can mark up an attached photo without changing its original. Markups on a task attachment do not automatically appear on the same photo's plan attachment. Its photo viewer shows linked plans/tasks/forms, and a plan link can be removed without deleting the project photo. [Official original/link behavior](https://help.fieldwire.com/hc/en-us/articles/211358926-Introduction-to-the-Photos-Tab).

**Fence AI adaptation, inference:** show Original, optional Annotation, and Entered value as distinct information. For example, a gate-width entry can link to a contract page while a conflicting message is retained as a second source and an unresolved discrepancy. Do not automatically decide that the latest message changes the signed scope. Removing a run attachment should remove the link, with original deletion a separate action.

**MVP fit:** high for original preservation and source links; photo drawing tools can wait. **Size:** medium for references and separate interpretation fields; medium-to-large for non-destructive image markup with export. Source attachment is traceability, not proof of agreement or correctness.

### 6. Separate draft saving, recoverable revisions and explicit submission

**Documented:** magicplan describes automatic saving when leaving a room/floor. It also offers a Floor Plan Backups list under Help, but backups depend on unspecified conditions, may not exist for every project, and restoring one overwrites the current version. [Save behavior](https://help.magicplan.app/undo), [backup limitations and restore procedure](https://help.magicplan.app/restore-a-previous-version-of-floor-plan).

Its device-switch procedure requires syncing, then refreshing the second device; the documentation advises using one device at a time and warns that offline changes are not yet synced. [Official sync procedure](https://help.magicplan.app/synchronize-your-projects-between-two-devices).

Fieldwire identifies uploaded plan versions by upload date, displays the latest first and watermarks previous versions. Its version management is restricted to Project Admins. This is drawing-file versioning, not evidence of a signed-sales submission workflow. [Official version behavior](https://help.fieldwire.com/hc/en-us/articles/207718776-What-is-Version-Control-for-Plans).

**Fence AI adaptation, inference:** show a persisted draft and actual save status; reopen it by job. Submit creates a durable snapshot of drawing, entered values, source references and unresolved notes. Subsequent edits create a revision with a reason while preserving the prior submission. This is a proposed Fence AI workflow, not a documented competitor feature.

**MVP fit:** essential. **Size:** medium-to-large because submission must bind the saved layout and source set together. Defer simultaneous editing, automatic sheet replacement, visual revision comparison and offline conflict merging. Do not equate Undo/Redo, local save, server save and submission.

## Proposed salesperson workflow

This is a concrete design proposal, not a tested workflow. Example values are illustrative.

| Step | Click/input | Saved result |
| --- | --- | --- |
| Open job | Open the signed job, or Resume draft | Job context and last persisted drawing |
| Capture sources | Sources > Upload; choose contract PDF, sketch image and saved site/message photos; assign categories | Source originals, filenames, upload timestamps and upload state |
| Add promise | Add message > paste exact text; enter sender/date if known; link screenshot | Manual source text, separate from interpretation |
| Read and draw | Open sketch preview; use existing connected-run tool; type each written length, such as 4,200 mm | Exact structured geometry linked to its source |
| Enter signed details | Click to place gate; type width/kit; apply existing height/base/model tools to relevant intervals | Structured gate and interval values |
| Attach context | Select gate/run/interval > paperclip > choose photo/message > add caption; optionally place a location pin | Link between evidence and element |
| Handle discrepancy | Open competing sources; record issue and affected element; leave unresolved when clarification is needed | Visible uncertainty, no invented resolution |
| Pause/resume | Save draft; wait for confirmed save status; reopen job later | Persisted layout, sources and unresolved notes; failed uploads stay visible |
| Review/submit | Review drawing/elevation and entered values against sources; inspect missing sources and failed uploads; Submit | Versioned snapshot and submission timestamp |
| Revise | Open submitted job > Create revision > enter reason > edit and submit again | New version retaining previous submission and original evidence |

Recommended submission rule: failed or pending source uploads prevent a completed submission. Missing required signed material or unresolved scope contradictions keep the job in draft with a visible needs-clarification state. General nonblocking notes can travel with a submission. The precise required fields and blocker policy need stakeholder agreement; the researched documentation does not decide them.

## Implementation judgment and boundaries

The combined MVP is **medium-to-large**, not a toolbar-only change. Small means a bounded view or field over existing persistence; medium adds data relationships or file handling; large crosses storage, versioning and failure recovery. These are relative engineering judgments, not delivery estimates or human performance claims.

The minimum additions are source storage/preview, plain-text message capture, stable source-to-element links, reliable draft restoration and explicit submission snapshots. Browser reload must preserve the data; a submission must still resolve the exact sources it referenced after later uploads or revisions. A deleted/split run and a failed upload are important acceptance cases.

A brief local read found an existing evidence viewer, but its comments explicitly describe a fixture-backed source resolver and absent pixel service. Reuse its distinction between source and interpretation as a design precedent; do not count it as implemented signed-contract upload storage. [Local evidence viewer](../../references/repository/src/fenceai/web/static/js/evidence.js.txt), especially lines 1-19. No backend implementation audit was performed, so storage and versioning effort remains conditional.

Out of scope: pricing, fresh proposals, signing, office approvals/engineering, procurement, automatic WhatsApp access, AI extraction as authoritative data, and field-team task management. CompanyCam's ability to create documents from selected photos is useful precedent for grouping evidence, but does not establish structured fence capture. [Official document creation](https://help.companycam.com/en/articles/8695593-creating-documents).

## Evidence limits and visual references

- **Documented** means stated in an official help article read through extraction. Some instructions are embedded in images and did not extract as text; missing click details were not invented.
- **Marketing** language about speed, accuracy or productivity was not treated as measured evidence. No salesperson success rates, task times or usability outcomes were observed.
- **Inference** labels cover the proposed Fence AI workflow, schema relationships, priority and sizing. **Unknowns:** exact subscription entitlements beyond stated article limits, behavior on the team's devices, full audit-history retention, and suitability for outdoor fence geometry. magicplan's element photos/notes article specifies Report/Pro access. [Entitlement statement](https://help.magicplan.app/add-information-and-photos-on-floor-level).
- The sync and backup articles establish mechanisms and caveats, not a guarantee of lossless resume or a complete revision ledger. None of the reviewed articles establishes the proposed post-signature submission semantics.
- Official help image URL, discovered in the Fieldwire mobile article: [plan hyperlink tools GIF](https://help.fieldwire.com/hc/article_attachments/360069011452). Useful reference for on-plan attachment placement; image content was not independently visually inspected.
- Official help image URL, discovered in the Fieldwire Photos article: [photo linked to project entities](https://help.fieldwire.com/hc/article_attachments/15607687783323). Useful reference for reverse navigation from photo to plan; image content was not independently visually inspected. These are source URLs, not locally captured competitor screenshots.
