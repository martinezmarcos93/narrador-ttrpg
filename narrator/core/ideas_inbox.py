"""
Ideas Inbox — bandeja de borradores en el vault (Notas/) con workflow de estados.

    raw_idea -> developing -> ready_to_implement -> implemented

Notas sueltas para anotar ideas durante la sesión antes de convertirlas en
NPC/Locación formal. Frontmatter mínimo: tipo, titulo, estado, prioridad.
"""

import re
from datetime import datetime
from pathlib import Path

from narrator.logger import logger

try:
    import frontmatter as fm
    _HAS_FRONTMATTER = True
except ImportError:
    _HAS_FRONTMATTER = False

ESTADOS = ("raw_idea", "developing", "ready_to_implement", "implemented")
_ESTADO_INICIAL = "raw_idea"
_TIPO_DIRS = {"npc": "NPCs", "locacion": "Locaciones"}


def _read(path: Path) -> "tuple[dict, str]":
    text = path.read_text(encoding="utf-8", errors="ignore")
    if _HAS_FRONTMATTER:
        try:
            post = fm.loads(text)
            return dict(post.metadata), post.content
        except Exception as e:
            logger.warning("Frontmatter inválido en %s: %s", path, e)
    return {}, text


def _safe_filename(titulo: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "", titulo)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:60] or "idea"


class IdeasInbox:
    def __init__(self, vault_path: str = "./vault"):
        self.vault = Path(vault_path)

    def _ideas_dir(self) -> Path:
        d = self.vault / "Notas"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── Creación ────────────────────────────────────────────────
    def create(self, titulo: str, contenido: str = "", prioridad: str = "media") -> Path:
        """Crea una nueva idea en estado raw_idea. Devuelve la ruta del archivo."""
        base = _safe_filename(titulo)
        path = self._ideas_dir() / f"Idea_{base}.md"
        n = 1
        while path.exists():
            n += 1
            path = self._ideas_dir() / f"Idea_{base}_{n}.md"

        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        text = (
            "---\n"
            "tipo: idea\n"
            f'titulo: "{titulo}"\n'
            f"estado: {_ESTADO_INICIAL}\n"
            f"prioridad: {prioridad}\n"
            f'creada: "{fecha}"\n'
            'tags: ["idea"]\n'
            "---\n\n"
            f"# {titulo}\n\n"
            f"{contenido}\n"
        )
        path.write_text(text, encoding="utf-8")
        return path

    # ── Lectura ─────────────────────────────────────────────────
    def list_by_state(self, estado: "str | None" = None) -> "list[dict]":
        """Ideas del vault, opcionalmente filtradas por estado."""
        ideas = []
        if not self._ideas_dir_exists():
            return ideas
        for path in self._ideas_dir().glob("Idea_*.md"):
            meta, _ = _read(path)
            if meta.get("tipo") != "idea":
                continue
            if estado and meta.get("estado") != estado:
                continue
            ideas.append({"path": path, "meta": meta})
        return ideas

    def _ideas_dir_exists(self) -> bool:
        return (self.vault / "Notas").exists()

    # ── Transición de estado ───────────────────────────────────
    def set_state(self, path: "Path | str", nuevo_estado: str) -> bool:
        if nuevo_estado not in ESTADOS:
            raise ValueError(f"Estado desconocido: '{nuevo_estado}'. Válidos: {ESTADOS}")
        path = Path(path)
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False

        if re.search(r"^estado:\s*\S+", content, re.MULTILINE):
            content = re.sub(
                r"^estado:\s*\S+", f"estado: {nuevo_estado}", content, count=1, flags=re.MULTILINE
            )
        else:
            content = content.replace("---\n", f"---\nestado: {nuevo_estado}\n", 1)
        path.write_text(content, encoding="utf-8")
        return True

    # ── Promoción a entidad formal ─────────────────────────────
    def promote(self, path: "Path | str", tipo: str) -> Path:
        """Materializa una idea como NPC o Locación formal del vault y
        marca la idea original como 'implemented'."""
        if tipo not in _TIPO_DIRS:
            raise ValueError(f"Tipo no soportado para promoción: '{tipo}'. Válidos: {list(_TIPO_DIRS)}")
        path = Path(path)
        meta, body = _read(path)
        titulo = meta.get("titulo") or path.stem

        target_dir = self.vault / _TIPO_DIRS[tipo]
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{_safe_filename(titulo)}.md"

        text = (
            "---\n"
            f"tipo: {tipo}\n"
            f'nombre: "{titulo}"\n'
            "---\n\n"
            f"{body.strip()}\n"
        )
        target_path.write_text(text, encoding="utf-8")
        self.set_state(path, "implemented")
        return target_path
