"""Ejecutor seguro de propuestas narrativas.

Pipeline:
propuesta estructurada -> validación de forma/continuidad -> aplicación Python.
Nunca interpreta texto narrativo ni ejecuta una propuesta inválida.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from narrator.core.continuity_validator import ContinuityValidator
from narrator.core.proposal_contract import NarrativeProposal, ProposalValidator


@dataclass
class ProposalExecution:
    applied: bool
    report: Any
    changes: list[str]


class ProposalExecutor:
    def __init__(self, state_manager, narrator_agent=None, character_schema=None):
        self.state = state_manager
        self.narrator_agent = narrator_agent
        self.character_schema = character_schema or {}
        self.continuity = ContinuityValidator(state_manager)
        self.validator = ProposalValidator(self.continuity)

    def _validate_character_changes(self, proposal: NarrativeProposal, report) -> None:
        if not proposal.character_changes:
            return
        from narrator.core.continuity_validator import ContinuityIssue
        allowed = (
            self.narrator_agent.character_field_specs(self.character_schema)
            if self.narrator_agent else {}
        )
        for item in proposal.character_changes:
            field = str(item.get("field") or "").strip()
            if not field or not allowed or field not in allowed:
                report.issues.append(ContinuityIssue(
                    "undeclared_character_field", "error",
                    f"Campo de personaje no declarado: {field or '<vacío>'}.",
                ))
                continue
            if "delta" not in item and "value" not in item:
                report.issues.append(ContinuityIssue(
                    "invalid_character_change", "error",
                    f"El cambio de '{field}' debe declarar delta o value.",
                ))
        report.valid = not any(issue.severity == "error" for issue in report.issues)

    def execute(self, raw: dict[str, Any], character: dict | None = None) -> ProposalExecution:
        try:
            proposal = NarrativeProposal.from_dict(raw)
        except (TypeError, ValueError) as exc:
            report = self.continuity.validate({})
            report.valid = False
            from narrator.core.continuity_validator import ContinuityIssue
            report.issues.append(ContinuityIssue("invalid_proposal", "error", str(exc)))
            return ProposalExecution(False, report, [])

        report = self.validator.validate(proposal)
        self._validate_character_changes(proposal, report)
        if not report.valid:
            return ProposalExecution(False, report, [])

        result = self.state.apply_proposal(proposal)
        changes = list(result.get("changes", []))

        if character is not None and self.narrator_agent and proposal.character_changes:
            allowed = self.narrator_agent.character_field_specs(self.character_schema)
            normalized = []
            for item in proposal.character_changes:
                mutation = dict(item)
                if "field" in mutation:
                    normalized.append(mutation)
            char_changes = self.narrator_agent.apply_state_mutations(
                character, normalized, allowed_fields=allowed
            )
            changes.extend(f"character:{item}" for item in char_changes)

        return ProposalExecution(True, report, changes)
