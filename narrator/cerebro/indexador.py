"""Índice persistente del Cerebro.

Indexa las neuronas Markdown del vault del cerebro usando el mismo Embedder
que el resto del narrador. El índice es independiente del vault de campaña:
comparten infraestructura, no datos ni memoria.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

import yaml

from narrator.core.embedder import Embedder
from narrator.logger import logger

_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_YAML_DUMPER = getattr(yaml, "CSafeDumper", yaml.SafeDumper)


def lexical_text(meta: dict, body: str) -> str:
    """Texto normalizado (sin tildes, minúsculas) para la coincidencia léxica."""
    from narrator.core.entity_registry import fold_name

    tags = " ".join(map(str, meta.get("tags", []) or []))
    return fold_name(f"{meta.get('title', '')} {tags} {body[:5000]}")


class IndiceCerebro:
    INDEX_FILENAME = ".brain_embeddings.json"
    META_FILENAME = ".brain_index.yaml"
    META_JSON_FILENAME = ".brain_index.json"
    LEXICAL_FILENAME = ".brain_lexical.json"

    def __init__(
        self,
        brain_path: str | Path = "./cerebro",
        embedder: Embedder | None = None,
        embedding_model: str = "nomic-embed-text",
    ):
        self.brain_path = Path(brain_path)
        self.embedder = embedder or Embedder(model=embedding_model)
        self._index: dict[str, list[float]] | None = None
        self._metadata: dict[str, dict] | None = None
        self._lexical: dict[str, str] | None = None
        self._matrix = None  # (paths, matriz normalizada) si numpy está disponible

    @property
    def index_path(self) -> Path:
        return self.brain_path / self.INDEX_FILENAME

    @property
    def metadata_path(self) -> Path:
        return self.brain_path / self.META_FILENAME

    @property
    def metadata_json_path(self) -> Path:
        return self.brain_path / self.META_JSON_FILENAME

    @property
    def lexical_path(self) -> Path:
        return self.brain_path / self.LEXICAL_FILENAME

    def _files(self) -> list[Path]:
        if not self.brain_path.exists():
            return []
        return sorted(
            p for p in self.brain_path.rglob("*.md")
            if p.name not in {self.INDEX_FILENAME, self.META_FILENAME}
        )

    @staticmethod
    def _parse_neuron(path: Path) -> tuple[dict, str]:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if not raw.startswith("---"):
            return {}, raw
        parts = raw.split("---", 2)
        if len(parts) != 3:
            return {}, raw
        try:
            meta = yaml.load(parts[1], Loader=_YAML_LOADER) or {}
        except yaml.YAMLError as e:
            logger.warning("Frontmatter inválido en neurona: %s", e)
            meta = {}
        return meta if isinstance(meta, dict) else {}, parts[2].lstrip()

    def load(self) -> None:
        if self._index is None:
            try:
                self._index = json.loads(
                    self.index_path.read_text(encoding="utf-8")
                ) if self.index_path.exists() else {}
            except Exception as e:
                logger.error("Índice del cerebro ilegible (%s): %s", self.index_path, e, exc_info=True)
                self._index = {}
        if self._metadata is None:
            try:
                if self.metadata_json_path.exists():
                    self._metadata = json.loads(
                        self.metadata_json_path.read_text(encoding="utf-8")
                    ) or {}
                elif self.metadata_path.exists():
                    # Índices anteriores solo tenían YAML (lento de cargar).
                    self._metadata = yaml.load(
                        self.metadata_path.read_text(encoding="utf-8"), Loader=_YAML_LOADER
                    ) or {}
                else:
                    self._metadata = {}
            except Exception as e:
                logger.error("Metadata del cerebro ilegible (%s): %s", self.metadata_path, e, exc_info=True)
                self._metadata = {}

    def build(self, on_progress: Callable[[str], None] | None = None) -> int:
        """Indexación incremental. Devuelve la cantidad de neuronas nuevas."""
        self.load()
        assert self._index is not None and self._metadata is not None
        self.brain_path.mkdir(parents=True, exist_ok=True)

        changed = 0
        lexical: dict[str, str] = {}
        current = {str(p) for p in self._files()}
        for path_str in list(self._index):
            if path_str not in current:
                self._index.pop(path_str, None)
                self._metadata.pop(path_str, None)

        for path in self._files():
            key = str(path)
            meta, body = self._parse_neuron(path)
            tags = meta.get("tags", [])
            if not isinstance(tags, list):
                tags = [tags] if tags else []
            links = re.findall(r"\[\[([^|\]]+)(?:\|[^\]]+)?\]\]", body)
            content_hash = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            previous_hash = (
                self._metadata.get(key, {}).get("content_hash")
                if self._metadata
                else None
            )
            self._metadata[key] = {
                "id": meta.get("id", path.stem),
                "title": meta.get("title", meta.get("titulo", path.stem)),
                "source": meta.get("source", meta.get("fuente", "")),
                "system": meta.get("system", meta.get("sistema", "")),
                "kind": meta.get("kind", meta.get("tipo", "knowledge")),
                "layer": meta.get("layer", meta.get("capa", "universal")),
                "tags": tags,
                "contains": meta.get("contains", meta.get("contiene", [])),
                "also": meta.get("also", meta.get("ver_tambien", [])),
                "previous": meta.get("previous", meta.get("anterior", "")),
                "next": meta.get("next", meta.get("siguiente", "")),
                "links": links,
                "path": key,
                "content_hash": content_hash,
            }

            lexical[key] = lexical_text(self._metadata[key], body)

            if key in self._index and previous_hash == content_hash:
                continue

            text = "\n".join(
                str(x) for x in [
                    self._metadata[key]["title"],
                    self._metadata[key]["kind"],
                    self._metadata[key]["system"],
                    " ".join(map(str, tags)),
                    body,
                ] if x
            )
            vector = self.embedder.embed(text[:4000])
            if vector:
                self._index[key] = vector
                changed += 1
                if on_progress:
                    on_progress(f"  Cerebro: {path.name}")

        self.index_path.write_text(
            json.dumps(self._index, ensure_ascii=False),
            encoding="utf-8",
        )
        self.metadata_json_path.write_text(
            json.dumps(self._metadata, ensure_ascii=False), encoding="utf-8"
        )
        # Copia YAML legible para inspección humana (no se usa para cargar).
        self.metadata_path.write_text(
            yaml.dump(self._metadata, Dumper=_YAML_DUMPER, allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )
        self.lexical_path.write_text(
            json.dumps(lexical, ensure_ascii=False), encoding="utf-8"
        )
        self._lexical = lexical
        self._matrix = None
        logger.info("Índice del cerebro: %d nuevas neuronas, %d totales", changed, len(self._index))
        return changed

    def ready(self) -> bool:
        self.load()
        return bool(self._index)

    def metadata(self, path: str) -> dict:
        self.load()
        return (self._metadata or {}).get(path, {})

    def paths(self) -> list[str]:
        self.load()
        return list(self._index or {})

    def lexical(self, path: str) -> str:
        """Texto léxico precalculado; si falta (índice viejo) lo calcula una vez."""
        if self._lexical is None:
            try:
                self._lexical = json.loads(
                    self.lexical_path.read_text(encoding="utf-8")
                ) if self.lexical_path.exists() else {}
            except Exception as e:
                logger.error("Caché léxica ilegible (%s): %s", self.lexical_path, e, exc_info=True)
                self._lexical = {}
        if path not in self._lexical:
            p = Path(path)
            meta, body = self._parse_neuron(p) if p.exists() else ({}, "")
            merged = dict(self.metadata(path))
            merged.setdefault("title", meta.get("title", meta.get("titulo", "")))
            self._lexical[path] = lexical_text(merged, body)
        return self._lexical[path]

    def semantic_scores(self, query_vec: list[float], paths: list[str]) -> dict[str, float]:
        """Coseno de la consulta contra ``paths`` (vectorizado si hay numpy)."""
        self.load()
        index = self._index or {}
        if not query_vec:
            return {}
        try:
            import numpy as np
        except ImportError:  # extra opcional 'semantic'
            np = None
        if np is None:
            return {
                p: Embedder.cosine_similarity(query_vec, index[p]) for p in paths if index.get(p)
            }
        if self._matrix is None:
            keys = [p for p, v in index.items() if v and len(v) == len(query_vec)]
            if not keys:
                return {}
            matrix = np.asarray([index[p] for p in keys], dtype=np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            matrix /= np.maximum(norms, 1e-9)
            self._matrix = ({p: i for i, p in enumerate(keys)}, matrix)
        positions, matrix = self._matrix
        q = np.asarray(query_vec, dtype=np.float32)
        q /= max(float(np.linalg.norm(q)), 1e-9)
        sims = matrix @ q
        return {p: float(sims[positions[p]]) for p in paths if p in positions}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Construye el índice persistente del Cerebro.")
    parser.add_argument("--path", default="cerebro", help="Ruta del vault de neuronas.")
    parser.add_argument("--model", default="nomic-embed-text", help="Modelo Ollama de embeddings.")
    args = parser.parse_args()

    index = IndiceCerebro(args.path, embedding_model=args.model)
    total = index.build(on_progress=print)
    print(f"Índice actualizado: {total} neuronas nuevas.")
