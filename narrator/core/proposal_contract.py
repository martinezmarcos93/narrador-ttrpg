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

        def optional_map(key: str) -> dict[str, Any]:
            value = data.get(key, {})
            if value is None:
                return {}
            if not isinstance(value, dict):
                raise ValueError(f"'{key}' debe ser un objeto.")
            return dict(value)

        def optional_list(key: str) -> list[Any]:
            value = data.get(key, [])
            if value is None:
                return []
            if not isinstance(value, list):
                raise ValueError(f"'{key}' debe ser una lista.")
            return list(value)

        facts = optional_map("facts")
        events = optional_list("events")
        npc_presence = optional_map("npc_presence")
        npcs = optional_list("npcs")
        locations = optional_list("locations")
        consequences = optional_list("consequences")
        character_changes = optional_list("character_changes")
        scene_changes = optional_map("scene_changes")
        clock_changes = optional_list("clock_changes")

        if any(not isinstance(item, str) for item in events):
            raise ValueError("'events' solo admite cadenas.")
        if any(
            not isinstance(key, str) or not isinstance(value, bool)
            for key, value in npc_presence.items()
        ):
            raise ValueError("'npc_presence' requiere nombres de texto y valores booleanos.")
        for key, items in {
            "npcs": npcs,
            "locations": locations,
            "consequences": consequences,
            "character_changes": character_changes,
            "clock_changes": clock_changes,
        }.items():
            if any(not isinstance(item, dict) for item in items):
                raise ValueError(f"'{key}' solo admite objetos.")

        return cls(
            facts=facts,
            events=[item.strip() for item in events if item.strip()],
            npc_presence={str(k).strip(): v for k, v in npc_presence.items()},
            npcs=[dict(x) for x in npcs],
            locations=[dict(x) for x in locations],
            consequences=[dict(x) for x in consequences],
            character_changes=[dict(x) for x in character_changes],
            scene_changes=scene_changes,
            clock_changes=[dict(x) for x in clock_changes],
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

    def __init__(self, continuity_validator, *, allowed_fronts=None):
        self.continuity = continuity_validator
        self.allowed_fronts = set(allowed_fronts or [])

    def validate(self, proposal: NarrativeProposal):
        continuity_payload = {
            "facts": proposal.facts,
            "events": proposal.events,
            "npc_presence": proposal.npc_presence,
            "npcs": proposal.npcs,
            "locations": proposal.locations,
            "consequences": proposal.consequences,
            "scene_changes": proposal.scene_changes,
            "clock_changes": proposal.clock_changes,
        }
        report = self.continuity.validate(continuity_payload)
        from narrator.core.continuity_validator import ContinuityIssue

        if any(not isinstance(item.get("field"), str) for item in proposal.character_changes):
            report.issues.append(ContinuityIssue(
                "invalid_character_change", "error",
                "Cada cambio de personaje debe declarar un field.",
            ))

        allowed_effects = {
            "fact", "flag", "npc_presence", "scene_location", "clock_delta",
            "event", "queue_consequence", "world_fact", "character_fact",
            "player_fact", "relation", "front_clock_delta",
        }
        for consequence in proposal.consequences:
            for effect in consequence.get("effects", []) or []:
                if not isinstance(effect, dict) or effect.get("type") not in allowed_effects:
                    report.issues.append(ContinuityIssue(
                        "invalid_causal_effect", "error",
                        f"Efecto causal no permitido: "
                        f"{effect.get('type') if isinstance(effect, dict) else '<inválido>'}.",
                    ))

        if self.allowed_fronts:
            for consequence in proposal.consequences:
                for effect in consequence.get("effects", []) or []:
                    if not isinstance(effect, dict):
                        continue
                    if effect.get("type") == "front_clock_delta":
                        name = str(effect.get("name") or "").strip()
                        if name and name not in self.allowed_fronts:
                            report.issues.append(ContinuityIssue(
                                "unknown_front", "error",
                                f"Frente no declarado por el contrato activo: {name}.",
                            ))

        report.valid = not any(issue.severity == "error" for issue in report.issues)
        return report
