from narrator.core.causality_engine import CausalityEngine
from narrator.core.fronts import change_clock
from narrator.core.state_manager import StateManager


def _state(tmp_path):
    state = StateManager(str(tmp_path / "e.yaml"))
    state.add_front("Culto", max_stage=4, thresholds={2: "secuestran a un testigo"},
                    on_full=[{"frente": "Guardia", "delta": 2}])
    state.add_front("Guardia", max_stage=4, on_full=[{"frente": "Culto", "delta": 1}])
    return state


def test_threshold_and_full_events(tmp_path):
    state = _state(tmp_path)
    events = change_clock(state, "Culto", 2)
    assert "frente Culto umbral 2: secuestran a un testigo" in events
    assert state.data["eventos"][-1]["evento"].startswith("frente Culto umbral 2")
    assert change_clock(state, "Culto", 0) == ["reloj Culto: 2->2"]


def test_full_front_pushes_linked_front_with_bounded_cycle(tmp_path):
    state = _state(tmp_path)
    state.data["relojes"]["Guardia"]["llenos"] = 3
    events = change_clock(state, "Culto", 4)
    assert "frente Culto lleno" in events
    assert state.data["relojes"]["Guardia"]["llenos"] == 4
    assert "frente Guardia lleno" in events  # Guardia -> Culto ya está lleno: sin ciclo


def test_session_advance(tmp_path):
    state = StateManager(str(tmp_path / "e.yaml"))
    state.add_front("Plaga", max_stage=6, advance_per_session=1)
    state.start_session()
    state.start_session()
    assert state.data["relojes"]["Plaga"]["llenos"] == 2


def test_causality_uses_threshold_events(tmp_path):
    state = _state(tmp_path)
    state.add_pending_consequence("La policía investiga", trigger="secuestran a un testigo",
                                  effects=[{"type": "world_fact", "key": "policia", "value": True}])
    state.add_pending_consequence("Empuje", trigger="ritual",
                                  effects=[{"type": "front_clock_delta", "name": "Culto", "delta": 2}])
    CausalityEngine(state).evaluate("ritual")
    assert state.get_world_fact("policia") is True
