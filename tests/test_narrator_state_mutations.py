from narrator.agents.narrator_agent import NarratorAgent


def test_state_mutations_are_restricted_to_schema_fields():
    agent = NarratorAgent()
    specs = {
        "hp": {"key": "hp", "type": "int", "min": 0, "max": 10},
    }
    character = {"hp": 5}
    mutations = [
        {"field": "hp", "delta": "-20", "reason": "daño"},
        {"field": "secret_admin_flag", "value": "true"},
    ]
    changelog = agent.apply_state_mutations(character, mutations, allowed_fields=specs)
    assert character["hp"] == 0
    assert "secret_admin_flag" not in character
    assert len(changelog) == 1


def test_character_field_specs_collects_base_and_conditional_fields():
    schema = {
        "base_sections": [{"name": "Base", "fields": [{"key": "hp", "type": "int"}]}],
        "conditional_sections": {
            "clan": [{"name": "Clan", "fields": [{"key": "discipline", "type": "string"}]}]
        },
    }
    specs = NarratorAgent.character_field_specs(schema)
    assert set(specs) == {"hp", "discipline"}
