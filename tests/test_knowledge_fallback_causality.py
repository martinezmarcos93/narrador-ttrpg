from narrator.core.knowledge_router import KnowledgeRouter
from narrator.core.context_contract import ContextFragment
from narrator.core.narrator_service import NarratorService
from narrator.core.causality_engine import CausalityEngine
from narrator.core.state_manager import StateManager
from narrator.core.system_pack import KnowledgePolicy, SystemPack
from narrator.core.prompt_builder import PromptBuilder


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


def test_social_relations_are_part_of_the_compound_proposal_contract(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.data["escena_actual"]["npcs_presentes"] = ["Alicia", "Bruno"]
    from narrator.core.proposal_executor import ProposalExecutor

    result = ProposalExecutor(state).execute({
        "relations": [{
            "source": "Alicia",
            "target": "Bruno",
            "relation": "desconfianza",
            "strength": -60,
            "reason": "ruptura de negociación",
        }]
    })
    assert result.applied
    assert state.get_relations("Alicia")[0]["strength"] == -60


def test_front_clock_effect_rejects_unknown_or_out_of_range_clock(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_front("Amenaza", faction="culto", goal="portal", max_stage=3)
    from narrator.core.proposal_executor import ProposalExecutor

    unknown = ProposalExecutor(state).execute({
        "consequences": [{
            "text": "efecto",
            "trigger": "evento",
            "effects": [{"type": "front_clock_delta", "name": "NoExiste", "delta": 1}],
        }]
    })
    assert not unknown.applied

    overflow = ProposalExecutor(state).execute({
        "consequences": [{
            "text": "efecto",
            "trigger": "evento",
            "effects": [{"type": "front_clock_delta", "name": "Amenaza", "delta": 4}],
        }]
    })
    assert not overflow.applied


def test_cross_front_consequences_progress_multiple_clocks_and_persist(tmp_path):
    path = tmp_path / "estado.yaml"
    state = StateManager(str(path))
    state.add_front("Culto", faction="culto", goal="ritual", max_stage=3)
    state.add_front("Guardia", faction="ciudad", goal="toque de queda", max_stage=4)

    from narrator.core.proposal_executor import ProposalExecutor

    result = ProposalExecutor(state).execute({
        "consequences": [{
            "text": "La presión crece en ambos frentes.",
            "trigger": "alarma",
            "effects": [
                {"type": "front_clock_delta", "name": "Culto", "delta": 2},
                {"type": "front_clock_delta", "name": "Guardia", "delta": 1},
                {"type": "event", "text": "ambos frentes avanzan"},
            ],
        }]
    })
    assert result.applied

    # La consecuencia está plantada; la cascada siguiente la resuelve.
    from narrator.core.narrator_service import NarratorService
    service = NarratorService.__new__(NarratorService)
    service.state = state
    service.causality = CausalityEngine(state)
    activated = service.evaluate_causality("alarma")
    assert activated["activated"]
    assert state.data["relojes"]["Culto"]["llenos"] == 2
    assert state.data["relojes"]["Guardia"]["llenos"] == 1

    reloaded = StateManager(str(path))
    assert reloaded.load()
    assert reloaded.data["relojes"]["Culto"]["llenos"] == 2
    assert reloaded.data["relojes"]["Guardia"]["llenos"] == 1


def test_restart_preserves_relations_consequences_and_perspective(tmp_path):
    path = tmp_path / "estado.yaml"
    state = StateManager(str(path))
    state.set_relation("Alicia", "Bruno", "confianza", 70, reason="alianza")
    state.add_pending_consequence(
        "Bruno aparecerá",
        trigger="alarma",
        due="turno:4",
    )
    state.set_world_fact("portal_abierto", True, source="test")
    state.set_character_fact("Alicia", "vio_el_portal", True, source="test")
    state.set_player_fact("sabe_del_portal", True, source="test")

    reloaded = StateManager(str(path))
    assert reloaded.load()
    assert reloaded.get_relations("Alicia")[0]["strength"] == 70
    assert reloaded.get_pending_consequences()[0]["trigger"] == "alarma"
    assert reloaded.get_world_fact("portal_abierto") is True
    assert reloaded.get_character_fact("Alicia", "vio_el_portal") is True
    assert reloaded.get_player_fact("sabe_del_portal") is True


def test_reload_merges_new_nested_defaults(tmp_path):
    path = tmp_path / "estado.yaml"
    path.write_text(
        "meta:\n  sistema: generic\n"
        "conocimiento:\n  mundo:\n    secreto: true\n",
        encoding="utf-8",
    )
    state = StateManager(str(path))
    assert state.load()
    assert "personajes" in state.data["conocimiento"]
    assert "jugador" in state.data["conocimiento"]
    assert "flags" in state.data
    assert state.data["conocimiento"]["mundo"]["secreto"] is True
