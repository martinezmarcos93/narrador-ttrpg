from narrator.agents.narrator_agent import NarratorAgent
from narrator.core.proposal_executor import ProposalExecutor
from narrator.core.state_manager import StateManager


def test_executor_rejects_conflicting_proposal(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_known_fact("puerta", "cerrada")
    executor = ProposalExecutor(state)
    result = executor.execute({"facts": {"puerta": "abierta"}})
    assert not result.applied
    assert result.changes == []


def test_executor_applies_valid_campaign_proposal(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_clock("alarma", segments=4)
    executor = ProposalExecutor(state)
    result = executor.execute({
        "facts": {"puerta_abierta": True},
        "events": ["El grupo abre la puerta"],
        "npc_presence": {"Guardia": True},
        "consequences": [{"text": "El ruido alerta a los guardias", "trigger": "siguiente turno"}],
        "clock_changes": [{"name": "alarma", "delta": 1}],
        "scene_changes": {"locacion": "Patio"},
    })
    assert result.applied
    assert state.get_known_fact("puerta_abierta") is True
    assert "Guardia" in state.data["escena_actual"]["npcs_presentes"]
    assert state.data["relojes"]["alarma"]["llenos"] == 1
    assert state.get_location() == "Patio"


def test_executor_validates_character_fields_before_mutation(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    agent = NarratorAgent()
    schema = {
        "base_sections": [{
            "fields": [{"key": "hp", "type": "int", "min": 0, "max": 20}]
        }]
    }
    character = {"hp": 10}
    executor = ProposalExecutor(state, agent, schema)
    result = executor.execute({
        "character_changes": [{"field": "hp", "delta": -30}],
    }, character=character)
    assert result.applied
    assert character["hp"] == 0
