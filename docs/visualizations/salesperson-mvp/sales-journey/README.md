# Salesperson walkthrough

Open `../index.html` directly in a browser. No server or build is required.

This is a proposed, interactive storyboard, not the production application. Sam Example,
the address, measurements, contract, signed sketch, amendment, and customer message are fictional.
The site photo is AI-generated and explicitly labeled as illustrative, not measured evidence.
Chapter navigation prepares untouched example states; user drafts are retained separately
from saved facts and flagged in review. Edits live only in memory. Reloading resets
the example. No files are uploaded and no office handover is actually sent.

The six chapters show sources, measured layout entry, saved stretch details, a partial
height change, numeric gate placement, and a human-review package. The gate arrow shows
opening direction only; hinge side remains unresolved.

The office package now displays saved specifications, plan/elevation snapshots, and
six inspectable source records. Unsaved drafts are excluded and reported as open items.
Plan zoom uses a scrollable viewport; it is explicitly scoped to the plan, not the
unfolded elevations. The illustrative house is a reference, not a measured building.

The extended fictional scenario has an existing soil-supported street stretch and a
side stretch on a planned 600 mm masonry wall. The side ground rises 300 mm according
to an illustrative construction drawing, revision 3; finished levels remain unconfirmed.
This new scenario does not replace the archived research fixtures.

Ground, Base and Fence tabs separately edit local rise/steps, soil/concrete/wall support,
base-top shape and height, and fence-top intent. Step locations are entered in metres;
their internal proportions follow stretch-length edits. The side view is an illustrative
profile, not an engineered panel or footing calculation. A level/stepped fence top uses
the entered fence height as a minimum above its base. Unknown ground is dashed and flagged.

Site controls cover current/planned construction, work area, final-level confirmation,
pool status, fence relationship, affected components and the next site action. Reference
outlines are schematic, not measured pool or house geometry. Pool-enclosure intent is
flagged for office review and never treated as safety approval.

Notes can be attached to the job, a stretch, the selected range, the gate or pool.
Type, status and optional supporting source are retained. Range notes retain the interval
recorded at attachment time. The Message source is copied example text originating from
WhatsApp, not a WhatsApp integration. Notes never modify the signed facts automatically.

The previous research report is preserved at `../sales-study-round2-evidence.html`.
The current-app comparison links to existing screenshot evidence. None of the proposed
controls or bug fixes in this storyboard have been implemented in the application.

Verified with Chromium/Playwright at desktop widths 1280, 1440, 1600, and 1920:
chapter navigation, drawing, saved details, range and gate validation, package review,
source dialogs, zoom, local links, horizontal overflow, and browser console errors.

`review-regression.cjs` adds draft recovery, restore behavior, source access, package
contents, focus retention, dialog names, selection and geometric regression checks.
`site-regression.cjs` additionally checks profile validation/rendering, planned conditions,
site drafts, pool review flags, scoped notes and measured-versus-planned handover content.
Run with an available Playwright installation and Chromium executable:

```sh
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright CHROME_PATH=/path/to/chrome node docs/visualizations/salesperson-mvp/sales-journey/review-regression.cjs
```

Screenshots are written to `/tmp/bom-journey-regression`, or `SCREENSHOT_DIR` when set.
No app dependencies, production files, or original research artifacts were changed.

Icons are vendored from lucide 0.468.0; see `vendor/LUCIDE-LICENSE`.
