"""Clasificador formal y determinista de la intención del jugador (Fase C).

No reemplaza al LLM: decide qué necesita Python antes de narrar.

Categorías (``IntentResult.kind``):

- ``out_of_character``: el jugador habla con el sistema/director ("OOC", "(fuera de rol)").
- ``rules_question``: pregunta por una regla o mecánica ("¿cómo funciona...?").
- ``lore_question``: pregunta por el mundo ("¿quién es...?", "¿qué sé de...?").
- ``recall``: pide recordar lo ocurrido ("¿qué pasó...?", "recordame").
- ``mechanical_action``: acción con riesgo que coincide con una acción del System Pack
  o con verbos de riesgo (atacar, escalar, esconderse...).
- ``investigation``: buscar, examinar, analizar pistas.
- ``social``: persuadir, negociar, intimidar, mentir, preguntar a un NPC.
- ``player_action``: acción declarada sin riesgo evidente.
- ``dialogue_or_description``: diálogo en personaje o descripción.
- ``unknown``: texto vacío.

``needs_roll`` indica si conviene pedir una tirada; ``action`` trae la acción
del pack (atributo/habilidad) cuando hubo coincidencia.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from narrator.core.entity_registry import fold_name

_OOC = ("ooc", "fuera de rol", "fuera de personaje", "pregunta al master", "pregunta al narrador",
        "((", "[ooc")
_RULES_Q = ("como funciona", "que tirada", "que dado", "cuantos dados", "que regla", "regla de",
            "que dificultad", "puedo usar", "me sirve", "cuanto cuesta", "como se calcula")
_LORE_Q = ("quien es", "quienes son", "que es", "que son", "que se de", "que sabe mi personaje",
           "donde queda", "historia de", "que significa")
_RECALL = ("que paso", "recordame", "recuerdame", "resumen de", "que hicimos", "en que estabamos")
_RISK = ("ataco", "atacar", "golpeo", "disparo", "apunalo", "corro", "huyo", "salto", "trepo",
         "escalo", "me escondo", "esquivo", "forcejeo", "fuerzo", "rompo", "robo", "embisto",
         "lucho", "peleo", "muerdo", "desgarro", "lanzo", "conjuro", "invoco", "nado",
         "golpear", "disparar", "apunalar", "correr", "huir", "saltar", "trepar", "escalar",
         "esconderme", "esquivar", "forzar", "romper", "robar", "embestir", "luchar", "pelear",
         "morder", "desgarrar", "lanzar", "conjurar", "invocar", "nadar")
_INVESTIGATION = ("investigo", "examino", "busco", "reviso", "analizo", "inspecciono", "rastreo",
                  "sigo el rastro", "leo", "estudio", "descifro", "registro",
                  "investigar", "examinar", "buscar", "revisar", "analizar", "inspeccionar",
                  "rastrear", "estudiar", "descifrar", "registrar")
_SOCIAL = ("convenzo", "persuado", "negocio", "intimido", "amenazo", "miento", "engano",
           "seduzco", "soborno", "le pregunto", "le digo", "le pido", "interrogo", "regateo",
           "convencer", "persuadir", "negociar", "intimidar", "amenazar", "mentirle",
           "enganar", "seducir", "sobornar", "interrogar", "regatear")
_ACTION = ("quiero", "intento", "voy a", "entro", "salgo", "camino", "abro", "cierro", "tomo",
           "agarro", "me acerco", "me alejo", "espero", "me quedo")
_QUESTION_RE = re.compile(r"[¿?]")


def _contains(text: str, needles) -> list[str]:
    hits = []
    for needle in needles:
        n = fold_name(needle)
        if n and re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", text):
            hits.append(needle)
    return hits


@dataclass
class IntentResult:
    kind: str
    reason: str
    needs_roll: bool = False
    categories: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    action: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "needs_roll": self.needs_roll,
            "categories": list(self.categories),
            "matched": list(self.matched),
            "action": dict(self.action) if self.action else None,
        }


def _pack_action(text: str, resolution: dict | None) -> tuple[dict | None, list[str]]:
    for accion in (resolution or {}).get("acciones", []) or []:
        hits = _contains(text, accion.get("keywords", []))
        if hits:
            return dict(accion), hits
    return None, []


def classify_intent(text: str, resolution: dict | None = None) -> IntentResult:
    """Clasifica ``text``; ``resolution`` es el bloque del System Pack activo."""
    raw = (text or "").strip()
    if not raw:
        return IntentResult("unknown", "texto vacío")
    folded = fold_name(raw)
    is_question = bool(_QUESTION_RE.search(raw))

    if hits := _contains(folded, _OOC) or (raw.startswith("(") and raw.endswith(")")):
        return IntentResult("out_of_character", "el jugador habla fuera de personaje",
                            matched=hits if isinstance(hits, list) else [])
    if is_question or folded.startswith(("como ", "que ", "quien ", "donde ", "cuanto")):
        if hits := _contains(folded, _RECALL):
            return IntentResult("recall", "pide recordar sucesos previos", matched=hits)
        if hits := _contains(folded, _RULES_Q):
            return IntentResult("rules_question", "pregunta por una regla o mecánica",
                                matched=hits)
        if hits := _contains(folded, _LORE_Q):
            return IntentResult("lore_question", "pregunta por el mundo o el lore",
                                matched=hits)
    elif hits := _contains(folded, _RECALL):
        return IntentResult("recall", "pide recordar sucesos previos", matched=hits)

    action, pack_hits = _pack_action(folded, resolution)
    categories = []
    matched = list(pack_hits)
    if risk := _contains(folded, _RISK):
        categories.append("mechanical")
        matched += risk
    if inv := _contains(folded, _INVESTIGATION):
        categories.append("investigation")
        matched += inv
    if social := _contains(folded, _SOCIAL):
        categories.append("social")
        matched += social
    if action is not None and not categories:
        categories.append("mechanical")

    if "mechanical" in categories:
        return IntentResult("mechanical_action", "acción con riesgo que puede requerir tirada",
                            needs_roll=True, categories=categories, matched=matched,
                            action=action)
    if "investigation" in categories:
        return IntentResult("investigation", "búsqueda o análisis de pistas",
                            needs_roll=action is not None, categories=categories,
                            matched=matched, action=action)
    if "social" in categories:
        return IntentResult("social", "interacción social con un NPC",
                            needs_roll=action is not None, categories=categories,
                            matched=matched, action=action)
    if hits := _contains(folded, _ACTION):
        return IntentResult("player_action", "acción declarada sin riesgo evidente",
                            matched=hits)
    return IntentResult("dialogue_or_description",
                        "interacción narrativa sin señal mecánica explícita")
