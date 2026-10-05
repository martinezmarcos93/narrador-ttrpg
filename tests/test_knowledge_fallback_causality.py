from narrator.core.knowledge_router import KnowledgeRouter
from narrator.core.context_contract import ContextFragment
from narrator.core.narrator_service import NarratorService
from narrator.core.causality_engine import CausalityEngine
from narrator.core.state_manager import StateManager
from narrator.core.system_pack import KnowledgePolicy, SystemPack


class _Retriever:
    class _Brain:
        def search(self, query, max_results, system=None, expand_graph=True):
            return []
    def __init__(self):
        self.brain = self._Brain()
    def get_vault_fragments_by_layer(self, query, layer, limit):
        return [
            ContextFragment(
                text="SECRETO-DM" if layer == "campaign" else "PUBLICO",
                source="dm" if layer == "campaign" else "campaign",
                layer=layer,
                title="secret" if layer == "campaign" else "public",
                score=1.0,
                metadata={"llm_visible": layer != "campaign"},
            )
        ]


def _pack():
    return SystemPack(
        slug="generic",
        sistema="Generic",
        edition="test",
        knowledge=KnowledgePolicy(
            preferred_sources=("campaign",),
            universal_fallback=False,
        ),
    )


def test_visibility_survives_router_to_final_prompt():
    router = KnowledgeRouter(_Retriever())
    rendered = router.retrieve("pista", _pack())
    prompt = "NARRADOR\n\nCONTEXTO RECUPERADO:\n" + rendered
    assert "SECRETO-DM" not in rendered
    assert "SECRETO-DM" not in prompt


def test_invalid_structured_proposal_has_explicit_narration_only_fallback():
    service = NarratorService.__new__(NarratorService)

    class Orchestrator:
        def validate_and_apply_proposal(self, proposal, app_state=None):
            return {
                "applied": False,
                "changes": [],
                "validation": {"valid": False, "issues": [{"code": "invalid_proposal"}]},
            }

    service.orchestrator = Orchestrator()
    result = service.apply_proposal_with_fallback({"unknown": True}, app_state={})
    assert result["applied"] is False
    assert result["fallback"]["mode"] == "narration_only"
    assert result["fallback"]["executed"] is False


def test_long_causal_chain_stops_at_configured_depth(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    for index in range(12):
        trigger = "inicio" if index == 0 else f"evento-{index - 1}"
        state.add_pending_consequence(
            f"C{index}",
            trigger=trigger,
            effects=[{"type": "event", "text": f"evento-{index}"}],
        )

    engine = CausalityEngine(state, max_cascade_depth=5)
    activations = engine.evaluate("inicio")
    assert len(activations) == 5
    assert engine.last_metrics["max_depth"] == 4
    assert engine.last_metrics["depth_limit_reached"] is True
    assert len(state.get_pending_consequences()) == 7


def test_causal_cycle_is_bounded_and_records_limit(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_pending_consequence(
        "A",
        trigger="start",
        effects=[{"type": "event", "text": "cycle-b"}],
    )
    state.add_pending_consequence(
        "B",
        trigger="cycle-b",
        effects=[{"type": "event", "text": "start"}],
    )
    engine = CausalityEngine(state, max_cascade_depth=3)
    activations = engine.evaluate("start")
    assert len(activations) == 2
    assert engine.last_metrics["depth_limit_reached"] is False
