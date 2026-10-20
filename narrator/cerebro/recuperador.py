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
import unicodedata
from pathlib import Path

from narrator.cerebro.indexador import IndiceCerebro
from narrator.core.context_contract import ContextFragment

# Peso de la similitud semántica frente a la coincidencia léxica (0..1).
# Ajustado con scripts/evaluate_retrieval.py; ver docs/RETRIEVAL-BASELINE.md.
SEMANTIC_WEIGHT = 0.9

_TOKEN_RE = re.compile(r"[\wáéíóúüñÁÉÍÓÚÜÑ]{3,}")


def _fold(text: str) -> str:
    """Minúsculas sin tildes: 'Investigación' y 'investigacion' coinciden."""
    decomposed = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


class RecuperadorCerebro:
    def __init__(
        self,
        brain_path: str | Path = "./cerebro",
        embedding_model: str = "nomic-embed-text",
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
        q = set(_fold(t) for t in _TOKEN_RE.findall(query))
        if not q:
            return 0.0
        title = _fold(meta.get("title", ""))
        tags = _fold(" ".join(map(str, meta.get("tags", []))))
        text = f"{title} {tags} {_fold(body[:5000])}"
        hits = sum(1 for token in q if token in text)
        title_hits = sum(1 for token in q if token in title)
        return hits / len(q) + (title_hits / len(q)) * 1.5

    @staticmethod
    def _normalize_layer(meta: dict) -> str:
        layer = str(meta.get("layer", meta.get("capa", "universal")) or "universal")
        if layer == "sistema":
            return "system"
        if layer not in {"universal", "system", "manual", "campaign", "state"}:
            return "universal"
        return layer

    @staticmethod
    def _lexical_from_text(query_tokens: set[str], text: str, title: str) -> float:
        if not query_tokens:
            return 0.0
        hits = sum(1 for token in query_tokens if token in text)
        title_hits = sum(1 for token in query_tokens if token in title)
        return hits / len(query_tokens) + (title_hits / len(query_tokens)) * 1.5

    @staticmethod
    def _wanted_system(meta: dict, system: str | None) -> bool:
        if not system:
            return True
        value = str(meta.get("system", "")).strip().lower()
        if not value:
            return True
        return value in {system.lower(), "universal", "generic", "all"}

    @staticmethod
    def _wanted_campaign(meta: dict, campaign: str | None) -> bool:
        if not campaign:
            return True
        value = str(meta.get("campaign", meta.get("campaña", ""))).strip().lower()
        if not value:
            return True
        return value in {campaign.lower(), "universal", "all", "generic"}

    def _graph_neighbors(self, path: str) -> list[str]:
        meta = self.index.metadata(path)
        values = []
        values.extend(meta.get("links", []))
        for key in ("contains", "also", "previous", "next"):
            value = meta.get(key, [])
            if isinstance(value, str):
                value = [value] if value else []
            for item in value or []:
                # Neurona serializa relaciones como (id, título).
                if isinstance(item, (list, tuple)) and item:
                    values.append(item[0])
                else:
                    values.append(item)
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
        campaign: str | None = None,
        kind: str | None = None,
        expand_graph: bool = True,
        layer: str | None = None,
    ) -> list[dict]:
        """``layer`` filtra por capa normalizada (universal/system/manual/...)
        ANTES de rankear, para que una capa grande no tape a otra chica."""
        self.index.load()
        paths = self.index.paths()
        if not paths:
            return []

        query_vec = self.index.embedder.embed(query)
        candidates = []
        for path in paths:
            # Filtros con la metadata del índice: no se relee cada archivo.
            meta = self.index.metadata(path)
            if not self._wanted_system(meta, system):
                continue
            if not self._wanted_campaign(meta, campaign):
                continue
            if kind and str(meta.get("kind", "")) != kind:
                continue
            if layer and self._normalize_layer(meta) != layer:
                continue
            candidates.append(path)

        semantic_by_path = self.index.semantic_scores(query_vec, candidates)
        query_tokens = {_fold(t) for t in _TOKEN_RE.findall(query)}
        scored: list[tuple[float, str]] = []
        for path in candidates:
            semantic = semantic_by_path.get(path, 0.0)
            lexical = self._lexical_from_text(query_tokens, self.index.lexical(path),
                                              _fold(self.index.metadata(path).get("title", "")))
            score = semantic * SEMANTIC_WEIGHT + min(lexical, 2.5) * (1 - SEMANTIC_WEIGHT)
            if score > 0:
                scored.append((score, path))

        # Desempate determinista: mayor score primero, luego ruta alfabética.
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = scored[:max_results]
        selected_paths = {p for _, p in selected}

        if expand_graph and selected:
            for _, root in selected[:2]:
                for neighbor in self._graph_neighbors(root):
                    if neighbor in selected_paths:
                        continue
                    if layer and self._normalize_layer(self.index.metadata(neighbor)) != layer:
                        continue
                    root_score = next((score for score, path_ in selected if path_ == root), 0.0)
                    selected.append((max(0.35, root_score * 0.60), neighbor))
                    selected_paths.add(neighbor)
                    if len(selected) >= max_results + 2:
                        break
            selected.sort(key=lambda item: (-item[0], item[1]))

        results = []
        for score, path in selected[:max_results]:
            meta, body = self._read(path)
            layer_name = self._normalize_layer(meta)
            results.append({
                "score": round(score, 5),
                "path": path,
                "meta": meta,
                "body": body,
                "source": "brain",
                "layer": layer_name,
                "fragment": ContextFragment(
                    text=body,
                    source=str(meta.get("source", meta.get("fuente", "cerebro"))),
                    layer=layer_name,
                    title=str(meta.get("title", meta.get("titulo", path))),
                    score=round(score, 5),
                    metadata=meta,
                ),
            })
        return results

    def get_context(
        self,
        query: str,
        max_words: int = 700,
        system: str | None = None,
        campaign: str | None = None,
        kind: str | None = None,
    ) -> str:
        results = self.search(
            query,
            max_results=8,
            system=system,
            campaign=campaign,
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
