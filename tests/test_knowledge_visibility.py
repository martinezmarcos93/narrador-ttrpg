from narrator.core.knowledge_visibility import KnowledgeVisibility
from narrator.core.state_manager import StateManager


def test_world_fact_is_not_exposed_as_character_knowledge(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_world_fact("villain_identity", "Arconte", source="manual")
    visibility = KnowledgeVisibility(state)

    view = visibility.snapshot(character="Marcos")

    assert "villain_identity" in view.world
    assert "villain_identity" not in view.character
    assert "villain_identity" not in view.player


def test_character_and_player_knowledge_are_separate(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_character_fact("Aldren", "heard_name", "Mara", source="scene")
    state.set_player_fact("secret_room_seen", True, source="narration")
    visibility = KnowledgeVisibility(state)

    view = visibility.snapshot(character="Aldren")

    assert view.character["heard_name"]["valor"] == "Mara"
    assert "secret_room_seen" not in view.character
    assert view.player["secret_room_seen"]["valor"] is True
    assert "villain_identity" not in visibility.narrator_view(character="Aldren")


def test_character_view_does_not_leak_world_bucket(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_world_fact("secret", "ritual", source="world")
    state.set_character_fact("Aldren", "known", "tavern", source="npc")
    visibility = KnowledgeVisibility(state)

    rendered = visibility.narrator_view(character="Aldren")

    assert "known=tavern" in rendered
    assert "secret=ritual" not in rendered
