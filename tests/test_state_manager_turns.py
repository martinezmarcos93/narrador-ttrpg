from narrator.core.state_manager import StateManager


def test_state_manager_persists_bounded_turn_summaries(tmp_path):
    manager = StateManager(str(tmp_path / "estado.yaml"))
    for i in range(205):
        manager.record_turn({
            "turn_id": f"turn-{i}",
            "created_at": "",
            "completed_at": "",
            "system": "generic",
            "stage": "persist",
            "intent": "dialogue",
            "rule_need": "",
            "mechanical_resolution": None,
            "state_delta": {},
            "provenance": [],
            "errors": [],
        })

    turns = manager.get_recent_turns(300)
    assert len(turns) == 200
    assert turns[0]["turn_id"] == "turn-5"
    assert turns[-1]["turn_id"] == "turn-204"
