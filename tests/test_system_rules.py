import pytest

from narrator.core.continuity_validator import ContinuityValidator
from narrator.core.proposal_executor import ProposalExecutor
from narrator.core.state_manager import StateManager
from narrator.core.system_pack import SystemPack
from narrator.core.system_rules import SystemContinuityRules

RULES = SystemContinuityRules.from_dict({
    "fact_ranges": {"humanidad": {"min": 0, "max": 10}},
    "fact_values": {"estado_vampiro": ["despierto", "torpor"]},
    "mutually_exclusive": [["en_torpor", "en_combate"]],
    "forbidden_effects": ["scene_location"],
})


def _validator(tmp_path):
    validator = ContinuityValidator(StateManager(str(tmp_path / "estado.yaml")))
    validator.system_rules = RULES
    validator.system_slug = "vtm_v20"
    return validator


@pytest.mark.parametrize("data, message", [
    ({"unknown": {}}, "claves desconocidas"),
    ({"fact_ranges": {"x": {}}}, "min y/o max"),
    ({"fact_ranges": {"x": {"min": 5, "max": 1}}}, "min > max"),
    ({"fact_values": {"x": []}}, "lista no vacía"),
    ({"mutually_exclusive": [["solo"]]}, "al menos dos"),
    ({"forbidden_effects": ["borrar_disco"]}, "tipos desconocidos"),
])
def test_rules_reject_malformed_declarations(data, message):
    with pytest.raises(ValueError, match=message):
        SystemContinuityRules.from_dict(data)


def test_fact_range_and_type(tmp_path):
    v = _validator(tmp_path)
    assert v.validate({"facts": {"humanidad": 7}}).valid
    codes = {i.code for i in v.validate({"facts": {"humanidad": 12}}).errors}
    assert "system_fact_out_of_range" in codes
    codes = {i.code for i in v.validate({"facts": {"humanidad": "alta"}}).errors}
    assert "system_fact_type" in codes


def test_fact_values_inside_nested_causal_effect(tmp_path):
    v = _validator(tmp_path)
    proposal = {"consequences": [{
        "text": "El sol sale", "trigger": "amanecer",
        "effects": [{"type": "queue_consequence", "consequence": "c", "trigger": "t",
                     "effects": [{"type": "world_fact", "key": "estado_vampiro", "value": "zombi"}]}],
    }]}
    assert any(i.code == "system_fact_value" for i in v.validate(proposal).errors)


def test_mutually_exclusive_considers_live_state(tmp_path):
    v = _validator(tmp_path)
    v.state.set_known_fact("en_torpor", True)
    report = v.validate({"facts": {"en_combate": True}})
    assert any(i.code == "system_exclusive_facts" for i in report.errors)
    assert v.validate({"facts": {"en_combate": False}}).valid


def test_forbidden_effect(tmp_path):
    v = _validator(tmp_path)
    report = v.validate({"consequences": [{
        "text": "x", "trigger": "y", "effects": [{"type": "scene_location", "value": "Patio"}],
    }]})
    assert any(i.code == "system_forbidden_effect" for i in report.errors)


def test_bundled_packs_declare_parseable_rules():
    for slug in ("vtm_v20", "dnd_5e", "coc_7e", "pathfinder_2e"):
        pack = SystemPack.load(slug, "data/systems")
        assert not pack.continuity_rules.empty, slug
    assert SystemPack.load("generic", "data/systems").continuity_rules.empty


def test_executor_applies_pack_rules(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    executor = ProposalExecutor(state)
    pack = SystemPack.load("dnd_5e", "data/systems")
    executor.configure_system_rules(pack.continuity_rules, pack.slug)
    rejected = executor.execute({"facts": {"nivel_agotamiento": 7}})
    assert not rejected.applied
    assert executor.execute({"facts": {"nivel_agotamiento": 2}}).applied
