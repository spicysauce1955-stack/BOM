#!/usr/bin/env python3
"""The persona's only tool.

Invoked once per action. Reads session.json, attaches to the already-open tab,
acts, appends to trace.jsonl, prints the new screen, exits. The browser holds
the state between calls, which is what lets a persona agent work through a
plain shell command.

Every action demands --intent and --expected before it happens, and --observed
plus --confusion for the action before it. That is not bookkeeping: it is what
turns clicking into think-aloud, and confusion >= 2 is what becomes a finding.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BROWSER_VERBS = {"look", "click", "type", "key", "drag", "hover", "scroll",
                 "wait", "move"}
BOOKKEEPING_VERBS = {"give-up", "finding", "done"}

# how many positional arguments each verb needs before it can act
ARITY = {"look": 0, "click": 1, "type": 1, "key": 1, "drag": 4,
         "hover": 1, "scroll": 1, "wait": 1, "move": 2}

# Perception is not an action — real users look constantly. Run 1 spent a
# third of its 30-step budget on looking and measured the first three minutes
# of a first-ever session.
ACTION_BUDGET = 60
FREE_VERBS = {"look"}


def load_trace(run_dir: Path) -> list[dict]:
    path = run_dir / "trace.jsonl"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_trace(run_dir: Path, records: list[dict]) -> None:
    (run_dir / "trace.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def die(msg: str) -> None:
    print(f"REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _is_point(args: list[str]) -> bool:
    """click may be aimed at a handle (e07) or at plain viewport pixels (x y)."""
    return len(args) >= 2 and args[0].isdigit() and args[1].isdigit()


def main() -> int:
    p = argparse.ArgumentParser(prog="act.py")
    p.add_argument("--session", required=True, type=Path)
    p.add_argument("verb")
    p.add_argument("args", nargs="*")
    p.add_argument("--intent", default=None)
    p.add_argument("--expected", default=None)
    p.add_argument("--observed", default=None)
    p.add_argument("--confusion", default=None, type=int)
    p.add_argument("--reason", default=None)
    p.add_argument("--fallback", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--surface", default=None)
    p.add_argument("--symptom", default=None)
    p.add_argument("--steps", default="")
    a = p.parse_args()

    run_dir: Path = a.session
    if a.verb not in BROWSER_VERBS | BOOKKEEPING_VERBS:
        die(f"unknown verb {a.verb!r}")

    records = load_trace(run_dir)

    # close the previous record before anything new may happen
    if records and records[-1].get("observed") is None:
        if a.observed is None:
            die("the previous step is still open — pass --observed to say what you saw")
        if a.confusion is None:
            die("pass --confusion 0-3 for the previous step")
        if not 0 <= a.confusion <= 3:
            die("--confusion must be 0, 1, 2 or 3")
        records[-1]["observed"] = a.observed
        records[-1]["confusion"] = a.confusion

    if a.verb in BROWSER_VERBS:
        if not a.intent:
            die("--intent is required: say what you are trying to do, in role")
        if not a.expected:
            die("--expected is required: say what you think will happen")
        if len(a.args) < ARITY[a.verb]:
            die(f"{a.verb} needs {ARITY[a.verb]} argument(s), got {len(a.args)}")

    n = len(records) + 1
    spent = sum(1 for r in records if r.get("verb") not in FREE_VERBS)
    action_n = spent if a.verb in FREE_VERBS else spent + 1
    t0 = time.time()
    shot = ""
    screen = ""

    if a.verb in BROWSER_VERBS:
        from persona_lab import driver  # imported late so bookkeeping needs no browser

        session = json.loads((run_dir / "session.json").read_text(encoding="utf-8"))
        d = driver.Driver(session)
        # only aiming at a named handle needs the live page read first; every
        # other verb carries its own target, so one look (the one after the
        # action) is enough
        aims_by_handle = a.verb == "hover" or (a.verb == "click" and not _is_point(a.args))
        if aims_by_handle:
            d.look(f"{n:02d}-pre.jpg")

        if a.verb == "click":
            d.click((int(a.args[0]), int(a.args[1])) if _is_point(a.args) else a.args[0])
        elif a.verb == "type":
            d.type_text(a.args[0])
        elif a.verb == "key":
            d.key(a.args[0])
        elif a.verb == "drag":
            d.drag(*(int(v) for v in a.args[:4]))
        elif a.verb == "hover":
            tip = d.hover(a.args[0])
            screen = f"tooltip: {tip}"
        elif a.verb == "move":
            d.move(int(a.args[0]), int(a.args[1]))
        elif a.verb == "scroll":
            d.scroll(int(a.args[0]))
        elif a.verb == "wait":
            d.wait(float(a.args[0]))
        shot, seen = d.look(f"{n:02d}.jpg")
        # hover's tooltip is the point of the verb — keep it above the outline
        screen = f"{screen}\n{seen}" if screen else seen
        d.close()

    record = {
        "n": n, "action_n": action_n, "verb": a.verb, "arg": " ".join(a.args),
        "intent": a.intent, "expected": a.expected,
        "observed": None, "confusion": None,
        "shot": shot, "t_ms": int((time.time() - t0) * 1000),
    }
    if a.verb == "give-up":
        record.update(reason=a.reason, fallback=a.fallback, observed="", confusion=3)
    if a.verb == "finding":
        record.update(title=a.title, surface=a.surface, symptom=a.symptom,
                      steps=a.steps, observed="", confusion=0)
    if a.verb == "done":
        record.update(observed="", confusion=0)

    records.append(record)
    write_trace(run_dir, records)

    print(f"step {n} recorded")
    print(f"actions {action_n}/{ACTION_BUDGET} (look is free)")
    if shot:
        print(f"screenshot: {shot}")
    if screen:
        print("--- screen ---")
        print(screen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
