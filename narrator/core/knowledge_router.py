"""Router de conocimiento: aplica la política del System Pack a la recuperación.

La política no decide autoridad narrativa por sí sola; decide qué fuentes son
consultadas. La autoridad final sigue definida por ContextFragment.
"""

from __future__ import annotations

from dataclasses import dataclass
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

    def retrieve(
        self,
        query: str,
        pack: SystemPack,
        *,
        manual_text: str = "",
        max_words: int = 700,
    ) -> str:
        fragments: list[ContextFragment] = []
        routes = self.routes(pack, manual_available=bool(manual_text.strip()))

        for route in routes:
            if route.source == "manual":
                fragments.extend(self._manual(manual_text))
            elif route.source == "system":
                fragments.extend(
                    self._system_fragments(query, pack, route.budget)
                )
            elif route.source == "campaign":
                fragments.extend(
                    self._campaign_fragments(query, route.budget)
                )
            elif route.source == "state":
                fragments.extend(
                    self._state_fragments(query, route.budget)
                )
            elif route.source == "universal":
                fragments.extend(
                    self._universal_fragments(query, pack, route.budget)
                )

        return self._render_unique(fragments, max_words)

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
        results = self.retriever.brain.search(
            pack.knowledge_query(query),
            max_results=limit,
            system=pack.knowledge.brain_system,
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
