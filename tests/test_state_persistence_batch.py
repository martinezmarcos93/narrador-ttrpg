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


def test_atomic_save_preserves_previous_file_when_replace_fails(tmp_path, monkeypatch):
    import os
    import yaml

    path = tmp_path / "estado.yaml"
    state = StateManager(str(path))
    state.set_known_fact("original", True)
    original = path.read_text(encoding="utf-8")

    state.set_known_fact("nuevo", True)

    real_replace = os.replace

    def failing_replace(source, destination):
        if destination == path:
            raise OSError("fallo deliberado de replace")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", failing_replace)

    try:
        state.save()
    except OSError:
        pass
    else:
        raise AssertionError("se esperaba fallo de persistencia")

    assert path.read_text(encoding="utf-8") == original
    leftovers = list(tmp_path.glob(".estado.yaml.*.tmp"))
    assert leftovers == []
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["hechos_conocidos"]["original"]["valor"] is True


def test_atomic_save_removes_temp_after_yaml_serialization_failure(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_known_fact("original", True)
    original = state.path.read_text(encoding="utf-8")

    class Broken:
        def __repr__(self):
            raise RuntimeError("serialization failure")

    state.data["hechos_conocidos"]["broken"] = {"valor": Broken()}

    try:
        state.save()
    except RuntimeError:
        pass
    else:
        raise AssertionError("se esperaba fallo de serialización")

    assert state.path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".estado.yaml.*.tmp")) == []


def test_corrupt_state_is_quarantined_on_load(tmp_path):
    path = tmp_path / "estado.yaml"
    path.write_text("::: yaml roto [", encoding="utf-8")
    state = StateManager(str(path))

    assert state.load() is False
    backups = list(tmp_path.glob("estado.corrupto-*.yaml"))
    assert len(backups) == 1
    assert not path.exists()
