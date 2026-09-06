# Round 2: Salesperson Tasks and Existing Patterns

Date: 2026-09-06. This round investigates the salesperson's laptop workflow after a signed sale. No live quoting, office-engineering study or production redesign is included.

## Assignments

Seven independent assignments: three UI-only salesperson simulations and four primary-source research tracks. The runtime permitted six active agent threads, so the seventh assignment starts after one research slot is released; seven simultaneous agents are not claimed.

| Track | Question | Evidence method |
| --- | --- | --- |
| Source-driven entry | Can signed facts, a measured drawing and a later unapproved message be recorded without losing their meaning? | Fresh agent, isolated app 8831; supplied fictional source packet |
| Partial-stretch amendment | Can different heights and models along one stretch be revised without disturbing the rest? | Fresh agent, isolated app 8832; seeded 8 m + 5 m job |
| Resume two customer sites | Can a salesperson find and resume the correct job and retain correctly scoped promises? | Fresh agent, isolated app 8833; two same-name customer jobs |
| Fence products | How do fence-specific products capture layouts and sold scope? | Official product guides; marketing distinguished from demonstrated steps |
| Measured-editing guides | How are exact dimensions, endpoints, angles and local edits communicated? | Official interaction guides |
| Source capture | How are original sketches, photos and notes linked to a plan? | Official field-documentation guides |
| Open projects | Which existing projects provide useful patterns or reusable components? | Official repositories, documentation and licenses |

## Simulation Limits

Agents receive no prior findings, source access, APIs, databases or application runtime state. They may inspect rendered DOM and screenshots and use normal UI interactions with Playwright/Chrome at 1440 x 900. Each task is limited to 30 meaningful decisions and three sensible attempts at a blocked operation. Automation failures and screenshot timing problems must not be reported as product defects.

These are agent simulations, not human interviews, completion-rate estimates or evidence of preference. Different tasks are not aggregated into a percentage. Research documents other products' published behavior, not hands-on competitor usability trials. Suggested adaptations require testing with actual salespeople.

## Fixtures

The [source packet](source-packet.html) is fictional. Its diagram is explicitly not to scale. A later message requests a height change but does not establish approval. A photo is described, not supplied; attaching an actual photo cannot be claimed.

The amendment server uses a separate copy of round 1's office fixture database, retaining its original specifications and notes. Preparation is not counted as salesperson work. The other two servers use fresh seeded test databases. All use the stub AI. Production customer data and the existing application server are excluded.

Parent code checks, if performed, are labeled separately from participant observations. Raw reports remain independent and any qualifications are recorded in the synthesis.

## Completed Round

All seven assignments completed: Laplace (source entry), Nietzsche (amendment), Epicurus (resume), Singer (fence products), Carson (measured guides), Erdos (source capture), and Hume (open projects). The three simulations report 27, 27 and 30 task-level decisions respectively; these are agent-defined bounded task groups, not comparable timing or efficiency measures.

All seven agents were closed, and the three temporary app servers were stopped after collection. Application code and production customer data were not changed. The source-entry and resume reports explicitly distinguish their automation retries from product defects.

## Visualization Verification

The parent rendered the completed HTML with Playwright/Chrome. All three session selectors and their images worked; seven research patterns rendered; local links resolved. The partial-height example was checked for a middle interval with both complements retained, a whole-run replacement, invalid boundaries and invalid/empty input. SVG text stayed within its view box. Desktop widths of 1280, 1440, 1600 and 1920 pixels were checked without page-level horizontal overflow or JavaScript errors.

Rendered overview, session, research and range-example screenshots were visually inspected. Primary application screenshots and the attributed Fieldwire help image were also inspected. The full application automated test suite was not run; this was an observation/research/artifact task, not an application patch.
