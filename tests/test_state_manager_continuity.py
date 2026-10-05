from narrator.core.state_manager import StateManager


def test_state_manager_tracks_pending_consequences_and_known_facts(tmp_path):
    manager = StateManager(str(tmp_path / "estado.yaml"))
    manager.add_pending_consequence("El culto enviará un cazador", trigger="si el ritual falla")
    manager.set_known_fact("puerta_norte", "cerrada", source="observación")

    pending = manager.get_pending_consequences()
    assert pending[0]["estado"] == "pendiente"
    assert manager.get_known_fact("puerta_norte") == "cerrada"

    resolved = manager.resolve_pending_consequence(0, "El cazador llega a la ciudad")
    assert resolved["estado"] == "resuelta"
    assert manager.get_pending_consequences() == []


def test_turn_context_includes_recent_causality_state(tmp_path):
    manager = StateManager(str(tmp_path / "estado.yaml"))
    manager.record_event("El grupo abrió la cripta", actor="grupo", location="cripta")
    manager.add_pending_consequence("Los guardianes investigarán la intrusión")
    manager.set_known_fact("cripta_abierta", True)

    context = manager.get_turn_context_text()
    assert "El grupo abrió la cripta" in context
    assert "Los guardianes investigarán la intrusión" in context
    assert "cripta_abierta=True" in context
