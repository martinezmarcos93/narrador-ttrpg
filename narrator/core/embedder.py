"""
Embedder — genera y gestiona embeddings vectoriales via Ollama.
Usa nomic-embed-text por defecto. Sin dependencias externas (solo requests + json).

Guarda el índice en vault/.embeddings.json para no re-generar en cada sesión.
"""

import json
import math
from pathlib import Path
from typing import Optional

import requests

from narrator.logger import logger


class Embedder:
    INDEX_FILENAME = ".embeddings.json"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._available: Optional[bool] = None

    # ── Disponibilidad ────────────────────────────────────────
    def is_available(self) -> bool:
        """Verifica si el modelo de embeddings está disponible en Ollama."""
        if self._available is not None:
            return self._available
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            self._available = any(self.model in m for m in models)
        except Exception as e:
            logger.info("Embeddings no disponibles (%s): %s", self.model, e)
            self._available = False
        return self._available

    # ── Generación de embedding ───────────────────────────────
    def embed(self, text: str) -> list[float]:
        """
        Genera el embedding de un texto.
        Devuelve lista vacía si el modelo no está disponible.
        """
        if not self.is_available():
            return []
        text = text[:2000]  # cap por si el texto es muy largo
        try:
            r = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=self.timeout,
            )
            return r.json().get("embedding", [])
        except Exception as e:
            logger.warning("Fallo al generar embedding con %s: %s", self.model, e)
            return []

    # ── Similitud coseno ──────────────────────────────────────
    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b + 1e-9)

    # ── Índice de vault ───────────────────────────────────────
    def _index_path(self, vault_path: Path) -> Path:
        return vault_path / self.INDEX_FILENAME

    def load_index(self, vault_path: Path) -> dict[str, list[float]]:
        """Carga el índice de embeddings desde vault/.embeddings.json"""
        idx_path = self._index_path(vault_path)
        if not idx_path.exists():
            return {}
        try:
            return json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Índice de embeddings ilegible en %s: %s", idx_path, e, exc_info=True)
            return {}

    def save_index(self, index: dict[str, list[float]], vault_path: Path):
        """Guarda el índice de embeddings."""
        idx_path = self._index_path(vault_path)
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        idx_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    def index_file(
        self,
        file_path: Path,
        content: str,
        index: dict[str, list[float]],
    ) -> bool:
        """
        Genera el embedding de un archivo y lo añade al índice en memoria.
        Devuelve True si se generó exitosamente.
        """
        embedding = self.embed(content[:1500])
        if embedding:
            index[str(file_path)] = embedding
            return True
        return False

    def build_index_for_vault(self, vault_path: Path, on_progress=None) -> dict:
        """
        Recorre todos los .md del vault y genera embeddings para los que falten.
        Útil para indexar un vault ya existente sin re-extraer.
        """
        index = self.load_index(vault_path)
        updated = 0

        for md_file in vault_path.rglob("*.md"):
            if str(md_file) in index:
                continue
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            if self.index_file(md_file, content, index):
                updated += 1
                on_progress and on_progress(f"  Indexado: {md_file.name}")

        if updated:
            self.save_index(index, vault_path)
            on_progress and on_progress(f"Índice actualizado: {updated} archivos nuevos.")

        return index
