"""Secretos con descubrimiento gradual y control de fugas (Fase E).

Un secreto pertenece a una entidad (NPC, facción o locación) y se descubre por
pistas ordenadas. Lo que cada perspectiva sabe se guarda por separado:

    secretos:
      principe-tremere:
        tema: "La identidad del Príncipe"       # rótulo público, sin spoiler
        verdad: "El Príncipe es un Tremere..."  # oculta hasta descubrir todo
        sobre: {tipo: npc, nombre: "Valerius"}
        pistas: ["Lleva un anillo con sello...", "Sus guardias..."]
        descubiertas: {jugador: 1, personajes: {Alicia: 2}}

Reglas:
- El narrador ve el tema, las pistas ya conocidas por la perspectiva y SOLO la
  próxima pista disponible (para revelarla si la ficción lo justifica).
- La verdad se expone recién cuando la perspectiva conoce todas las pistas.
- ``find_leaks`` detecta en un texto material todavía oculto (verdad o pistas
  posteriores a la próxima), por coincidencia de n-gramas normalizados.
"""

from __future__ import annotations

import re
from typing import Any

from narrator.core.entity_registry import fold_name

ENTITY_TYPES = {"npc", "faccion", "locacion"}
_WORD_RE = re.compile(r"[a-z0-9ñ]+")
_LEAK_NGRAM = 4


class SecretError(ValueError):
    pass


def _bucket(state) -> dict:
    return state.data.setdefault("secretos", {})


def add_secret(
    state,
    secret_id: str,
    *,
    tema: str,
    verdad: str,
    pistas: list[str],
    sobre_tipo: str = "",
    sobre_nombre: str = "",
) -> dict:
    secret_id = str(secret_id).strip()
    if not secret_id or not str(tema).strip() or not str(verdad).strip():
        raise SecretError("un secreto requiere id, tema y verdad")
    clean_clues = [str(p).strip() for p in pistas or [] if str(p).strip()]
    if not clean_clues:
        raise SecretError("un secreto requiere al menos una pista")
    if sobre_tipo and sobre_tipo not in ENTITY_TYPES:
        raise SecretError(f"tipo de entidad inválido: {sobre_tipo}")
    entry = {
        "tema": str(tema).strip(),
        "verdad": str(verdad).strip(),
        "sobre": {"tipo": sobre_tipo, "nombre": str(sobre_nombre).strip()},
        "pistas": clean_clues,
        "descubiertas": {"jugador": 0, "personajes": {}},
    }
    _bucket(state)[secret_id] = entry
    state.save()
    return dict(entry)


def known_count(entry: dict, *, character: str = "") -> int:
    found = entry.get("descubiertas", {}) or {}
    if character:
        return int((found.get("personajes", {}) or {}).get(character, 0) or 0)
    return int(found.get("jugador", 0) or 0)


def status(entry: dict, *, character: str = "") -> str:
    known = known_count(entry, character=character)
    if known <= 0:
        return "oculto"
    if known >= len(entry.get("pistas", [])):
        return "revelado"
    return "parcial"


def reveal_clue(state, secret_id: str, *, character: str = "", source: str = "") -> dict:
    """Avanza una pista para la perspectiva indicada (jugador por defecto)."""
    entry = _bucket(state).get(str(secret_id).strip())
    if entry is None:
        raise SecretError(f"secreto inexistente: {secret_id}")
    total = len(entry.get("pistas", []))
    known = known_count(entry, character=character)
    if known >= total:
        return {"secret": secret_id, "known": known, "status": "revelado", "advanced": False}
    known += 1
    found = entry.setdefault("descubiertas", {"jugador": 0, "personajes": {}})
    if character:
        found.setdefault("personajes", {})[character] = known
    else:
        found["jugador"] = known
    clue = entry["pistas"][known - 1]
    key = f"pista:{secret_id}:{known}"
    if character:
        state._set_perspective_fact("personajes", key, clue, source=source, subject=character)
    else:
        state._set_perspective_fact("jugador", key, clue, source=source)
    result_status = status(entry, character=character)
    if result_status == "revelado":
        truth_key = f"secreto:{secret_id}"
        if character:
            state._set_perspective_fact("personajes", truth_key, entry["verdad"],
                                        source=source, subject=character)
        else:
            state._set_perspective_fact("jugador", truth_key, entry["verdad"], source=source)
    state.save()
    return {"secret": secret_id, "known": known, "status": result_status, "advanced": True,
            "clue": clue}


def _relevant(entry: dict, entities: set[str]) -> bool:
    name = (entry.get("sobre") or {}).get("nombre", "")
    return not entities or not name or fold_name(name) in entities


def narrator_section(state, *, character: str = "", scene_entities: list[str] | None = None,
                     limit: int = 4) -> str:
    """Bloque de prompt con lo que el narrador puede usar de cada secreto."""
    entities = {fold_name(e) for e in (scene_entities or []) if e}
    lines = []
    for secret_id, entry in _bucket(state).items():
        if not _relevant(entry, entities):
            continue
        known = known_count(entry, character=character)
        clues = entry.get("pistas", [])
        about = (entry.get("sobre") or {}).get("nombre", "")
        header = f"- {entry.get('tema')}" + (f" (sobre {about})" if about else "")
        st = status(entry, character=character)
        if st == "revelado":
            lines.append(f"{header} — REVELADO: {entry.get('verdad')}")
        else:
            parts = [f"{header} — {st} {known}/{len(clues)}"]
            if known:
                parts.append("pistas ya conocidas: " + " | ".join(clues[:known]))
            parts.append(f"próxima pista (solo si la acción la merece): {clues[known]}")
            parts.append(f"para registrarla: discoveries [{{\"secret\": \"{secret_id}\"}}]")
            lines.append("; ".join(parts))
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    return ("SECRETOS EN JUEGO (no reveles la verdad oculta ni pistas posteriores a la "
            "próxima; el descubrimiento es gradual):\n" + "\n".join(lines))


def _ngrams(text: str, n: int = _LEAK_NGRAM) -> set[tuple[str, ...]]:
    words = _WORD_RE.findall(fold_name(text))
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def hidden_material(state, *, character: str = "") -> list[tuple[str, str]]:
    """(secreto, texto) que todavía no debe aparecer: verdad y pistas lejanas."""
    hidden = []
    for secret_id, entry in _bucket(state).items():
        if status(entry, character=character) == "revelado":
            continue
        hidden.append((secret_id, entry.get("verdad", "")))
        known = known_count(entry, character=character)
        for clue in entry.get("pistas", [])[known + 1:]:
            hidden.append((secret_id, clue))
    return hidden


def find_leaks(text: str, state, *, character: str = "") -> list[str]:
    """Secretos cuyo material oculto aparece en ``text`` (4-gramas sin tildes)."""
    grams = _ngrams(text)
    if not grams:
        return []
    leaked = []
    for secret_id, material in hidden_material(state, character=character):
        material_grams = _ngrams(material)
        if material_grams and grams & material_grams and secret_id not in leaked:
            leaked.append(secret_id)
    return leaked


def validate_discoveries(state, discoveries: Any) -> list[str]:
    """Errores de forma/referencia de una lista de descubrimientos propuesta."""
    if discoveries in (None, []):
        return []
    if not isinstance(discoveries, list):
        return ["discoveries debe ser una lista"]
    errors = []
    bucket = getattr(state, "data", {}).get("secretos", {}) if state is not None else {}
    for item in discoveries:
        if not isinstance(item, dict) or not str(item.get("secret") or "").strip():
            errors.append("cada descubrimiento requiere 'secret'")
            continue
        if state is not None and str(item["secret"]).strip() not in bucket:
            errors.append(f"secreto inexistente: {item['secret']}")
    return errors
