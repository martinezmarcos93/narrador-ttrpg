"""Motor determinista de causalidad encadenada.

No interpreta narrativa libre ni genera contenido. Evalúa triggers/due explícitos,
aplica efectos declarativos y puede propagar eventos a consecuencias posteriores.
La profundidad de cascada está acotada para impedir ciclos infinitos.
"""

from __future__ import annotations

from dataclasses import dataclass


_NEXT_TURN = {"siguiente turno", "next turn", "proximo turno", "próximo turno"}
_MAX_CASCADE_DEPTH = 8


@dataclass
class CausalActivation:
    index: int
    consequence: str
    reason: str
    depth: int = 0
    provenance_id: str = ""


class CausalityEngine:
    def __init__(self, state_manager, *, max_cascade_depth: int = _MAX_CASCADE_DEPTH):
        self.state = state_manager
        self.max_cascade_depth = max(1, int(max_cascade_depth))
        self.last_activations: list[CausalActivation] = []

    @staticmethod
    def _trigger_matches(trigger: str, event_text: str) -> bool:
        trigger = str(trigger or "").strip().lower()
        event_text = str(event_text or "").strip().lower()
        if not trigger or trigger in _NEXT_TURN:
            return False
        return trigger in event_text

    def _due_matches(self, due: str) -> bool:
        due = str(due or "").strip().lower()
        if not due:
            return False
        current_session = self.state.get_session_number()
        current_turn = int(self.state.data.get("escena_actual", {}).get("turno_narrativo", 0))
        try:
            if due.startswith(("sesion:", "session:")):
                return current_session >= int(due.split(":", 1)[1])
            if due.startswith(("turno:", "turn:")):
                return current_turn >= int(due.split(":", 1)[1])
        except (TypeError, ValueError):
            return False
        return False

    @staticmethod
    def _effects(item: dict) -> list[dict]:
        return [dict(effect) for effect in item.get("effects", []) if isinstance(effect, dict)]

    def _apply_secondary_effects(self, effects: list[dict], *, parent_id: str = "") -> list[str]:
        """Aplica efectos que generan nuevos eventos o consecuencias."""
        emitted_events = []
        pending = self.state.data.setdefault("consecuencias_pendientes", [])
        for effect in effects:
            kind = str(effect.get("type") or "").strip().lower()
            if kind == "event":
                event = str(effect.get("text") or "").strip()
                if event:
                    self.state.record_event(
                        event,
                        actor="CausalityEngine",
                        location=self.state.get_location() or "",
                    )
                    emitted_events.append(event)
            elif kind == "world_fact":
                key = str(effect.get("key") or "").strip()
                if key:
                    self.state.set_world_fact(key, effect.get("value"), source="causality_engine")
            elif kind == "character_fact":
                character = str(effect.get("character") or "").strip()
                key = str(effect.get("key") or "").strip()
                if character and key:
                    self.state.set_character_fact(character, key, effect.get("value"), source="causality_engine")
            elif kind == "player_fact":
                key = str(effect.get("key") or "").strip()
                if key:
                    self.state.set_player_fact(key, effect.get("value"), source="causality_engine")
            elif kind == "relation":
                source = str(effect.get("source") or "").strip()
                target = str(effect.get("target") or "").strip()
                relation = str(effect.get("relation") or "").strip()
                if source and target and relation:
                    self.state.set_relation(
                        source,
                        target,
                        relation,
                        int(effect.get("strength", 0)),
                        source_type=str(effect.get("source_type") or "npc"),
                        target_type=str(effect.get("target_type") or "npc"),
                        reason=str(effect.get("reason") or "causalidad"),
                    )
            elif kind == "front_clock_delta":
                name = str(effect.get("name") or "").strip()
                if name:
                    try:
                        delta = int(effect.get("delta", 0))
                    except (TypeError, ValueError):
                        delta = 0
                    clock = self.state.data.get("relojes", {}).get(name)
                    if clock is not None:
                        before = int(clock.get("llenos", 0))
                        clock["llenos"] = min(
                            max(0, before + delta),
                            int(clock.get("segmentos", 6)),
                        )
                        emitted_events.append(
                            f"reloj {name}: {before}->{clock['llenos']}"
                        )
            elif kind == "queue_consequence":
                consequence = str(effect.get("consequence") or effect.get("text") or "").strip()
                if not consequence:
                    continue
                pending.append({
                    "consecuencia": consequence,
                    "trigger": str(effect.get("trigger") or ""),
                    "due": str(effect.get("due") or ""),
                    "effects": [dict(x) for x in effect.get("effects", []) if isinstance(x, dict)],
                    "estado": "pendiente",
                    "sesion_creacion": self.state.get_session_number(),
                    "causal_parent": str(effect.get("parent") or parent_id),
                })
                emitted_events.append(consequence)
        if any(str(e.get("type") or "").strip().lower() == "queue_consequence" for e in effects):
            del pending[:-200]
            self.state.save()
        return emitted_events

    def _find_matches(self, event_text: str, *, next_turn: bool) -> list[tuple[int, dict, str]]:
        matches = []
        for index, item in enumerate(self.state.data.get("consecuencias_pendientes", [])):
            if item.get("estado", "pendiente") != "pendiente":
                continue
            trigger = str(item.get("trigger") or "")
            due = str(item.get("due") or "")
            if next_turn and trigger.strip().lower() in _NEXT_TURN:
                matches.append((index, item, "next_turn"))
            elif self._trigger_matches(trigger, event_text):
                matches.append((index, item, "trigger"))
            elif self._due_matches(due):
                matches.append((index, item, "due"))
        return matches

    def evaluate(self, event_text: str = "", *, next_turn: bool = False) -> list[CausalActivation]:
        """Evalúa una cascada completa hasta agotarla o alcanzar el límite."""
        activations: list[CausalActivation] = []
        current_event = str(event_text or "")
        current_next_turn = bool(next_turn)

        for depth in range(self.max_cascade_depth):
            matches = self._find_matches(current_event, next_turn=current_next_turn)
            if not matches:
                break

            emitted: list[str] = []
            for index, item, reason in reversed(matches):
                pending = self.state.data.get("consecuencias_pendientes", [])
                if not (0 <= index < len(pending)) or pending[index].get("estado", "pendiente") != "pendiente":
                    continue
                effects = self._effects(pending[index])
                parent_id = str(pending[index].get("causal_parent") or "")
                provenance_id = self.state.record_provenance(
                    kind="causal_activation",
                    source="CausalityEngine",
                    detail=f"{pending[index].get('consecuencia', '')} [{reason}] depth={depth}",
                    parent_id=parent_id,
                )
                activation = CausalActivation(
                    index=index,
                    consequence=str(pending[index].get("consecuencia", "")),
                    reason=reason,
                    depth=depth,
                    provenance_id=provenance_id,
                )
                self.state.apply_causal_activation(
                    index,
                    outcome=f"Activada automáticamente ({reason}, profundidad {depth})",
                    effects=effects,
                )
                emitted.extend(self._apply_secondary_effects(effects, parent_id=provenance_id))
                activations.append(activation)

            # Una activación solo puede re-disparar por un evento explícito.
            # 'siguiente turno' no se propaga dentro de la misma cascada.
            current_event = " | ".join(emitted)
            current_next_turn = False

        self.last_activations = list(activations)
        return activations

    def summary(self, activations: list[CausalActivation]) -> str:
        if not activations:
            return ""
        return "\n".join(
            f"- {item.consequence} (profundidad {item.depth}, motivo: {item.reason})"
            for item in activations
            if item.consequence
        )
