from narrator.core.knowledge_router import KnowledgeRouter
from narrator.core.manual_index import ManualIndex, split_passages
from narrator.core.system_pack import KnowledgePolicy, SystemPack

MANUAL = (
    "Introducción al juego y a la ambientación gótica de la ciudad.\n\f"
    + "Reglas de combate. " + "palabra " * 200 + "\n\n"
    + "La iniciativa se determina con Destreza más Astucia más un dado.\n\f"
    + "El frenesí ocurre cuando la Bestia toma el control ante la ira o el hambre.\n\f"
)


class _NoBrain:
    def get_vault_fragments_by_layer(self, *a, **k):
        return []


def test_split_passages_keeps_page_numbers():
    passages = split_passages(MANUAL)
    assert passages[0].page == 1
    assert {p.page for p in passages} == {1, 2, 3}
    assert all(len(p.text.split()) <= 180 for p in passages)


def test_bm25_ranks_relevant_passage_first_and_cites_page():
    index = ManualIndex()
    index.build(MANUAL)
    hits = index.search("¿qué provoca el frenesi de la bestia?", k=2)
    assert hits[0][0].page == 3
    assert hits[0][1] == 1.0
    assert index.search("xenomorfos espaciales") == []


def test_router_returns_relevant_manual_passages_with_citation():
    router = KnowledgeRouter(_NoBrain())
    pack = SystemPack(slug="x", sistema="X", edition="1",
                      knowledge=KnowledgePolicy(preferred_sources=("manual",),
                                                universal_fallback=False))
    fragments, _ = router.retrieve_fragments("como se tira la iniciativa", pack,
                                             manual_text=MANUAL)
    assert fragments and fragments[0].metadata["page"] == 2
    assert fragments[0].metadata["citation"] == "manual adjunto, pág. 2"
    assert "pág. 2" in fragments[0].render()


def test_citations_for_each_layer_and_coverage_metric():
    from narrator.core.context_contract import ContextFragment
    from narrator.core.knowledge_router import _citation_coverage

    manual = ContextFragment("x", "manual adjunto", "manual",
                             metadata={"citation": "manual adjunto, pág. 4"})
    barrido = ContextFragment("y", "v20-basico", "system",
                              metadata={"libro": "Vampiro V20", "paginas": "112-113"})
    universal = ContextFragment("z", "cerebro", "universal", metadata={"id": "universal-npc"})
    sin_cita = ContextFragment("w", "nota", "campaign")
    estado = ContextFragment("s", "StateManager", "state")
    assert barrido.citation == "Vampiro V20, pág. 112-113"
    assert universal.citation == "cerebro:universal-npc"
    assert "cita: Vampiro V20, pág. 112-113" in barrido.render()
    assert _citation_coverage([manual, barrido, universal, sin_cita, estado]) == 0.75
