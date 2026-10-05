from narrator.core.turn_contract import TURN_STAGES, TurnContract


def test_turn_contract_advances_through_known_stages():
    contract = TurnContract(input_text="intento abrir la puerta", system_slug="generic")
    for stage in TURN_STAGES[1:]:
        contract.advance(stage)
    assert contract.stage == "persist"


def test_turn_contract_rejects_unknown_stage():
    contract = TurnContract(input_text="hola", system_slug="generic")
    try:
        contract.advance("invented")
    except ValueError as exc:
        assert "Etapa de turno desconocida" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_turn_contract_exposes_mechanical_result():
    contract = TurnContract(
        input_text="ataco",
        system_slug="dnd_5e",
        mechanical_resolution={"detalle": "Ataque: 18 vs CD 15 → ÉXITO", "banda": "10+"},
    )
    assert contract.mechanical_verdict == "Ataque: 18 vs CD 15 → ÉXITO"
    assert contract.mechanical_band == "10+"
    payload = contract.narrative_input()
    assert payload["mechanical_resolution"]["banda"] == "10+"
