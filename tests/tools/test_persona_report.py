"""Collation is mechanical on purpose: severity is the refuter's judgment,
and the collator must not quietly promote an unconfirmed finding.

Run 2 moves the taxonomy off the finding and onto the verdict: a persona that
is told "jargon-leak" is a category goes looking for jargon, so personas write
free prose and the refuter classifies what it reproduced.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def write_persona(root: Path, persona: str, findings: list[dict],
                  verdicts: list[dict] | None, *, gave_up_at_step=None,
                  fallback: str = "אקסל") -> Path:
    """Findings carry prose only; taxonomy lives in verdicts.json."""
    d = root / persona
    d.mkdir(parents=True, exist_ok=True)
    (d / "findings.json").write_text(json.dumps({
        "persona": persona, "gave_up_at_step": gave_up_at_step,
        "fallback": fallback, "findings": findings,
    }, ensure_ascii=False), encoding="utf-8")
    if verdicts is not None:
        (d / "verdicts.json").write_text(
            json.dumps({"verdicts": verdicts}, ensure_ascii=False), encoding="utf-8")
    return d


def finding(fid: str, title: str, *, steps=(1,), shots=()) -> dict:
    return {"id": fid, "title": title,
            "what_happened": f"{title} — in the persona's own words",
            "steps": list(steps), "shots": list(shots)}


def verdict(fid: str, *, verdict: str = "CONFIRMED", severity: int = 3,
            blocks_job: bool = False, symptom: str = "jargon-leak",
            surface: str = "bom", note: str = "") -> dict:
    return {"finding_id": fid, "verdict": verdict, "severity": severity,
            "blocks_job": blocks_job, "symptom": symptom, "surface": surface,
            "note": note}


def seed(root: Path):
    """Two personas hit the same wall and describe it differently; a third
    finding is not reproducible."""
    write_persona(root, "expert", [finding("F1", "catalog code is untranslated")],
                  [verdict("F1", severity=3, blocks_job=True,
                           symptom="jargon-leak", surface="bom")])
    write_persona(root, "topology-author", [finding("F1", "codes I do not recognise")],
                  [verdict("F1", severity=2, blocks_job=False,
                           symptom="jargon-leak", surface="bom")])
    write_persona(root, "approver", [finding("F1", "no way back to the version")],
                  [verdict("F1", verdict="NOT-REPRODUCIBLE", severity=3,
                           blocks_job=True, symptom="not-found", surface="quotes")])


def test_taxonomy_comes_from_the_verdict_not_the_finding(tmp_path):
    """Personas write prose only. If collate ever read f["symptom"] again it
    would KeyError here rather than silently trusting a primed persona."""
    from persona_lab import report

    write_persona(tmp_path, "expert", [finding("F1", "the run editor lost my edit")],
                  [verdict("F1", severity=4, blocks_job=True,
                           symptom="data-loss", surface="run-editing")])

    out = report.collate(tmp_path)

    assert len(out["confirmed"]) == 1
    entry = out["confirmed"][0]
    assert (entry["surface"], entry["symptom"]) == ("run-editing", "data-loss")
    assert entry["severity"] == 4 and entry["blocks_job"] is True


def test_confirmed_findings_dedupe_across_personas(tmp_path):
    """Enum surfaces are what makes this merge: run 1's free text produced 48
    groups from 51 findings because personas named one screen three ways."""
    from persona_lab import report

    seed(tmp_path)
    out = report.collate(tmp_path)

    bom = [f for f in out["confirmed"] if f["surface"] == "bom"]
    assert len(bom) == 1
    assert sorted(bom[0]["personas"]) == ["expert", "topology-author"]
    assert bom[0]["findings"] == 2


def test_group_takes_its_title_from_the_highest_severity_member(tmp_path):
    """Whichever persona happened to be read first must not name the group."""
    from persona_lab import report

    write_persona(tmp_path, "aaa-first", [finding("F1", "mild wording nit")],
                  [verdict("F1", severity=1, symptom="jargon-leak", surface="bom")])
    write_persona(tmp_path, "zzz-last", [finding("F1", "BOM lines are unreadable Hebrew")],
                  [verdict("F1", severity=4, symptom="jargon-leak", surface="bom")])

    out = report.collate(tmp_path)

    assert out["confirmed"][0]["title"] == "BOM lines are unreadable Hebrew"
    assert out["confirmed"][0]["severity"] == 4


def test_unconfirmed_findings_never_enter_the_confirmed_list(tmp_path):
    from persona_lab import report

    seed(tmp_path)
    out = report.collate(tmp_path)

    assert all(f["surface"] != "quotes" for f in out["confirmed"])
    assert [h["title"] for h in out["hypotheses"]] == ["no way back to the version"]
    assert out["hypotheses"][0]["verdict"] == "NOT-REPRODUCIBLE"
    assert out["hypotheses"][0]["persona"] == "approver"


def test_finding_with_no_verdict_at_all_is_a_hypothesis(tmp_path):
    from persona_lab import report

    write_persona(tmp_path, "expert", [finding("F1", "the refuter never got here")], None)

    out = report.collate(tmp_path)

    assert out["confirmed"] == []
    assert out["hypotheses"][0]["verdict"] == "UNVERIFIED"


def test_blocking_findings_sort_above_higher_severity_non_blocking(tmp_path):
    from persona_lab import report

    write_persona(tmp_path, "measurer", [
        finding("A", "cannot place the last post"),
        finding("B", "the side view redraws slowly"),
    ], [
        verdict("A", severity=2, blocks_job=True, symptom="dead-end",
                surface="plan-canvas"),
        verdict("B", severity=4, blocks_job=False, symptom="slow",
                surface="side-view"),
    ], gave_up_at_step=5, fallback="סקיצה")

    out = report.collate(tmp_path)

    assert [f["surface"] for f in out["confirmed"]] == ["plan-canvas", "side-view"]


def test_off_enum_symptom_is_refused_loudly(tmp_path):
    """A typo'd symptom would split a dedupe group and quietly under-report
    how many personas hit the same wall — the opposite of what the report is for."""
    from persona_lab import report

    write_persona(tmp_path, "expert", [finding("A", "a")],
                  [verdict("A", symptom="jargon leak", surface="bom")])

    try:
        report.collate(tmp_path)
    except ValueError as exc:
        assert "jargon leak" in str(exc)
        assert "expert" in str(exc) and "A" in str(exc)
    else:
        raise AssertionError("off-enum symptom was silently accepted")


def test_off_enum_surface_is_refused_loudly(tmp_path):
    """Free-text surfaces are exactly what under-merged run 1."""
    from persona_lab import report

    write_persona(tmp_path, "expert", [finding("A", "a")],
                  [verdict("A", symptom="jargon-leak", surface="bom-tab")])

    try:
        report.collate(tmp_path)
    except ValueError as exc:
        assert "bom-tab" in str(exc)
        assert "expert" in str(exc) and "A" in str(exc)
    else:
        raise AssertionError("off-enum surface was silently accepted")


def test_missing_taxonomy_on_a_confirmed_verdict_is_refused(tmp_path):
    from persona_lab import report

    v = verdict("A")
    del v["surface"]
    write_persona(tmp_path, "expert", [finding("A", "a")], [v])

    try:
        report.collate(tmp_path)
    except ValueError as exc:
        assert "surface" in str(exc)
    else:
        raise AssertionError("a confirmed verdict with no surface was accepted")


def test_taxonomy_is_only_validated_on_confirmed_verdicts(tmp_path):
    """A refuted finding is not counted, so its taxonomy is not load-bearing;
    refusing it would only make the refuter's job noisier."""
    from persona_lab import report

    write_persona(tmp_path, "expert", [finding("A", "a")],
                  [{"finding_id": "A", "verdict": "REFUTED", "severity": 0,
                    "blocks_job": False, "note": "did not reproduce"}])

    out = report.collate(tmp_path)

    assert out["confirmed"] == []
    assert out["hypotheses"][0]["verdict"] == "REFUTED"


def test_render_reports_group_size_and_the_highest_severity_title(tmp_path):
    from persona_lab import report

    seed(tmp_path)
    text = report.render(report.collate(tmp_path), sha="abc1234")

    assert "catalog code is untranslated" in text
    assert "codes I do not recognise" not in text
    assert "| 2 |" in text  # two raw findings collapsed into one group


def test_render_marks_hypotheses_as_unconfirmed(tmp_path):
    from persona_lab import report

    seed(tmp_path)
    text = report.render(report.collate(tmp_path), sha="abc1234")

    assert "abc1234" in text
    assert "unconfirmed" in text.lower()
    assert "gave up" in text.lower()
    assert "no way back to the version" in text
    assert "## Limits" in text
