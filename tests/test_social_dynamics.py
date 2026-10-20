from narrator.core import social
from narrator.core.state_manager import StateManager


def test_tiers():
    assert [social.tier(v) for v in (-90, -40, 0, 40, 90)] == [
        "hostil", "tensa", "neutral", "cordial", "aliada"]


def test_history_and_tier_events(tmp_path):
    state = StateManager(str(tmp_path / "e.yaml"))
    state.set_relation("Ana", "Beto", "amistad", 10)
    assert not any("pasa a" in e["evento"] for e in state.data["eventos"])
    state.set_relation("Ana", "Beto", "amistad", 70, reason="lo salvó")
    rel = state.get_relations("Ana")[0]
    assert rel["tier"] == "aliada"
    assert [h["strength"] for h in rel["historial"]] == [10, 70]
    assert state.data["eventos"][-1]["evento"] == "relación Ana -> Beto pasa a aliada"


def test_session_decay_only_for_volatile_types(tmp_path):
    state = StateManager(str(tmp_path / "e.yaml"))
    state.set_relation("Ana", "Ogro", "temor", -30)
    state.set_relation("Ana", "Rey", "enemigo", -80)
    state.start_session()
    assert state.get_relations("Ogro")[0]["strength"] == -20
    assert state.get_relations("Rey")[0]["strength"] == -80


def test_valence_warning():
    assert social.valence_warning("enemigo", 70)
    assert social.valence_warning("Amistad", 50) == ""


def test_validator_warns_on_contradictory_valence(tmp_path):
    from narrator.core.continuity_validator import ContinuityValidator

    report = ContinuityValidator().validate({"relations": [
        {"source": "A", "target": "B", "relation": "enemigo", "strength": 80}]})
    assert report.valid
    assert any(i.code == "relation_valence" for i in report.warnings)
