"""Contrato estructural para propuestas del narrador.

El LLM podrá proponer cambios, pero este objeto no muta estado. La aplicación
debe validar la propuesta y recién después ejecutar cada operación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_KEYS = {
    "facts",
    "events",
    "npc_presence",
    "consequences",
    "character_changes",
    "scene_changes",
    "clock_changes",
}


@dataclass
class NarrativeProposal:
    facts: dict[str, Any] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    npc_presence: dict[str, bool] = field(default_factory=dict)
    consequences: list[dict[str, Any]] = field(default_factory=list)
    character_changes: list[dict[str, Any]] = field(default_factory=list)
    scene_changes: dict[str, Any] = field(default_factory=dict)
    clock_changes: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NarrativeProposal":
        if not isinstance(data, dict):
            raise ValueError("La propuesta debe ser un objeto.")
        unknown = set(data) - ALLOWED_KEYS
        if unknown:
            raise ValueError(f"Claves de propuesta no permitidas: {sorted(unknown)}")
        return cls(
            facts=dict(data.get("facts") or {}),
            events=[str(x).strip() for x in data.get("events", []) if str(x).strip()],
            npc_presence={str(k): bool(v) for k, v in (data.get("npc_presence") or {}).items()},
            consequences=[dict(x) for x in data.get("consequences", []) if isinstance(x, dict)],
            character_changes=[dict(x) for x in data.get("character_changes", []) if isinstance(x, dict)],
            scene_changes=dict(data.get("scene_changes") or {}),
            clock_changes=[dict(x) for x in data.get("clock_changes", []) if isinstance(x, dict)],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": dict(self.facts),
            "events": list(self.events),
            "npc_presence": dict(self.npc_presence),
            "consequences": [dict(x) for x in self.consequences],
            "character_changes": [dict(x) for x in self.character_changes],
            "scene_changes": dict(self.scene_changes),
            "clock_changes": [dict(x) for x in self.clock_changes],
        }


class ProposalValidator:
    """Valida forma y continuidad; no aplica ninguna mutación."""

    def __init__(self, continuity_validator):
        self.continuity = continuity_validator

    def validate(self, proposal: NarrativeProposal):
        continuity_payload = {
            "facts": proposal.facts,
            "events": proposal.events,
            "npc_presence": proposal.npc_presence,
        }
        report = self.continuity.validate(continuity_payload)

        if any(not isinstance(item.get("field"), str) for item in proposal.character_changes):
            from narrator.core.continuity_validator import ContinuityIssue
            report.issues.append(ContinuityIssue(
                "invalid_character_change", "error",
                "Cada cambio de personaje debe declarar un field.",
            ))
        for item in proposal.clock_changes:
            if "name" not in item or "delta" not in item:
                from narrator.core.continuity_validator import ContinuityIssue
                report.issues.append(ContinuityIssue(
                    "invalid_clock_change", "error",
                    "Cada cambio de reloj debe declarar name y delta.",
                ))
        report.valid = not any(issue.severity == "error" for issue in report.issues)
        return report
