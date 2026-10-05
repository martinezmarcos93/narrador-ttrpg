"""Router de conocimiento: aplica la política del System Pack a la recuperación.

La política no decide autoridad narrativa por sí sola; decide qué fuentes son
consultadas. La autoridad final sigue definida por ContextFragment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
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

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "fragment_count": self.fragment_count,
            "layers": dict(self.layers),
            "sources": dict(self.sources),
            "duplicate_count": self.duplicate_count,
            "context_words": self.context_words,
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
        fragments, duplicates = self.retrieve_fragments(
            query,
            pack,
            manual_text=manual_text,
            state_context=state_context,
        )
        rendered = self._render_unique(fragments, max_words)
        metrics = RetrievalMetrics(
            query=query,
            fragment_count=len(fragments),
            layers=dict(Counter(fragment.layer for fragment in fragments)),
            sources=dict(Counter(fragment.source for fragment in fragments)),
            duplicate_count=duplicates,
            context_words=len(rendered.split()),
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
        return self.retriever.get_vault_fragments_by_layer(query, "campaign", limit)

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
