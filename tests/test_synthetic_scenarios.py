from narrator.core.causality_engine import CausalityEngine
from narrator.core.context_contract import ContextFragment, render_context
from narrator.core.continuity_validator import ContinuityValidator
from narrator.core.knowledge_visibility import KnowledgeVisibility
from narrator.core.state_manager import StateManager


def test_synthetic_turn_context_causal_chain_and_continuity(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_front("culto", faction="culto", goal="abrir el portal")
    state.add_pending_consequence(
        "El culto avanza el ritual",
        trigger="ritual",
        )
    state.data["consecuencias_pendientes"][0]["effects"] = [
        {"type": "front_clock_delta", "name": "culto", "delta": 2},
        {"type": "event", "text": "el ritual acelera"},
    ]

    context = render_context([
        ContextFragment(
            "El reloj del culto representa presión narrativa.",
            "brain",
            "universal",
            title="Frentes y relojes",
            score=0.8,
        ),
        ContextFragment(
            state.get_turn_context_text(),
            "StateManager",
            "state",
            title="Estado vivo",
            score=1.0,
        ),
    ], max_words=250)

    assert "[STATE" in context
    result = CausalityEngine(state).evaluate("ritual")
    assert len(result) == 1
    assert state.get_front("culto")
    assert state.data["relojes"]["culto"]["llenos"] == 2

    report = ContinuityValidator(state).validate({
        "facts": {},
        "events": ["el ritual acelera"],
        "npc_presence": {},
    })
    assert report.valid


def test_synthetic_secret_does_not_leak_into_narrator_context(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_world_fact("ritual_real", True, source="manual")
    state.set_character_fact("Aldren", "ritual_real", False, source="observacion")
    state.set_player_fact("pista_ritual", True, source="jugador")

    visible = KnowledgeVisibility(state).narrator_view(
        character="Aldren",
        include_player=True,
    )
    assert "ritual_real=False" in visible
    assert "ritual_real=True" not in visible
    assert "pista_ritual=True" in visible


def test_synthetic_conflicting_fact_is_blocked_before_state_mutation(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_known_fact("puerta", "cerrada")
    validator = ContinuityValidator(state)
    report = validator.validate({
        "facts": {"puerta": "abierta"},
        "events": [],
        "npc_presence": {},
    })
    assert not report.valid
    assert any(issue.code == "fact_conflict" for issue in report.errors)
    assert state.get_known_fact("puerta") == "cerrada"
