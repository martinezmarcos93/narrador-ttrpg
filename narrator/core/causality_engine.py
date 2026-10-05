"""Motor determinista de causalidad para consecuencias pendientes.

No interpreta narrativa libre ni genera contenido. Solo decide cuándo una
consecuencia ya plantada está habilitada por un trigger explícito o por su
fecha lógica.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CausalActivation:
    index: int
    consequence: str
    reason: str


class CausalityEngine:
    def __init__(self, state_manager):
        self.state = state_manager

    @staticmethod
    def _trigger_matches(trigger: str, event_text: str) -> bool:
        trigger = str(trigger or "").strip().lower()
        event_text = str(event_text or "").strip().lower()
        if not trigger:
            return False
        if trigger in {"siguiente turno", "next turn", "proximo turno", "próximo turno"}:
            return False
        return trigger in event_text

    def _due_matches(self, due: str) -> bool:
        due = str(due or "").strip().lower()
        if not due:
            return False
        current_session = self.state.get_session_number()
        current_turn = int(self.state.data.get("escena_actual", {}).get("turno_narrativo", 0))
        try:
            if due.startswith("sesion:") or due.startswith("session:"):
                return current_session >= int(due.split(":", 1)[1])
            if due.startswith("turno:") or due.startswith("turn:"):
                return current_turn >= int(due.split(":", 1)[1])
        except (TypeError, ValueError):
            return False
        return False

    def evaluate(self, event_text: str = "", *, next_turn: bool = False) -> list[CausalActivation]:
        pending = self.state.data.get("consecuencias_pendientes", [])
        activations = []
        for index, item in enumerate(pending):
            if item.get("estado", "pendiente") != "pendiente":
                continue
            trigger = item.get("trigger", "")
            due = item.get("due", "")
            matched = self._trigger_matches(trigger, event_text)
            if next_turn and str(trigger).strip().lower() in {
                "siguiente turno", "next turn", "proximo turno", "próximo turno"
            }:
                matched = True
            if self._due_matches(due):
                matched = True
            if matched:
                activations.append(CausalActivation(
                    index=index,
                    consequence=str(item.get("consecuencia", "")),
                    reason="trigger" if self._trigger_matches(trigger, event_text) else "due",
                ))

        for activation in reversed(activations):
            resolved = self.state.resolve_pending_consequence(
                activation.index,
                outcome=f"Activada automáticamente ({activation.reason})",
            )
            if resolved:
                self.state.record_event(
                    f"Consecuencia activada: {activation.consequence}",
                    actor="CausalityEngine",
                    location=self.state.get_location() or "",
                )
        return list(reversed(activations))

    def summary(self, activations: list[CausalActivation]) -> str:
        if not activations:
            return ""
        return "
".join(
            f"- {item.consequence}" for item in activations if item.consequence
        )
