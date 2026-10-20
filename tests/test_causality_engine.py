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



def test_causality_exposes_metrics(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_pending_consequence("Refuerzos llegan", trigger="alarma")
    engine = CausalityEngine(state)
    result = engine.evaluate("alarma")
    assert len(result) == 1
    assert engine.last_metrics["activations"] == 1
    assert engine.last_metrics["max_depth"] == 0
    assert engine.last_metrics["provenance_ids"] == [result[0].provenance_id]


def test_causality_executes_state_and_scene_primitives(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.data["escena_actual"]["npcs_presentes"] = ["Guardia"]
    state.add_pending_consequence("La escena cambia", trigger="señal")
    state.data["consecuencias_pendientes"][0]["effects"] = [
        {"type": "fact", "key": "puerta_abierta", "value": True},
        {"type": "flag", "name": "alarma", "value": True},
        {"type": "npc_presence", "name": "Guardia", "present": False},
        {"type": "scene_location", "value": "Patio"},
    ]

    result = CausalityEngine(state).evaluate("señal")

    assert len(result) == 1
    assert state.get_known_fact("puerta_abierta") is True
    assert state.get_flag("alarma") is True
    assert state.data["escena_actual"]["npcs_presentes"] == []
    assert state.get_location() == "Patio"


def test_same_step_clock_deltas_are_aggregated_before_clamp(tmp_path):
    """+3 y -2 en el mismo paso equivalen a +1, sin importar el orden."""
    results = []
    for order in ((3, -2), (-2, 3)):
        state = StateManager(str(tmp_path / f"estado_{order[0]}.yaml"))
        state.add_clock("culto", segments=6)
        state.data["relojes"]["culto"]["llenos"] = 5
        for delta in order:
            state.add_pending_consequence(
                f"cambio {delta}", trigger="señal",
                effects=[{"type": "clock_delta", "name": "culto", "delta": delta}],
            )
        CausalityEngine(state).evaluate("señal")
        results.append(state.data["relojes"]["culto"]["llenos"])
    assert results == [6, 6]


def test_threshold_event_emitted_once_for_aggregated_step(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_clock("culto", segments=4)
    for _ in range(3):
        state.add_pending_consequence(
            "empuje", trigger="ritual",
            effects=[{"type": "front_clock_delta", "name": "culto", "delta": 2}],
        )
    state.add_pending_consequence(
        "reacción", trigger="frente culto lleno",
        effects=[{"type": "player_fact", "key": "portal", "value": "abierto"}],
    )
    engine = CausalityEngine(state)
    activations = engine.evaluate("ritual")
    assert state.data["relojes"]["culto"]["llenos"] == 4
    assert [a.consequence for a in activations].count("reacción") == 1
    assert state.get_player_fact("portal") == "abierto"


def test_event_cursor_feeds_new_facts_to_causality_once(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_pending_consequence("Llegan refuerzos", trigger="alarma")
    state.record_event("Suena la alarma del banco")
    assert state.pending_causal_events() == ["Suena la alarma del banco"]

    result = CausalityEngine(state).evaluate(" | ".join(state.pending_causal_events()))
    state.mark_causal_events_consumed()
    assert len(result) == 1
    # Los eventos generados por la cascada no se vuelven a alimentar.
    assert state.pending_causal_events() == []


def test_prepare_turn_activates_trigger_from_previous_proposal(tmp_path, monkeypatch):
    from pathlib import Path

    from narrator.agents.orchestrator import Orchestrator

    root = Path(__file__).resolve().parent.parent
    monkeypatch.setattr("narrator.core.embedder.Embedder.is_available", lambda self: False)
    config = tmp_path / "config.yaml"
    config.write_text(
        f"systems_path: {root / 'data' / 'systems'}\n"
        f"vault:\n  path: {tmp_path / 'vault'}\n"
        f"cerebro:\n  path: {tmp_path / 'cerebro'}\n"
        f"estado:\n  path: {tmp_path / 'estado.yaml'}\n",
        encoding="utf-8",
    )
    orch = Orchestrator(config_path=str(config))
    app_state = {"system_slug": "generic", "messages": [{"role": "user", "content": "Espero"}]}
    applied = orch.validate_and_apply_proposal({
        "events": ["El grupo rompe el sello de la cripta"],
        "consequences": [{"text": "Los guardianes despiertan", "trigger": "sello de la cripta",
                          "effects": [{"type": "world_fact", "key": "guardianes", "value": "despiertos"}]}],
    }, app_state)
    assert applied["applied"]
    contract = orch.prepare_turn(app_state)
    assert orch.state.get_world_fact("guardianes") == "despiertos"
    assert contract.causal_metrics["activations"] == 1
