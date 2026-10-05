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


class _FakeVaultWriter:
    def __init__(self):
        self.created = []

    def create_npc(self, data):
        self.created.append(("npc", data["nombre"]))
        return object()

    def create_locacion(self, data):
        self.created.append(("locacion", data["nombre"]))
        return object()


def test_executor_creates_structured_entities(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    writer = _FakeVaultWriter()
    executor = ProposalExecutor(state, vault_writer=writer)
    result = executor.execute({
        "npcs": [{"nombre": "El Vigía", "rol": "guardián"}],
        "locations": [{"nombre": "Cripta del Norte"}],
        "npc_presence": {"El Vigía": True},
        "scene_changes": {"locacion": "Cripta del Norte"},
    })
    assert result.applied
    assert ("npc", "El Vigía") in writer.created
    assert ("locacion", "Cripta del Norte") in writer.created
    assert "El Vigía" in state.data["escena_actual"]["npcs_presentes"]



class _FailingNarrator:
    @staticmethod
    def character_field_specs(schema):
        return {"hp": {"key": "hp", "type": "int"}}

    @staticmethod
    def apply_state_mutations(character, mutations, allowed_fields=None):
        character["hp"] = 1
        raise RuntimeError("fallo deliberado")


def test_executor_rolls_back_state_character_and_entities(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    character = {"hp": 10}
    from narrator.core.vault_writer import VaultWriter
    vault = VaultWriter(str(tmp_path / "vault"))
    executor = ProposalExecutor(
        state,
        narrator_agent=_FailingNarrator(),
        character_schema={"base_sections": [{"fields": [{"key": "hp", "type": "int"}]}]},
        vault_writer=vault,
    )

    result = executor.execute({
        "facts": {"temporary": True},
        "npcs": [{"nombre": "NPC Temporal"}],
        "character_changes": [{"field": "hp", "delta": -3}],
    }, character=character)

    assert not result.applied
    assert result.rolled_back
    assert character["hp"] == 10
    assert "temporary" not in state.data["hechos_conocidos"]
    assert not (tmp_path / "vault" / "NPCs" / "NPC_Temporal.md").exists()
    assert any(issue.code == "proposal_execution_failed" for issue in result.report.issues)


def test_executor_success_keeps_created_entity(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    from narrator.core.vault_writer import VaultWriter
    vault = VaultWriter(str(tmp_path / "vault"))
    executor = ProposalExecutor(state, vault_writer=vault)

    result = executor.execute({
        "facts": {"persistent": True},
        "npcs": [{"nombre": "Guardia Persistente"}],
    })

    assert result.applied
    assert state.get_known_fact("persistent") is True
    assert (tmp_path / "vault" / "NPCs" / "Guardia_Persistente.md").exists()
