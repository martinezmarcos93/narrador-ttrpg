from narrator.core.state_manager import StateManager


def test_social_relation_is_persistent_and_queryable(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_relation("Aldren", "Mara", "desconfia", -40, reason="traición")

    relations = state.get_relations("Aldren")

    assert len(relations) == 1
    assert relations[0]["target"] == "Mara"
    assert relations[0]["strength"] == -40


def test_relation_graph_text_filters_to_scene_entities(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_relation("Aldren", "Mara", "aliado", 60)
    state.set_relation("Aldren", "Culto", "enemigo", -80)

    text = state.get_relation_graph_text(["Aldren", "Mara"])

    assert "Aldren" in text
    assert "Mara" in text
    assert "Culto" not in text


def test_provenance_is_chainable(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    root = state.record_provenance(
        kind="causal_activation",
        source="CausalityEngine",
        detail="alarma",
    )
    child = state.record_provenance(
        kind="causal_activation",
        source="CausalityEngine",
        detail="guardias",
        parent_id=root,
    )

    recent = state.get_recent_provenance()

    assert recent[-1]["id"] == child
    assert recent[-1]["parent_id"] == root
