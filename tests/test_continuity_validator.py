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
