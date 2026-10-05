"""
Neurona — una nota Markdown con frontmatter YAML: la unidad del cerebro.

El formato es Obsidian puro: los enlaces son wikilinks con ruta completa
dentro del vault (`[[sistemas/vtm_v20/.../Dominación|Dominación]]`), porque
en los manuales los títulos se repiten ("Sistema", "Introducción") y el
nombre de archivo solo no alcanza para identificar una nota.
"""

import re
import unicodedata
from dataclasses import dataclass, field

import yaml

# Caracteres que no puede llevar un nombre de archivo (el vault vive en un
# disco NTFS) o que rompen un wikilink de Obsidian.
_PROHIBIDOS = re.compile(r'[\\/:*?"<>|#^\[\]]')
LARGO_MAX_NOMBRE = 80


def nombre_seguro(titulo: str) -> str:
    """Título → nombre de archivo legible (conserva acentos y mayúsculas)."""
    t = _PROHIBIDOS.sub(" ", titulo or "")
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t[:LARGO_MAX_NOMBRE].rstrip(" .") or "sin título"


def slug(texto: str, largo: int = 40) -> str:
    """Texto → identificador ASCII en minúsculas con guiones (para carpetas)."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:largo].rstrip("-") or "seccion"


def enlace(id_destino: str, alias: str) -> str:
    return f"[[{id_destino}|{alias.replace('|', ' ').replace(']', ' ')}]]"


@dataclass
class Neurona:
    id: str                      # ruta dentro del vault, sin ".md"
    titulo: str
    texto: str = ""
    meta: dict = field(default_factory=dict)
    migas: list = field(default_factory=list)        # [(id, título)] de la raíz al padre
    contiene: list = field(default_factory=list)     # [(id, título)]
    anterior: "tuple | None" = None                  # (id, título)
    siguiente: "tuple | None" = None
    ver_tambien: list = field(default_factory=list)  # [(id, título)]

    def a_markdown(self) -> str:
        meta = {"id": self.id, "titulo": self.titulo, **self.meta}
        frontmatter = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000)
        partes = [f"---\n{frontmatter}---", f"# {self.titulo}"]
        if self.migas:
            partes.append("*" + " › ".join(enlace(i, t) for i, t in self.migas) + "*")
        if self.texto:
            partes.append(self.texto)
        if self.contiene:
            partes.append("## Contiene\n" + "\n".join(f"- {enlace(i, t)}" for i, t in self.contiene))
        if self.anterior or self.siguiente:
            hilo = []
            if self.anterior:
                hilo.append(f"- Viene de {enlace(*self.anterior)}")
            if self.siguiente:
                hilo.append(f"- Continúa en {enlace(*self.siguiente)}")
            partes.append("## Continuidad\n" + "\n".join(hilo))
        if self.ver_tambien:
            partes.append(
                "## Ver también\n" + "\n".join(f"- {enlace(i, t)}" for i, t in self.ver_tambien)
            )
        return "\n\n".join(partes) + "\n"
