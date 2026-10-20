from narrator.core.continuity_validator import ContinuityValidator
from narrator.core.entity_registry import EntityRegistry, NameSet, fold_name
from narrator.core.proposal_executor import ProposalExecutor
from narrator.core.state_manager import StateManager


def _note(path, nombre=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f'---\ntipo: npc\nnombre: "{nombre}"\n---\n' if nombre else ""
    path.write_text(head + "# nota\n", encoding="utf-8")


def test_fold_name_ignores_case_accents_and_underscores():
    assert fold_name("Cripta_del  Norte") == fold_name("cripta del norte")
    assert fold_name("Ángel Caído") == "angel caido"


def test_nameset_membership_is_normalized():
    names = NameSet(["El Vigía"])
    assert "el vigia" in names
    assert "Otro" not in names
    assert "Otro" in names | ["otro"]


def test_registry_reads_frontmatter_names_and_refreshes(tmp_path):
    _note(tmp_path / "NPCs" / "Vigia.md", nombre="El Vigía")
    _note(tmp_path / "Locaciones" / "Cripta_del_Norte.md")
    registry = EntityRegistry(tmp_path)
    assert registry.has("npc", "el vigia")
    assert registry.has("locacion", "Cripta del Norte")
    assert not registry.has("npc", "Bruno")

    _note(tmp_path / "NPCs" / "Bruno.md")
    assert registry.has("npc", "Bruno")
    assert registry.snapshot()["npc"] == ["Bruno", "El Vigía"]


def test_validator_accepts_vault_npc_not_present_in_scene(tmp_path):
    vault = tmp_path / "vault"
    _note(vault / "NPCs" / "Guardia.md", nombre="Guardia")
    state = StateManager(str(tmp_path / "estado.yaml"))

    without_registry = ContinuityValidator(state).validate({"npc_presence": {"Guardia": True}})
    assert any(i.code == "unknown_npc" for i in without_registry.errors)

    with_registry = ContinuityValidator(state, entity_registry=EntityRegistry(vault))
    assert with_registry.validate({"npc_presence": {"guardia": True}}).valid


def test_validator_rejects_unknown_location_when_vault_has_locations(tmp_path):
    vault = tmp_path / "vault"
    _note(vault / "Locaciones" / "Patio.md")
    state = StateManager(str(tmp_path / "estado.yaml"))
    validator = ContinuityValidator(state, entity_registry=EntityRegistry(vault))

    assert validator.validate({"scene_changes": {"locacion": "patio"}}).valid
    report = validator.validate({"scene_changes": {"locacion": "Luna"}})
    assert any(i.code == "unknown_location" for i in report.errors)


def test_executor_uses_registry_for_relations_with_vault_factions(tmp_path):
    vault = tmp_path / "vault"
    _note(vault / "NPCs" / "Aldren.md")
    _note(vault / "Cofradias" / "Culto.md")
    state = StateManager(str(tmp_path / "estado.yaml"))
    executor = ProposalExecutor(state, entity_registry=EntityRegistry(vault))
    result = executor.execute({
        "relations": [{"source": "Aldren", "target": "Culto", "relation": "enemigo", "strength": -50}]
    })
    assert result.applied, result.report.to_dict()
