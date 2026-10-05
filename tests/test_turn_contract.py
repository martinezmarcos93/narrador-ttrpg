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


def test_turn_contract_has_identity_and_rejects_retroceso():
    contract = TurnContract(input_text="hola", system_slug="generic")
    assert contract.turn_id
    assert contract.created_at
    contract.advance("interpretation")
    try:
        contract.advance("input")
    except ValueError as exc:
        assert "Retroceso" in str(exc)
    else:
        raise AssertionError("expected backward transition to fail")


def test_turn_contract_marks_completion():
    contract = TurnContract(input_text="hola", system_slug="generic")
    contract.advance("narrative_prompt")
    contract.advance("llm")
    contract.mark_llm_output("respuesta")
    contract.mark_persisted()
    assert contract.stage == "persist"
    assert contract.completed_at


def test_turn_contract_serializes_retrieval_metrics():
    contract = TurnContract(input_text="busco una pista", system_slug="generic")
    contract.retrieval_metrics = {
        "fragment_count": 3,
        "layers": {"state": 1, "universal": 2},
    }
    payload = contract.to_dict()
    assert payload["retrieval_metrics"]["fragment_count"] == 3

def test_turn_contract_serializes_causal_metrics():
    contract = TurnContract(input_text="alarma", system_slug="generic")
    contract.causal_metrics = {
        "activations": 2,
        "max_depth": 1,
        "pending_remaining": 3,
    }
    payload = contract.to_dict()
    assert payload["causal_metrics"]["activations"] == 2
    assert payload["causal_metrics"]["max_depth"] == 1


def test_turn_contract_records_proposal_without_losing_existing_state_delta():
    contract = TurnContract(input_text="abro la puerta", system_slug="generic")
    contract.state_delta = {"causalidad": {"activations": 1}}
    contract.record_proposal_result({
        "applied": True,
        "changes": ["fact:puerta_abierta=True"],
        "validation": {"valid": True},
    })
    assert contract.state_delta["causalidad"]["activations"] == 1
    assert contract.state_delta["proposal_changes"] == ["fact:puerta_abierta=True"]
    assert "ProposalExecutor" in contract.provenance


def test_turn_contract_records_rejected_proposal_as_error():
    contract = TurnContract(input_text="intento", system_slug="generic")
    contract.record_proposal_result({
        "applied": False,
        "changes": [],
        "validation": {"valid": False},
    })
    assert "proposal_validation_failed" in contract.errors
    assert "ProposalValidator" in contract.provenance
