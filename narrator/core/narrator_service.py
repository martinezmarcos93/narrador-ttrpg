"""Fachada de aplicación independiente de la interfaz.

Esta clase define el límite entre el motor de narración y cualquier UI:
Dear PyGui, Flask, CLI o una futura API. No importa widgets ni framework web.
"""

from __future__ import annotations

from pathlib import Path

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

    def apply_proposal_with_fallback(self, proposal: dict, app_state: dict | None = None) -> dict:
        """Aplica la propuesta o degrada explícitamente a narración-only."""
        result = self.apply_proposal(proposal, app_state=app_state)
        if result.get("applied"):
            result["fallback"] = {"mode": "stateful", "executed": True}
        else:
            result["fallback"] = {
                "mode": "narration_only",
                "executed": False,
                "reason": "invalid_or_rejected_proposal",
            }
        return result

    @staticmethod
    def build_character_changes(character_data: dict | None) -> list[dict]:
        """Convierte JSON legacy en cambios de propuesta sin ejecutar nada."""
        if not isinstance(character_data, dict):
            return []
        return [
            {"field": str(field), "value": value, "reason": "json legacy"}
            for field, value in character_data.items()
        ]

    @classmethod
    def compose_postprocessing_proposal(
        cls, *, narrative_proposal: dict | None = None, character_data: dict | None = None,
        mutations: list | None = None, new_entities: list | None = None,
        include_entities: bool = False,
    ) -> dict:
        """Compone todas las salidas estructuradas del LLM en una sola propuesta."""
        proposal = dict(narrative_proposal) if isinstance(narrative_proposal, dict) else {}
        if not proposal.get("character_changes"):
            legacy_changes = list(mutations or []) or cls.build_character_changes(character_data)
            if legacy_changes:
                proposal["character_changes"] = legacy_changes
        if include_entities:
            for tipo, data in new_entities or []:
                if not isinstance(data, dict):
                    continue
                key = str(data.get("nombre", data.get("name", ""))).strip().lower()
                field = "npcs" if tipo == "npc" else "locations" if tipo in {"location", "locacion"} else None
                if not key or field is None:
                    continue
                existing = proposal.get(field) or []
                if not any(isinstance(item, dict) and str(item.get("nombre", item.get("name", ""))).strip().lower() == key for item in existing):
                    proposal[field] = [*existing, data]
        return proposal

    def apply_character_snapshot(self, character_data: dict, app_state: dict) -> dict:
        """Convierte una salida estructurada de personaje en una propuesta validable."""
        changes = self.build_character_changes(character_data)
        if not changes:
            return {"applied": False, "changes": [], "validation": {"valid": False}}
        return self.apply_proposal({"character_changes": changes}, app_state=app_state)
    def apply_world_advances(self, advances: list[dict]) -> list[str]:
        return self.orchestrator.apply_world_advances(advances)

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

    def resolve_roll_with_costs(
        self,
        *,
        action_text: str,
        app_state: dict,
        rolls: list[int],
        sides: int,
    ) -> dict | None:
        """Resuelve la tirada y aplica sus costos (p. ej. Fuerza de Voluntad)
        como propuesta validada; la UI nunca muta la ficha directamente."""
        result = self.resolve_roll(
            action_text=action_text,
            character=app_state.get("character") or {},
            system_slug=app_state.get("system_slug", "generic"),
            rolls=rolls,
            sides=sides,
        )
        if result and result.get("costos"):
            applied = self.apply_proposal(
                {"character_changes": [dict(c) for c in result["costos"]]},
                app_state=app_state,
            )
            result["costos_aplicados"] = bool(applied.get("applied"))
        return result

    def suggest_roll(self, action_text: str, app_state: dict) -> dict | None:
        return self.rule_arbiter.suggest_roll(
            action_text,
            app_state.get("character") or {},
            app_state.get("system_slug", "generic"),
        )

    def run_turn(self, app_state: dict, player_text: str, llm, *, max_tokens: int = 600,
                 history: int = 8) -> dict:
        """Turno completo sin interfaz: contrato → LLM → propuesta → fugas → persistencia.

        Lo usan la API web y los scripts headless. ``llm`` expone ``chat(messages,
        max_tokens)``. Devuelve el texto limpio y el resultado trazable del turno.
        """
        from time import perf_counter

        from narrator.core import secrets

        started = perf_counter()
        app_state.setdefault("messages", []).append({"role": "user", "content": player_text})
        contract = self.prepare_turn(app_state)
        recent = [m for m in app_state["messages"] if m.get("role") in {"user", "assistant"}]
        messages = [{"role": "system", "content": contract.narrative_prompt}, *recent[-history:]]
        raw = llm.chat(messages, max_tokens=max_tokens) or ""
        contract.mark_llm_output(raw)

        agent = self.narrator_agent
        proposal = agent.extract_narrative_proposal(raw)
        mutations = [] if proposal and proposal.get("character_changes") else (
            agent.extract_state_mutations(raw))
        composed = self.compose_postprocessing_proposal(
            narrative_proposal=proposal, mutations=mutations,
            new_entities=agent.extract_new_entities(raw), include_entities=True,
        )
        proposal_result = None
        if composed:
            proposal_result = self.apply_proposal_with_fallback(composed, app_state=app_state)
            contract.record_proposal_result(proposal_result)
        _, echoed = agent.strip_context_echo(raw)
        if echoed:
            contract.record_error("context_echo")
        text = agent.strip_system_tags(raw)
        leaks = secrets.find_leaks(text, self.state_manager)
        if leaks:
            contract.record_error(f"knowledge_leak:{','.join(leaks)}")
        app_state["messages"].append({"role": "assistant", "content": text})
        contract.state_delta["latency_ms"] = round((perf_counter() - started) * 1000, 1)
        persisted = self.persist_turn(contract)
        return {
            "text": text,
            "intent": contract.intent,
            "proposal": composed or None,
            "proposal_result": proposal_result,
            "leaks": leaks,
            "context_echo": echoed,
            "contract": persisted,
        }

    # ── Consultas y servicios para la UI ──────────────────────
    # La UI no debe tocar orchestrator.state/retriever/builder directamente:
    # todo acceso pasa por estos métodos (ver docs/architecture/SERVICE-BOUNDARY.md).

    @property
    def vault_path(self) -> Path:
        return Path(self.orchestrator.retriever.vault_path)

    @property
    def vault_template_path(self) -> Path:
        from narrator import resolve_path

        cfg = self.orchestrator.config.get("vault", {}) or {}
        return Path(resolve_path(cfg.get("template_path", "data/vault_template")))

    @property
    def live_vault_updates(self) -> bool:
        return bool((self.orchestrator.config.get("vault", {}) or {}).get("live_updates", True))

    @property
    def sessions_dir(self) -> Path:
        return self.vault_path / "Sesiones"

    def system_data(self, system_slug: str) -> dict:
        return self.orchestrator.builder.load_system(system_slug)

    def character_sheet_schema(self, system_slug: str) -> dict:
        return self.system_data(system_slug).get("character_sheet_schema") or {}

    def clocks_summary(self) -> str:
        return self.orchestrator.state.get_clocks_summary()

    def fronts_with_clocks(self) -> list:
        return self.orchestrator.retriever.get_fronts_with_clocks()

    def scenes_status(self) -> str:
        return self.orchestrator.scenes.get_status_summary()

    def reset_session_pacing(self) -> None:
        self.orchestrator.pacing_agent.reset_session()

    def invalidate_retrieval_cache(self) -> None:
        self.orchestrator.retriever.invalidate_cache()

    def create_world_agent(self, llm):
        from narrator.agents.world_agent import WorldAgent

        return WorldAgent(
            llm=llm,
            retriever=self.orchestrator.retriever,
            state=self.orchestrator.state,
        )

    def create_extractor(self, llm):
        from narrator.agents.extractor_agent import ExtractorAgent

        return ExtractorAgent(llm=llm, builder=self.orchestrator.builder)
