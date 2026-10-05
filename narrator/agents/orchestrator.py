"""
Orchestrator — coordina agentes y construye el contexto correcto para cada llamada al LLM.
Es Python puro: no hace llamadas al LLM, solo decide QUÉ contexto armar y QUIÉN habla.
"""

import yaml
from narrator.logger import logger
from narrator.core.system_pack import SystemPack
from narrator.core.knowledge_router import KnowledgeRouter
from pathlib import Path
from narrator import resolve_path
from narrator.core import mention_detector
from narrator.core.prompt_builder import PromptBuilder
from narrator.core.retriever import VaultRetriever
from narrator.core.scene_manager import SceneManager
from narrator.core.state_manager import StateManager
from narrator.core.turn_contract import TurnContract
from narrator.core.theory_engine import MasterMoveEngine, PacingToneAgent, WorldSimulationEngine, InvestigationEngine

_THEORY_ENGINE_PATH = Path(__file__).parent.parent / "core" / "theory_engine"


class Orchestrator:
    def __init__(self, config_path: str = "./config/config.yaml"):
        self.config = self._load_config(config_path)

        # Rutas del config ancladas a la raíz del proyecto (no al CWD)
        systems_path = str(resolve_path(self.config.get("systems_path", "data/systems")))
        vault_path = str(resolve_path(self.config.get("vault", {}).get("path", "vault")))
        brain_cfg = self.config.get("cerebro", {}) or {}
        brain_path = str(resolve_path(brain_cfg.get("path", "cerebro")))
        brain_embedding_model = brain_cfg.get("embedding_model", "bge-m3")
        state_path = str(resolve_path(self.config.get("estado", {}).get("path", "estado_campana.yaml")))

        self.builder = PromptBuilder(systems_path=systems_path)
        self.retriever = VaultRetriever(
            vault_path=vault_path,
            brain_path=brain_path,
            brain_embedding_model=brain_embedding_model,
        )
        self.state = StateManager(state_path=state_path)
        self.state.load()
        self.scenes = SceneManager(retriever=self.retriever, state=self.state)

        self.master_moves = MasterMoveEngine(config_path=_THEORY_ENGINE_PATH)
        self.pacing_agent = PacingToneAgent(config_path=_THEORY_ENGINE_PATH)
        self.world_sim = WorldSimulationEngine(
            config_path=_THEORY_ENGINE_PATH,
            vault_path=Path(vault_path),
        )
        self.investigation = InvestigationEngine(
            config_path=_THEORY_ENGINE_PATH,
            vault_path=Path(vault_path),
        )
        self._investigation_quiet_turns: int = 0
        # Fronts reactivos (C3): frente cuyo reloj se llenó en vivo y debe
        # interrumpir la escena en el próximo turno del narrador.
        self._pending_interruption: str = ""
        self.knowledge_router = KnowledgeRouter(self.retriever)
        self._last_retrieved_context = ""

    def _load_config(self, path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            return {}

    # ── Theory engine ─────────────────────────────────────────
    def get_world_status_text(self) -> str:
        """Resumen del WorldSimulationEngine para el system prompt."""
        status = self.world_sim.get_world_status()
        lines = []
        critical = status.get("critical_fronts", {})
        if critical:
            lines.append("Frentes críticos: " + ", ".join(
                f"{n} (etapa {s})" for n, s in critical.items()
            ))
        rep = status.get("reputation", {})
        if rep:
            lines.append("Reputación: " + ", ".join(
                f"{f}: {v:+d}" for f, v in rep.items()
            ))
        events = status.get("recent_events", [])
        if events:
            lines.append("Eventos recientes:\n" + "\n".join(f"  - {e}" for e in events[-3:]))
        return "\n".join(lines)

    def get_investigation_hint(self, app_state: dict) -> str:
        """
        Aplica la Regla de los 3 indicios.
        Devuelve una instrucción para el narrador si los jugadores llevan
        varios turnos sin avanzar en un misterio activo; cadena vacía si todo fluye.
        """
        ultimo = app_state.get("ultimo_evento", "dialogo")
        if ultimo in ("exploracion", "dialogo"):
            self._investigation_quiet_turns += 1
        else:
            self._investigation_quiet_turns = 0

        context = {"quiet_turns": self._investigation_quiet_turns}
        blockade = self.investigation.check_for_blockade(context)
        if not blockade:
            summary = self.investigation.get_active_mysteries_summary()
            return f"Misterios activos:\n{summary}" if summary else ""

        mystery_id = blockade["mystery_id"]
        stall = self.investigation.resolve_stall(mystery_id)
        self._investigation_quiet_turns = 0  # reset tras sugerir pista
        return (
            f"REGLA DE LOS 3 INDICIOS — los jugadores llevan varios turnos sin avanzar.\n"
            f"Pista sugerida para '{mystery_id}': {stall.get('description', '')}\n"
            f"Instrucción: {stall.get('instruction', '')}"
        )

    def record_event(self, event_type: str, intensity: int = 1) -> None:
        """Registra un evento de sesión (llamar desde app.py tras cada turno)."""
        self.pacing_agent.update_event_history(event_type, intensity)
        self._react_fronts(event_type, intensity)

    def _react_fronts(self, event_type: str, intensity: int) -> None:
        """Fronts reactivos (C3): las acciones del jugador aceleran en vivo
        los relojes de los frentes sensibles a ese tipo de evento
        (frontmatter ``reactivo_a``). Reloj lleno → interrupción forzosa."""
        try:
            fronts = self.retriever.get_by_type("frente")
        except Exception as e:
            logger.error(f"Fronts reactivos: error leyendo frentes: {e}", exc_info=True)
            return
        ticks = 2 if intensity >= 3 else 1
        for front in fronts:
            meta = front.get("meta", {})
            nombre = meta.get("nombre", "")
            reactivo = meta.get("reactivo_a") or []
            if not nombre or event_type not in reactivo:
                continue
            ya_lleno = self.state.is_clock_full(nombre)
            self.state.add_front(nombre, meta.get("escasez", ""))
            self.state.advance_front_clock(nombre, ticks)
            if not ya_lleno and self.state.is_clock_full(nombre):
                self._pending_interruption = nombre

    def _build_move_context(self, app_state: dict, active_fronts: str, active_npcs: str) -> dict:
        relojes = self.state.data.get("relojes", {})
        relojes_por_estallar = sum(
            1 for c in relojes.values()
            if c.get("llenos", 0) >= c.get("segmentos", 6) - 1
        )
        return {
            # Banda '10+'/'7-9'/'6-' calculada en do_roll (app.py). NO usar
            # last_dice_result: se consume antes de armar el contexto.
            "tirada_resultado": app_state.get("tirada_banda"),
            "tiempo_sin_accion": 0,
            "frente_activo": bool(active_fronts),
            "jugadores_bloqueados": app_state.get("jugadores_bloqueados", False),
            "peligro_inminente": relojes_por_estallar > 0,
            "ultimo_evento": app_state.get("ultimo_evento", "dialogo"),
            "sesion_tiempo_total": self.state.get_session_number(),
            "relojes_por_estallar": relojes_por_estallar,
            "pnj_en_escena": bool(active_npcs),
        }

    # ── Sistema activo ────────────────────────────────────────
    def get_active_system(self, app_state: dict) -> str:
        if app_state.get("system_slug"):
            return app_state["system_slug"]
        return self.config.get("sistema_activo", "generic")

    def detect_and_set_system(self, text: str, app_state: dict) -> str:
        slug = self.builder.detect_system_from_text(text)
        app_state["system_slug"] = slug
        return slug

    # ── Context builders ──────────────────────────────────────
    def _get_last_user_message(self, app_state: dict) -> str:
        messages = app_state.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg["content"]
        return ""

    def _get_last_assistant_message(self, app_state: dict) -> str:
        messages = app_state.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                return msg["content"]
        return ""

    def _get_known_entity_names(self) -> "list[str]":
        """Nombres de NPCs y Locaciones del vault (Fase 8: recall por mención)."""
        names = []
        for tipo in ("npc", "locacion"):
            for item in self.retriever.get_by_type(tipo, max_files=50):
                nombre = item["meta"].get("nombre")
                if nombre:
                    names.append(nombre)
        return names

    def build_narrator_context(self, app_state: dict) -> str:
        system_slug = self.get_active_system(app_state)
        last_user_msg = self._get_last_user_message(app_state)
        # Lorebook (Fase 5): reglas del sistema activo indexadas por keyword,
        # complemento liviano cuando no hay búsqueda semántica disponible.
        lorebook_entries = self.builder.load_system(system_slug).get("lorebook", [])

        # Recuperación unificada: cerebro, sistema, manual y campaña llegan
        # al prompt conservando su procedencia y autoridad relativa.
        brain_query = last_user_msg or "escena, personaje, conflicto, investigación y consecuencias"
        manual_text = app_state.get("manual_text", "")
        system_pack = SystemPack.load(
            system_slug,
            getattr(self.builder, "systems_path", "data/systems"),
        )
        vault_ctx = self.knowledge_router.retrieve(
            brain_query,
            system_pack,
            manual_text=manual_text,
            max_words=700,
        )
        brain_ctx = ""
        self._last_retrieved_context = vault_ctx

        # Recall por mención: complementa el contexto híbrido, pero ya no lo
        # reemplaza. Así el cerebro y los manuales siguen presentes aunque
        # exista una ficha de NPC/locación muy relevante.
        if last_user_msg:
            mentioned = mention_detector.detect_mentions(
                last_user_msg, self._get_known_entity_names()
            )
            if mentioned:
                extra_ctx = self.retriever.get_relevant_context(
                    mentioned[0], max_words=150, lorebook_entries=lorebook_entries
                )
                if extra_ctx and extra_ctx not in vault_ctx:
                    vault_ctx = f"{vault_ctx}\n---\n[CAMPAIGN | mención explícita]\n{extra_ctx}"


        active_npcs = self.retriever.get_active_npcs_summary(max_npcs=6)
        active_fronts = self.retriever.get_active_fronts_summary()
        clocks = self.state.get_clocks_summary()

        pacing_result = self.pacing_agent.tick()
        move_ctx = self._build_move_context(app_state, active_fronts, active_npcs)
        master_move = self.master_moves.select_move(move_ctx)
        world_status = self.get_world_status_text()
        investigation_hint = self.get_investigation_hint(app_state)

        # Escenas (C2): evaluar desbloqueos/jugadas de forma determinística
        scene_events = self.scenes.evaluate(
            player_text=last_user_msg,
            narrator_text=self._get_last_assistant_message(app_state),
        )
        scenes_info = self.scenes.get_prompt_section(scene_events["desbloqueadas"])

        # Fronts reactivos (C3): interrupción forzosa de un reloj llenado en vivo
        forced_event = ""
        if self._pending_interruption:
            forced_event = self._pending_interruption
            self._pending_interruption = ""

        return self.builder.build_narrator_prompt(
            system_slug=system_slug,
            vault_context=vault_ctx,
            brain_context=brain_ctx,
            character=app_state.get("character") or None,
            last_session=self.state.get_last_session_summary(),
            scene_location=self.state.get_location() or "",
            active_npcs=active_npcs,
            active_fronts=active_fronts,
            clocks_summary=clocks,
            pacing_instruction=pacing_result["instruction"],
            master_move=master_move,
            world_status=world_status,
            investigation_hint=investigation_hint,
            mechanical_resolution=app_state.get("resolucion_mecanica", ""),
            scenes_info=scenes_info,
            forced_event=forced_event,
            combat_status=self.state.get_combat_status_text(),
            state_context=self.state.get_turn_context_text(),
        )

    def build_char_creation_context(self, app_state: dict) -> str:
        system_slug = self.get_active_system(app_state)
        manual_text = app_state.get("manual_text", "")
        brain_ctx = self.retriever.get_brain_context(
            f"creación de personaje {system_slug} atributos habilidades arquetipos ventajas desventajas",
            max_words=500,
            system=system_slug,
        )
        return self.builder.build_char_creation_prompt(
            system_slug=system_slug,
            manual_excerpt=manual_text,
            brain_context=brain_ctx,
        )


    # ── Contrato formal de turno ──────────────────────────────
    @staticmethod
    def _infer_intent(text: str) -> tuple[str, str]:
        """Clasificación determinista mínima; no pretende reemplazar al LLM."""
        t = (text or "").strip().lower()
        if not t:
            return "unknown", ""
        if any(k in t for k in ("quiero", "intento", "voy a", "ataco", "investigo", "busco", "hablo", "pregunto", "huyo", "entro", "salgo")):
            return "player_action", "acción declarada por el jugador"
        if any(k in t for k in ("qué pasó", "que paso", "recordame", "recuérdame", "recuerdame")):
            return "information_request", "consulta sobre ficción/estado"
        return "dialogue_or_description", "interacción narrativa sin señal mecánica explícita"

    def prepare_turn(self, app_state: dict) -> TurnContract:
        """Ejecuta las etapas Python del contrato hasta dejar listo el prompt.

        No llama al LLM. La respuesta generativa queda fuera de este método.
        """
        system_slug = self.get_active_system(app_state)
        input_text = self._get_last_user_message(app_state)
        contract = TurnContract(
            input_text=input_text,
            system_slug=system_slug,
            character_snapshot=dict(app_state.get("character") or {}),
        )
        contract.advance("interpretation")
        contract.interpretation = input_text.strip()
        contract.advance("intent")
        contract.intent, intent_reason = self._infer_intent(input_text)
        contract.provenance.append(f"interpretación: {intent_reason}")

        contract.advance("rule_need")
        if app_state.get("resolucion_mecanica"):
            contract.rule_need = "resolver y narrar una tirada ya ejecutada"
        elif app_state.get("pending_roll"):
            contract.rule_need = "hay una tirada pendiente de resolución"
        elif contract.intent == "player_action":
            contract.rule_need = "determinar si la acción requiere resolución mecánica"
        else:
            contract.rule_need = "sin resolución mecánica explícita"

        contract.advance("retrieval")
        prompt = self.build_narrator_context(app_state)
        contract.retrieved_context = self._last_retrieved_context
        contract.state_snapshot = self.state.get_turn_context_text()
        if contract.retrieved_context:
            contract.record_source("KnowledgeRouter")
        contract.record_source("StateManager")

        contract.advance("resolution")
        if app_state.get("resolucion_mecanica"):
            contract.mechanical_resolution = {
                "detalle": app_state.get("resolucion_mecanica", ""),
                "banda": app_state.get("tirada_banda", ""),
            }

        contract.advance("state_update")
        contract.state_delta = dict(app_state.get("turn_state_delta") or {})
        contract.advance("context_selection")
        contract.advance("narrative_prompt")
        contract.narrative_prompt = prompt
        return contract

    # ── Dispatch principal ────────────────────────────────────
    def get_context_for_phase(self, app_state: dict) -> str:
        """
        Punto de entrada principal. Devuelve el system prompt correcto
        según la fase actual de la sesión.
        """
        phase = app_state.get("phase", "idle")
        if phase == "char_creation":
            return self.build_char_creation_context(app_state)
        return self.build_narrator_context(app_state)
