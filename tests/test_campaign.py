from pathlib import Path

import pytest

from narrator.core.campaign import load_campaign, read_manifest, validate_manifest
from narrator.core.entity_registry import EntityRegistry
from narrator.core.state_manager import StateManager

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "campaigns" / "noches_de_ceniza.yaml"


def test_example_campaign_is_valid():
    assert validate_manifest(read_manifest(MANIFEST), ROOT / "data" / "systems") == []


def test_validation_catches_broken_references():
    data = read_manifest(MANIFEST)
    data["frentes"][0]["al_llenarse"] = [{"frente": "Inexistente", "delta": 1}]
    data["escena_inicial"]["npcs_presentes"] = ["Fantasma"]
    data["secretos"][0]["sobre"]["nombre"] = "Nadie"
    errors = validate_manifest(data, ROOT / "data" / "systems")
    assert any("Inexistente" in e for e in errors)
    assert any("Fantasma" in e for e in errors)
    assert any("Nadie" in e for e in errors)


def test_load_campaign_populates_state_and_vault(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    summary = load_campaign(read_manifest(MANIFEST), state, tmp_path / "vault",
                            systems_path=ROOT / "data" / "systems")
    assert summary["protagonista"]["nombre"] == "Lucía Ferro"
    assert state.get_location() == "Comedor San Roque"
    assert "Desapariciones en Constitución" in state.data["frentes"]
    assert state.data["frentes"]["Desapariciones en Constitución"]["umbrales"] == {
        2: "La prensa publica una nota sobre los desaparecidos"}
    assert "cacería-valerius" in state.data["secretos"]
    assert len(state.get_pending_consequences()) == 2
    registry = EntityRegistry(tmp_path / "vault")
    assert registry.has("npc", "valerius") and registry.has("locacion", "Eliseo del Colon")
    reloaded = StateManager(str(tmp_path / "estado.yaml"))
    assert reloaded.load() and reloaded.data["meta"]["campana"] == "Noches de Ceniza"


def test_invalid_manifest_does_not_touch_state(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    data = read_manifest(MANIFEST)
    data["meta"]["sistema"] = "inexistente"
    with pytest.raises(ValueError):
        load_campaign(data, state, tmp_path / "vault", systems_path=ROOT / "data" / "systems")
    assert not (tmp_path / "estado.yaml").exists()
    assert not (tmp_path / "vault").exists()
