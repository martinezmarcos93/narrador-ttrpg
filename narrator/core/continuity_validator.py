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
    """Comprueba referencias y coherencia estructural sin interpretar narrativa libre.

    El validador solo rechaza referencias que puede demostrar que son inválidas
    a partir del estado canónico y de entidades declaradas en la misma propuesta.
    Cuando el estado no mantiene un registro global de una clase de entidad, no
    inventa una autoridad alternativa.
    """

    def __init__(self, state_manager):
        self.state = state_manager

    def validate(self, proposal: dict[str, Any]) -> ContinuityReport:
        issues: list[ContinuityIssue] = []
        if not isinstance(proposal, dict):
            return ContinuityReport(False, [
                ContinuityIssue("invalid_proposal", "error", "La propuesta no es un objeto.")
            ])

        proposed_npcs = self._proposed_names(proposal.get("npcs", []), "nombre", "invalid_npc")
        proposed_locations = self._proposed_names(
            proposal.get("locations", []), "nombre", "invalid_location"
        )
        known_npcs = self._known_npcs() | proposed_npcs
        known_locations = self._known_locations() | proposed_locations

        self._check_facts(proposal.get("facts", {}), issues)
        self._check_events(proposal.get("events", []), issues)
        self._check_npcs(proposal.get("npc_presence", {}), known_npcs, issues)
        self._check_entities(proposal.get("npcs", []), proposal.get("locations", []), issues)
        self._check_scene_changes(proposal.get("scene_changes", {}), known_locations, issues)
        self._check_clocks(proposal.get("clock_changes", []), issues)
        self._check_relations(proposal.get("relations", []), known_npcs, issues)
        self._check_consequences(
            proposal.get("consequences", []),
            known_npcs,
            known_locations,
            issues,
        )
        self._check_temporal(proposal.get("session"), issues)

        return ContinuityReport(not any(i.severity == "error" for i in issues), issues)

    @staticmethod
    def _proposed_names(items: Any, field: str, code: str) -> set[str]:
        if not isinstance(items, list):
            return set()
        return {
            str(item.get(field)).strip()
            for item in items
            if isinstance(item, dict) and str(item.get(field) or "").strip()
        }

    def _known_npcs(self) -> set[str]:
        scene = self.state.data.get("escena_actual", {})
        known = {
            str(name).strip()
            for name in scene.get("npcs_presentes", [])
            if str(name).strip()
        }
        for relation in self.state.data.get("relaciones", {}).values():
            if isinstance(relation, dict):
                for key in ("source", "target"):
                    value = str(relation.get(key) or "").strip()
                    if value:
                        known.add(value)
        return known

    def _known_locations(self) -> set[str]:
        current = str(self.state.data.get("escena_actual", {}).get("locacion") or "").strip()
        known = {current} if current else set()
        scenes = self.state.data.get("escenas", {})
        if isinstance(scenes, dict):
            known.update(str(name).strip() for name in scenes if str(name).strip())
        return known

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

    def _check_npcs(
        self,
        presence: Any,
        known_npcs: set[str],
        issues: list[ContinuityIssue],
    ) -> None:
        if not isinstance(presence, dict):
            issues.append(ContinuityIssue(
                "invalid_npc_presence", "error", "npc_presence debe ser un objeto."
            ))
            return
        current = {
            str(name).strip()
            for name in self.state.data.get("escena_actual", {}).get("npcs_presentes", [])
        }
        for name, desired in presence.items():
            normalized = str(name).strip()
            if not normalized:
                issues.append(ContinuityIssue(
                    "invalid_npc_reference", "error", "npc_presence no puede usar un nombre vacío."
                ))
                continue
            if not isinstance(desired, bool):
                issues.append(ContinuityIssue(
                    "invalid_npc_presence_value", "error",
                    f"La presencia de '{normalized}' debe ser booleana.",
                ))
                continue
            if normalized not in known_npcs:
                issues.append(ContinuityIssue(
                    "unknown_npc",
                    "error",
                    f"El NPC '{normalized}' no existe en el estado visible ni fue creado en la propuesta.",
                ))
            elif desired is False and normalized not in current:
                issues.append(ContinuityIssue(
                    "npc_not_present",
                    "warning",
                    f"No se puede retirar de la escena a '{normalized}' porque no figura presente.",
                ))

    def _check_entities(
        self,
        npcs: Any,
        locations: Any,
        issues: list[ContinuityIssue],
    ) -> None:
        if not isinstance(npcs, list):
            issues.append(ContinuityIssue("invalid_npcs", "error", "npcs debe ser una lista."))
        else:
            seen: set[str] = set()
            for item in npcs:
                if not isinstance(item, dict):
                    issues.append(ContinuityIssue(
                        "invalid_npc", "error", "Cada NPC propuesto debe ser un objeto."
                    ))
                    continue
                name = str(item.get("nombre") or "").strip()
                if not name:
                    issues.append(ContinuityIssue(
                        "invalid_npc", "error", "Cada NPC propuesto debe declarar nombre."
                    ))
                elif name in seen:
                    issues.append(ContinuityIssue(
                        "duplicate_npc", "error", f"El NPC '{name}' aparece más de una vez."
                    ))
                seen.add(name)

        if not isinstance(locations, list):
            issues.append(ContinuityIssue(
                "invalid_locations", "error", "locations debe ser una lista."
            ))
        else:
            seen = set()
            for item in locations:
                if not isinstance(item, dict):
                    issues.append(ContinuityIssue(
                        "invalid_location", "error", "Cada locación propuesta debe ser un objeto."
                    ))
                    continue
                name = str(item.get("nombre") or "").strip()
                if not name:
                    issues.append(ContinuityIssue(
                        "invalid_location", "error", "Cada locación propuesta debe declarar nombre."
                    ))
                elif name in seen:
                    issues.append(ContinuityIssue(
                        "duplicate_location", "error", f"La locación '{name}' aparece más de una vez."
                    ))
                seen.add(name)

    def _check_scene_changes(
        self,
        changes: Any,
        known_locations: set[str],
        issues: list[ContinuityIssue],
    ) -> None:
        if not isinstance(changes, dict):
            issues.append(ContinuityIssue(
                "invalid_scene_changes", "error", "scene_changes debe ser un objeto."
            ))
            return
        if "locacion" in changes:
            location = str(changes.get("locacion") or "").strip()
            if not location:
                issues.append(ContinuityIssue(
                    "invalid_location_reference", "error",
                    "scene_changes.locacion no puede ser vacío.",
                ))
            elif known_locations and location not in known_locations:
                # El estado actual no posee un registro global de locaciones;
                # si no conocemos ninguna, permitimos la primera locación de campaña.
                issues.append(ContinuityIssue(
                    "unknown_location", "error",
                    f"La locación '{location}' no existe en el estado ni en la propuesta.",
                ))

    def _check_clocks(self, changes: Any, issues: list[ContinuityIssue]) -> None:
        if not isinstance(changes, list):
            issues.append(ContinuityIssue(
                "invalid_clock_changes", "error",
                "clock_changes debe ser una lista.",
            ))
            return

        clocks = self.state.data.get("relojes", {})
        aggregate: dict[str, int] = {}
        for item in changes:
            if not isinstance(item, dict):
                issues.append(ContinuityIssue(
                    "invalid_clock_change", "error",
                    "Cada cambio de reloj debe ser un objeto.",
                ))
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                issues.append(ContinuityIssue(
                    "invalid_clock_change", "error",
                    "Cada cambio de reloj debe declarar name.",
                ))
                continue
            if name not in clocks:
                issues.append(ContinuityIssue(
                    "unknown_clock", "error",
                    f"El reloj '{name}' no existe en el estado de campaña.",
                ))
                continue
            delta_raw = item.get("delta")
            if isinstance(delta_raw, bool):
                issues.append(ContinuityIssue(
                    "invalid_clock_delta", "error",
                    f"El delta del reloj '{name}' debe ser entero.",
                ))
                continue
            try:
                delta = int(delta_raw)
            except (TypeError, ValueError):
                issues.append(ContinuityIssue(
                    "invalid_clock_delta", "error",
                    f"El delta del reloj '{name}' debe ser entero.",
                ))
                continue
            aggregate[name] = aggregate.get(name, 0) + delta

        for name, delta in aggregate.items():
            clock = clocks[name]
            try:
                current = int(clock.get("llenos", 0))
                maximum = int(clock.get("segmentos", 6))
            except (TypeError, ValueError):
                issues.append(ContinuityIssue(
                    "invalid_clock_definition", "error",
                    f"El reloj '{name}' tiene una definición inválida.",
                ))
                continue
            target = current + delta
            if target < 0 or target > maximum:
                issues.append(ContinuityIssue(
                    "clock_out_of_bounds", "error",
                    f"Los cambios acumulados del reloj '{name}' llevarían {current} a {target}; rango permitido 0..{maximum}.",
                ))

    def _check_relations(
        self,
        relations: Any,
        known_npcs: set[str],
        issues: list[ContinuityIssue],
    ) -> None:
        if relations is None:
            return
        if not isinstance(relations, list):
            issues.append(ContinuityIssue(
                "invalid_relations", "error", "relations debe ser una lista."
            ))
            return
        existing_keys = {
            (str(item.get("source") or "").strip(), str(item.get("target") or "").strip())
            for item in self.state.data.get("relaciones", {}).values()
            if isinstance(item, dict)
        }
        seen = set()
        for item in relations:
            if not isinstance(item, dict):
                issues.append(ContinuityIssue(
                    "invalid_relation", "error", "Cada relación debe ser un objeto."
                ))
                continue
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            relation = str(item.get("relation") or "").strip()
            if not source or not target or not relation:
                issues.append(ContinuityIssue(
                    "invalid_relation", "error",
                    "Una relación requiere source, target y relation.",
                ))
                continue
            if source == target:
                issues.append(ContinuityIssue(
                    "self_relation", "error",
                    f"La relación '{source}' -> '{target}' no puede apuntar a sí misma.",
                ))
            for endpoint in (source, target):
                if endpoint not in known_npcs and endpoint not in self._known_factions():
                    issues.append(ContinuityIssue(
                        "unknown_relation_entity", "error",
                        f"La entidad '{endpoint}' de la relación no existe en el estado ni en la propuesta.",
                    ))
            try:
                strength = int(item.get("strength", 0))
            except (TypeError, ValueError):
                issues.append(ContinuityIssue(
                    "invalid_relation_strength", "error",
                    "La fuerza de una relación debe ser entera.",
                ))
                continue
            if not -100 <= strength <= 100:
                issues.append(ContinuityIssue(
                    "invalid_relation_strength", "error",
                    "La fuerza de una relación debe estar entre -100 y 100.",
                ))
            key = (source, target)
            if key in existing_keys or key in seen:
                issues.append(ContinuityIssue(
                    "duplicate_relation", "warning",
                    f"La relación '{source}' -> '{target}' ya existe o se propone más de una vez.",
                ))
            seen.add(key)

    def _known_factions(self) -> set[str]:
        return {
            str(name).strip()
            for name in self.state.data.get("facciones", {})
            if str(name).strip()
        }

    def _check_consequences(
        self,
        consequences: Any,
        known_npcs: set[str],
        known_locations: set[str],
        issues: list[ContinuityIssue],
    ) -> None:
        if not isinstance(consequences, list):
            issues.append(ContinuityIssue(
                "invalid_consequences", "error", "consequences debe ser una lista."
            ))
            return

        for index, item in enumerate(consequences):
            if not isinstance(item, dict):
                issues.append(ContinuityIssue(
                    "invalid_consequence", "error",
                    f"La consecuencia #{index + 1} debe ser un objeto.",
                ))
                continue
            text = str(item.get("text") or item.get("consecuencia") or "").strip()
            if not text:
                issues.append(ContinuityIssue(
                    "invalid_consequence", "error",
                    f"La consecuencia #{index + 1} debe declarar text o consecuencia.",
                ))
            trigger = str(item.get("trigger") or "").strip()
            due = str(item.get("due") or "").strip()
            if not trigger and not due:
                issues.append(ContinuityIssue(
                    "untriggered_consequence", "error",
                    f"La consecuencia #{index + 1} no tiene trigger ni due.",
                ))
            effects = item.get("effects", [])
            if effects is None:
                effects = []
            if not isinstance(effects, list):
                issues.append(ContinuityIssue(
                    "invalid_consequence_effects", "error",
                    f"Los effects de la consecuencia #{index + 1} deben ser una lista.",
                ))
                continue
            self._check_effects(effects, known_npcs, known_locations, issues)

    def _check_effects(
        self,
        effects: list[Any],
        known_npcs: set[str],
        known_locations: set[str],
        issues: list[ContinuityIssue],
    ) -> None:
        allowed = {
            "fact", "flag", "npc_presence", "scene_location", "clock_delta",
            "event", "queue_consequence", "world_fact", "character_fact",
            "player_fact", "relation", "front_clock_delta",
        }
        seen_clock_deltas: dict[str, int] = {}
        for effect in effects:
            if not isinstance(effect, dict):
                issues.append(ContinuityIssue(
                    "invalid_causal_effect", "error", "Cada efecto causal debe ser un objeto."
                ))
                continue
            kind = str(effect.get("type") or "").strip()
            if kind not in allowed:
                issues.append(ContinuityIssue(
                    "invalid_causal_effect", "error",
                    f"Efecto causal no permitido: {kind or '<vacío>'}.",
                ))
                continue

            required = {
                "fact": ("key",),
                "flag": ("name",),
                "npc_presence": ("name", "present"),
                "scene_location": ("value",),
                "clock_delta": ("name", "delta"),
                "event": ("text",),
                "queue_consequence": ("consequence",),
                "world_fact": ("key", "value"),
                "character_fact": ("character", "key", "value"),
                "player_fact": ("key", "value"),
                "relation": ("source", "target", "relation"),
                "front_clock_delta": ("name", "delta"),
            }[kind]
            if any(key not in effect for key in required):
                issues.append(ContinuityIssue(
                    "invalid_causal_effect", "error",
                    f"Efecto causal '{kind}' incompleto.",
                ))
                continue

            if kind == "npc_presence":
                name = str(effect.get("name") or "").strip()
                if not name or not isinstance(effect.get("present"), bool):
                    issues.append(ContinuityIssue(
                        "invalid_npc_presence_effect", "error",
                        "npc_presence requiere name no vacío y present booleano.",
                    ))
                elif name not in known_npcs:
                    issues.append(ContinuityIssue(
                        "unknown_npc", "error",
                        f"El NPC '{name}' del efecto causal no existe en el estado ni en la propuesta.",
                    ))
            elif kind == "scene_location":
                value = str(effect.get("value") or "").strip()
                if not value:
                    issues.append(ContinuityIssue(
                        "invalid_location_reference", "error",
                        "scene_location requiere una locación no vacía.",
                    ))
                elif known_locations and value not in known_locations:
                    issues.append(ContinuityIssue(
                        "unknown_location", "error",
                        f"La locación '{value}' del efecto causal no existe en el estado ni en la propuesta.",
                    ))
            elif kind == "clock_delta":
                name = str(effect.get("name") or "").strip()
                if name not in self.state.data.get("relojes", {}):
                    issues.append(ContinuityIssue(
                        "unknown_clock", "error",
                        f"El reloj '{name}' del efecto causal no existe en el estado.",
                    ))
                else:
                    try:
                        delta = int(effect.get("delta"))
                    except (TypeError, ValueError):
                        issues.append(ContinuityIssue(
                            "invalid_clock_delta", "error",
                            f"El delta del reloj '{name}' debe ser entero.",
                        ))
                    else:
                        seen_clock_deltas[name] = seen_clock_deltas.get(name, 0) + delta
            elif kind in {"relation", "front_clock_delta"}:
                self._check_relation_or_front_effect(kind, effect, known_npcs, issues)
            elif kind == "character_fact":
                if not str(effect.get("character") or "").strip() or not str(effect.get("key") or "").strip():
                    issues.append(ContinuityIssue(
                        "invalid_character_fact", "error",
                        "character_fact requiere character y key.",
                    ))
            elif kind in {"fact", "world_fact", "player_fact"}:
                if not str(effect.get("key") or "").strip():
                    issues.append(ContinuityIssue(
                        "invalid_fact_effect", "error",
                        f"{kind} requiere key no vacío.",
                    ))
            elif kind == "flag" and not str(effect.get("name") or "").strip():
                issues.append(ContinuityIssue(
                    "invalid_flag_effect", "error", "flag requiere name no vacío."
                ))
            elif kind == "event" and not str(effect.get("text") or "").strip():
                issues.append(ContinuityIssue(
                    "invalid_event_effect", "error", "event requiere text no vacío."
                ))
            elif kind == "queue_consequence":
                if not str(effect.get("consequence") or effect.get("text") or "").strip():
                    issues.append(ContinuityIssue(
                        "invalid_queue_consequence", "error",
                        "queue_consequence requiere consequence o text.",
                    ))
                if not str(effect.get("trigger") or effect.get("due") or "").strip():
                    issues.append(ContinuityIssue(
                        "untriggered_consequence", "error",
                        "queue_consequence requiere trigger o due.",
                    ))

        for name, delta in seen_clock_deltas.items():
            clock = self.state.data.get("relojes", {}).get(name, {})
            try:
                target = int(clock.get("llenos", 0)) + delta
                maximum = int(clock.get("segmentos", 6))
            except (TypeError, ValueError):
                issues.append(ContinuityIssue(
                    "invalid_clock_definition", "error",
                    f"El reloj '{name}' tiene una definición inválida.",
                ))
                continue
            if target < 0 or target > maximum:
                issues.append(ContinuityIssue(
                    "clock_out_of_bounds", "error",
                    f"Los efectos causales acumulados del reloj '{name}' salen del rango 0..{maximum}.",
                ))

    def _check_relation_or_front_effect(
        self,
        kind: str,
        effect: dict[str, Any],
        known_npcs: set[str],
        issues: list[ContinuityIssue],
    ) -> None:
        if kind == "relation":
            source = str(effect.get("source") or "").strip()
            target = str(effect.get("target") or "").strip()
            relation = str(effect.get("relation") or "").strip()
            if not source or not target or not relation:
                issues.append(ContinuityIssue(
                    "invalid_relation", "error",
                    "Una relación causal requiere source, target y relation.",
                ))
                return
            for endpoint in (source, target):
                if endpoint not in known_npcs and endpoint not in self._known_factions():
                    issues.append(ContinuityIssue(
                        "unknown_relation_entity", "error",
                        f"La entidad '{endpoint}' de la relación causal no existe.",
                    ))
            try:
                strength = int(effect.get("strength", 0))
            except (TypeError, ValueError):
                issues.append(ContinuityIssue(
                    "invalid_relation_strength", "error",
                    "La fuerza de una relación causal debe ser entera.",
                ))
                return
            if not -100 <= strength <= 100:
                issues.append(ContinuityIssue(
                    "invalid_relation_strength", "error",
                    "La fuerza de una relación causal debe estar entre -100 y 100.",
                ))
        else:
            name = str(effect.get("name") or "").strip()
            if not name:
                issues.append(ContinuityIssue(
                    "invalid_front_clock_delta", "error",
                    "front_clock_delta requiere name.",
                ))
                return
            if name not in self.state.data.get("frentes", {}):
                issues.append(ContinuityIssue(
                    "unknown_front", "error",
                    f"El frente '{name}' no existe en el estado de campaña.",
                ))
            try:
                delta = int(effect.get("delta"))
            except (TypeError, ValueError):
                issues.append(ContinuityIssue(
                    "invalid_front_clock_delta", "error",
                    "El delta de un frente debe ser entero.",
                ))
                return
            clock = self.state.data.get("relojes", {}).get(name)
            if clock is not None:
                try:
                    target = int(clock.get("llenos", 0)) + delta
                    maximum = int(clock.get("segmentos", 6))
                    if target < 0 or target > maximum:
                        issues.append(ContinuityIssue(
                            "clock_out_of_bounds", "error",
                            f"El avance del frente '{name}' saldría del rango 0..{maximum}.",
                        ))
                except (TypeError, ValueError):
                    issues.append(ContinuityIssue(
                        "invalid_clock_definition", "error",
                        f"El reloj del frente '{name}' tiene una definición inválida.",
                    ))

    def _check_temporal(self, session: Any, issues: list[ContinuityIssue]) -> None:
        if session is None:
            return
        if isinstance(session, bool):
            issues.append(ContinuityIssue(
                "invalid_session", "error", "La sesión propuesta no es numérica."
            ))
            return
        try:
            proposed = int(session)
            current = int(self.state.get_session_number())
        except (TypeError, ValueError):
            issues.append(ContinuityIssue(
                "invalid_session", "error", "La sesión propuesta no es numérica."
            ))
            return
        if proposed < current:
            issues.append(ContinuityIssue(
                "temporal_regression",
                "error",
                f"La propuesta retrocede de sesión {current} a {proposed}.",
            ))
