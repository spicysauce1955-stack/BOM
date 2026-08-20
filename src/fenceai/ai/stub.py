"""Deterministic stub implementations of the AI ports (ADR-0009).

A small keyword table — deliberately capped so it never becomes a second rule engine.
Powers the offline demo and all unit tests; byte-stable output.
"""

from __future__ import annotations

import re

from fenceai.ai.records import CandidateIntent, CritiqueNote, InterpretationRecord
from fenceai.knowledge.model import AddNote, KnowledgeVersion
from fenceai.learning.model import Correction
from fenceai.project.model import Annotation
from fenceai.strategy.model import GenerationResult

_MM_IN_TEXT = re.compile(r"(\d{3,4})\s*(?:mm)?")


class StubInterpreter:
    interpreter_id = "stub"

    def interpret(self, annotation: Annotation) -> InterpretationRecord:
        text = annotation.text
        lower = text.lower()
        # record ordinal is part of every intent id so re-interpretation never
        # collides with earlier records (final architecture review, finding 3)
        rec_no = len(annotation.interpretations) + 1
        candidates: list[CandidateIntent] = []
        unparsed: list[str] = []

        # Hebrew demo vocabulary (capped — mirrors the English set only, UI v2 §4):
        # ליישר/יישר + עם -> top_line; גובה -> height_intent; פרטיות -> privacy;
        # עמוד + כאן/בתחנה -> post_request; בערך/בסביבות hedge like approx/about.
        he_top = "יישר" in text and "עם" in text
        he_height = "גובה" in text
        hedged = any(k in lower for k in ("approx", "about")) or any(
            k in text for k in ("בערך", "בסביבות")
        )

        if any(k in lower for k in ("top", "align", "level with", "height")) or he_top or he_height:
            m = _MM_IN_TEXT.search(lower)
            if m and (any(k in lower for k in ("align", "level", "top")) or he_top):
                candidates.append(
                    CandidateIntent(
                        id=f"intent_{annotation.id}_{rec_no}_1",
                        kind="top_line",
                        params={"mode": "level", "z_mm": int(m.group(1))},
                        source_text=text,
                        confidence="medium" if hedged else "high",
                        ambiguity_note=(
                            "approximate value in source text" if hedged else None
                        ),
                    )
                )
            elif m:
                candidates.append(
                    CandidateIntent(
                        id=f"intent_{annotation.id}_{rec_no}_1",
                        kind="height_intent",
                        params={"height_mm": int(m.group(1))},
                        source_text=text,
                        confidence="medium" if hedged else "high",
                        ambiguity_note=(
                            "approximate value in source text" if hedged else None
                        ),
                    )
                )
            else:
                unparsed.append(text)
        elif "privacy" in lower or "פרטיות" in text:
            candidates.append(
                CandidateIntent(
                    id=f"intent_{annotation.id}_{rec_no}_1",
                    kind="height_intent",
                    params={"height_mm": 1800},
                    source_text=text,
                    confidence="low",
                    ambiguity_note="'privacy' mapped to default privacy height 1800",
                )
            )
        elif ("post" in lower and any(k in lower for k in ("here", "at "))) or (
            "עמוד" in text and any(k in text for k in ("כאן", "בתחנה"))
        ):
            m = _MM_IN_TEXT.search(lower)
            candidates.append(
                CandidateIntent(
                    id=f"intent_{annotation.id}_{rec_no}_1",
                    kind="post_request",
                    params={"station_mm": int(m.group(1))} if m else {},
                    source_text=text,
                    confidence="medium" if m else "low",
                    ambiguity_note=None if m else "no station given",
                )
            )
        else:
            unparsed.append(text)

        return InterpretationRecord(
            id=f"interp_{annotation.id}_{rec_no}",
            annotation_id=annotation.id,
            interpreter=self.interpreter_id,
            candidates=candidates,
            unparsed_spans=unparsed,
        )


class StubProposer:
    interpreter_id = "stub"

    # The one demo pattern this stub knows, in both demo languages (capped on
    # purpose — the stub must not become a second rule engine). The Hebrew stem
    # יסוד covers יסודות / היסוד / ליסוד by substring; casefolding is a no-op on it.
    FOUNDATION_WORDS = ("foundation", "יסוד")

    def propose(self, corrections: list[Correction]) -> list[KnowledgeVersion]:
        """One narrow-scope proposed heuristic per repeated correction pattern.

        The stub recognizes the demo pattern: posts moved onto existing foundations.
        """
        foundation_corrections = [
            c for c in corrections
            if any(w in (c.comment or "").lower() for w in self.FOUNDATION_WORDS)
        ]
        if not foundation_corrections:
            return []
        example = foundation_corrections[0]
        return [
            KnowledgeVersion(
                object_id=f"K-CAND-{example.id}",
                version=1,
                type="candidate",
                title="Prefer existing foundation points for posts (candidate)",
                title_i18n={"he": "העדפת יסודות קיימים למיקום עמודים (מועמד)"},
                scope={"project_id": example.project_id},  # narrowest scope by default
                actions=[AddNote(text="Prefer snapping posts to existing foundations within 300 mm")],
                source_text=example.comment or "",
                # The correction ids AND the decisions they were made about. A
                # candidate born from an argument about a specific decision kept
                # no link to it, which is the one place the decision graph is the
                # natural evidence for a proposed rule — a reviewer asking "what
                # was this about" had only the sentence. A ref is meaningful only
                # inside its own run (`core/ids.py`), so the run is carried with
                # it rather than the bare id.
                derived_from=[c.id for c in foundation_corrections]
                + sorted({f"{c.generation_run_id}#{c.decision_ref}"
                          for c in foundation_corrections if c.decision_ref}),
                attributed_to=f"proposer:{self.interpreter_id}",
                status="proposed",
            )
        ]


class StubCritic:
    interpreter_id = "stub"

    def critique(self, result: GenerationResult) -> list[CritiqueNote]:
        notes: list[CritiqueNote] = []
        for span in result.strategy.spans:
            if span.width_mm < 500:
                notes.append(
                    CritiqueNote(
                        element_refs=[span.id],
                        severity="warning",
                        text=f"Span {span.id} is only {span.width_mm} mm wide — check buildability.",
                        code="narrow_span",
                        params={"span_id": span.id, "width_mm": span.width_mm},
                    )
                )
        return notes
