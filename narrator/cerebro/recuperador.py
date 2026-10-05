"""Recuperación híbrida del Cerebro.

No es un segundo RAG: es el adaptador que convierte el vault de neuronas en
una fuente de contexto para el Retriever existente.

Ranking:
1. similitud semántica;
2. coincidencia léxica;
3. filtros de sistema/capa;
4. expansión por grafo de la neurona ganadora.
"""

from __future__ import annotations

import re
from pathlib import Path

from narrator.core.embedder import Embedder
from narrator.cerebro.indexador import IndiceCerebro


_TOKEN_RE = re.compile(r"[\wáéíóúüñÁÉÍÓÚÜÑ]{3,}")


class RecuperadorCerebro:
    def __init__(
        self,
        brain_path: str | Path = "./cerebro",
        embedding_model: str = "bge-m3",
    ):
        self.index = IndiceCerebro(brain_path, embedding_model=embedding_model)

    @property
    def available(self) -> bool:
        return self.index.ready()

    def build_index(self, on_progress=None) -> int:
        return self.index.build(on_progress=on_progress)

    def _read(self, path: str) -> tuple[dict, str]:
        p = Path(path)
        if not p.exists():
            return self.index.metadata(path), ""
        return self.index._parse_neuron(p)

    @staticmethod
    def _lexical_score(query: str, meta: dict, body: str) -> float:
        q = set(t.lower() for t in _TOKEN_RE.findall(query))
        if not q:
            return 0.0
        title = str(meta.get("title", "")).lower()
        tags = " ".join(map(str, meta.get("tags", []))).lower()
        text = f"{title} {tags} {body[:5000]}".lower()
        hits = sum(1 for token in q if token in text)
        title_hits = sum(1 for token in q if token in title)
        return hits / len(q) + (title_hits / len(q)) * 1.5

    @staticmethod
    def _wanted_system(meta: dict, system: str | None) -> bool:
        if not system:
            return True
        value = str(meta.get("system", "")).strip().lower()
        if not value:
            return True
        return value in {system.lower(), "universal", "generic", "all"}

    def _graph_neighbors(self, path: str) -> list[str]:
        meta = self.index.metadata(path)
        values = []
        for key in ("contains", "also", "previous", "next"):
            value = meta.get(key, [])
            if isinstance(value, str):
                value = [value] if value else []
            values.extend(value or [])
        by_id = {
            str(self.index.metadata(p).get("id", "")): p
            for p in self.index.paths()
        }
        out = []
        for value in values:
            target = by_id.get(str(value))
            if target and target != path:
                out.append(target)
        return out

    def search(
        self,
        query: str,
        max_results: int = 6,
        system: str | None = None,
        kind: str | None = None,
        expand_graph: bool = True,
    ) -> list[dict]:
        self.index.load()
        paths = self.index.paths()
        if not paths:
            return []

        query_vec = self.index.embedder.embed(query)
        scored: list[tuple[float, str]] = []

        for path in paths:
            meta, body = self._read(path)
            if not self._wanted_system(meta, system):
                continue
            if kind and str(meta.get("kind", "")) != kind:
                continue

            semantic = 0.0
            vector = (self.index._index or {}).get(path, [])
            if query_vec and vector:
                semantic = Embedder.cosine_similarity(query_vec, vector)

            lexical = self._lexical_score(query, meta, body)
            score = semantic * 0.72 + min(lexical, 2.5) * 0.28
            if score > 0:
                scored.append((score, path))

        scored.sort(reverse=True)
        selected = scored[:max_results]
        selected_paths = {p for _, p in selected}

        if expand_graph and selected:
            for _, root in selected[:2]:
                for neighbor in self._graph_neighbors(root):
                    if neighbor in selected_paths:
                        continue
                    selected.append((0.35, neighbor))
                    selected_paths.add(neighbor)
                    if len(selected) >= max_results + 2:
                        break

        results = []
        for score, path in selected[:max_results]:
            meta, body = self._read(path)
            results.append({
                "score": round(score, 5),
                "path": path,
                "meta": meta,
                "body": body,
                "source": "brain",
            })
        return results

    def get_context(
        self,
        query: str,
        max_words: int = 700,
        system: str | None = None,
        kind: str | None = None,
    ) -> str:
        results = self.search(
            query,
            max_results=8,
            system=system,
            kind=kind,
            expand_graph=True,
        )
        parts = []
        total = 0
        for result in results:
            meta = result["meta"]
            title = meta.get("title", Path(result["path"]).stem)
            source = meta.get("source", "")
            body = result["body"].strip()
            snippet = " ".join(body.split())[:3500]
            header = f"[CEREBRO | {title}"
            if source:
                header += f" | fuente: {source}"
            header += "]"
            block = f"{header}\n{snippet}"
            words = len(block.split())
            if total + words > max_words:
                remaining = max_words - total
                if remaining > 30:
                    parts.append(" ".join(block.split()[:remaining]))
                break
            parts.append(block)
            total += words
        return "\n---\n".join(parts)
