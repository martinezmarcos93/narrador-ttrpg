"""Ejecutor seguro de propuestas narrativas.

Pipeline:
propuesta estructurada -> validación de forma/continuidad -> aplicación Python.
Nunca interpreta texto narrativo ni ejecuta una propuesta inválida.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from narrator.core.continuity_validator import ContinuityValidator
from narrator.core.proposal_contract import NarrativeProposal, ProposalValidator


@dataclass
class ProposalExecution:
    applied: bool
    report: Any
    changes: list[str]
    rolled_back: bool = False
    error: str = ""


class ProposalExecutor:
    def __init__(
        self,
        state_manager,
        narrator_agent=None,
        character_schema=None,
        vault_writer=None,
    ):
        self.state = state_manager
        self.narrator_agent = narrator_agent
        self.character_schema = character_schema or {}
        self.vault_writer = vault_writer
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

    def _create_entities(self, proposal: NarrativeProposal) -> tuple[list[str], list[Any]]:
        if not self.vault_writer:
            return [], []
        changes = []
        created_paths = []
        for npc in proposal.npcs:
            path = self.vault_writer.create_npc(npc)
            if path:
                created_paths.append(path)
                changes.append(f"entity:npc+{npc.get('nombre')}")
        for location in proposal.locations:
            path = self.vault_writer.create_locacion(location)
            if path:
                created_paths.append(path)
                changes.append(f"entity:locacion+{location.get('nombre')}")
        return changes, created_paths

    def _rollback(self, state_snapshot, character_snapshot, character, created_paths, state_file_existed) -> None:
        """Revierte las mutaciones propias de esta ejecución."""
        self.state.data = deepcopy(state_snapshot)
        try:
            if state_file_existed:
                self.state.save()
            elif self.state.path.exists():
                self.state.path.unlink()
        except Exception:
            pass
        if character is not None and character_snapshot is not None:
            character.clear()
            character.update(deepcopy(character_snapshot))
        rollback = getattr(self.vault_writer, "rollback_created_entities", None)
        if rollback and created_paths:
            rollback(created_paths)

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

        state_snapshot = deepcopy(self.state.data)
        character_snapshot = deepcopy(character) if character is not None else None
        created_paths = []
        try:
            entity_changes, created_paths = self._create_entities(proposal)
            changes = list(entity_changes)
            result = self.state.apply_proposal(proposal)
            changes.extend(result.get("changes", []))
            if character is not None and self.narrator_agent and proposal.character_changes:
                allowed = self.narrator_agent.character_field_specs(self.character_schema)
                normalized = [dict(item) for item in proposal.character_changes if "field" in item]
                char_changes = self.narrator_agent.apply_state_mutations(
                    character, normalized, allowed_fields=allowed
                )
                changes.extend(f"character:{item}" for item in char_changes)
            return ProposalExecution(True, report, changes)
        except Exception as exc:
            self._rollback(
                state_snapshot,
                character_snapshot,
                character,
                created_paths,
                state_file_existed,
            )
            report.valid = False
            from narrator.core.continuity_validator import ContinuityIssue
            report.issues.append(ContinuityIssue(
                "proposal_execution_failed", "error",
                f"La propuesta fue revertida por un error de ejecución: {exc}",
            ))
            return ProposalExecution(False, report, [], rolled_back=True, error=str(exc))
