from narrator.core.state_manager import StateManager


def test_front_has_formal_metadata_and_legacy_clock(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_front(
        "Culto",
        "Expansión del culto",
        max_stage=8,
        faction="Orden Negra",
        goal="Abrir el portal",
        priority=5,
    )

    front = state.get_front("Culto")
    assert front["faccion"] == "Orden Negra"
    assert front["objetivo"] == "Abrir el portal"
    assert front["prioridad"] == 5
    assert state.data["relojes"]["Culto"]["segmentos"] == 8


def test_active_fronts_are_sorted_by_priority(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_front("Bajo", faction="A", priority=1)
    state.add_front("Alto", faction="B", priority=10)
    state.advance_front_clock("Alto", 2)

    fronts = state.get_active_fronts()
    assert [item["nombre"] for item in fronts] == ["Alto", "Bajo"]
    assert fronts[0]["llenos"] == 2
