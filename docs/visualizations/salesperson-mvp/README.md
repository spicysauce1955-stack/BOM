# Salesperson MVP Visualization Package

Start here: **[Open index.html](index.html)**. It opens the interactive walkthrough,
not a landing page. Double-click it or open it directly in a desktop browser.
No server, build, account, installation, or internet connection is needed for the demo.

This directory is self-contained: keep its subdirectories together when moving,
copying, or sharing it. Online research links still require internet access.

## What to Open

| File | Purpose |
| --- | --- |
| [index.html](index.html) | Latest six-step interactive salesperson proposal. |
| [sales-journey/adversarial-review.md](sales-journey/adversarial-review.md) | Five-agent review, reproduction steps, and follow-up fixes. |
| [sales-workspace.html](sales-workspace.html) | Screenshot walkthrough of the existing application and its recorded findings. |
| [sales-handover.html](sales-handover.html) | Signed-sale-to-office workflow and existing implementation boundaries. |
| [sales-user-study.html](sales-user-study.html) | First round of agent simulations and product research. |
| [sales-study-round2-evidence.html](sales-study-round2-evidence.html) | Second round of salesperson simulations and product research. |
| [sales-ui-audit.md](sales-ui-audit.md) | Detailed original UI audit. |
| [sales-journey/README.md](sales-journey/README.md) | Implementation notes, example semantics, and test details. |

## Walkthrough

1. Job and sources: signed records, construction status, and unfinished site levels.
2. Layout: measured stretches, pool context, and the construction work area.
3. Details: separate Ground, Base, and Fence controls, including slopes and steps.
4. Selected section: preview and apply a partial-height change.
5. Gate: enter width, offset, and opening direction; retain the hinge question.
6. Office review: inspect saved facts, diagrams, evidence, notes, and open questions.

The Notes & evidence pane supports notes attached to the job, a stretch, a selected
range, the gate, or pool. Message provenance is distinct from the note's target.
WhatsApp is an example source, not a live connection.

## Contents

```text
salesperson-mvp/
  index.html                         Latest interactive walkthrough
  README.md                          This guide and document index
  sales-journey/                     UI code, generated photo, review, tests, icons
  sales-workspace.html               Existing-app screenshot walkthrough
  sales-handover.html                Handover workflow
  sales-ui-audit.md                  Original audit
  sales-user-study.html              Round 1 report
  sales-study-round2-evidence.html    Round 2 report
  sales-ui-evidence/                 Application screenshots and audit records
  user-study/                        Round 1 session reports and screenshots
  user-study-round2/                 Round 2 reports, fixtures and screenshots
  references/                       Cited repository source snapshots and manifest
```

There are no symlinks or dependencies outside this directory needed to open the
walkthrough, local reports, or images. Compatibility redirects and links remain in
the original `docs/visualizations/` location, but are not needed when sharing this folder.

## Evidence and Limits

- The walkthrough is a proposal, not the production application. Its customer,
  contract, dimensions, messages, and construction drawing are fictional.
- The site photo is AI-generated and labeled as illustrative. It is not measured evidence.
- Edits and attached notes live only in browser memory. Reloading resets them.
  No files are uploaded, no WhatsApp account is accessed, and nothing is sent to the office.
- Pool and construction outlines are schematic. The demo does not approve safety,
  buildability, engineering, installation readiness, or regulatory compliance.
- Studies contain AI-agent simulations, not human usability studies. Existing-app
  observations, external research, and proposed changes retain their original labels.
- Repository files cited by reports are included as read-only `.txt` snapshots in
  `references/repository/`. They were captured during packaging, not reconstructed
  from an earlier audit revision. They are not a runnable copy of the application.
  [The manifest](references/source-manifest.json) records original paths, capture time,
  and SHA-256 hashes. Source-line fragments in citations refer to the cited line numbers.
- Lucide's license is included at `sales-journey/vendor/LUCIDE-LICENSE`.
  External product screenshots retain their original attribution in the reports.

## Verification

The package is checked from a relocated copy, with browser network access disabled
for local walkthrough/reports, including local links, images, and both regression suites.
Desktop checks cover 1280, 1440, 1600, and 1920 px. This is targeted testing, not a
full accessibility audit or installation-safety review.

To rerun the tests, use an existing Playwright installation and Chromium executable.
From this directory:

```sh
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright CHROME_PATH=/path/to/chrome node verify-package.cjs
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright CHROME_PATH=/path/to/chrome node sales-journey/review-regression.cjs
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright CHROME_PATH=/path/to/chrome node sales-journey/site-regression.cjs
```

Screenshot output defaults to `/tmp/bom-journey-regression` and
`/tmp/bom-site-regression`. Set `SCREENSHOT_DIR` to change the output directory.
