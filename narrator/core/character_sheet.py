"""Contrato de las fichas de personaje declaradas en los System Packs.

`character_sheet_schema` describe secciones y campos; este módulo:

- valida el schema (tipos, rangos, tracks de salud, derivados);
- calcula estadísticas derivadas con el DSL seguro de ``derived_stats``;
- interpreta tracks (p. ej. niveles de salud con penalizador).

Formato de un track::

    - name: Salud
      display: track
      track_field: salud_danio        # int: niveles de daño marcados
      levels:
        - {label: Magullado, penalty: 0}
        - {label: Lastimado, penalty: -1}
        ...

Formato de derivados::

    derived:
      sangre_max: {computer: vtm_sangre_max}
      fuerza_voluntad_temp_max: {copy_of: fuerza_voluntad}
"""

from __future__ import annotations

from typing import Any

from narrator.core import derived_stats
from narrator.logger import logger

FIELD_TYPES = {"string", "int", "list", "map", "bool"}
DISPLAYS = {"default", "dots", "stat_block", "track"}


# ── Funciones derivadas registradas (vocabulario cerrado) ──────────────
# Vampiro V20: reserva de sangre máxima y gasto por turno según generación.
_VTM_GENERATION_BLOOD = {
    15: (10, 1), 14: (10, 1), 13: (10, 1), 12: (11, 1), 11: (12, 1), 10: (13, 1),
    9: (14, 2), 8: (15, 3), 7: (20, 4), 6: (30, 6), 5: (40, 8), 4: (50, 10),
    3: (100, 50),
}


def _vtm_generation(data: dict) -> int:
    try:
        return int(data["generacion"])
    except (KeyError, TypeError, ValueError):
        raise derived_stats.DerivedStatError("generacion ausente o no numérica")


@derived_stats.register_computer("vtm_sangre_max")
def _vtm_sangre_max(data: dict) -> int:
    gen = _vtm_generation(data)
    return _VTM_GENERATION_BLOOD.get(max(3, min(15, gen)))[0]


@derived_stats.register_computer("vtm_sangre_por_turno")
def _vtm_sangre_por_turno(data: dict) -> int:
    gen = _vtm_generation(data)
    return _VTM_GENERATION_BLOOD.get(max(3, min(15, gen)))[1]


@derived_stats.register_computer("coc_cordura_maxima")
def _coc_cordura_maxima(data: dict) -> int:
    try:
        mitos = int(data.get("mitos_cthulhu", 0) or 0)
    except (TypeError, ValueError):
        raise derived_stats.DerivedStatError("mitos_cthulhu no numérico")
    return max(0, 99 - mitos)


@derived_stats.register_computer("coc_puntos_vida")
def _coc_puntos_vida(data: dict) -> int:
    try:
        return (int(data["constitucion"]) + int(data["tamano"])) // 10
    except (KeyError, TypeError, ValueError):
        raise derived_stats.DerivedStatError("constitucion/tamano ausentes")


# ── Utilidades de schema ──────────────────────────────────────────────
def iter_sections(schema: dict):
    """Todas las secciones (base y condicionales) con su origen."""
    for section in (schema or {}).get("base_sections", []) or []:
        yield "base", section
    for archetype, sections in ((schema or {}).get("conditional_sections", {}) or {}).items():
        for section in sections or []:
            yield str(archetype), section


def field_specs(schema: dict) -> dict[str, dict]:
    specs: dict[str, dict] = {}
    for _origin, section in iter_sections(schema):
        for field in section.get("fields", []) or []:
            if isinstance(field, dict) and field.get("key"):
                specs.setdefault(field["key"], field)
    return specs


def _referenced_fields(spec: Any) -> list[str]:
    if not isinstance(spec, dict):
        return []
    refs = []
    for key in ("copy_of", "half_of", "floor_div"):
        if key in spec:
            refs.append(str(spec[key]))
    if isinstance(spec.get("sum_of"), list):
        refs.extend(str(x) for x in spec["sum_of"])
    return refs


def validate_schema(schema: Any) -> list[str]:
    """Errores del schema de ficha; lista vacía si es válido."""
    if schema in (None, {}):
        return []
    if not isinstance(schema, dict):
        return ["character_sheet_schema debe ser un mapa"]
    errors: list[str] = []
    seen_base: set[str] = set()
    for origin, section in iter_sections(schema):
        name = section.get("name", "?") if isinstance(section, dict) else "?"
        where = f"{origin}/{name}"
        if not isinstance(section, dict):
            errors.append(f"{where}: la sección debe ser un mapa")
            continue
        display = section.get("display", "default")
        if display not in DISPLAYS:
            errors.append(f"{where}: display desconocido '{display}'")
        keys_in_section = set()
        for field in section.get("fields", []) or []:
            if not isinstance(field, dict) or not field.get("key"):
                errors.append(f"{where}: campo sin key")
                continue
            key = field["key"]
            ftype = field.get("type", "string")
            if ftype not in FIELD_TYPES:
                errors.append(f"{where}.{key}: tipo desconocido '{ftype}'")
            if "min" in field and "max" in field and field["min"] > field["max"]:
                errors.append(f"{where}.{key}: min > max")
            if key in keys_in_section:
                errors.append(f"{where}.{key}: clave repetida en la sección")
            keys_in_section.add(key)
            if origin == "base":
                if key in seen_base:
                    errors.append(f"{where}.{key}: clave repetida entre secciones base")
                seen_base.add(key)
        if display == "track":
            levels = section.get("levels")
            track_field = section.get("track_field")
            if not isinstance(levels, list) or not levels:
                errors.append(f"{where}: un track necesita 'levels'")
            elif any(not isinstance(lv, dict) or "label" not in lv for lv in levels):
                errors.append(f"{where}: cada nivel necesita 'label'")
            if not track_field or track_field not in keys_in_section:
                errors.append(f"{where}: 'track_field' debe ser un campo de la sección")
    specs = field_specs(schema)
    derived = schema.get("derived", {}) or {}
    if not isinstance(derived, dict):
        errors.append("derived debe ser un mapa")
        derived = {}
    available = set(specs)
    for key, spec in derived.items():
        if not isinstance(spec, dict) or not spec:
            errors.append(f"derived.{key}: spec inválida")
            continue
        for ref in _referenced_fields(spec):
            if ref not in available:
                errors.append(f"derived.{key}: referencia campo inexistente '{ref}'")
        if "computer" in spec and spec["computer"] not in derived_stats._REGISTRY:
            errors.append(f"derived.{key}: computer desconocido '{spec['computer']}'")
        available.add(key)
    return errors


def compute_derived(schema: dict, character: dict) -> dict[str, Any]:
    """Calcula los derivados posibles; omite los que dependen de campos ausentes."""
    result: dict[str, Any] = {}
    working = dict(character or {})
    for key, spec in ((schema or {}).get("derived", {}) or {}).items():
        try:
            value = derived_stats.evaluate(spec, working)
        except derived_stats.DerivedStatError as exc:
            logger.debug("Derivado '%s' no calculable todavía: %s", key, exc)
            continue
        result[key] = value
        working[key] = value
    return result


def track_sections(schema: dict) -> list[dict]:
    return [s for _o, s in iter_sections(schema) if s.get("display") == "track"]


def track_status(section: dict, character: dict) -> dict[str, Any]:
    """Nivel actual de un track: etiqueta, penalizador y si está al máximo."""
    levels = section.get("levels") or []
    try:
        marked = int((character or {}).get(section.get("track_field"), 0) or 0)
    except (TypeError, ValueError):
        marked = 0
    marked = max(0, min(marked, len(levels)))
    if marked == 0:
        return {"marked": 0, "label": "Ileso", "penalty": 0, "maxed": False}
    level = levels[marked - 1]
    return {
        "marked": marked,
        "label": str(level.get("label")),
        "penalty": int(level.get("penalty", 0) or 0),
        "maxed": marked >= len(levels),
    }


def wound_penalty(schema: dict, character: dict) -> int:
    """Penalizador combinado de todos los tracks (en V20, la salud)."""
    return sum(track_status(s, character)["penalty"] for s in track_sections(schema))
