"""Reglas de continuidad declarativas por System Pack.

Cada sistema puede declarar en su YAML restricciones de dominio que Python
verifica antes de mutar el estado. Son reglas simples y deterministas: no
interpretan narrativa, solo valores de hechos y tipos de efecto.

Formato (todas las claves son opcionales)::

    continuity_rules:
      fact_ranges:            # hechos numéricos acotados
        humanidad: {min: 0, max: 10}
      fact_values:            # hechos con valores permitidos
        estado_vampiro: [despierto, letargo, torpor]
      mutually_exclusive:     # hechos que no pueden ser verdaderos a la vez
        - [en_torpor, en_combate]
      forbidden_effects:      # tipos de efecto causal deshabilitados
        - scene_location

Los hechos se buscan en ``facts`` de la propuesta, en efectos causales
``fact``/``world_fact``/``player_fact``/``character_fact`` (incluidos los
anidados) y en el estado vivo (``hechos_conocidos`` y ``conocimiento.mundo``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

_FACT_EFFECTS = {"fact", "world_fact", "player_fact", "character_fact"}
_KNOWN_EFFECTS = {
    "fact", "flag", "npc_presence", "scene_location", "clock_delta",
    "event", "queue_consequence", "world_fact", "character_fact",
    "player_fact", "relation", "front_clock_delta", "reveal_clue",
}


@dataclass(frozen=True)
class SystemContinuityRules:
    fact_ranges: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    fact_values: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    mutually_exclusive: tuple[tuple[str, ...], ...] = ()
    forbidden_effects: frozenset[str] = frozenset()

    @classmethod
    def from_dict(cls, data: Any) -> "SystemContinuityRules":
        if data in (None, {}):
            return cls()
        if not isinstance(data, dict):
            raise ValueError("continuity_rules debe ser un mapa")
        unknown = set(data) - {"fact_ranges", "fact_values", "mutually_exclusive", "forbidden_effects"}
        if unknown:
            raise ValueError(f"continuity_rules: claves desconocidas {sorted(unknown)}")

        ranges: dict[str, tuple[float | None, float | None]] = {}
        for key, spec in (data.get("fact_ranges") or {}).items():
            if not isinstance(spec, dict) or not ({"min", "max"} & set(spec)):
                raise ValueError(f"fact_ranges.{key} requiere min y/o max")
            low = spec.get("min")
            high = spec.get("max")
            for bound in (low, high):
                if bound is not None and (isinstance(bound, bool) or not isinstance(bound, (int, float))):
                    raise ValueError(f"fact_ranges.{key}: límites numéricos")
            if low is not None and high is not None and low > high:
                raise ValueError(f"fact_ranges.{key}: min > max")
            ranges[str(key)] = (low, high)

        values: dict[str, tuple[Any, ...]] = {}
        for key, allowed in (data.get("fact_values") or {}).items():
            if not isinstance(allowed, list) or not allowed:
                raise ValueError(f"fact_values.{key} debe ser una lista no vacía")
            values[str(key)] = tuple(allowed)

        groups = []
        for group in data.get("mutually_exclusive") or []:
            if not isinstance(group, list) or len(group) < 2:
                raise ValueError("mutually_exclusive: cada grupo necesita al menos dos hechos")
            groups.append(tuple(str(x) for x in group))

        forbidden = frozenset(str(x) for x in data.get("forbidden_effects") or [])
        bad = forbidden - _KNOWN_EFFECTS
        if bad:
            raise ValueError(f"forbidden_effects: tipos desconocidos {sorted(bad)}")

        return cls(ranges, values, tuple(groups), forbidden)

    @property
    def empty(self) -> bool:
        return not (self.fact_ranges or self.fact_values or self.mutually_exclusive
                    or self.forbidden_effects)

    # ── Validación ────────────────────────────────────────────
    @staticmethod
    def _iter_effects(effects: Any, depth: int = 0) -> Iterator[dict]:
        if not isinstance(effects, list) or depth > 5:
            return
        for effect in effects:
            if not isinstance(effect, dict):
                continue
            yield effect
            if effect.get("type") == "queue_consequence":
                yield from SystemContinuityRules._iter_effects(effect.get("effects"), depth + 1)

    def _proposed_facts(self, proposal: dict) -> list[tuple[str, Any, str]]:
        """(clave, valor, origen) de todos los hechos que la propuesta fijaría."""
        found = []
        facts = proposal.get("facts")
        if isinstance(facts, dict):
            for key, value in facts.items():
                found.append((str(key), value, "facts"))
        for consequence in proposal.get("consequences") or []:
            if not isinstance(consequence, dict):
                continue
            for effect in self._iter_effects(consequence.get("effects")):
                if effect.get("type") in _FACT_EFFECTS and "key" in effect:
                    found.append((str(effect["key"]), effect.get("value"), effect["type"]))
        return found

    @staticmethod
    def _state_facts(state_data: dict) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for bucket in (
            state_data.get("hechos_conocidos", {}),
            (state_data.get("conocimiento", {}) or {}).get("mundo", {}),
        ):
            if not isinstance(bucket, dict):
                continue
            for key, entry in bucket.items():
                merged[str(key)] = entry.get("valor") if isinstance(entry, dict) else entry
        return merged

    def validate(self, proposal: dict, state_data: dict, system_slug: str = "") -> list:
        from narrator.core.continuity_validator import ContinuityIssue

        if self.empty or not isinstance(proposal, dict):
            return []
        label = f" ({system_slug})" if system_slug else ""
        issues = []

        for consequence in proposal.get("consequences") or []:
            if not isinstance(consequence, dict):
                continue
            for effect in self._iter_effects(consequence.get("effects")):
                kind = str(effect.get("type") or "")
                if kind in self.forbidden_effects:
                    issues.append(ContinuityIssue(
                        "system_forbidden_effect", "error",
                        f"El sistema{label} no admite efectos '{kind}'.",
                    ))

        proposed = self._proposed_facts(proposal)
        for key, value, origin in proposed:
            if key in self.fact_ranges:
                low, high = self.fact_ranges[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    issues.append(ContinuityIssue(
                        "system_fact_type", "error",
                        f"El hecho '{key}'{label} debe ser numérico (origen: {origin}).",
                    ))
                elif (low is not None and value < low) or (high is not None and value > high):
                    issues.append(ContinuityIssue(
                        "system_fact_out_of_range", "error",
                        f"El hecho '{key}'{label}={value} sale del rango {low}..{high}.",
                    ))
            if key in self.fact_values and value not in self.fact_values[key]:
                issues.append(ContinuityIssue(
                    "system_fact_value", "error",
                    f"El hecho '{key}'{label}={value!r} no es uno de {list(self.fact_values[key])}.",
                ))

        if self.mutually_exclusive:
            combined = self._state_facts(state_data or {})
            for key, value, _origin in proposed:
                combined[key] = value
            for group in self.mutually_exclusive:
                active = [key for key in group if combined.get(key) is True]
                if len(active) > 1:
                    issues.append(ContinuityIssue(
                        "system_exclusive_facts", "error",
                        f"Los hechos {active}{label} son incompatibles entre sí.",
                    ))
        return issues
