"""Dinámica social determinista (Fase D).

- Tipos de relación con valencia y decaimiento por sesión.
- Niveles (tiers) por fuerza: hostil, tensa, neutral, cordial, aliada.
- Historial temporal de cada arista.
- Consecuencias sociales: cruzar de nivel registra un evento
  ("relación A -> B pasa a hostil") que la causalidad puede usar como trigger.
"""

from __future__ import annotations

from narrator.core.entity_registry import fold_name

# tipo -> (valencia esperada, decaimiento hacia 0 por sesión)
RELATION_TYPES: dict[str, tuple[int, int]] = {
    "aliado": (1, 0), "amistad": (1, 0), "lealtad": (1, 0), "confianza": (1, 0),
    "amor": (1, 0), "respeto": (1, 0), "deuda": (0, 0), "favor": (1, 5),
    "neutral": (0, 0), "rivalidad": (-1, 0), "desconfianza": (-1, 5),
    "enemigo": (-1, 0), "odio": (-1, 0), "amenaza": (-1, 0), "temor": (-1, 10),
    "desprecio": (-1, 0),
}
TIERS = ((-60, "hostil"), (-20, "tensa"), (20, "neutral"), (60, "cordial"))
HISTORY_LIMIT = 20


def tier(strength: int) -> str:
    for upper, label in TIERS:
        if strength <= upper:
            return label
    return "aliada"


def relation_type(name: str) -> str:
    """Tipo normalizado (sin tildes); los desconocidos se conservan tal cual."""
    return fold_name(name).replace(" ", "_") or "neutral"


def valence_warning(relation: str, strength: int) -> str:
    """Aviso si la fuerza contradice la valencia del tipo (p. ej. 'enemigo' con +70)."""
    expected = RELATION_TYPES.get(relation_type(relation), (0, 0))[0]
    if expected > 0 and strength < -20:
        return f"'{relation}' con fuerza {strength} es contradictorio"
    if expected < 0 and strength > 20:
        return f"'{relation}' con fuerza {strength} es contradictorio"
    return ""


def tier_change_event(source: str, target: str, before: int | None, after: int) -> str:
    """Evento social si la arista cambió de nivel (o se creó fuera de neutral)."""
    new_tier = tier(after)
    if before is None:
        return "" if new_tier == "neutral" else f"relación {source} -> {target} pasa a {new_tier}"
    if tier(before) == new_tier:
        return ""
    return f"relación {source} -> {target} pasa a {new_tier}"


def session_decay(relations: dict) -> list[str]:
    """Aplica el decaimiento por sesión de tipos volátiles (temor, favor...).
    Devuelve las claves modificadas. No crea eventos: es erosión, no un hecho."""
    changed = []
    for key, item in relations.items():
        if not isinstance(item, dict):
            continue
        rate = RELATION_TYPES.get(relation_type(item.get("relation", "")), (0, 0))[1]
        strength = int(item.get("strength", 0) or 0)
        if not rate or strength == 0:
            continue
        step = min(rate, abs(strength))
        item["strength"] = strength - step if strength > 0 else strength + step
        item.setdefault("historial", []).append({
            "sesion": item.get("sesion"), "strength": item["strength"], "reason": "decaimiento",
        })
        del item["historial"][:-HISTORY_LIMIT]
        changed.append(key)
    return changed
