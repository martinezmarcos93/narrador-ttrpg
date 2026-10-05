"""Política determinista de visibilidad del conocimiento.

La verdad objetiva de campaña puede existir sin ser conocida por personajes o
jugadores. Este módulo decide qué perspectivas pueden exponerse al narrador.
No usa LLM y no infiere conocimiento a partir de prosa libre.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KnowledgeView:
    world: dict[str, Any]
    character: dict[str, Any]
    player: dict[str, Any]

    def render_for_narrator(self, *, include_player: bool = True) -> str:
        lines: list[str] = []
        if self.character:
            lines.append(
                "CONOCIMIENTO DEL PERSONAJE (no equivale a verdad objetiva): "
                + self._compact(self.character)
            )
        if include_player and self.player:
            lines.append(
                "INFORMACIÓN CONOCIDA POR EL JUGADOR: "
                + self._compact(self.player)
            )
        return "\n".join(lines)

    @staticmethod
    def _compact(bucket: dict[str, Any]) -> str:
        values = []
        for key, entry in list(bucket.items())[-16:]:
            value = entry.get("valor") if isinstance(entry, dict) else entry
            values.append(f"{key}={value}")
        return ", ".join(values)


class KnowledgeVisibility:
    """Construye vistas de conocimiento sin filtrar la verdad objetiva al LLM."""

    def __init__(self, state_manager):
        self.state = state_manager

    def snapshot(self, *, character: str = "", include_player: bool = True) -> KnowledgeView:
        data = self.state.get_knowledge_snapshot(
            character=character,
            include_player=include_player,
        )
        return KnowledgeView(
            world=dict(data.get("world", {})),
            character=dict(data.get("character", {})),
            player=dict(data.get("player", {})),
        )

    def narrator_view(self, *, character: str = "", include_player: bool = True) -> str:
        return self.snapshot(
            character=character,
            include_player=include_player,
        ).render_for_narrator(include_player=include_player)

    def can_expose_world_fact(self, key: str, *, character: str = "", player: bool = False) -> bool:
        """True solo si la perspectiva ya contiene explícitamente el hecho."""
        view = self.snapshot(character=character, include_player=player)
        return key in view.character or (player and key in view.player)

    def grant_character_fact(self, character: str, key: str, value: Any, *, source: str = "") -> None:
        self.state.set_character_fact(character, key, value, source=source)

    def grant_player_fact(self, key: str, value: Any, *, source: str = "") -> None:
        self.state.set_player_fact(key, value, source=source)
