"""act.py forces think-aloud: you may not act without saying what you expect,
and you may not act again without saying what you saw."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ACT = Path(__file__).resolve().parents[2] / "tools" / "persona_lab" / "act.py"


def run(run_dir: Path, *args):
    return subprocess.run(
        [sys.executable, str(ACT), "--session", str(run_dir), *args],
        capture_output=True, text=True,
    )


def seed(tmp_path: Path) -> Path:
    run_dir = tmp_path / "kablan-gderot"
    (run_dir / "shots").mkdir(parents=True)
    (run_dir / "session.json").write_text(json.dumps({
        "persona": "kablan-gderot", "port": 8800, "cdp_port": 9400,
        "ws_url": "ws://localhost:9400/devtools/page/FAKE", "target_id": "FAKE",
        "db": "/tmp/none.db", "server_pid": 0, "chrome_pid": 0,
        "run_dir": str(run_dir),
    }))
    return run_dir


def test_action_without_intent_is_refused(tmp_path):
    r = run(seed(tmp_path), "click", "e01", "--expected", "משהו")

    assert r.returncode == 2
    assert "intent" in (r.stderr + r.stdout).lower()


def test_action_without_expected_is_refused(tmp_path):
    r = run(seed(tmp_path), "click", "e01", "--intent", "משהו")

    assert r.returncode == 2
    assert "expected" in (r.stderr + r.stdout).lower()


def test_second_action_must_close_the_open_record(tmp_path):
    run_dir = seed(tmp_path)
    (run_dir / "trace.jsonl").write_text(json.dumps({
        "n": 1, "verb": "look", "arg": "", "intent": "a", "expected": "b",
        "observed": None, "confusion": None, "shot": "shots/01.jpg", "t_ms": 10,
    }) + "\n")

    r = run(run_dir, "click", "e01", "--intent", "c", "--expected", "d")

    assert r.returncode == 2
    assert "observed" in (r.stderr + r.stdout).lower()


def test_closing_patches_the_previous_record(tmp_path):
    run_dir = seed(tmp_path)
    (run_dir / "trace.jsonl").write_text(json.dumps({
        "n": 1, "verb": "look", "arg": "", "intent": "a", "expected": "b",
        "observed": None, "confusion": None, "shot": "shots/01.jpg", "t_ms": 10,
    }) + "\n")

    r = run(run_dir, "give-up", "--reason", "לא מצאתי", "--fallback", "אקסל",
            "--observed", "מסך עם קוד", "--confusion", "3")

    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in
             (run_dir / "trace.jsonl").read_text().splitlines() if x.strip()]
    assert lines[0]["observed"] == "מסך עם קוד"
    assert lines[0]["confusion"] == 3
    assert lines[-1]["verb"] == "give-up"


def test_confusion_must_be_in_range(tmp_path):
    run_dir = seed(tmp_path)
    (run_dir / "trace.jsonl").write_text(json.dumps({
        "n": 1, "verb": "look", "arg": "", "intent": "a", "expected": "b",
        "observed": None, "confusion": None, "shot": "shots/01.jpg", "t_ms": 10,
    }) + "\n")

    r = run(run_dir, "give-up", "--reason", "x", "--fallback", "y",
            "--observed", "z", "--confusion", "9")

    assert r.returncode == 2
