from narrator.core.proposal_executor import ProposalExecutor
from narrator.core.state_manager import StateManager


class FailingState(StateManager):
    def apply_proposal(self, proposal):
        self.data.setdefault("hechos_conocidos", {})["partial"] = {"valor": True}
        self.save()
        raise RuntimeError("fallo durante apply_proposal")


class Vault:
    def __init__(self):
        self.created = []

    def create_npc(self, data):
        marker = data["nombre"]
        self.created.append(marker)
        return marker

    def rollback_created_entities(self, paths):
        self.created = [item for item in self.created if item not in paths]


def test_state_failure_rolls_back_state_character_and_external_entities(tmp_path):
    state = FailingState(str(tmp_path / "state.yaml"))
    character = {"hp": 10}
    vault = Vault()
    executor = ProposalExecutor(state, vault_writer=vault)

    result = executor.execute({"facts": {"temporary": True}, "npcs": [{"nombre": "Temporal"}]}, character=character)

    assert result.applied is False
    assert result.rolled_back is True
    assert "partial" not in state.data["hechos_conocidos"]
    assert "temporary" not in state.data["hechos_conocidos"]
    assert character == {"hp": 10}
    assert vault.created == []


def test_nested_failure_preserves_outer_batch_boundary(tmp_path):
    state = FailingState(str(tmp_path / "state.yaml"))
    state.begin_batch()
    result = ProposalExecutor(state).execute({"facts": {"temporary": True}})
    assert result.applied is False
    assert state.batch_depth == 1
    assert "partial" not in state.data["hechos_conocidos"]
    state.end_batch()
