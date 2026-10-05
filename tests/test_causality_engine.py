from narrator.core.causality_engine import CausalityEngine
from narrator.core.state_manager import StateManager


def test_causality_activates_matching_trigger(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_pending_consequence(
        "Los refuerzos llegan",
        trigger="alarma",
    )
    engine = CausalityEngine(state)
    result = engine.evaluate("La alarma comienza a sonar", next_turn=True)
    assert len(result) == 1
    assert state.get_pending_consequences() == []
    assert "Consecuencia activada" in state.data["eventos"][-1]["evento"]


def test_causality_activates_due_session(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.start_session()
    state.add_pending_consequence("El pacto expira", due="sesion:1")
    result = CausalityEngine(state).evaluate("")
    assert len(result) == 1
    assert state.get_pending_consequences() == []


def test_causality_keeps_unmatched_consequence_pending(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_pending_consequence("Llegan refuerzos", trigger="campana")
    result = CausalityEngine(state).evaluate("El grupo descansa")
    assert result == []
    assert len(state.get_pending_consequences()) == 1
