from pathlib import Path

import pytest

from narrator.core.system_pack import KnowledgePolicy, SystemPack


def test_vtm_system_pack_declares_knowledge_policy():
    pack = SystemPack.load("vtm_v20", Path("data/systems"))
    assert pack.slug == "vtm_v20"
    assert pack.knowledge.brain_system == "vtm_v20"
    assert pack.knowledge.preferred_sources[:2] == ("manual", "system")


def test_system_pack_rejects_missing_contract_fields():
    data = {"slug": "x", "sistema": "X", "edition": "1"}
    with pytest.raises(ValueError, match="faltan campos"):
        SystemPack.from_dict(data)


def test_knowledge_policy_rejects_unknown_source():
    with pytest.raises(ValueError, match="Fuentes de conocimiento inválidas"):
        KnowledgePolicy(brain_system="x", preferred_sources=("manual", "internet"))


@pytest.mark.parametrize("slug", ["generic", "vtm_v20", "dnd_5e", "coc_7e", "pathfinder_2e"])
def test_all_shipped_systems_satisfy_contract(slug):
    pack = SystemPack.load(slug, Path("data/systems"))
    assert pack.slug == slug
    assert pack.knowledge.brain_system == slug

def test_system_pack_formal_front_contract():
    pack = SystemPack.from_dict({
        "slug": "test",
        "sistema": "Test",
        "edition": "1",
        "vocabulario": {},
        "character_sheet_schema": {},
        "resolution": {},
        "lorebook": [],
        "knowledge": {},
        "factions": {
            "culto": {"nombre": "Culto del Eclipse"},
        },
        "fronts": {
            "ritual": {"nombre": "Ritual", "faccion": "culto"},
        },
        "llm_system_prompt": "",
    })
    assert pack.validate_front_contract() == []
    assert pack.front_definition("ritual")["faccion"] == "culto"


def test_system_pack_rejects_front_unknown_faction():
    pack = SystemPack.from_dict({
        "slug": "test",
        "sistema": "Test",
        "edition": "1",
        "vocabulario": {},
        "character_sheet_schema": {},
        "resolution": {},
        "lorebook": [],
        "knowledge": {},
        "fronts": {"ritual": {"nombre": "Ritual", "faccion": "missing"}},
        "llm_system_prompt": "",
    })
    assert any("facción inexistente" in error for error in pack.validate_front_contract())
