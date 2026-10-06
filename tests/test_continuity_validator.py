from narrator.core.continuity_validator import ContinuityValidator
from narrator.core.state_manager import StateManager


def test_continuity_rejects_fact_conflict(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_known_fact("puerta_norte", "cerrada")
    report = ContinuityValidator(state).validate({
        "facts": {"puerta_norte": "abierta"},
    })
    assert not report.valid
    assert report.errors[0].code == "fact_conflict"


def test_continuity_warns_duplicate_event(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.record_event("El grupo abrió la cripta")
    report = ContinuityValidator(state).validate({
        "events": ["El grupo abrió la cripta"],
    })
    assert report.valid
    assert report.warnings[0].code == "duplicate_event"


def test_continuity_rejects_temporal_regression(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.data["meta"]["sesion_actual"] = 4
    report = ContinuityValidator(state).validate({"session": 3})
    assert not report.valid
    assert report.errors[0].code == "temporal_regression"


def test_continuity_rejects_unknown_clock(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    report = ContinuityValidator(state).validate({
        "clock_changes": [{"name": "inexistente", "delta": 1}],
    })
    assert not report.valid
    assert any(issue.code == "unknown_clock" for issue in report.errors)


def test_continuity_rejects_clock_out_of_bounds(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_clock("alarma", segments=4)
    state.data["relojes"]["alarma"]["llenos"] = 4
    report = ContinuityValidator(state).validate({
        "clock_changes": [{"name": "alarma", "delta": 1}],
    })
    assert not report.valid
    assert any(issue.code == "clock_out_of_bounds" for issue in report.errors)


def test_continuity_accumulates_multiple_clock_changes(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_clock("alarma", segments=4)
    state.data["relojes"]["alarma"]["llenos"] = 2
    report = ContinuityValidator(state).validate({
        "clock_changes": [
            {"name": "alarma", "delta": 1},
            {"name": "alarma", "delta": 2},
        ],
    })
    assert not report.valid
    assert any(issue.code == "clock_out_of_bounds" for issue in report.errors)


def test_continuity_rejects_unknown_npc_presence(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    report = ContinuityValidator(state).validate({
        "npc_presence": {"NPC inexistente": True},
    })
    assert not report.valid
    assert any(issue.code == "unknown_npc" for issue in report.errors)


def test_continuity_allows_npc_created_in_same_proposal(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    report = ContinuityValidator(state).validate({
        "npcs": [{"nombre": "El Vigía"}],
        "npc_presence": {"El Vigía": True},
    })
    assert report.valid


def test_continuity_rejects_unknown_relation_entity(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    report = ContinuityValidator(state).validate({
        "relations": [{
            "source": "Alicia",
            "target": "NPC inexistente",
            "relation": "desconfianza",
            "strength": -40,
        }],
    })
    assert not report.valid
    assert any(issue.code == "unknown_relation_entity" for issue in report.errors)


def test_continuity_validates_front_and_relation_effects(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_faction("culto", "Culto")
    state.add_front("Amenaza", faction="culto", max_stage=4)
    state.data["escena_actual"]["npcs_presentes"] = ["Alicia"]
    report = ContinuityValidator(state).validate({
        "consequences": [{
            "text": "El culto avanza",
            "trigger": "ritual descubierto",
            "effects": [
                {
                    "type": "relation",
                    "source": "Alicia",
                    "target": "culto",
                    "relation": "hostilidad",
                    "strength": -50,
                },
                {
                    "type": "front_clock_delta",
                    "name": "Amenaza",
                    "delta": 1,
                },
            ],
        }],
    })
    assert report.valid


def test_continuity_rejects_untriggered_consequence(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    report = ContinuityValidator(state).validate({
        "consequences": [{"text": "Algo sucede"}],
    })
    assert not report.valid
    assert any(issue.code == "untriggered_consequence" for issue in report.errors)


def test_continuity_rejects_invalid_consequence_effect(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    report = ContinuityValidator(state).validate({
        "consequences": [{
            "text": "Algo sucede",
            "trigger": "evento",
            "effects": [{"type": "unknown_effect"}],
        }],
    })
    assert not report.valid
    assert any(issue.code == "invalid_causal_effect" for issue in report.errors)
