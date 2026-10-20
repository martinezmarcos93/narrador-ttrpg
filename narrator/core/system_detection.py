"""Detección del sistema de juego a partir del texto de un manual.

Cada System Pack declara su bloque ``deteccion``::

    deteccion:
      nombre_visible: "Mundo de Tinieblas (Vampiro V20)"
      keywords: {vampiro: 3, mascarada: 3, camarilla: 2, clan: 1}

Se cuentan las apariciones (sin tildes ni mayúsculas) ponderadas por peso y
gana el pack con mayor puntaje. Puntaje cero → ``generic``. Así un manual de
Hombre Lobo que menciona vampiros no se confunde con Vampiro.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from narrator.core.entity_registry import fold_name
from narrator.logger import logger

GENERIC_SLUG = "generic"


def load_detection_profiles(systems_path: str | Path) -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    for path in sorted(Path(systems_path).glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            logger.error("Pack ilegible al detectar sistema (%s): %s", path, exc)
            continue
        block = data.get("deteccion") or {}
        slug = str(data.get("slug") or path.stem)
        profiles[slug] = {
            "nombre_visible": str(block.get("nombre_visible") or data.get("sistema") or slug),
            "keywords": {
                fold_name(k): float(v) for k, v in (block.get("keywords") or {}).items()
            },
        }
    return profiles


def score_text(text: str, profiles: dict[str, dict]) -> dict[str, float]:
    folded = fold_name(text)
    scores: dict[str, float] = {}
    for slug, profile in profiles.items():
        total = 0.0
        for keyword, weight in profile["keywords"].items():
            if not keyword:
                continue
            pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])"
            total += weight * len(re.findall(pattern, folded))
        scores[slug] = total
    return scores


def detect_system(text: str, systems_path: str | Path) -> tuple[str, str]:
    """Devuelve (nombre_visible, slug) del sistema más probable."""
    profiles = load_detection_profiles(systems_path)
    scores = score_text(text or "", profiles)
    best = max(scores.items(), key=lambda item: (item[1], item[0] != GENERIC_SLUG), default=None)
    if not best or best[1] <= 0:
        slug = GENERIC_SLUG
    else:
        slug = best[0]
    name = profiles.get(slug, {}).get("nombre_visible", "Sistema Genérico")
    return name, slug
