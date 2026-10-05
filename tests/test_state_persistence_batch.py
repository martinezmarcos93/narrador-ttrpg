from narrator.core.causality_engine import CausalityEngine
from narrator.core.state_manager import StateManager


class CountingState(StateManager):
    def __init__(self, path):
        super().__init__(path)
        self.disk_writes = 0

    def _save_now(self):
        self.disk_writes += 1
        super()._save_now()


def test_causal_cascade_persists_once(tmp_path):
    state = CountingState(str(tmp_path / "estado.yaml"))
    state.add_pending_consequence("Primera consecuencia", trigger="alarma")
    state.data["consecuencias_pendientes"][0]["effects"] = [
        {"type": "event", "text": "guardias movilizados"},
    ]
    state.data["consecuencias_pendientes"].append({
        "consecuencia": "Segunda consecuencia",
        "trigger": "guardias movilizados",
        "estado": "pendiente",
    })
    state.disk_writes = 0

    result = CausalityEngine(state).evaluate("alarma")

    assert len(result) == 2
    assert state.disk_writes == 1


def test_batch_persistence_supports_nested_batches(tmp_path):
    state = CountingState(str(tmp_path / "estado.yaml"))
    state.disk_writes = 0
    state.begin_batch()
    state.set_known_fact("a", 1)
    state.begin_batch()
    state.set_known_fact("b", 2)
    state.end_batch()
    assert state.disk_writes == 0
    state.end_batch()
    assert state.disk_writes == 1


def test_rollback_batch_discards_pending_persistence(tmp_path):
    state = CountingState(str(tmp_path / "estado.yaml"))
    state.disk_writes = 0
    state.begin_batch()
    state.set_known_fact("temporal", True)
    state.rollback_batch()
    assert state.disk_writes == 0
    assert not state.path.exists()
    assert state.get_known_fact("temporal") is True
