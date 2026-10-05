"""Fachada de aplicación independiente de la interfaz.

Esta clase define el límite entre el motor de narración y cualquier UI:
Dear PyGui, Flask, CLI o una futura API. No importa widgets ni framework web.
"""

from __future__ import annotations

from narrator.agents.orchestrator import Orchestrator
from narrator.core.rule_arbiter import RuleArbiter


class NarratorService:
    """API de dominio para una sesión de narración."""

    def __init__(self, config_path: str = "./config/config.yaml"):
        self.orchestrator = Orchestrator(config_path=config_path)
        self.narrator_agent = self.orchestrator.narrator_agent
        self.rule_arbiter = RuleArbiter(builder=self.orchestrator.builder)

    @property
    def state_manager(self):
        return self.orchestrator.state

    def prepare_turn(self, app_state: dict):
        return self.orchestrator.prepare_turn(app_state)

    def persist_turn(self, contract) -> dict:
        """Persiste el resumen técnico de un turno completado."""
        contract.mark_persisted()
        self.orchestrator.state.record_turn(contract.to_dict())
        return contract.to_dict()

    def apply_proposal(self, proposal: dict, app_state: dict | None = None) -> dict:
        return self.orchestrator.validate_and_apply_proposal(
            proposal,
            app_state=app_state,
        )

    def evaluate_causality(self, event_text: str = "", *, next_turn: bool = False) -> dict:
        return self.orchestrator.evaluate_causality(
            event_text,
            next_turn=next_turn,
        )

    def detect_system(self, text: str, app_state: dict) -> str:
        return self.orchestrator.detect_and_set_system(text, app_state)

    def record_event(self, event_type: str, intensity: int = 1) -> None:
        self.orchestrator.record_event(event_type, intensity)

    def world_status(self) -> str:
        return self.orchestrator.get_world_status_text()

    def context_for_phase(self, app_state: dict) -> str:
        return self.orchestrator.get_context_for_phase(app_state)

    def extract_proposal(self, narrative_text: str) -> dict | None:
        return self.narrator_agent.extract_narrative_proposal(narrative_text)

    def clean_narrative(self, narrative_text: str) -> str:
        return self.narrator_agent.strip_system_tags(narrative_text)

    def resolve_roll(
        self,
        *,
        action_text: str,
        character: dict,
        system_slug: str,
        rolls: list[int],
        sides: int,
    ) -> dict | None:
        return self.rule_arbiter.resolve(
            action_text=action_text,
            character=character,
            system_slug=system_slug,
            rolls=rolls,
            sides=sides,
        )
