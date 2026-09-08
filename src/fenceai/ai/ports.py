"""AI capability ports (ADR-0009). Domain types in, domain types out — no prompt
strings in signatures. Implementations: stub (default, deterministic) and claude."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from fenceai.ai.records import CritiqueNote, InterpretationRecord

if TYPE_CHECKING:
    from fenceai.agent.proposal import TaskResult
    from fenceai.agent.tasks import TaskSpec
    from fenceai.agent.view import AgentView
    from fenceai.knowledge.model import KnowledgeVersion
    from fenceai.learning.model import Correction
    from fenceai.project.model import Annotation
    from fenceai.strategy.model import GenerationResult


class AnnotationInterpreter(Protocol):
    interpreter_id: str

    def interpret(self, annotation: "Annotation") -> InterpretationRecord: ...


class KnowledgeProposer(Protocol):
    interpreter_id: str

    def propose(self, corrections: list["Correction"]) -> list["KnowledgeVersion"]:
        """Returns versions with status='proposed' only — never active."""
        ...


class StrategyCritic(Protocol):
    interpreter_id: str

    def critique(self, result: "GenerationResult") -> list[CritiqueNote]: ...


class TaskRunner(Protocol):
    """Runs ONE goal-scoped agent task. Broad read via the view, narrow run via
    the task's own permission list (ADR-0009, agent-framework-design §4)."""

    interpreter_id: str

    def run(self, task: "TaskSpec", view: "AgentView", project_id: str) -> "TaskResult": ...
