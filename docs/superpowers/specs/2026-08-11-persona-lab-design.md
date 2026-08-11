# Persona lab design — "six real users try to do their job"

Approved by user 2026-08-11 (brainstorm session). Research basis: two Tavily research
passes — (a) synthetic-persona / LLM-agent usability testing methodology 2025–26
(MeasuringU's critical review of synthetic users, WebProber, UXAgent, browser-use
agent→Playwright loop patterns, JSON-schema-constrained agent output, HITL guardrails);
(b) who actually does fence estimating and BOM work in Israel (roles, field workflows,
tooling, catalog and כתב כמויות conventions, permit thresholds).

The goal is **not** a test suite. It is a repeatable evaluation harness that answers one
question: *can a non-technical person in a real fence-trade role get their job done with
this app, and where exactly do they give up?*

Decisions from brainstorm:
- Personas drive the **real browser** over CDP. No static-screenshot critique.
- **Five Hebrew personas + one English control.** The product is Hebrew-first RTL;
  testing it in English would measure the wrong product. The single English persona
  exists to separate "RTL bug" from "usability bug".
- Output is a **report plus a ranked backlog**. No code changes in this cycle.
- Every finding is a hypothesis until an independent **refuter** reproduces it.

## 1. Why this shape

The methodology research is blunt about how these exercises fail: hallucinated findings,
erratic navigation, and sycophancy. Practitioner and peer sources converge on the same
controls — the agent perceives only rendered UI, emits a structured per-step trace, and
its findings are treated as hypotheses requiring independent reproduction. Every design
choice below traces to one of those three controls. Where we cannot enforce a control
mechanically, §4.4 says so rather than implying more rigor than exists.

The domain research supplies the roles and the jobs. These personas are not invented:
the Israeli fence trade runs on phone photos, tape and laser measurements, hand sketches,
Excel or PDF quotes sent over WhatsApp, and supplier catalog codes (Ysteel, ATIR, BNH).
That workflow — not a competitor product — is the bar this app has to clear, and it is
what a persona falls back to when it gives up.

## 2. Components

```
tools/cdp.py                       Cdp class, moved verbatim out of ui_smoke.py
tools/persona_lab/
  driver.py                        perception + action; user-plausible verbs only
  act.py                           the CLI a persona agent shells out to
  outline.py                       DOM → labelled handle outline
  run.py                           --setup / --teardown for isolated per-persona stacks
  personas/*.json                  persona definitions (schema-validated)
  scenarios/*.md                   job briefs, one per persona
  report.py                        mechanical collation: joins findings to verdicts,
                                   dedupes by (surface, symptom), sorts, renders markdown
tests/tools/test_persona_driver.py thin harness self-test
<scratchpad>/persona-lab/<date>/<persona>/
  session.json  trace.jsonl  shots/NN.png  findings.json
```

Run artifacts live in the scratchpad, **not** the repo — persona agents are told they
may read only that directory, and keeping it outside the tree makes an accidental repo
read visible in the transcript audit (§4.4).

### 2.1 The one change to existing code

`Cdp` moves from `tools/ui_smoke.py` into `tools/cdp.py`; `ui_smoke.py` imports it. The
class is copied unchanged — no signature or behavior edits. `tools/ui_smoke.py` is the
release gate, so **34/34 smoke checks must still pass after the move**, and that is the
first verifiable step of the implementation plan, before any persona code exists.

## 3. The driver — what a persona is allowed to perceive

This is the part that decides whether findings are real, so it is the strictest part of
the design.

### 3.1 Verbs

`look`, `click`, `type`, `key`, `drag`, `hover`, `scroll`, `wait`. That is the whole
vocabulary. There is deliberately **no `js()`, no `fetch`, no API call, and no DB read**.
If a persona wants to know whether their work saved, they must find out the way a קבלן
would: look at the screen.

### 3.2 Handles, not selectors

`look` returns a downscaled screenshot path plus an outline built from **visible labels
only**, with opaque handles:

```
[e07] button  "✏️ צייר"
[e08] button  icon:"🚪"  tooltip-on-hover
[e14] button  "⚙ צור אסטרטגיה"
[e21] input   placeholder:"שם פרויקט חדש"
[e33] canvas  "plan" 900x500 at (312,148)
```

Never `#btn-generate`. An internal id encodes the developer's intent, which is exactly
the information a real user does not have; leaking it is the main way these exercises
produce falsely reassuring results. Handles are assigned per `look` in document order
and are valid only until the next `look`.

Icon-only controls expose their glyph and are marked `tooltip-on-hover`; the tooltip text
is revealed only by an actual `hover` call. Discoverability of icon-only tools is a real
question for this UI, and this keeps it a question rather than answering it for free.

`click` accepts a handle (`e07`) or a screen coordinate. Coordinates matter because the
plan canvas and profile SVG are the heart of the product and cannot be operated by
handle — a persona aims at the picture, like a person does. Screenshots carry a light
coordinate ruler along the edges so aiming is possible without world-mm math.

### 3.3 Session model

`act.py` is invoked once per action and must not lose the browser between calls. It reads
`session.json` (CDP port + target id), opens a websocket to the **already-open tab**, acts,
appends to `trace.jsonl`, and exits. The tab, the server, and all app state persist across
invocations. This keeps the agent-facing interface a plain shell command while the browser
stays live.

### 3.4 Trace record

Every `act.py` call appends one line. The agent must supply the reasoning fields; `act.py`
rejects the call if they are missing, which is what forces think-aloud rather than
silent clicking:

```json
{"n": 12, "verb": "click", "arg": "e14",
 "intent": "אני רוצה לראות את הכמויות",
 "expected": "רשימת חומרים",
 "observed": "נפתחה טבלה עם עמודה באנגלית 'run_id'",
 "confusion": 2,
 "shot": "shots/12.png", "t_ms": 1732}
```

`confusion` is 0–3. Any step at ≥2 becomes a finding candidate. `t_ms` accumulates into
time-on-task, which is the metric the sales-rep scenario actually turns on.

## 4. Personas, scenarios, protocol

### 4.1 Persona definition

Schema-validated JSON, one file per persona. Fields exist because the research named
them as the attributes that change behavior:

```json
{
  "id": "kablan-gderot",
  "role_he": "קבלן גדרות",
  "locale": "he",
  "tech_literacy": "low",
  "context": "בשטח, טלפון ביד, מדד לייזר, סקיצה על נייר",
  "goal": "להוציא הצעת מחיר ללקוח היום",
  "vocabulary": ["גדר רשת", "עמוד", "חגורת בטון", "שער", "מטר רץ"],
  "fallback_today": "אקסל + וואטסאפ",
  "quit_triggers": ["מסך שנראה כמו קוד", "יותר מ-3 ניסיונות באותו מקום"],
  "success": "מספר סופי שאפשר לשלוח ללקוח"
}
```

### 4.2 The roster

| Persona | Locale | Scenario | The question it answers |
|---|---|---|---|
| קבלן גדרות, crew lead | he | 42 m mesh fence, one corner, sloped ground, one 3.5 m gate → a quote to send today | Does he ever find "Generate strategy" at all? |
| Estimator / כתב כמויות | he | 180 m municipal tender; needs חגורת בטון and post lines that match catalog codes | Do BOM lines map to procurable items? |
| Sales rep at a homeowner | he | 15-minute visit, 1.50 m permit question, quote before leaving | Time-to-first-quote |
| Procurement / warehouse | he | Turn an accepted quote into an order list; check remnants and inventory | Is a quote actionable downstream? |
| Field measurer | he | Site with a retaining wall and a step in the base | Is base-top editing discoverable? |
| Export engineer (control) | **en** | The same job as persona 1, in English | Splits RTL bugs from real usability bugs |

Every persona starts where a genuine new user starts: a fresh DB, which opens into the
seeded sample project with the getting-started checklist. First-run experience is part of
what is under test, so it is not bypassed.

### 4.3 Run protocol

One subagent per persona, dispatched in parallel, each on an isolated stack (own port,
own throwaway DB, own Chrome instance) so a crash or a stray mutation cannot cross
personas. `run.py --setup` boots the stacks and writes each `session.json`;
`run.py --teardown` kills them and asserts every port is released.

Rules carried in the persona system prompt:

- **Step budget 30.** On exhaustion the persona writes up where it stood.
- **Give-up rule.** Quit when a real person in that role would quit, record the step at
  which it happened, and record what they would do instead (Excel + WhatsApp). The
  give-up point is the single most informative output of a run — more than any
  individual finding.
- **Anti-sycophancy clause**, verbatim in the prompt: *"You are not reviewing software.
  You are trying to finish a job you are paid for. Do not praise. Do not speculate about
  what the designers intended. Do not describe features you did not personally use."*
  The research names over-agreeableness as the dominant failure mode of this technique.
- **Non-technical stance as a detector.** The persona does not know what JSON is. Hitting
  a raw-JSON textarea, a bare `run_id`, an untranslated English string, or a millimetre
  integer where the trade speaks in metres is automatically a finding.
- **No repo access.** The persona may read only its own scratchpad run directory.

### 4.4 Honest limits of enforcement

The no-repo-access rule is enforced by prompt and by post-hoc transcript audit, **not by
a sandbox**. A project-wide permissions deny-list would also blind the main session, so
it is not used. Two things make this acceptable: run artifacts live outside the repo, so
any repo read stands out in the audit; and the refuter pass (§5) independently re-derives
each finding from the UI, so a finding that could only have come from reading source
fails to reproduce and is discarded. The audit step is a required item in the run
checklist, not an optional one.

## 5. Verification

Findings from a persona are **hypotheses**. A refuter agent — a separate subagent, with
repo access, adversarially prompted to *disprove* — replays the cited steps in a fresh
browser and returns one verdict per finding:

- `CONFIRMED` — reproduced from the UI alone.
- `NOT-REPRODUCIBLE` — the described behavior did not occur.
- `MISREAD-UI` — the behavior occurred but the persona misread it (still interesting:
  a systematic misread is itself a usability finding, and is re-filed as one).

Only `CONFIRMED` findings receive a severity. This pass is the control that separates the
exercise from a machine generating plausible complaints; if the run has to be cut for
cost, personas get cut before verification does.

Severity is Nielsen 0–4 (0 not a problem, 1 cosmetic, 2 minor, 3 major, 4 catastrophe),
plus a boolean `blocks_job` — because a cosmetic-looking issue that stops a קבלן from
sending a quote outranks a major-looking one that does not. Severity is judgment, so the
**refuter assigns it** as part of its verdict, in the same pass that reproduced the
finding; `report.py` only collates and sorts what the refuters returned. No agent rates
the severity of a finding it authored.

## 6. Output

`docs/reviews/persona-lab-2026-08-11.md`:

1. **Per-persona narrative** — what they were trying to do, the path they took, and the
   step where they gave up.
2. **Confirmed findings** — severity, `blocks_job`, persona, and a citation of
   `trace.jsonl` step number plus screenshot.
3. **Hypotheses** — findings that failed refutation, listed separately and explicitly
   labelled as unconfirmed, so a later reader cannot mistake them for evidence.
4. **Ranked backlog** — deduped across personas, ordered by `blocks_job` then severity
   then persona count.
5. **Limits section** — see §8, restated in the report itself.

## 7. Testing the harness

`tests/tools/test_persona_driver.py` (pytest, skipped when `google-chrome` is absent, so
CI stays browser-free per the existing convention): boots a stack, asserts `look` returns
a non-empty outline with visible labels and no `#`-selectors, asserts click-by-handle
changes the visible screen, and asserts `act.py` rejects a call missing `intent` or
`expected`. Plus the standing gate: `tools/ui_smoke.py` still reports 34/34 after the
`Cdp` move.

## 8. Non-goals and limits

- **No code changes.** This cycle produces evidence. Fixing is a separate, approved cycle.
- **This is not a substitute for human research.** Simulated users find mechanical dead
  ends, missing affordances, and vocabulary mismatches. They cannot tell you whether a
  קבלן would *trust* a number enough to send it to a paying customer, whether the price
  is credible, or whether the app is worth switching to. Every source in the methodology
  research is explicit on this point, and the report states it in its own voice rather
  than leaving it implied.
- **Cost is real.** Six personas at roughly thirty screenshots each is a heavyweight run.
  Screenshots are downscaled and the step budget is fixed. This is a milestone activity,
  not something to fire casually.
- **Findings are a snapshot** of the build they ran against. The report records the git
  SHA so a later reader knows what was tested.
