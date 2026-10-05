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
