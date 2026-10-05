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
