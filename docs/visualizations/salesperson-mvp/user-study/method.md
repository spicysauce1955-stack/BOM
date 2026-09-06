# Independent Agent User Sessions

Date: 2026-09-06.

## Purpose

Observe whether unfamiliar agents can complete realistic sales-entry, correction and receiving tasks through the existing UI, then compare the observed friction with established editing patterns. These are agent simulations, not interviews or usability results from real employees.

## Isolation

Four fresh agents were spawned without the parent conversation. They were told not to read application source, previous findings, visualizations, hidden state, databases or each other's reports. Only rendered text, accessibility information, visible geometry, screenshots and ordinary browser interactions were permitted.

Playwright and Chrome were supplied as interaction tools, not as a way to bypass the UI. Each agent used a separate application server/database and browser session. Existing customer data and port 8000 were excluded. The parent prepared scenario fixtures for correction and office review through setup APIs before the agents began; setup is not counted as agent completion.

| Agent | Role | Assigned task | Setup |
| --- | --- | --- | --- |
| Newton | First-time salesperson | Create signed job; draw 8 m + 5 m L, height 1.8 m, soil, Slat model, 1 m gate at 2 m; context and note | Fresh seeded app on 8821 |
| Mencius | Returning salesperson | Change street length 8 m to 8.4 m; preserve 5 m side; change side height to 1.6 m; move gate to 3 m; preserve/add notes; verify reload | Prepared project on 8822 |
| Dirac | Hebrew-first salesperson | Enter 600 cm fence, 180 cm height, masonry base top 40 cm, 100 cm gate at 200 cm; context, note and reopen | Fresh seeded app on 8823 |
| Mill | Office recipient | Reconstruct sold scope and promises; inspect assumptions; locate sources and handover state; seek clarification | Prepared generated project on 8824 |

Each agent received a limit of 30 meaningful decision steps and up to three sensible attempts at a blocked interaction. These limits are task boundaries, not human timing measurements. Raw reports and screenshots are retained in each role's directory.

## Interpretation

- Distinguish completed, partial and blocked tasks; do not equate a ready banner with successful task execution.
- Treat automation targeting failures separately from interaction design problems.
- Do not combine different scenarios into a human success rate or invent satisfaction scores.
- Strongest evidence: visible before/after states, exact entered values, persistence after reload, and a clear mismatch between task requirement and observed outcome.
- Candidate improvements remain hypotheses until tested with actual salespeople and office staff.

The parent performs separate follow-up verification where an agent report suggests a concrete bug. Such checks must be labeled as parent verification, not additional independent users.

## Artifact Verification

The parent rendered `sales-user-study.html` in Chrome with Playwright and checked all four role selectors, decoded screenshots, local navigation links, the relative/fixed gate and endpoint comparison, invalid numeric input, and desktop widths of 1280, 1440 and 1920 pixels. No JavaScript errors or page-level horizontal overflow were found. Screenshots of the rendered report and diagram were visually inspected. See [parent verification](verification.md) for the separately checked app behavior and screenshot caveats.

All four study agents were closed and the four temporary study servers were stopped after their reports were collected. The existing application server and customer data were not changed. This study did not run or modify the application's automated test suite.
