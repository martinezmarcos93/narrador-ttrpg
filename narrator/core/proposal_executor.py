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
