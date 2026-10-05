from pathlib import Path

from narrator.core.system_pack import SystemPack, KnowledgePolicy
from narrator.core.knowledge_router import KnowledgeRouter, KnowledgeRoute


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def get_vault_fragments_by_layer(self, query, layer, limit):
        self.calls.append((layer, limit))
        return []


def test_routes_respect_preferred_sources_and_manual():
    retriever = FakeRetriever()
    router = KnowledgeRouter(retriever)
    pack = SystemPack(
        slug="x",
        sistema="X",
        edition="1",
        knowledge=KnowledgePolicy(
            brain_system="x",
            preferred_sources=("manual", "system", "campaign"),
            universal_fallback=True,
        ),
    )
    routes = router.routes(pack, manual_available=False)
    assert [r.source for r in routes] == ["system", "campaign", "universal"]


def test_router_can_retrieve_campaign_and_state_without_second_rag():
    retriever = FakeRetriever()
    router = KnowledgeRouter(retriever)
    pack = SystemPack(
        slug="x",
        sistema="X",
        edition="1",
        knowledge=KnowledgePolicy(
            brain_system="x",
            preferred_sources=("campaign", "state"),
            universal_fallback=False,
        ),
    )
    assert router.retrieve("pista", pack) == ""
    assert retriever.calls == [("campaign", 4), ("state", 4)]


def test_router_incluye_estado_vivo_como_fuente_autoritativa():
    router = KnowledgeRouter(FakeRetriever())
    pack = SystemPack(
        slug="x",
        sistema="X",
        edition="1",
        knowledge=KnowledgePolicy(
            brain_system="x",
            preferred_sources=("state",),
            universal_fallback=False,
        ),
    )
    rendered = router.retrieve(
        "qué ocurre",
        pack,
        state_context="Locación: Mansión Blackwood\nFlag: puerta_abierta=True",
    )
    assert "Estado mutable de la campaña" in rendered
    assert "Locación: Mansión Blackwood" in rendered


def test_router_retrieval_metrics_reporta_capas_y_fuentes():
    router = KnowledgeRouter(FakeRetriever())
    pack = SystemPack(
        slug="x",
        sistema="X",
        edition="1",
        knowledge=KnowledgePolicy(
            brain_system="x",
            preferred_sources=("state",),
            universal_fallback=False,
        ),
    )
    rendered, metrics = router.retrieve_with_metrics(
        "qué ocurre",
        pack,
        state_context="Locación: Mansión Blackwood",
    )
    assert "Mansión Blackwood" in rendered
    assert metrics.fragment_count == 1
    assert metrics.layers == {"state": 1}
    assert metrics.sources == {"StateManager": 1}
    assert metrics.context_words > 0
    assert metrics.to_dict()["duplicate_count"] == 0


def test_retrieval_metrics_include_quality_proxies(tmp_path):
    from narrator.core.knowledge_router import RetrievalMetrics

    metrics = RetrievalMetrics(
        query="prueba",
        fragment_count=2,
        layers={"universal": 1, "campaign": 1},
        sources={"brain": 2},
        context_words=20,
        latency_ms=1.5,
        relevance_mean=0.7,
        relevance_max=0.9,
        diversity_ratio=1.0,
        provenance_coverage=1.0,
        context_utilization=0.8,
    )
    data = metrics.to_dict()
    assert data["latency_ms"] == 1.5
    assert data["relevance_max"] == 0.9
    assert data["diversity_ratio"] == 1.0
    assert data["provenance_coverage"] == 1.0
    assert data["context_utilization"] == 0.8
