"""Validación determinista de continuidad antes de mutar el estado de campaña."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContinuityIssue:
    code: str
    severity: str
    message: str


@dataclass
class ContinuityReport:
    valid: bool
    issues: list[ContinuityIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ContinuityIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ContinuityIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [
                {"code": i.code, "severity": i.severity, "message": i.message}
                for i in self.issues
            ],
        }


class ContinuityValidator:
    """Comprueba hechos persistentes sin intentar interpretar narrativa libre."""

    def __init__(self, state_manager):
        self.state = state_manager

    def validate(self, proposal: dict[str, Any]) -> ContinuityReport:
        issues: list[ContinuityIssue] = []
        if not isinstance(proposal, dict):
            return ContinuityReport(False, [
                ContinuityIssue("invalid_proposal", "error", "La propuesta no es un objeto.")
            ])

        self._check_facts(proposal.get("facts", {}), issues)
        self._check_events(proposal.get("events", []), issues)
        self._check_npcs(proposal.get("npc_presence", {}), issues)
        self._check_temporal(proposal.get("session"), issues)

        return ContinuityReport(not any(i.severity == "error" for i in issues), issues)

    def _check_facts(self, facts: Any, issues: list[ContinuityIssue]) -> None:
        if not isinstance(facts, dict):
            issues.append(ContinuityIssue("invalid_facts", "error", "facts debe ser un objeto."))
            return
        for key, value in facts.items():
            existing = self.state.get_known_fact(str(key), None)
            if existing is not None and existing != value:
                issues.append(ContinuityIssue(
                    "fact_conflict",
                    "error",
                    f"El hecho '{key}' ya está establecido como {existing!r}; propuesta: {value!r}.",
                ))

    def _check_events(self, events: Any, issues: list[ContinuityIssue]) -> None:
        if not isinstance(events, list):
            issues.append(ContinuityIssue("invalid_events", "error", "events debe ser una lista."))
            return
        recent = {
            str(item.get("evento", "")).strip()
            for item in self.state.data.get("eventos", [])[-50:]
            if isinstance(item, dict)
        }
        for event in events:
            text = str(event).strip()
            if text and text in recent:
                issues.append(ContinuityIssue(
                    "duplicate_event",
                    "warning",
                    f"El evento ya figura en el historial reciente: {text}",
                ))

    def _check_npcs(self, presence: Any, issues: list[ContinuityIssue]) -> None:
        if not isinstance(presence, dict):
            issues.append(ContinuityIssue("invalid_npc_presence", "error", "npc_presence debe ser un objeto."))
            return
        current = set(self.state.data.get("escena_actual", {}).get("npcs_presentes", []))
        for name, desired in presence.items():
            if desired is False and name not in current:
                issues.append(ContinuityIssue(
                    "npc_not_present",
                    "warning",
                    f"No se puede retirar de la escena a '{name}' porque no figura presente.",
                ))

    def _check_temporal(self, session: Any, issues: list[ContinuityIssue]) -> None:
        if session is None:
            return
        try:
            proposed = int(session)
            current = int(self.state.get_session_number())
        except (TypeError, ValueError):
            issues.append(ContinuityIssue("invalid_session", "error", "La sesión propuesta no es numérica."))
            return
        if proposed < current:
            issues.append(ContinuityIssue(
                "temporal_regression",
                "error",
                f"La propuesta retrocede de sesión {current} a {proposed}.",
            ))
