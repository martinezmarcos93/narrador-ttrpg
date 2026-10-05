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
