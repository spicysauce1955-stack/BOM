"""Join findings to verdicts, dedupe, sort, render. No judgment here.

Severity, blocks_job **and the taxonomy** come from the refuter that reproduced
the finding; this module only arranges what it was given. Keeping it dumb is
what stops a persona from grading its own homework.

Run 2 moved `symptom`/`surface` off the finding and onto the verdict. Naming the
symptom enum in a persona prompt primes the very findings we are counting — a
persona told "jargon-leak" is a category goes looking for jargon. Personas now
write free prose (`id`, `title`, `what_happened`, `steps`, `shots`) and the
refuter classifies what it could reproduce.
"""

from __future__ import annotations

import json
from pathlib import Path

SYMPTOMS = ["not-found", "wrong-language", "jargon-leak", "no-feedback",
            "dead-end", "data-loss", "wrong-value", "slow", "layout-broken"]

# Free-text surfaces under-merged run 1: 51 confirmed findings became 48 groups
# because personas named the same screen three different ways.
SURFACES = ["plan-canvas", "side-view", "toolbar", "inspector", "run-editing",
            "annotations", "knowledge", "review-queue", "bom", "quotes",
            "inventory", "header", "warnings", "whole-app"]


def _checked(value: object, allowed: list[str], field: str,
             persona: str, finding_id: str) -> str:
    """Dedupe is keyed on (surface, symptom), so an off-enum value would
    silently split a group and under-report how many personas hit the same
    thing. Refusing it loudly is schema validation, not judgment."""
    if value not in allowed:
        raise ValueError(
            f"{persona} finding {finding_id}: verdict {field} {value!r} "
            f"is not one of {allowed}"
        )
    return str(value)


def collate(runs_root: Path) -> dict:
    confirmed: dict[tuple[str, str], dict] = {}
    hypotheses: list[dict] = []
    narratives: list[dict] = []

    for d in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        f_path, v_path = d / "findings.json", d / "verdicts.json"
        if not f_path.exists():
            continue
        found = json.loads(f_path.read_text(encoding="utf-8"))
        persona = found["persona"]
        verdicts = {}
        if v_path.exists():
            verdicts = {v["finding_id"]: v
                        for v in json.loads(v_path.read_text(encoding="utf-8"))["verdicts"]}
        narratives.append({
            "persona": persona,
            "gave_up_at_step": found.get("gave_up_at_step"),
            "fallback": found.get("fallback", ""),
        })
        for f in found["findings"]:
            v = verdicts.get(f["id"])
            if v is None or v["verdict"] != "CONFIRMED":
                hypotheses.append({**f, "persona": persona,
                                   "verdict": (v or {}).get("verdict", "UNVERIFIED")})
                continue
            # Only a confirmed verdict's taxonomy is load-bearing: it is what
            # gets counted, so it is what gets validated.
            symptom = _checked(v.get("symptom"), SYMPTOMS, "symptom", persona, f["id"])
            surface = _checked(v.get("surface"), SURFACES, "surface", persona, f["id"])

            key = (surface, symptom)
            entry = confirmed.setdefault(key, {
                "surface": surface, "symptom": symptom,
                "title": f["title"], "personas": [], "findings": 0,
                "steps": [], "shots": [], "notes": [],
                "severity": v["severity"], "blocks_job": v["blocks_job"],
            })
            # The loudest member names the group; whichever persona happened to
            # be read first must not.
            if v["severity"] > entry["severity"]:
                entry["title"] = f["title"]
            entry["findings"] += 1
            if persona not in entry["personas"]:
                entry["personas"].append(persona)
            entry["steps"] += f.get("steps", [])
            entry["shots"] += f.get("shots", [])
            if v.get("note"):
                entry["notes"].append(v["note"])
            entry["severity"] = max(entry["severity"], v["severity"])
            entry["blocks_job"] = entry["blocks_job"] or v["blocks_job"]

    ordered = sorted(
        confirmed.values(),
        key=lambda e: (e["blocks_job"], e["severity"], e["findings"]),
        reverse=True,
    )
    return {"confirmed": ordered, "hypotheses": hypotheses, "narratives": narratives}


def render(collated: dict, sha: str) -> str:
    lines = [
        "# Persona lab — findings",
        "",
        f"Build under test: `{sha}`. Personas drove the live app in a browser and",
        "described what happened in their own words; an independent refuter",
        "reproduced each finding before giving it a severity, a symptom and a",
        "surface. The personas never saw those categories.",
        "",
        "## Where each persona gave up",
        "",
        "| Persona | Gave up at step | What they would do instead |",
        "|---|---|---|",
    ]
    for n in collated["narratives"]:
        lines.append(f"| {n['persona']} | {n['gave_up_at_step']} | {n['fallback']} |")

    lines += ["", "## Confirmed findings", "",
              "| # | Blocks job | Severity | Surface | Symptom | Findings | Personas | Title | Steps |",
              "|---|---|---|---|---|---|---|---|---|"]
    for i, f in enumerate(collated["confirmed"], start=1):
        lines.append(
            f"| {i} | {'YES' if f['blocks_job'] else 'no'} | {f['severity']} | "
            f"{f['surface']} | {f['symptom']} | {f['findings']} | "
            f"{', '.join(f['personas'])} | {f['title']} | "
            f"{', '.join(str(s) for s in f['steps'])} |"
        )

    lines += ["", "## Hypotheses (unconfirmed — not evidence)", ""]
    if not collated["hypotheses"]:
        lines.append("None.")
    for h in collated["hypotheses"]:
        lines.append(f"- **{h['title']}** ({h['persona']}) — {h['verdict']}")

    lines += [
        "", "## Limits", "",
        "These are simulated users. They find mechanical dead ends, missing",
        "affordances and vocabulary mismatches. They cannot tell you whether a",
        "קבלן would trust a number enough to send it to a paying customer.",
        "",
    ]
    return "\n".join(lines)
