"""Collation is mechanical on purpose: severity is the refuter's judgment,
and the collator must not quietly promote an unconfirmed finding."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def seed(root: Path):
    for pid, fid, surface, symptom in [
        ("kablan-gderot", "F1", "bom-tab", "jargon-leak"),
        ("estimator", "F1", "bom-tab", "jargon-leak"),
        ("sales-rep", "F1", "toolbar", "not-found"),
    ]:
        d = root / pid
        d.mkdir(parents=True, exist_ok=True)
        (d / "findings.json").write_text(json.dumps({
            "persona": pid, "gave_up_at_step": 19, "fallback": "אקסל",
            "findings": [{"id": fid, "title": f"{surface} problem",
                          "surface": surface, "symptom": symptom,
                          "steps": [12], "shots": ["shots/12.jpg"]}],
        }, ensure_ascii=False), encoding="utf-8")
        verdict = "CONFIRMED" if surface == "bom-tab" else "NOT-REPRODUCIBLE"
        (d / "verdicts.json").write_text(json.dumps({
            "verdicts": [{"finding_id": fid, "verdict": verdict,
                          "severity": 3, "blocks_job": True, "note": ""}],
        }), encoding="utf-8")


def test_confirmed_findings_dedupe_across_personas(tmp_path):
    from persona_lab import report

    seed(tmp_path)
    out = report.collate(tmp_path)

    bom = [f for f in out["confirmed"] if f["surface"] == "bom-tab"]
    assert len(bom) == 1
    assert sorted(bom[0]["personas"]) == ["estimator", "kablan-gderot"]


def test_unconfirmed_findings_never_enter_the_confirmed_list(tmp_path):
    from persona_lab import report

    seed(tmp_path)
    out = report.collate(tmp_path)

    assert all(f["surface"] != "toolbar" for f in out["confirmed"])
    assert any(f["surface"] == "toolbar" for f in out["hypotheses"])


def test_blocking_findings_sort_above_higher_severity_non_blocking(tmp_path):
    from persona_lab import report

    d = tmp_path / "measurer"
    d.mkdir(parents=True)
    (d / "findings.json").write_text(json.dumps({
        "persona": "measurer", "gave_up_at_step": 5, "fallback": "סקיצה",
        "findings": [
            {"id": "A", "title": "a", "surface": "s1", "symptom": "dead-end",
             "steps": [1], "shots": []},
            {"id": "B", "title": "b", "surface": "s2", "symptom": "slow",
             "steps": [2], "shots": []},
        ]}, ensure_ascii=False), encoding="utf-8")
    (d / "verdicts.json").write_text(json.dumps({"verdicts": [
        {"finding_id": "A", "verdict": "CONFIRMED", "severity": 2,
         "blocks_job": True, "note": ""},
        {"finding_id": "B", "verdict": "CONFIRMED", "severity": 4,
         "blocks_job": False, "note": ""},
    ]}), encoding="utf-8")

    out = report.collate(tmp_path)

    assert [f["surface"] for f in out["confirmed"]] == ["s1", "s2"]


def test_render_marks_hypotheses_as_unconfirmed(tmp_path):
    from persona_lab import report

    seed(tmp_path)
    text = report.render(report.collate(tmp_path), sha="abc1234")

    assert "abc1234" in text
    assert "unconfirmed" in text.lower()
    assert "gave up" in text.lower()
