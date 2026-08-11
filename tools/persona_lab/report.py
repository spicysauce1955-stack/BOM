"""Join findings to verdicts, dedupe, sort, render. No judgment here.

Severity and blocks_job come from the refuter that reproduced the finding;
this module only arranges what it was given. Keeping it dumb is what stops a
persona from grading its own homework.
"""

from __future__ import annotations

import json
from pathlib import Path

SYMPTOMS = ["not-found", "wrong-language", "jargon-leak", "no-feedback",
            "dead-end", "data-loss", "wrong-value", "slow", "layout-broken"]


def collate(runs_root: Path) -> dict:
    confirmed: dict[tuple[str, str], dict] = {}
    hypotheses: list[dict] = []
    narratives: list[dict] = []

    for d in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        f_path, v_path = d / "findings.json", d / "verdicts.json"
        if not f_path.exists():
            continue
        found = json.loads(f_path.read_text(encoding="utf-8"))
        verdicts = {}
        if v_path.exists():
            verdicts = {v["finding_id"]: v
                        for v in json.loads(v_path.read_text(encoding="utf-8"))["verdicts"]}
        narratives.append({
            "persona": found["persona"],
            "gave_up_at_step": found.get("gave_up_at_step"),
            "fallback": found.get("fallback", ""),
        })
        for f in found["findings"]:
            v = verdicts.get(f["id"])
            if v is None or v["verdict"] != "CONFIRMED":
                hypotheses.append({**f, "persona": found["persona"],
                                   "verdict": (v or {}).get("verdict", "UNVERIFIED")})
                continue
            key = (f["surface"], f["symptom"])
            entry = confirmed.setdefault(key, {
                "surface": f["surface"], "symptom": f["symptom"],
                "title": f["title"], "personas": [], "steps": [], "shots": [],
                "severity": v["severity"], "blocks_job": v["blocks_job"],
                "note": v.get("note", ""),
            })
            entry["personas"].append(found["persona"])
            entry["steps"] += f.get("steps", [])
            entry["shots"] += f.get("shots", [])
            entry["severity"] = max(entry["severity"], v["severity"])
            entry["blocks_job"] = entry["blocks_job"] or v["blocks_job"]

    ordered = sorted(
        confirmed.values(),
        key=lambda e: (e["blocks_job"], e["severity"], len(e["personas"])),
        reverse=True,
    )
    return {"confirmed": ordered, "hypotheses": hypotheses, "narratives": narratives}


def render(collated: dict, sha: str) -> str:
    lines = [
        "# Persona lab — findings",
        "",
        f"Build under test: `{sha}`. Six personas drove the live app in a browser;",
        "each finding below was reproduced by an independent refuter before it was",
        "given a severity.",
        "",
        "## Where each persona gave up",
        "",
        "| Persona | Gave up at step | What they would do instead |",
        "|---|---|---|",
    ]
    for n in collated["narratives"]:
        lines.append(f"| {n['persona']} | {n['gave_up_at_step']} | {n['fallback']} |")

    lines += ["", "## Confirmed findings", "",
              "| # | Blocks job | Severity | Surface | Symptom | Personas | Steps |",
              "|---|---|---|---|---|---|---|"]
    for i, f in enumerate(collated["confirmed"], start=1):
        lines.append(
            f"| {i} | {'YES' if f['blocks_job'] else 'no'} | {f['severity']} | "
            f"{f['surface']} | {f['symptom']} | {', '.join(f['personas'])} | "
            f"{', '.join(str(s) for s in f['steps'])} |"
        )

    lines += ["", "## Hypotheses (unconfirmed — not evidence)", ""]
    if not collated["hypotheses"]:
        lines.append("None.")
    for h in collated["hypotheses"]:
        lines.append(f"- **{h['title']}** ({h['persona']}, {h['surface']}) — {h['verdict']}")

    lines += [
        "", "## Limits", "",
        "These are simulated users. They find mechanical dead ends, missing",
        "affordances and vocabulary mismatches. They cannot tell you whether a",
        "קבלן would trust a number enough to send it to a paying customer.",
        "",
    ]
    return "\n".join(lines)
