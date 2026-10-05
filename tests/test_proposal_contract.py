from narrator.core.continuity_validator import ContinuityValidator
from narrator.core.proposal_contract import NarrativeProposal, ProposalValidator
from narrator.core.state_manager import StateManager


def test_proposal_contract_rejects_unknown_keys():
    try:
        NarrativeProposal.from_dict({"inventado": True})
    except ValueError as exc:
        assert "no permitidas" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_proposal_validator_rejects_conflicting_fact(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.set_known_fact("puerta", "cerrada")
    proposal = NarrativeProposal.from_dict({
        "facts": {"puerta": "abierta"},
        "character_changes": [{"field": "hp", "delta": -2}],
        "clock_changes": [{"name": "culto", "delta": 1}],
    })
    report = ProposalValidator(ContinuityValidator(state)).validate(proposal)
    assert not report.valid
    assert any(issue.code == "fact_conflict" for issue in report.errors)


def test_proposal_contract_roundtrip():
    proposal = NarrativeProposal.from_dict({
        "events": ["El grupo entra"],
        "npc_presence": {"Guardia": True},
        "consequences": [{"text": "Llegarán refuerzos"}],
    })
    restored = NarrativeProposal.from_dict(proposal.to_dict())
    assert restored.events == ["El grupo entra"]
    assert restored.npc_presence == {"Guardia": True}
