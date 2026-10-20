"""
Taxonomía y validación del bloque `resolution:` de los YAML de sistema —
detecta config mal formada al cargar el sistema, antes de que llegue al
RuleArbiter en tiempo de juego. Sin dependencias externas (ni Pydantic ni
jsonschema): validación manual, mismo estilo que RuleArbiter/derived_stats.

Modos de resolución soportados hoy: d20_vs_dc, pool_d10, percentil, ratio.
"""

MECANICAS_CONOCIDAS = ("d20_vs_dc", "pool_d10", "percentil", "ratio")

# d20_vs_dc, pool_d10 y percentil comparten la misma forma de config:
# escalera de dificultades + atributo por defecto + acciones por keyword.
_MECANICAS_CON_DIFICULTADES = ("d20_vs_dc", "pool_d10", "percentil")


class ResolutionSchemaError(ValueError):
    """El bloque `resolution:` de un YAML de sistema no cumple su schema."""


def _require(res: dict, key: str, tipo: type, path: str) -> None:
    if key not in res:
        raise ResolutionSchemaError(f"{path}: falta la clave requerida '{key}'")
    if not isinstance(res[key], tipo):
        raise ResolutionSchemaError(
            f"{path}.{key}: esperado {tipo.__name__}, recibido {type(res[key]).__name__}"
        )


def _validate_acciones(acciones, path: str) -> None:
    if not isinstance(acciones, list) or not acciones:
        raise ResolutionSchemaError(f"{path}.acciones: esperado una lista no vacía")
    for i, accion in enumerate(acciones):
        if not isinstance(accion, dict):
            raise ResolutionSchemaError(f"{path}.acciones[{i}]: esperado un objeto")
        for campo in ("keywords", "atributo", "etiqueta"):
            if campo not in accion:
                raise ResolutionSchemaError(f"{path}.acciones[{i}]: falta '{campo}'")
        if "habilidad" in accion and not isinstance(accion["habilidad"], str):
            raise ResolutionSchemaError(f"{path}.acciones[{i}].habilidad: esperado texto")
        if not isinstance(accion["keywords"], list) or not accion["keywords"]:
            raise ResolutionSchemaError(
                f"{path}.acciones[{i}].keywords: esperado una lista no vacía"
            )


def _validate_dificultades_comunes(res: dict, path: str) -> None:
    """Compartido por d20_vs_dc / pool_d10 / percentil."""
    _require(res, "dificultades", dict, path)
    if not res["dificultades"]:
        raise ResolutionSchemaError(f"{path}.dificultades: no puede estar vacío")

    _require(res, "dificultad_default", str, path)
    if res["dificultad_default"] not in res["dificultades"]:
        raise ResolutionSchemaError(
            f"{path}.dificultad_default: '{res['dificultad_default']}' no está en "
            f"dificultades ({list(res['dificultades'])})"
        )

    _require(res, "atributo_default", str, path)
    _require(res, "acciones", list, path)
    _validate_acciones(res["acciones"], path)

    if "keywords_dificultad" in res and not isinstance(res["keywords_dificultad"], dict):
        raise ResolutionSchemaError(f"{path}.keywords_dificultad: esperado un objeto")


def validate_resolution(res: dict, system_slug: str = "?") -> None:
    """Valida el bloque `resolution:` de un sistema contra el schema de su
    mecánica declarada. Lanza ResolutionSchemaError (path/esperado/recibido)
    ante cualquier inconsistencia; no devuelve nada si es válido."""
    path = f"data/systems/{system_slug}.yaml:resolution"
    if not isinstance(res, dict):
        raise ResolutionSchemaError(f"{path}: esperado un objeto, recibido {type(res).__name__}")

    _require(res, "mecanica", str, path)
    mecanica = res["mecanica"]
    if mecanica not in MECANICAS_CONOCIDAS:
        raise ResolutionSchemaError(
            f"{path}.mecanica: '{mecanica}' desconocida. Válidas: {MECANICAS_CONOCIDAS}"
        )

    if mecanica in _MECANICAS_CON_DIFICULTADES:
        _validate_dificultades_comunes(res, path)
    elif mecanica == "ratio":
        _require(res, "bandas", dict, path)
        if not res["bandas"]:
            raise ResolutionSchemaError(f"{path}.bandas: no puede estar vacío")
