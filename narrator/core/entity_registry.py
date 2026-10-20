"""Registro global de entidades del vault de campaña.

ContinuityValidator solo conocía las entidades del estado vivo (escena actual,
relaciones). Este registro le da una autoridad adicional y determinista: las
notas de NPCs, Locaciones, Facciones y Frentes que existen en el vault.

Los nombres se comparan sin distinguir mayúsculas ni tildes, porque el LLM y el
jugador escriben "Cripta del Norte" o "cripta del norte" indistintamente.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Iterable

from narrator.logger import logger

try:
    import frontmatter as _fm

    _HAS_FRONTMATTER = True
except ImportError:  # pragma: no cover - dependencia declarada en pyproject
    _HAS_FRONTMATTER = False


# Carpeta(s) del vault por tipo de entidad.
ENTITY_FOLDERS: dict[str, tuple[str, ...]] = {
    "npc": ("NPCs",),
    "locacion": ("Locaciones",),
    "faccion": ("Cofradias", "Facciones"),
    "frente": ("Frentes",),
}


def fold_name(name: object) -> str:
    """Normaliza un nombre: sin tildes, minúsculas, '_' como espacio, sin dobles espacios."""
    text = unicodedata.normalize("NFKD", str(name or "").replace("_", " ").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


class NameSet:
    """Conjunto de nombres con pertenencia insensible a mayúsculas y tildes."""

    def __init__(self, names: Iterable[object] = ()) -> None:
        self._display: dict[str, str] = {}
        for name in names:
            self.add(name)

    def add(self, name: object) -> None:
        display = str(name or "").strip()
        key = fold_name(display)
        if key:
            self._display.setdefault(key, display)

    def __contains__(self, name: object) -> bool:
        return fold_name(name) in self._display

    def __or__(self, other: Iterable[object]) -> "NameSet":
        merged = NameSet(self._display.values())
        for name in other:
            merged.add(name)
        return merged

    def __iter__(self):
        return iter(self._display.values())

    def __len__(self) -> int:
        return len(self._display)

    def __bool__(self) -> bool:
        return bool(self._display)

    def __repr__(self) -> str:
        return f"NameSet({sorted(self._display.values())!r})"


class EntityRegistry:
    """Índice de nombres de entidades del vault, recalculado si cambian las carpetas."""

    def __init__(self, vault_path: str | Path) -> None:
        self.vault = Path(vault_path)
        self._cache: dict[str, NameSet] = {}
        self._stamp: tuple = ()

    def _current_stamp(self) -> tuple:
        stamp = []
        for folders in ENTITY_FOLDERS.values():
            for folder in folders:
                path = self.vault / folder
                try:
                    stamp.append((folder, path.stat().st_mtime_ns))
                except OSError:
                    stamp.append((folder, None))
        return tuple(stamp)

    @staticmethod
    def _entity_name(path: Path) -> str:
        if _HAS_FRONTMATTER:
            try:
                meta = _fm.load(path).metadata
                nombre = str(meta.get("nombre") or meta.get("name") or "").strip()
                if nombre:
                    return nombre
            except Exception as exc:
                logger.warning("Frontmatter ilegible en %s: %s", path, exc)
        return path.stem.replace("_", " ")

    def refresh(self, *, force: bool = False) -> None:
        stamp = self._current_stamp()
        if not force and stamp == self._stamp and self._cache:
            return
        cache: dict[str, NameSet] = {}
        for kind, folders in ENTITY_FOLDERS.items():
            names = NameSet()
            for folder in folders:
                directory = self.vault / folder
                if not directory.is_dir():
                    continue
                for path in sorted(directory.glob("*.md")):
                    names.add(self._entity_name(path))
            cache[kind] = names
        self._cache = cache
        self._stamp = stamp

    def names(self, kind: str) -> NameSet:
        if kind not in ENTITY_FOLDERS:
            raise ValueError(f"Tipo de entidad desconocido: {kind}")
        self.refresh()
        return self._cache.get(kind, NameSet())

    def has(self, kind: str, name: object) -> bool:
        return name in self.names(kind)

    def snapshot(self) -> dict[str, list[str]]:
        self.refresh()
        return {kind: sorted(names) for kind, names in self._cache.items()}
