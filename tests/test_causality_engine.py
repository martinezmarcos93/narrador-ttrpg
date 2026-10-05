from narrator.core.causality_engine import CausalityEngine
from narrator.core.state_manager import StateManager


def test_causality_activates_matching_trigger(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_pending_consequence("Los refuerzos llegan", trigger="alarma")
    result = CausalityEngine(state).evaluate("La alarma comienza a sonar", next_turn=True)
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


def test_causality_applies_declared_effects(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_clock("alarma", segments=4)
    state.add_pending_consequence(
        "La alarma dispara refuerzos",
        trigger="alarma",
    )
    state.data["consecuencias_pendientes"][0]["effects"] = [
        {"type": "clock_delta", "name": "alarma", "delta": 2},
    ]
    result = CausalityEngine(state).evaluate("La alarma comienza a sonar")
    assert len(result) == 1
    assert state.data["relojes"]["alarma"]["llenos"] == 2


def test_causality_chains_through_emitted_event(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_pending_consequence(
        "La alarma activa a los guardias",
        trigger="alarma",
        )
    state.data["consecuencias_pendientes"][0]["effects"] = [
        {"type": "event", "text": "los guardias reciben la alarma"},
    ]
    state.data["consecuencias_pendientes"].append({
        "consecuencia": "Los guardias cierran las puertas",
        "trigger": "guardias reciben",
        "effects": [{"type": "player_fact", "key": "doors_closed", "value": True}],
        "estado": "pendiente",
    })

    result = CausalityEngine(state, max_cascade_depth=4).evaluate("alarma")

    assert len(result) == 2
    assert state.get_player_fact("doors_closed") is True
    assert state.get_pending_consequences() == []


def test_causality_depth_limit_prevents_infinite_cycle(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.data["consecuencias_pendientes"] = [
        {
            "consecuencia": "A",
            "trigger": "b",
            "effects": [{"type": "event", "text": "b"}],
            "estado": "pendiente",
        },
        {
            "consecuencia": "B",
            "trigger": "a",
            "effects": [{"type": "event", "text": "a"}],
            "estado": "pendiente",
        },
    ]

    result = CausalityEngine(state, max_cascade_depth=3).evaluate("a")

    assert len(result) <= 3


def test_causality_can_change_relation_and_front_clock(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_clock("frente_culto", segments=6)
    state.add_pending_consequence("El culto gana influencia", trigger="ritual")
    state.data["consecuencias_pendientes"][0]["effects"] = [
        {
            "type": "relation",
            "source": "Culto",
            "target": "Aldren",
            "relation": "amenaza",
            "strength": -70,
        },
        {"type": "front_clock_delta", "name": "frente_culto", "delta": 2},
    ]

    result = CausalityEngine(state).evaluate("ritual")

    assert len(result) == 1
    assert state.data["relojes"]["frente_culto"]["llenos"] == 2
    assert state.get_relations("Culto")[0]["relation"] == "amenaza"
    assert result[0].provenance_id
