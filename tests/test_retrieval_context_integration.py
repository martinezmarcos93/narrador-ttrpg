from narrator.core.context_contract import ContextFragment
from narrator.core.knowledge_router import KnowledgeRouter
from narrator.core.system_pack import KnowledgePolicy, SystemPack


class BrainStub:
    def search(self, query, max_results, system=None, expand_graph=True):
        layer = "system" if system else "universal"
        return [{
            "fragment": ContextFragment(
                text=f"{layer} evidence for {query}",
                source=f"brain-{layer}",
                layer=layer,
                title=f"{layer}-rule",
                score=0.9,
                metadata={"id": f"{layer}-rule"},
            )
        }]


class RetrieverStub:
    def __init__(self):
        self.brain = BrainStub()

    def get_vault_fragments_by_layer(self, query, layer, limit):
        return [ContextFragment(
            text=f"{layer} evidence",
            source=f"{layer}-source",
            layer=layer,
            title=f"{layer}-entry",
            score=0.8,
            metadata={"id": f"{layer}-entry"},
        )]


def test_router_composes_manual_system_universal_and_campaign():
    router = KnowledgeRouter(RetrieverStub())
    pack = SystemPack(
        slug="vampiro",
        sistema="Vampiro",
        edition="V20",
        knowledge=KnowledgePolicy(
            brain_system="vampiro",
            preferred_sources=("manual", "system", "campaign"),
            universal_fallback=True,
        ),
    )
    rendered, metrics = router.retrieve_with_metrics(
        "investigar una pista",
        pack,
        manual_text="Regla específica del manual.",
    )

    assert "[MANUAL" in rendered
    assert "[SYSTEM" in rendered
    assert "[UNIVERSAL" in rendered
    assert "[CAMPAIGN" in rendered
    assert metrics.layers == {"manual": 1, "system": 1, "campaign": 1, "universal": 1}


def test_router_authority_keeps_manual_above_system_and_universal():
    router = KnowledgeRouter(RetrieverStub())
    pack = SystemPack(
        slug="vampiro",
        sistema="Vampiro",
        edition="V20",
        knowledge=KnowledgePolicy(
            brain_system="vampiro",
            preferred_sources=("manual", "system"),
            universal_fallback=True,
        ),
    )
    rendered = router.retrieve(
        "regla",
        pack,
        manual_text="MANUAL-AUTHORITY",
    )
    assert rendered.index("MANUAL-AUTHORITY") < rendered.index("system evidence")
    assert rendered.index("system evidence") < rendered.index("universal evidence")


def test_context_contract_enforces_full_authority_order():
    fragments = [
        ContextFragment("universal", "u", "universal", score=1),
        ContextFragment("system", "s", "system", score=1),
        ContextFragment("manual", "m", "manual", score=1),
        ContextFragment("campaign", "c", "campaign", score=1),
        ContextFragment("state", "st", "state", score=1),
    ]
    from narrator.core.context_contract import render_context
    rendered = render_context(fragments, max_words=100)
    assert rendered.index("state") < rendered.index("manual")
    assert rendered.index("manual") < rendered.index("system")
    assert rendered.index("system") < rendered.index("campaign")
    assert rendered.index("campaign") < rendered.index("universal")


def test_router_can_place_state_above_manual():
    router = KnowledgeRouter(RetrieverStub())
    pack = SystemPack(
        slug="vampiro",
        sistema="Vampiro",
        edition="V20",
        knowledge=KnowledgePolicy(
            brain_system="vampiro",
            preferred_sources=("manual", "system", "campaign"),
            universal_fallback=True,
        ),
    )
    rendered, _ = router.retrieve_with_metrics(
        "regla y estado actual",
        pack,
        manual_text="MANUAL-AUTHORITY",
        state_context="STATE-AUTHORITY",
    )
    assert rendered.index("STATE-AUTHORITY") < rendered.index("MANUAL-AUTHORITY")
