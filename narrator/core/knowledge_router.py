"""Router de conocimiento: aplica la política del System Pack a la recuperación.

La política no decide autoridad narrativa por sí sola; decide qué fuentes son
consultadas. La autoridad final sigue definida por ContextFragment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
from time import perf_counter
from typing import TYPE_CHECKING

from narrator.core.context_contract import ContextFragment
from narrator.core.system_pack import SystemPack

if TYPE_CHECKING:
    from narrator.core.retriever import VaultRetriever


@dataclass(frozen=True)
class KnowledgeRoute:
    source: str
    enabled: bool
    budget: int


@dataclass(frozen=True)
class RetrievalMetrics:
    query: str
    fragment_count: int
    layers: dict[str, int] = field(default_factory=dict)
    sources: dict[str, int] = field(default_factory=dict)
    duplicate_count: int = 0
    context_words: int = 0
    latency_ms: float = 0.0
    relevance_mean: float = 0.0
    relevance_max: float = 0.0
    diversity_ratio: float = 0.0
    provenance_coverage: float = 0.0
    context_utilization: float = 0.0

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "fragment_count": self.fragment_count,
            "layers": dict(self.layers),
            "sources": dict(self.sources),
            "duplicate_count": self.duplicate_count,
            "context_words": self.context_words,
            "latency_ms": self.latency_ms,
            "relevance_mean": self.relevance_mean,
            "relevance_max": self.relevance_max,
            "diversity_ratio": self.diversity_ratio,
            "provenance_coverage": self.provenance_coverage,
            "context_utilization": self.context_utilization,
        }


class KnowledgeRouter:
    """Coordina cerebro, manual, sistema y campaña sin crear otro índice/RAG."""

    def __init__(self, retriever: "VaultRetriever"):
        self.retriever = retriever

    def routes(self, pack: SystemPack, manual_available: bool = False) -> tuple[KnowledgeRoute, ...]:
        preferred = pack.knowledge.preferred_sources
        result = []
        budgets = {"manual": 1, "system": 3, "campaign": 4, "state": 4, "universal": 4}
        for source in preferred:
            if source == "manual" and not manual_available:
                continue
            result.append(KnowledgeRoute(source, True, budgets.get(source, 2)))

        if pack.knowledge.universal_fallback and "universal" not in preferred:
            result.append(KnowledgeRoute("universal", True, budgets["universal"]))
        return tuple(result)

    def retrieve_fragments(
        self,
        query: str,
        pack: SystemPack,
        *,
        manual_text: str = "",
        state_context: str = "",
    ) -> tuple[list[ContextFragment], int]:
        fragments: list[ContextFragment] = []
        routes = self.routes(pack, manual_available=bool(manual_text.strip()))

        if state_context.strip():
            fragments.append(ContextFragment(
                text=state_context.strip(),
                source="StateManager",
                layer="state",
                title="Estado mutable de la campaña",
                score=1.0,
                metadata={"authoritative": True},
            ))

        for route in routes:
            if route.source == "manual":
                fragments.extend(self._manual(manual_text))
            elif route.source == "system":
                fragments.extend(self._system_fragments(query, pack, route.budget))
            elif route.source == "campaign":
                fragments.extend(self._campaign_fragments(query, route.budget))
            elif route.source == "state":
                fragments.extend(self._state_fragments(query, route.budget))
            elif route.source == "universal":
                fragments.extend(self._universal_fragments(query, pack, route.budget))

        seen: set[tuple[str, str]] = set()
        unique: list[ContextFragment] = []
        duplicates = 0
        for fragment in fragments:
            key = (fragment.source, fragment.title or fragment.text[:120])
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            unique.append(fragment)
        return unique, duplicates

    def retrieve(
        self,
        query: str,
        pack: SystemPack,
        *,
        manual_text: str = "",
        state_context: str = "",
        max_words: int = 700,
    ) -> str:
        fragments, _ = self.retrieve_fragments(
            query,
            pack,
            manual_text=manual_text,
            state_context=state_context,
        )
        return self._render_unique(fragments, max_words)

    def retrieve_with_metrics(
        self,
        query: str,
        pack: SystemPack,
        *,
        manual_text: str = "",
        state_context: str = "",
        max_words: int = 700,
    ) -> tuple[str, RetrievalMetrics]:
        started = perf_counter()
        fragments, duplicates = self.retrieve_fragments(
            query,
            pack,
            manual_text=manual_text,
            state_context=state_context,
        )
        rendered = self._render_unique(fragments, max_words)
        scores = [float(fragment.score) for fragment in fragments]
        layer_count = len(set(fragment.layer for fragment in fragments))
        source_count = len(set(fragment.source for fragment in fragments))
        source_words = sum(len(fragment.text.split()) for fragment in fragments)
        rendered_words = len(rendered.split())
        metrics = RetrievalMetrics(
            query=query,
            fragment_count=len(fragments),
            layers=dict(Counter(fragment.layer for fragment in fragments)),
            sources=dict(Counter(fragment.source for fragment in fragments)),
            duplicate_count=duplicates,
            context_words=rendered_words,
            latency_ms=round((perf_counter() - started) * 1000, 3),
            relevance_mean=round(sum(scores) / len(scores), 4) if scores else 0.0,
            relevance_max=round(max(scores), 4) if scores else 0.0,
            diversity_ratio=round(layer_count / len(fragments), 4) if fragments else 0.0,
            provenance_coverage=round(
                sum(1 for fragment in fragments if fragment.source and fragment.layer)
                / len(fragments), 4
            ) if fragments else 0.0,
            context_utilization=round(
                rendered_words / source_words, 4
            ) if source_words else 0.0,
        )
        return rendered, metrics

    @staticmethod
    def _manual(text: str) -> list[ContextFragment]:
        if not text.strip():
            return []
        return [ContextFragment(
            text=text.strip(),
            source="manual adjunto",
            layer="manual",
            title="Manual cargado en la sesión",
            score=1.0,
            metadata={"origen": "manual", "session_attached": True},
        )]

    def _system_fragments(self, query: str, pack: SystemPack, limit: int) -> list[ContextFragment]:
        results = self.retriever.brain.search(
            pack.knowledge_query(query),
            max_results=limit,
            system=pack.knowledge.brain_system,
            expand_graph=True,
        )
        return [
            result["fragment"]
            for result in results
            if result["fragment"].layer == "system"
        ]

    def _universal_fragments(self, query: str, pack: SystemPack, limit: int) -> list[ContextFragment]:
        # El conocimiento universal no debe quedar sesgado por el slug del sistema.
        results = self.retriever.brain.search(
            query,
            max_results=limit,
            system=None,
            expand_graph=True,
        )
        return [
            result["fragment"]
            for result in results
            if result["fragment"].layer == "universal"
        ]

    def _campaign_fragments(self, query: str, limit: int) -> list[ContextFragment]:
        fragments = self.retriever.get_vault_fragments_by_layer(query, "campaign", limit * 2)
        visible = []
        for fragment in fragments:
            metadata = fragment.metadata or {}
            llm_visible = metadata.get("llm_visible")
            visibility = str(
                metadata.get("visibility", metadata.get("visibilidad", ""))
            ).strip().lower()
            if llm_visible is False:
                continue
            if visibility in {"secret", "private", "dm", "hidden", "oculto", "secreto", "privado"}:
                continue
            visible.append(fragment)
            if len(visible) >= limit:
                break
        return visible

    def retrieve_visible_campaign_fragments(self, query: str, limit: int = 4) -> list[ContextFragment]:
        """Recupera exclusivamente campaña visible para el LLM."""
        return self._campaign_fragments(query, limit)

    def retrieve_visible_campaign_fragments(self, query: str, limit: int = 4) -> list[ContextFragment]:
        return self._campaign_fragments(query, limit)

    def _state_fragments(self, query: str, limit: int) -> list[ContextFragment]:
        return self.retriever.get_vault_fragments_by_layer(query, "state", limit)

    @staticmethod
    def _render_unique(fragments: list[ContextFragment], max_words: int) -> str:
        seen: set[tuple[str, str]] = set()
        unique = []
        for fragment in fragments:
            key = (fragment.source, fragment.title or fragment.text[:120])
            if key in seen:
                continue
            seen.add(key)
            unique.append(fragment)

        from narrator.core.context_contract import render_context
        return render_context(unique, max_words=max_words)
