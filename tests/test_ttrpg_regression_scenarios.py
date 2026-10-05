"""Escenarios sintéticos compuestos del motor TTRPG.

No llaman al LLM ni requieren Ollama. Sirven como contratos de integración
entre estado, resolución, causalidad, visibilidad y propuestas.
"""

from narrator.core.causality_engine import CausalityEngine
from narrator.core.knowledge_visibility import KnowledgeVisibility
from narrator.core.proposal_executor import ProposalExecutor
from narrator.core.rule_arbiter import RuleArbiter
from narrator.core.state_manager import StateManager


class FakeBuilder:
    def load_system(self, slug):
        return {
            "resolution": {
                "mecanica": "d20_vs_dc",
                "acciones": [
                    {"etiqueta": "Investigar", "atributo": "inteligencia", "keywords": ["investigar"]},
                ],
                "dificultades": {
                    "facil": 10,
                    "normal": 15,
                    "dificil": 20,
                },
            }
        }


def test_investigation_failure_creates_next_turn_consequence(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    executor = ProposalExecutor(state)

    result = executor.execute({
        "facts": {"pista_encontrada": False},
        "events": ["El investigador falla al examinar la pista."],
        "consequences": [{
            "text": "Los guardianes sospechan del grupo.",
            "trigger": "siguiente turno",
        }],
    })

    assert result.applied is True
    assert len(state.get_pending_consequences()) == 1

    state.increment_turn()
    activations = CausalityEngine(state).evaluate(next_turn=True)

    assert len(activations) == 1
    assert state.get_pending_consequences() == []
    assert any("guardianes" in item.get("evento", "") for item in state.data["eventos"])


def test_social_relation_and_visibility_remain_separate(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_world_fact("culto_activo", True)
    state.set_character_fact("Alicia", "sospecha_del_culto", True)
    state.set_player_fact("pista_publica", "sello roto")

    state.set_relation("Alicia", "Bruno", "desconfianza", -40, reason="negociación")

    visibility = KnowledgeVisibility(state)
    view = visibility.snapshot(character="Alicia", include_player=True)

    assert "culto_activo" not in view.character
    assert "culto_activo" not in view.player
    assert "sospecha_del_culto" in view.character
    assert "pista_publica" in view.player
    assert state.get_relations("Alicia")[0]["relation"] == "desconfianza"


def test_rule_arbiter_resolves_before_narrative_layer():
    arbiter = RuleArbiter(builder=FakeBuilder())
    result = arbiter.resolve(
        action_text="investigar la pista con dificultad 15",
        character={"inteligencia": 14},
        system_slug="generic",
        rolls=[13],
        sides=20,
    )

    assert result is not None
    assert result["mecanica"] == "d20_vs_dc"
    assert result["dificultad"] == 15
    assert result["veredicto"] == "ÉXITO"


def test_invalid_proposal_does_not_mutate_state(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    before = state.data.copy()

    result = ProposalExecutor(state).execute({
        "campo_inexistente": "no debe aplicarse",
    })

    assert result.applied is False
    assert state.data == before
    assert not state.path.exists()


def test_causal_chain_updates_world_relation_and_front_clock(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_front(
        "Amenaza",
        faction="culto",
        goal="Abrir el portal",
        max_stage=6,
    )

    state.add_pending_consequence(
        "El culto acelera sus preparativos.",
        trigger="ritual descubierto",
        effects=[
            {"type": "relation", "source": "Alicia", "target": "Culto", "relation": "hostilidad", "strength": -70},
            {"type": "front_clock_delta", "name": "Amenaza", "delta": 2},
            {"type": "world_fact", "key": "portal_inestable", "value": True},
        ],
    )

    activations = CausalityEngine(state).evaluate("ritual descubierto")

    assert len(activations) == 1
    assert state.get_world_fact("portal_inestable") is True
    assert state.get_relations("Alicia")[0]["strength"] == -70
    assert state.data["relojes"]["Amenaza"]["llenos"] == 2
