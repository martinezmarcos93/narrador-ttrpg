"""Índice persistente del Cerebro.

Indexa las neuronas Markdown del vault del cerebro usando el mismo Embedder
que el resto del narrador. El índice es independiente del vault de campaña:
comparten infraestructura, no datos ni memoria.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import yaml

from narrator.core.embedder import Embedder
from narrator.logger import logger


class IndiceCerebro:
    INDEX_FILENAME = ".brain_embeddings.json"
    META_FILENAME = ".brain_index.yaml"

    def __init__(
        self,
        brain_path: str | Path = "./cerebro",
        embedder: Embedder | None = None,
        embedding_model: str = "bge-m3",
    ):
        self.brain_path = Path(brain_path)
        self.embedder = embedder or Embedder(model=embedding_model)
        self._index: dict[str, list[float]] | None = None
        self._metadata: dict[str, dict] | None = None

    @property
    def index_path(self) -> Path:
        return self.brain_path / self.INDEX_FILENAME

    @property
    def metadata_path(self) -> Path:
        return self.brain_path / self.META_FILENAME

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
            meta = yaml.safe_load(parts[1]) or {}
        except Exception:
            meta = {}
        return meta if isinstance(meta, dict) else {}, parts[2].lstrip()

    def load(self) -> None:
        if self._index is None:
            try:
                self._index = json.loads(
                    self.index_path.read_text(encoding="utf-8")
                ) if self.index_path.exists() else {}
            except Exception:
                self._index = {}
        if self._metadata is None:
            try:
                self._metadata = yaml.safe_load(
                    self.metadata_path.read_text(encoding="utf-8")
                ) or {}
            except Exception:
                self._metadata = {}

    def build(self, on_progress: Callable[[str], None] | None = None) -> int:
        """Indexación incremental. Devuelve la cantidad de neuronas nuevas."""
        self.load()
        assert self._index is not None and self._metadata is not None
        self.brain_path.mkdir(parents=True, exist_ok=True)

        changed = 0
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
            self._metadata[key] = {
                "id": meta.get("id", path.stem),
                "title": meta.get("title", meta.get("titulo", path.stem)),
                "source": meta.get("source", meta.get("fuente", "")),
                "system": meta.get("system", meta.get("sistema", "")),
                "kind": meta.get("kind", meta.get("tipo", "knowledge")),
                "tags": tags,
                "contains": meta.get("contains", meta.get("contiene", [])),
                "also": meta.get("also", meta.get("ver_tambien", [])),
                "previous": meta.get("previous", meta.get("anterior", "")),
                "next": meta.get("next", meta.get("siguiente", "")),
                "path": key,
            }

            if key in self._index:
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
        self.metadata_path.write_text(
            yaml.safe_dump(self._metadata, allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Construye el índice persistente del Cerebro.")
    parser.add_argument("--path", default="cerebro", help="Ruta del vault de neuronas.")
    parser.add_argument("--model", default="bge-m3", help="Modelo Ollama de embeddings.")
    args = parser.parse_args()

    index = IndiceCerebro(args.path, embedding_model=args.model)
    total = index.build(on_progress=print)
    print(f"Índice actualizado: {total} neuronas nuevas.")
