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


def test_narrator_extracts_and_hides_structured_proposal():
    from narrator.agents.narrator_agent import NarratorAgent

    agent = NarratorAgent()
    text = "La puerta se abre.\n```json-proposal\n{\"events\":[\"El grupo abrió la puerta\"],\"facts\":{\"puerta_abierta\":true}}\n```\n"
    proposal = agent.extract_narrative_proposal(text)
    assert proposal["facts"]["puerta_abierta"] is True
    visible = agent.strip_system_tags(text)
    assert "json-proposal" not in visible
    assert "La puerta se abre." in visible


def test_proposal_contract_roundtrip_entities():
    proposal = NarrativeProposal.from_dict({
        "npcs": [{"nombre": "El Vigía", "rol": "guardián", "amenaza": "media"}],
        "locations": [{"nombre": "Cripta del Norte", "distrito": "Barrio Viejo"}],
    })
    restored = NarrativeProposal.from_dict(proposal.to_dict())
    assert restored.npcs[0]["nombre"] == "El Vigía"
    assert restored.locations[0]["nombre"] == "Cripta del Norte"


def test_proposal_validator_rejects_unnamed_entities(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    proposal = NarrativeProposal.from_dict({
        "npcs": [{}],
        "locations": [{"distrito": "Barrio Viejo"}],
    })
    report = ProposalValidator(ContinuityValidator(state)).validate(proposal)
    assert not report.valid
    assert any(issue.code == "invalid_npc" for issue in report.errors)
    assert any(issue.code == "invalid_location" for issue in report.errors)


def test_proposal_accepts_chained_causal_effects():
    proposal = NarrativeProposal.from_dict({
        "consequences": [{
            "text": "Los guardias reciben la alarma",
            "trigger": "alarma",
            "effects": [
                {"type": "event", "text": "guardias movilizados"},
                {
                    "type": "queue_consequence",
                    "consequence": "Las puertas se cierran",
                    "trigger": "guardias movilizados",
                    "effects": [
                        {"type": "player_fact", "key": "doors_closed", "value": True},
                    ],
                },
            ],
        }]
    })
    report = ProposalValidator(ContinuityValidator()).validate(proposal)
    assert report.valid


def test_proposal_rejects_unknown_causal_effect():
    proposal = NarrativeProposal.from_dict({
        "consequences": [{
            "text": "Cambio",
            "effects": [{"type": "execute_python", "code": "print(1)"}],
        }]
    })
    report = ProposalValidator(ContinuityValidator()).validate(proposal)
    assert not report.valid
    assert any(issue.code == "invalid_causal_effect" for issue in report.issues)


def test_proposal_rejects_invalid_relation_strength():
    proposal = NarrativeProposal.from_dict({
        "consequences": [{
            "text": "Cambio social",
            "effects": [{
                "type": "relation",
                "source": "A",
                "target": "B",
                "relation": "hostilidad",
                "strength": 101,
            }],
        }]
    })
    report = ProposalValidator(ContinuityValidator()).validate(proposal)
    assert not report.valid
    assert any(issue.code == "invalid_relation_strength" for issue in report.issues)


def test_proposal_rejects_non_integer_front_delta():
    proposal = NarrativeProposal.from_dict({
        "consequences": [{
            "text": "Cambio de frente",
            "effects": [{
                "type": "front_clock_delta",
                "name": "Culto",
                "delta": "mucho",
            }],
        }]
    })
    report = ProposalValidator(ContinuityValidator()).validate(proposal)
    assert not report.valid
    assert any(issue.code == "invalid_front_clock_delta" for issue in report.issues)

def test_proposal_rejects_unknown_front_when_contract_is_configured():
    proposal = NarrativeProposal.from_dict({
        "consequences": [{
            "text": "Cambio",
            "effects": [{
                "type": "front_clock_delta",
                "name": "Frente Inventado",
                "delta": 1,
            }],
        }]
    })
    report = ProposalValidator(
        ContinuityValidator(),
        allowed_fronts={"Culto"},
    ).validate(proposal)
    assert not report.valid
    assert any(issue.code == "unknown_front" for issue in report.issues)


def test_proposal_validator_rejects_unknown_clock_change(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    proposal = NarrativeProposal.from_dict({
        "clock_changes": [{"name": "inexistente", "delta": 1}],
    })
    report = ProposalValidator(ContinuityValidator(state)).validate(proposal)
    assert not report.valid
    assert any(issue.code == "unknown_clock" for issue in report.errors)


def test_proposal_validator_rejects_clock_overflow(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    state.add_clock("alarma", segments=3)
    state.data["relojes"]["alarma"]["llenos"] = 3
    proposal = NarrativeProposal.from_dict({
        "clock_changes": [{"name": "alarma", "delta": 1}],
    })
    report = ProposalValidator(ContinuityValidator(state)).validate(proposal)
    assert not report.valid
    assert any(issue.code == "clock_out_of_bounds" for issue in report.errors)


def test_proposal_contract_rejects_wrong_container_types():
    for payload in (
        {"facts": []},
        {"events": "evento"},
        {"npc_presence": {"Guardia": "true"}},
        {"npcs": ["no es objeto"]},
        {"clock_changes": {"name": "alarma", "delta": 1}},
    ):
        try:
            NarrativeProposal.from_dict(payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {payload!r}")


def test_proposal_validator_passes_entities_to_continuity(tmp_path):
    state = StateManager(str(tmp_path / "estado.yaml"))
    proposal = NarrativeProposal.from_dict({
        "npcs": [{"nombre": "El Vigía"}],
        "npc_presence": {"El Vigía": True},
        "consequences": [{
            "text": "El Vigía da la alarma",
            "trigger": "alarma",
            "effects": [{
                "type": "npc_presence",
                "name": "El Vigía",
                "present": True,
            }],
        }],
    })
    report = ProposalValidator(ContinuityValidator(state)).validate(proposal)
    assert report.valid
