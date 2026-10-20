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
from dataclasses import dataclass
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
            "edition": str(data.get("edition") or ""),
            "keywords": {
                fold_name(k): float(v) for k, v in (block.get("keywords") or {}).items()
            },
            "ediciones": {
                str(edition): [fold_name(k) for k in keywords or []]
                for edition, keywords in (block.get("ediciones") or {}).items()
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


def _count(folded: str, keyword: str) -> int:
    pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])"
    return len(re.findall(pattern, folded))


@dataclass(frozen=True)
class ManualIdentity:
    """Asociación manual ↔ System Pack."""

    slug: str
    nombre: str
    pack_edition: str
    edition: str            # edición detectada en el texto ('' si no hay señal)
    confidence: float       # fracción del puntaje total que obtuvo el pack ganador

    @property
    def edition_mismatch(self) -> bool:
        return bool(self.edition and self.pack_edition and
                    fold_name(self.edition) != fold_name(self.pack_edition))

    @property
    def warning(self) -> str:
        if self.edition_mismatch:
            return (f"El manual parece de la edición {self.edition}, pero el System Pack "
                    f"'{self.slug}' modela la edición {self.pack_edition}: revisá las "
                    "reglas antes de confiar en la resolución automática.")
        if self.slug != GENERIC_SLUG and self.confidence < 0.5:
            return "Detección de sistema poco segura: confirmalo manualmente."
        return ""

    def to_dict(self) -> dict:
        return {
            "slug": self.slug, "nombre": self.nombre, "pack_edition": self.pack_edition,
            "edition": self.edition, "confidence": self.confidence, "warning": self.warning,
        }


def identify_manual(text: str, systems_path: str | Path) -> ManualIdentity:
    """Sistema + edición de un manual, con confianza y aviso de incompatibilidad."""
    profiles = load_detection_profiles(systems_path)
    scores = score_text(text or "", profiles)
    name, slug = detect_system(text, systems_path)
    total = sum(scores.values())
    confidence = round(scores.get(slug, 0.0) / total, 3) if total else 0.0
    profile = profiles.get(slug, {})
    folded = fold_name(text)
    edition_scores = {
        edition: sum(_count(folded, k) for k in keywords if k)
        for edition, keywords in (profile.get("ediciones") or {}).items()
    }
    edition = ""
    if edition_scores and max(edition_scores.values()) > 0:
        edition = max(edition_scores.items(), key=lambda item: item[1])[0]
    return ManualIdentity(slug, name, profile.get("edition", ""), edition, confidence)
