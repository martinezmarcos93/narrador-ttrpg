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
    router = KnowledgeRouter(object())
    pack = _pack()
    # El método de render no necesita acceso al retriever si solo se inyecta estado.
    rendered = router.retrieve(
        "qué ocurre",
        pack,
        state_context="Locación: Mansión Blackwood\nFlag: puerta_abierta=True",
    )
    assert "Estado mutable de la campaña" in rendered
    assert "Locación: Mansión Blackwood" in rendered
