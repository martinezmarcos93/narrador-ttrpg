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
    "npcs",
    "locations",
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
    npcs: list[dict[str, Any]] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
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
            npcs=[dict(x) for x in data.get("npcs", []) if isinstance(x, dict)],
            locations=[dict(x) for x in data.get("locations", []) if isinstance(x, dict)],
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
            "npcs": [dict(x) for x in self.npcs],
            "locations": [dict(x) for x in self.locations],
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
        from narrator.core.continuity_validator import ContinuityIssue

        for item in proposal.npcs:
            if not str(item.get("nombre") or "").strip():
                report.issues.append(ContinuityIssue(
                    "invalid_npc", "error", "Cada NPC propuesto debe declarar nombre."
                ))
        for item in proposal.locations:
            if not str(item.get("nombre") or "").strip():
                report.issues.append(ContinuityIssue(
                    "invalid_location", "error", "Cada locación propuesta debe declarar nombre."
                ))

        if any(not isinstance(item.get("field"), str) for item in proposal.character_changes):
            report.issues.append(ContinuityIssue(
                "invalid_character_change", "error",
                "Cada cambio de personaje debe declarar un field.",
            ))
        allowed_effects = {"fact", "flag", "npc_presence", "scene_location", "clock_delta"}
        for consequence in proposal.consequences:
            for effect in consequence.get("effects", []) or []:
                if not isinstance(effect, dict) or effect.get("type") not in allowed_effects:
                    report.issues.append(ContinuityIssue(
                        "invalid_causal_effect", "error",
                        f"Efecto causal no permitido: {effect.get('type') if isinstance(effect, dict) else '<inválido>'}.",
                    ))
                    continue
                kind = effect.get("type")
                required = {
                    "fact": ("key",),
                    "flag": ("name",),
                    "npc_presence": ("name", "present"),
                    "scene_location": ("value",),
                    "clock_delta": ("name", "delta"),
                }[kind]
                if any(key not in effect for key in required):
                    report.issues.append(ContinuityIssue(
                        "invalid_causal_effect", "error",
                        f"Efecto causal '{kind}' incompleto.",
                    ))

        for item in proposal.clock_changes:
            if "name" not in item or "delta" not in item:
                report.issues.append(ContinuityIssue(
                    "invalid_clock_change", "error",
                    "Cada cambio de reloj debe declarar name y delta.",
                ))
        report.valid = not any(issue.severity == "error" for issue in report.issues)
        return report
