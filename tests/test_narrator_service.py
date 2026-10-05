from narrator.core.narrator_service import NarratorService


def test_service_exposes_domain_boundary():
    service = NarratorService.__new__(NarratorService)
    service.orchestrator = object()
    service.narrator_agent = object()
    service.rule_arbiter = object()
    assert hasattr(service, "prepare_turn")
    assert hasattr(service, "apply_proposal")
    assert hasattr(service, "evaluate_causality")
    assert hasattr(service, "resolve_roll")


def test_service_reuses_orchestrator_narrator_agent():
    service = NarratorService.__new__(NarratorService)
    agent = object()
    service.orchestrator = type("OrchestratorStub", (), {"narrator_agent": agent})()
    service.narrator_agent = service.orchestrator.narrator_agent
    assert service.narrator_agent is agent


def test_service_exposes_prepare_turn_without_ui_dependency():
    from narrator.core.narrator_service import NarratorService
    service = NarratorService.__new__(NarratorService)

    class _FakeOrchestrator:
        def prepare_turn(self, state):
            return ("prepared", state)

        def record_event(self, event_type, intensity):
            self.last_event = (event_type, intensity)

        def get_world_status_text(self):
            return "world"

    service.orchestrator = _FakeOrchestrator()
    assert service.prepare_turn({"messages": []}) == ("prepared", {"messages": []})
    service.record_event("combate", 2)
    assert service.orchestrator.last_event == ("combate", 2)
    assert service.world_status() == "world"


def test_service_persists_completed_turn_without_ui_dependency():
    service = NarratorService.__new__(NarratorService)

    class _State:
        def record_turn(self, payload):
            self.payload = payload

    class _FakeOrchestrator:
        def __init__(self):
            self.state = _State()

    service.orchestrator = _FakeOrchestrator()

    class _Contract:
        def __init__(self):
            self.persisted = False
        def mark_persisted(self):
            self.persisted = True
        def to_dict(self):
            return {"stage": "persist"}

    contract = _Contract()
    result = service.persist_turn(contract)
    assert contract.persisted is True
    assert result["stage"] == "persist"
    assert service.orchestrator.state.payload == {"stage": "persist"}


def test_service_character_snapshot_is_validated_as_proposal():
    service = NarratorService.__new__(NarratorService)

    class _Orchestrator:
        def validate_and_apply_proposal(self, proposal, app_state=None):
            self.proposal = proposal
            self.state = app_state
            return {"applied": True, "changes": ["character:hp"], "validation": {"valid": True}}

    service.orchestrator = _Orchestrator()
    result = service.apply_character_snapshot({"hp": 7}, {"character": {"hp": 10}})
    assert result["applied"] is True
    assert service.orchestrator.proposal["character_changes"][0]["field"] == "hp"
    assert service.orchestrator.proposal["character_changes"][0]["value"] == 7


def test_service_composes_structured_proposal_without_duplicate_legacy_character_changes():
    proposal = NarratorService.compose_postprocessing_proposal(
        narrative_proposal={"character_changes": [{"field": "hp", "value": 8}]},
        character_data={"hp": 4},
        mutations=[{"field": "hp", "value": 3}],
    )
    assert proposal["character_changes"] == [{"field": "hp", "value": 8}]


def test_service_composes_entities_and_deduplicates_structured_entities():
    proposal = NarratorService.compose_postprocessing_proposal(
        narrative_proposal={"npcs": [{"nombre": "El Custodio"}]},
        new_entities=[
            ("npc", {"nombre": "El Custodio"}),
            ("npc", {"nombre": "La Testigo"}),
            ("location", {"nombre": "Cripta"}),
        ],
        include_entities=True,
    )
    assert [item["nombre"] for item in proposal["npcs"]] == ["El Custodio", "La Testigo"]
    assert proposal["locations"] == [{"nombre": "Cripta"}]


def test_service_uses_legacy_character_json_only_when_no_structured_character_changes():
    proposal = NarratorService.compose_postprocessing_proposal(
        character_data={"hp": 7, "fuerza": 3},
        mutations=[],
    )
    assert proposal["character_changes"] == [
        {"field": "hp", "value": 7, "reason": "json legacy"},
        {"field": "fuerza", "value": 3, "reason": "json legacy"},
    ]
