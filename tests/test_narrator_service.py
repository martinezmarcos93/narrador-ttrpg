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


def test_service_world_advances_delegate_to_orchestrator():
    from narrator.core.narrator_service import NarratorService

    service = NarratorService.__new__(NarratorService)

    class StubOrchestrator:
        def apply_world_advances(self, advances):
            return [item["nombre"] for item in advances]

    service.orchestrator = StubOrchestrator()
    assert service.apply_world_advances([{"nombre": "Culto", "ticks": 2}]) == ["Culto"]


def test_roll_costs_are_applied_through_proposal():
    service = NarratorService.__new__(NarratorService)
    calls = {}

    class _Arbiter:
        def resolve(self, **kwargs):
            return {"detalle": "ok", "banda": "7-9", "costos": [
                {"field": "fuerza_voluntad_temp", "delta": -1}]}

    service.rule_arbiter = _Arbiter()
    service.apply_proposal = lambda proposal, app_state=None: calls.setdefault(
        "proposal", proposal) and {"applied": True}
    result = service.resolve_roll_with_costs(
        action_text="gasto fuerza de voluntad", app_state={"character": {}}, rolls=[5], sides=10,
    )
    assert calls["proposal"] == {"character_changes": [{"field": "fuerza_voluntad_temp", "delta": -1}]}
    assert result["costos_aplicados"] is True


def test_run_turn_end_to_end_with_fake_llm(tmp_path, monkeypatch):
    from pathlib import Path

    from narrator.core import secrets

    root = Path(__file__).resolve().parent.parent
    monkeypatch.setattr("narrator.core.embedder.Embedder.is_available", lambda self: False)
    config = tmp_path / "config.yaml"
    config.write_text(
        f"systems_path: {root / 'data' / 'systems'}\n"
        f"vault:\n  path: {tmp_path / 'vault'}\n"
        f"cerebro:\n  path: {tmp_path / 'cerebro'}\n"
        f"estado:\n  path: {tmp_path / 'estado.yaml'}\n",
        encoding="utf-8",
    )
    service = NarratorService(config_path=str(config))
    state = service.state_manager
    state.data["escena_actual"]["npcs_presentes"] = ["Valerius"]
    secrets.add_secret(state, "s1", tema="El anillo", verdad="Valerius es un Tremere infiltrado en la corte",
                       pistas=["un sello hermético en el anillo", "tiza en sus zapatos"],
                       sobre_tipo="npc", sobre_nombre="Valerius")

    class _LLM:
        def chat(self, messages, max_tokens=0):
            assert messages[0]["role"] == "system"
            return ("<think>razono</think>Notás un sello hermético en el anillo.\n"
                    "```json-proposal\n{\"events\": [\"Lucía ve el anillo\"], "
                    "\"discoveries\": [{\"secret\": \"s1\"}]}\n```")

    app_state = {"system_slug": "vtm_v20", "messages": []}
    result = service.run_turn(app_state, "Miro el anillo de Valerius", _LLM())
    assert result["text"] == "Notás un sello hermético en el anillo."
    assert result["proposal_result"]["applied"]
    assert result["leaks"] == []
    assert state.data["secretos"]["s1"]["descubiertas"]["jugador"] == 1
    assert result["contract"]["stage"] == "persist"
    assert state.get_recent_turns(1)

    class _Leaky:
        def chat(self, messages, max_tokens=0):
            return "Sabés que Valerius es un Tremere infiltrado en la corte."

    leaky = service.run_turn(app_state, "Pienso", _Leaky())
    assert leaky["leaks"] == ["s1"]
    assert any(e.startswith("knowledge_leak") for e in leaky["contract"]["errors"])
