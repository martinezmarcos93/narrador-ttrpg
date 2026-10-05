"""
AI NARRATOR — Motor de Rol con Ollama
======================================
GUI: Dear PyGui  |  Backend: narrator/core/ + narrator/agents/
"""

import dearpygui.dearpygui as dpg
from narrator.logger import logger
import fitz  # PyMuPDF
import requests
import threading
import queue as _queue_mod
import json
import random
import re
from pathlib import Path
from datetime import datetime

from narrator import PROJECT_ROOT, resolve_path
from narrator.core import derived_stats, dice_first_guard
from narrator.core.ideas_inbox import IdeasInbox
from narrator.core.llm_client import LLMClient
from narrator.core.memory_manager import MemoryManager
from narrator.core.session_manager import SessionManager
from narrator.core.sheet_parser import parse_character_sheet
session_manager = SessionManager()
_memory = MemoryManager()

# ── Backend de agentes ────────────────────────────────────
# Carga con fallback: si el package no está listo, usa modo legacy.
try:
    from narrator.agents.extractor_agent import ExtractorAgent
    from narrator.agents.world_agent import WorldAgent
    from narrator.core.narrator_service import NarratorService
    from narrator.core.vault_writer import VaultWriter

    _CONFIG_PATH = str(PROJECT_ROOT / "config" / "config.yaml")
    _narrator_service = NarratorService(config_path=_CONFIG_PATH)
    _orchestrator = _narrator_service.orchestrator
    _narrator_agent = _narrator_service.narrator_agent
    _rule_arbiter = _narrator_service.rule_arbiter
    _vault_writer: "VaultWriter | None" = None
    _AGENT_MODE = True
except Exception as _agent_err:
    _narrator_service = None
    _orchestrator = None
    _narrator_agent = None
    _rule_arbiter = None
    _vault_writer = None
    _AGENT_MODE = False
    print(f"⚠ Modo legacy (sin agentes): {_agent_err}")

# ─────────────────────────────────────────────
#  CONFIGURACIÓN GLOBAL
# ─────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434"
APP_TITLE  = "AI NARRATOR"

# Paleta: acero oscuro + azul metalico + plateado
C_BG          = (8,  12, 18,  255)
C_PANEL       = (13, 18, 28,  255)
C_SURFACE     = (20, 28, 42,  255)
C_BORDER      = (38, 62, 98,  255)
C_GOLD        = (95, 150, 210, 255)   # azul acero (acento principal)
C_GOLD_DIM    = (55, 95,  155, 255)   # acero atenuado
C_RED         = (150, 40, 50,  255)
C_RED_BRIGHT  = (195, 60, 68,  255)
C_TEXT        = (195, 215, 235, 255)
C_TEXT_DIM    = (108, 132, 158, 255)
C_TEXT_DARK   = (52,  72,  98,  255)
C_INPUT_BG    = (10,  14,  22,  255)
C_HOVER       = (26,  44,  68,  255)
C_ACTIVE      = (38,  62,  92,  255)
C_SUCCESS     = (45,  140, 88,  255)
C_DICE_BG     = (16,  24,  38,  255)

_CHAT_WRAP_W = 820   # actualizado en build_gui con el ancho real

_SYSTEM_PROMPT_LEGACY = """
Eres un Narrador de juegos de rol de élite. Experto en Mundo de Tinieblas, D&D, Pathfinder, Call of Cthulhu y sistemas PbtA.

FILOSOFÍA CENTRAL:
- La historia EMERGE de las decisiones de los jugadores, no está pre-escrita
- Nunca hagas railroading
- Cada escena debe tener tensión (física, emocional, psicológica, moral o existencial)
- Los fallos SIEMPRE avanzan la historia con complicaciones interesantes
- El mundo recuerda las acciones: consecuencias persistentes

NARRACIÓN ATMOSFÉRICA:
- Describe usando todos los sentidos: sonido, textura, olor, luz, sensación espacial
- El entorno refleja estados psicológicos
- Muestra, nunca expliques directamente ("Los guardias dejan de sonreír cuando pasa el carruaje del obispo")
- Dosifica información: el misterio parcial es más poderoso que la revelación total

SISTEMA DE RESOLUCIÓN:
Cuando el jugador quiera hacer algo con riesgo:
1. Indicá qué habilidad/atributo aplica según el sistema
2. Indicá qué dados lanzar (ej: "Tirá 1D20 + tu modificador de Destreza")
3. Cuando recibas el resultado, narrá las consecuencias con riqueza cinematográfica
4. En éxito parcial (PbtA 7-9): ofrecé una elección difícil
5. En fallo: avanzá la historia con una complicación, nunca "simplemente fallás"

PERSONAJE:
- La hoja del personaje llega YA CARGADA desde la planilla adjunta del jugador
- NO crees ni modifiques el personaje por tu cuenta; usá los datos provistos
- Si falta un dato de la hoja, preguntale al jugador en vez de inventarlo

TONO: Adaptá el vocabulario al sistema. Respondé en español rioplatense.
"""

# ─────────────────────────────────────────────
#  ESTADO GLOBAL
# ─────────────────────────────────────────────
state = {
    "model": "llama3.2",
    "models": [],
    "messages": [],
    "character": {},
    "manual_text": "",
    "manual_name": "",
    "manual_names": [],       # lista de todos los PDFs cargados (multi-PDF)
    "system_name": "",
    "system_slug": "generic",
    "declared_game": "",      # juego declarado por el jugador en el inicio guiado
    "phase": "idle",
    "pending_roll": None,
    "tirada_sugerida": None,  # (cantidad, caras) extraído de la última respuesta del narrador
    "_dice_rolled_this_turn": False,
    "session_log": [],
    "last_dice_result": None,
    "session_number": 1,
}

state_lock = threading.Lock()

# ─────────────────────────────────────────────
#  COLA THREAD-SAFE PARA ACTUALIZACIONES DE DPG
# ─────────────────────────────────────────────
_ui_queue: "_queue_mod.Queue" = _queue_mod.Queue()

def _ui(fn):
    """Encola una función para ejecutarse en el hilo principal de DPG."""
    _ui_queue.put(fn)

# ─────────────────────────────────────────────
#  SISTEMA DE PROGRESO EN SEGUNDO PLANO
# ─────────────────────────────────────────────
_proc_count = 0

def _proc_start(title: str):
    global _proc_count
    _proc_count = 0
    try:
        dpg.set_value("proc_bar_text", title)
        dpg.set_value("proc_detail_header", title)
        dpg.delete_item("proc_log_area", children_only=True)
        dpg.configure_item("proc_bar_group", show=True)
        dpg.configure_item("proc_detail_window", show=True)
        _relayout()   # la barra ocupa alto: reacomodar para no tapar el input
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)

def _proc_step(msg: str):
    global _proc_count
    _proc_count += 1
    try:
        dpg.set_value("proc_bar_text", f"{msg}")
        dpg.add_text(f"  {msg}", parent="proc_log_area",
                     color=list(C_TEXT_DIM), wrap=420)
        dpg.set_y_scroll("proc_log_area",
                         dpg.get_y_scroll_max("proc_log_area"))
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)

def _proc_done(summary: str):
    try:
        dpg.configure_item("proc_bar_group", show=False)
        dpg.configure_item("proc_detail_window", show=False)
        _relayout()
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
    append_to_chat("system", summary)

# ─────────────────────────────────────────────
#  OLLAMA API
# ─────────────────────────────────────────────
# Movido a narrator.core.llm_client

# ─────────────────────────────────────────────
#  PDF PROCESSING
# ─────────────────────────────────────────────
def extract_pdf_text(path: str, max_chars: int = 12000) -> str | None:
    """Extrae texto del PDF. Devuelve None si falla (no un string de error,
    que antes se trataba como contenido del manual y reportaba éxito)."""
    try:
        doc = fitz.open(path)
        text = ""
        for page in doc:
            text += page.get_text()
            if len(text) > max_chars:
                break
        doc.close()
        return text[:max_chars]
    except Exception as e:
        logger.error(f"Error leyendo PDF {path}: {e}", exc_info=True)
        return None

def detect_system(text: str) -> tuple[str, str]:
    """Detecta el sistema de juego. Devuelve (display_name, slug)."""
    if _AGENT_MODE and _orchestrator:
        slug = _orchestrator.detect_and_set_system(text, state)
        names = {
            "vtm_v20": "Mundo de Tinieblas (Vampiro V20)",
            "dnd_5e": "Dungeons & Dragons 5e",
            "pathfinder_2e": "Pathfinder 2e",
            "coc_7e": "La Llamada de Cthulhu 7e",
            "generic": "Sistema Genérico",
        }
        return names.get(slug, "Sistema Desconocido"), slug

    t = text.lower()
    if any(w in t for w in ["vampiro", "mascarada", "brujah", "toreador", "camarilla", "malkavian"]):
        return "Mundo de Tinieblas (Vampiro V20)", "vtm_v20"
    if any(w in t for w in ["hombre lobo", "garou", "apocalipsis", "tribus"]):
        return "Mundo de Tinieblas (Hombre Lobo)", "vtm_v20"
    if any(w in t for w in ["pathfinder", "golarion", "paizo"]):
        return "Pathfinder 2e", "pathfinder_2e"
    if any(w in t for w in ["dungeon", "d&d", "dungeons", "cleric", "paladin", "tiefling"]):
        return "Dungeons & Dragons 5e", "dnd_5e"
    if any(w in t for w in ["call of cthulhu", "investigador", "cordura", "mythos"]):
        return "La Llamada de Cthulhu 7e", "coc_7e"
    return "Sistema Desconocido", "generic"


def _build_legacy_context() -> str:
    content = _SYSTEM_PROMPT_LEGACY
    if state["manual_text"]:
        content += f"\n\n=== MANUAL: {state['manual_name']} ===\n{state['manual_text'][:6000]}"
    if state["character"]:
        content += f"\n\n=== PERSONAJE ===\n{json.dumps(state['character'], ensure_ascii=False, indent=2)}"
    if state.get("resolucion_mecanica"):
        content += (
            "\n\n=== RESOLUCIÓN MECÁNICA DE LA ÚLTIMA TIRADA ==="
            "\n(Calculada por el sistema. NO la recalcules ni la contradigas; narrá este resultado.)"
            f"\n{state['resolucion_mecanica']}"
        )
    return content

# ─────────────────────────────────────────────
#  DICE ENGINE
# ─────────────────────────────────────────────
DICE_TYPES = [4, 6, 8, 10, 12, 20, 100]  # D100: CoC 7e es percentil

def roll_dice(n: int, sides: int) -> list[int]:
    return [random.randint(1, sides) for _ in range(n)]

def format_roll_result(rolls: list[int], sides: int, modifier: int = 0) -> str:
    total = sum(rolls) + modifier
    rolls_str = " + ".join(str(r) for r in rolls)
    if modifier != 0:
        sign = "+" if modifier > 0 else ""
        return f"[{rolls_str}]{sign}{modifier} = {total}"
    return f"[{rolls_str}] = {total}"

# ─────────────────────────────────────────────
#  EVENT DETECTION (para PacingToneAgent)
# ─────────────────────────────────────────────
_EVENT_KEYWORDS: dict[str, tuple[list[str], int]] = {
    "combate":     (["ataco", "ataca", "disparo", "golpeo", "peleo", "lucho",
                     "combate", "hiero", "mato", "ataque", "corto", "apuñalo"], 2),
    "persecucion": (["huyo", "escapo", "corro", "perseguido", "persigo", "fuga",
                     "intento huir", "intento escapar"], 3),
    "horror":      (["me aterroriza", "me aterra", "horror", "sanidad",
                     "enloquezco", "cordura", "locura"], 3),
    "exploracion": (["investigo", "busco", "examino", "exploro", "inspecciono",
                     "observo", "miro alrededor", "pistas"], 1),
    "descanso":    (["descanso", "duermo", "descansamos", "acampo",
                     "me recupero", "recuperarse", "descansar"], 1),
}

def _detect_event_type(text: str) -> tuple[str, int]:
    """Devuelve (event_type, intensity) a partir del texto del jugador."""
    t = text.lower()
    for event_type, (keywords, intensity) in _EVENT_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return event_type, intensity
    return "dialogo", 1



# ─────────────────────────────────────────────
#  GUI — HELPERS
# ─────────────────────────────────────────────
def add_spacer(h=8):
    dpg.add_spacer(height=h)

def section_label(text, parent=None):
    # OJO: en add_text el texto va como primer posicional (default_value);
    # label= NO se renderiza en mvText.
    kwargs = {"color": list(C_GOLD)}
    if parent:
        kwargs["parent"] = parent
    dpg.add_text(text, **kwargs)

def dim_text(text, parent=None):
    kwargs = {"color": list(C_TEXT_DIM)}
    if parent:
        kwargs["parent"] = parent
    dpg.add_text(text, **kwargs)

# ─────────────────────────────────────────────
#  GUI — CHAT
# ─────────────────────────────────────────────
_streaming_token = ""
_is_streaming = False
_active_turn_contract = None

def append_to_chat(role: str, text: str):
    if role == "user":
        label_color = list(C_GOLD)
        prefix = "[Vos]"
    elif role == "assistant":
        label_color = list(C_GOLD)
        prefix = "[Narrador]"
    else:
        label_color = list(C_TEXT_DIM)
        prefix = "[Sistema]"

    with dpg.group(parent="chat_scroll"):
        dpg.add_text(prefix, color=label_color)
        dpg.add_text(text, color=list(C_TEXT), wrap=_CHAT_WRAP_W)
        dpg.add_separator()
        dpg.add_spacer(height=4, parent="chat_scroll")

    dpg.set_y_scroll("chat_scroll", dpg.get_y_scroll_max("chat_scroll"))

def _add_streaming_group():
    """Crea el grupo de streaming dentro de chat_scroll.
    Debe re-crearse cada vez que se limpia el chat (Nueva sesión)."""
    with dpg.group(tag="streaming_group", show=False, parent="chat_scroll"):
        dpg.add_text("[Narrador]", color=list(C_GOLD))
        dpg.add_text("", tag="streaming_label",
                     color=list(C_TEXT), wrap=_CHAT_WRAP_W)
        dpg.add_separator()

def update_streaming_label(chunk: str):
    global _streaming_token
    _streaming_token += chunk
    display = _streaming_token[-600:] if len(_streaming_token) > 600 else _streaming_token
    _ui(lambda d=display: dpg.set_value("streaming_label", d))

def finish_streaming(full_text: str):
    global _is_streaming, _streaming_token, _active_turn_contract
    _is_streaming = False
    _streaming_token = ""

    # Errores del LLM ([Error LLM...] / [Error de conexión...]) NO van al
    # historial: se muestran como mensaje de sistema y se corta el pipeline.
    if full_text.startswith("[Error") or not full_text.strip():
        msg = full_text if full_text.strip() else "[Error LLM: respuesta vacía del modelo]"

        def _ui_error():
            try:
                dpg.set_value("streaming_label", "")
                dpg.configure_item("streaming_group", show=False)
            except Exception as e:
                logger.error(f"Error ocultando streaming: {e}", exc_info=True)
            append_to_chat("system", f"⚠ {msg}")
            dpg.enable_item("send_btn")
            dpg.enable_item("user_input")

        _ui(_ui_error)
        return

    if _active_turn_contract is not None:
        try:
            _active_turn_contract.mark_llm_output(full_text)
        except Exception as e:
            logger.error(f"Error actualizando contrato de turno: {e}", exc_info=True)

    # Fase 11: extraer entidades/mutaciones del texto CRUDO (con etiquetas
    # técnicas) antes de limpiarlo — el jugador nunca debe ver las etiquetas.
    new_entities: list = []
    mutations: list = []
    narrative_proposal: dict | None = None
    if _narrator_agent:
        new_entities = _narrator_agent.extract_new_entities(full_text)
        mutations = _narrator_agent.extract_state_mutations(full_text)
        narrative_proposal = _narrator_agent.extract_narrative_proposal(full_text)
        if narrative_proposal and narrative_proposal.get("character_changes"):
            # El bloque estructurado es la fuente única para esos cambios;
            # evita aplicar dos veces una misma mutación declarada también con [state:].
            mutations = []
        full_text = _narrator_agent.strip_system_tags(full_text)

    # Procesamiento sin DPG — hilo worker
    with state_lock:
        state["messages"].append({"role": "assistant", "content": full_text})

    is_important = False
    needs_char_refresh = False
    if _narrator_agent:
        is_important = _narrator_agent.is_important_event(full_text)
        char_data = _narrator_agent.extract_character_json(full_text)
        if char_data:
            with state_lock:
                state["character"].update(char_data)
            needs_char_refresh = True
        with state_lock:
            state["tirada_sugerida"] = _narrator_agent.extract_dice_suggestion(full_text)

        if narrative_proposal:
            try:
                proposal_result = _orchestrator.validate_and_apply_proposal(
                    narrative_proposal,
                    app_state=state,
                )
                if not proposal_result.get("applied"):
                    logger.warning(
                        "Propuesta narrativa rechazada: %s",
                        proposal_result.get("validation", {}),
                    )
                elif proposal_result.get("changes"):
                    if _active_turn_contract is not None:
                        _active_turn_contract.state_delta = {
                            "proposal_changes": list(proposal_result["changes"])
                        }
                    is_important = True
            except Exception as e:
                logger.error(f"Error ejecutando propuesta narrativa: {e}", exc_info=True)

        if mutations:
            try:
                proposal_result = _orchestrator.validate_and_apply_proposal(
                    {"character_changes": mutations},
                    app_state=state,
                )
                changelog = list(proposal_result.get("changes", []))
                if not proposal_result.get("applied"):
                    logger.warning(
                        "Propuesta de mutación rechazada: %s",
                        proposal_result.get("validation", {}),
                    )
            except Exception as e:
                changelog = []
                logger.error(f"Error validando propuesta de estado: {e}", exc_info=True)

            if changelog:
                if _active_turn_contract is not None:
                    _active_turn_contract.state_delta = {"character_changes": list(changelog)}
                needs_char_refresh = True
                is_important = True
                ts = datetime.now().strftime("%H:%M")
                with state_lock:
                    state["session_log"].extend(f"[{ts}] Estado: {c}" for c in changelog)

        # Fase 13: solo señala (log), nunca bloquea el turno.
        last_user = next(
            (m["content"] for m in reversed(state["messages"]) if m.get("role") == "user"), ""
        )
        if dice_first_guard.check(last_user, full_text, state.get("_dice_rolled_this_turn", False)):
            logger.error(
                f"dice-first sospechado: el narrador narró un resultado sin tirada previa. "
                f"Jugador: {last_user[:80]!r}"
            )

        if new_entities and _vault_writer:
            for tipo, data in new_entities:
                try:
                    if tipo == "npc":
                        _vault_writer.create_npc(data)
                    else:
                        _vault_writer.create_locacion(data)
                except Exception as e:
                    logger.error(
                        f"Error auto-guardando entidad '{data.get('nombre')}': {e}", exc_info=True
                    )
    else:
        is_important = any(
            w in full_text.lower()
            for w in ["tirada", "dado", "d20", "éxito", "fallo", "consecuencia"]
        )

    if is_important:
        entry = f"[{datetime.now().strftime('%H:%M')}] {full_text[:120]}..."
        with state_lock:
            state["session_log"].append(entry)

    if _vault_writer and _AGENT_MODE:
        last_user = ""
        for m in reversed(state["messages"][:-1]):
            if m.get("role") == "user":
                last_user = m["content"]
                break
        session_n = state.get("session_number", 1)
        threading.Thread(
            target=_vault_writer.on_narrator_response,
            args=(last_user, full_text),
            kwargs={"session_number": session_n, "is_important": is_important},
            daemon=True,
        ).start()

    # Cierre determinista del contrato: persistimos solo el resumen técnico.
    if _active_turn_contract is not None and _orchestrator is not None:
        try:
            _active_turn_contract.mark_persisted()
            _orchestrator.state.record_turn(_active_turn_contract.to_dict())
        except Exception as e:
            logger.error(f"Error persistiendo contrato de turno: {e}", exc_info=True)
            _active_turn_contract.record_error(str(e))

    # Memoria episódica: si se acumuló un lote de turnos fuera de la
    # ventana, resumirlo en background (no bloquea el turno).
    with state_lock:
        messages_snapshot = list(state["messages"])
    if _memory.pending_batch(messages_snapshot):
        threading.Thread(
            target=_memory.summarize_batch,
            args=(messages_snapshot, LLMClient(model=state["model"])),
            daemon=True,
        ).start()

    # Actualizaciones de DPG — encoladas para el hilo principal
    _refresh_char = needs_char_refresh
    _refresh_log = is_important

    def _ui_update():
        try:
            dpg.set_value("streaming_label", "")
            dpg.configure_item("streaming_group", show=False)
        except Exception as e:
            logger.error(f"Error inesperado: {e}", exc_info=True)
        append_to_chat("assistant", full_text)
        if _refresh_char:
            refresh_character_panel()
        if _refresh_log:
            refresh_log()
        refresh_dice_suggestion()
        dpg.enable_item("send_btn")
        dpg.enable_item("user_input")

    _ui(_ui_update)

# ─────────────────────────────────────────────
#  FLUJO DE INICIO GUIADO (juego → manual → planilla)
# ─────────────────────────────────────────────
SETUP_PHASES = ("setup_game", "setup_manual", "setup_sheet")

def start_onboarding():
    """Arranca el flujo guiado de inicio de sesión de juego."""
    state["phase"] = "setup_game"
    append_to_chat(
        "system",
        "¿Qué juego vamos a jugar hoy?\n"
        "Escribí el nombre (ej.: Vampiro V20, D&D 5e, La Llamada de Cthulhu, "
        "Pathfinder 2e) y presioná Enter.",
    )

def _setup_reminder() -> str:
    phase = state.get("phase")
    if phase == "setup_game":
        return "decime qué juego vamos a jugar."
    if phase == "setup_manual":
        return "adjuntá el manual básico en PDF."
    return "adjuntá la planilla de tu personaje en PDF."

def _handle_setup_input(user_text: str):
    """Procesa el texto del jugador durante el inicio guiado (sin LLM)."""
    phase = state.get("phase")
    append_to_chat("user", user_text)
    if phase == "setup_game":
        state["declared_game"] = user_text.strip()
        state["phase"] = "setup_manual"
        append_to_chat(
            "system",
            f"Perfecto: {state['declared_game']}.\n"
            "Ahora adjuntá una copia del manual básico en PDF.",
        )
        dpg.show_item("pdf_dialog")
    elif phase == "setup_manual":
        append_to_chat("system", "Necesito el manual básico en PDF para continuar.")
        dpg.show_item("pdf_dialog")
    else:  # setup_sheet
        append_to_chat("system", "Necesito la planilla de tu personaje en PDF para continuar.")
        dpg.show_item("sheet_dialog")


def send_message(user_text: str = None):
    global _is_streaming, _streaming_token

    if _is_streaming:
        return

    typed = user_text is None
    if user_text is None:
        user_text = dpg.get_value("user_input").strip()

    if not user_text:
        return

    # Durante el inicio guiado no se llama al LLM: el sistema conduce.
    if state.get("phase") in SETUP_PHASES:
        if typed:
            dpg.set_value("user_input", "")
            _handle_setup_input(user_text)
        else:
            # Acciones rápidas / dados durante el setup: recordar el paso.
            append_to_chat("system", f"Primero completemos el inicio: {_setup_reminder()}")
        return

    dpg.set_value("user_input", "")
    dpg.disable_item("send_btn")
    dpg.disable_item("user_input")

    state["_dice_rolled_this_turn"] = bool(state["last_dice_result"])
    if state["last_dice_result"]:
        user_text = f"{user_text}\n\n[RESULTADO DE DADOS: {state['last_dice_result']}]"
        state["last_dice_result"] = None

        # Rule Arbiter: resolver la tirada en Python puro contra la planilla.
        # El contexto es el pedido del narrador + la acción del jugador.
        pending = state.pop("pending_roll", None)
        if pending and _rule_arbiter is not None:
            last_narrator = next(
                (m["content"] for m in reversed(state["messages"])
                 if m.get("role") == "assistant"), "")
            resultado = _rule_arbiter.resolve(
                action_text=f"{last_narrator}\n{user_text}",
                character=state.get("character") or {},
                system_slug=state.get("system_slug", "generic"),
                rolls=pending["rolls"],
                sides=pending["sides"],
            )
            if resultado:
                state["resolucion_mecanica"] = resultado["detalle"]
                state["tirada_banda"] = resultado["banda"]
                append_to_chat("system", f"⚖ {resultado['detalle']}")

    state["messages"].append({"role": "user", "content": user_text})
    append_to_chat("user", user_text)

    if _AGENT_MODE and _orchestrator:
        event_type, intensity = _detect_event_type(user_text)
        state["ultimo_evento"] = event_type
        _orchestrator.record_event(event_type, intensity)

    _is_streaming = True
    _streaming_token = ""
    try:
        # Mover el grupo de streaming al final del chat para que el texto
        # en vivo aparezca debajo del último mensaje, no arriba del historial.
        dpg.move_item("streaming_group", parent="chat_scroll")
        dpg.configure_item("streaming_group", show=True)
        dpg.set_value("streaming_label", "...")
    except Exception as e:
        logger.error(f"Error mostrando el grupo de streaming: {e}", exc_info=True)

    def run():
        # Construcción del contexto EN EL WORKER: lee todo el vault y puede
        # hacer un POST de embeddings a Ollama — antes congelaba la GUI.
        global _active_turn_contract
        if _AGENT_MODE and _orchestrator:
            try:
                contract = _orchestrator.prepare_turn(state)
                _active_turn_contract = contract
                system_content = contract.narrative_prompt
            except Exception as e:
                logger.error(f"Error en contrato de turno, usando modo legacy: {e}", exc_info=True)
                _active_turn_contract = None
                system_content = _build_legacy_context()
        else:
            _active_turn_contract = None
            system_content = _build_legacy_context()

        # Memoria episódica (capa 2): resúmenes de turnos fuera de la ventana.
        summary = _memory.get_summary_text()
        if summary:
            system_content += (
                "\n\nMEMORIA DE LA SESIÓN (hechos de turnos anteriores, ya "
                "resumidos — el historial reciente llega como mensajes):\n"
                f"{summary}"
            )

        with state_lock:
            # Banda y resolución mecánica ya consumidas por el contexto del turno.
            state.pop("tirada_banda", None)
            state.pop("resolucion_mecanica", None)
            # Capa 1: al LLM va solo la ventana reciente, no todo el historial.
            messages_to_send = ([{"role": "system", "content": system_content}]
                                + _memory.get_working_messages(state["messages"]))

        contract = _active_turn_contract
        if contract is not None:
            contract.advance("llm")
        LLMClient(model=state["model"]).stream_chat(messages_to_send, update_streaming_label, finish_streaming)

    threading.Thread(target=run, daemon=True).start()

# ─────────────────────────────────────────────
#  GUI — DICE PANEL
# ─────────────────────────────────────────────
def do_roll(sides: int):
    try:
        n = int(dpg.get_value(f"dice_count_{sides}"))
    except Exception as e:
        n = 1
    n = max(1, min(n, 20))

    rolls = roll_dice(n, sides)
    total = sum(rolls)
    result_str = format_roll_result(rolls, sides)

    state["last_dice_result"] = f"{n}D{sides}: {result_str}"
    # Tirada cruda para el Rule Arbiter: se resuelve mecánicamente al enviarla.
    state["pending_roll"] = {"rolls": rolls, "sides": sides}
    # Banda PbtA-like heurística (fallback si el arbiter no aplica):
    ratio = total / (n * sides)
    state["tirada_banda"] = "10+" if ratio >= 0.8 else ("7-9" if ratio >= 0.5 else "6-")

    color = list(C_RED_BRIGHT) if total == sides * n else (
        list(C_GOLD) if total >= sides * n * 0.75 else list(C_TEXT)
    )
    dpg.set_value("dice_result_main", f"{n}D{sides}")
    dpg.set_value("dice_result_total", str(total))
    dpg.configure_item("dice_result_total", color=color)
    dpg.set_value("dice_result_detail", result_str)

    entry = f"[{datetime.now().strftime('%H:%M')}] {n}D{sides} → {result_str}"
    state["session_log"].append(entry)
    refresh_log()

    if _vault_writer:
        _vault_writer.log_dice_roll(f"{n}D{sides} → {result_str}")

def _use_suggested_roll():
    """Precarga cantidad/tipo de dado desde la sugerencia del narrador (Fase 2)."""
    sugerida = state.get("tirada_sugerida")
    if not sugerida:
        return
    n, sides = sugerida
    try:
        dpg.set_value(f"dice_count_{sides}", n)
    except Exception as e:
        logger.error(f"Error precargando tirada sugerida: {e}", exc_info=True)
        return
    state["tirada_sugerida"] = None
    refresh_dice_suggestion()

def refresh_dice_suggestion():
    """Muestra/oculta la sugerencia de tirada del narrador en el panel de dados."""
    sugerida = state.get("tirada_sugerida")
    try:
        if sugerida:
            n, sides = sugerida
            dpg.set_value("dice_suggestion_text", f"El narrador sugiere: {n}D{sides}")
            dpg.configure_item("dice_suggestion_row", show=True)
        else:
            dpg.configure_item("dice_suggestion_row", show=False)
    except Exception as e:
        logger.error(f"Error refrescando sugerencia de tirada: {e}", exc_info=True)

def build_dice_panel(parent):
    section_label("DADOS", parent=parent)
    dpg.add_spacer(height=6, parent=parent)

    with dpg.group(tag="dice_suggestion_row", show=False, parent=parent):
        dpg.add_text("", tag="dice_suggestion_text", color=list(C_GOLD), wrap=160)
        dpg.add_button(label="Usar sugerida", width=170, callback=_use_suggested_roll)
        dpg.add_spacer(height=8)

    for sides in DICE_TYPES:
        with dpg.group(horizontal=True, parent=parent):
            dpg.add_input_int(
                tag=f"dice_count_{sides}",
                default_value=1,
                min_value=1,
                max_value=20,
                width=55,
                min_clamped=True,
                max_clamped=True,
            )
            dpg.add_button(
                label=f"D{sides}",
                width=72,
                height=32,
                callback=lambda s, a, u=sides: do_roll(u),
            )
        dpg.add_spacer(height=4, parent=parent)

    dpg.add_spacer(height=10, parent=parent)
    dpg.add_separator(parent=parent)
    dpg.add_spacer(height=8, parent=parent)

    dpg.add_text("Última tirada:", color=list(C_TEXT_DIM), parent=parent)
    dpg.add_text("—", tag="dice_result_main", color=list(C_GOLD_DIM), parent=parent)
    dpg.add_text("—", tag="dice_result_total", color=list(C_TEXT), parent=parent)
    dpg.add_text("", tag="dice_result_detail", color=list(C_TEXT_DIM), wrap=160, parent=parent)

    dpg.add_spacer(height=10, parent=parent)
    dpg.add_button(
        label="Enviar resultado",
        parent=parent,
        width=170,
        callback=lambda: send_message(
            "El resultado de mi tirada fue: " + (state["last_dice_result"] or "ninguna")
        )
    )

# ─────────────────────────────────────────────
#  GUI — CHARACTER SHEET (schema-driven)
# ─────────────────────────────────────────────
def _dots(value, max_val: int = 5) -> str:
    try:
        v = max(0, min(int(value), max_val))
    except (ValueError, TypeError):
        v = 0
    return "●" * v + "○" * (max_val - v)

def _stat(value, formula: dict = None) -> str:
    """Formatea un stat_block. Si el sistema define `stat_modifier_formula` en su
    character_sheet_schema, calcula el modificador vía el DSL (narrator.core.derived_stats);
    si no, muestra el valor crudo (ej. características 1-99 de CoC 7e, que no usan modificador)."""
    try:
        v = int(value)
    except (ValueError, TypeError):
        return str(value)
    if not formula:
        return str(v)
    try:
        mod = derived_stats.evaluate(formula, {"value": v})
    except derived_stats.DerivedStatError:
        return str(v)
    return f"{v} ({'+' if mod >= 0 else ''}{mod})"

def _render_field(label: str, value, display: str, ftype: str, max_val: int, parent: str, stat_formula: dict = None):
    with dpg.group(horizontal=True, parent=parent):
        dpg.add_text(f"{label}:", color=list(C_TEXT_DIM), wrap=72)
        if value is None or value == "":
            dpg.add_text("—", color=list(C_TEXT_DARK))
        elif isinstance(value, list):
            dpg.add_text(", ".join(str(x) for x in value), color=list(C_TEXT), wrap=88)
        elif display == "dots" and ftype == "int":
            dpg.add_text(_dots(value, max_val), color=list(C_GOLD))
        elif display == "stat_block" and ftype == "int":
            dpg.add_text(_stat(value, stat_formula), color=list(C_TEXT))
        else:
            dpg.add_text(str(value), color=list(C_TEXT), wrap=88)

def _render_section(section: dict, char: dict, parent: str, rendered: set, stat_formula: dict = None):
    display = section.get("display", "default")
    dpg.add_text(section.get("name", "").upper(), color=list(C_GOLD_DIM), parent=parent)
    for field in section.get("fields", []):
        key = field.get("key", "")
        rendered.add(key)
        value = char.get(key)
        if value is None:
            continue
        _render_field(
            label=field.get("label", key),
            value=value,
            display=display,
            ftype=field.get("type", "string"),
            max_val=field.get("max", 5),
            parent=parent,
            stat_formula=stat_formula,
        )
    dpg.add_spacer(height=5, parent=parent)

def refresh_character_panel():
    try:
        dpg.delete_item("char_content", children_only=True)
    except Exception as e:
        return

    char = state["character"]
    if not char:
        dpg.add_text("Sin personaje creado.", parent="char_content", color=list(C_TEXT_DIM))
        dpg.add_spacer(height=6, parent="char_content")
        dpg.add_text("Cargá un manual y pedile\nal narrador que te guíe.",
                     parent="char_content", color=list(C_TEXT_DIM), wrap=160)
        return

    # Intentar cargar schema del sistema activo
    schema = None
    if _AGENT_MODE and _orchestrator:
        try:
            sys_data = _orchestrator.builder.load_system(state.get("system_slug", "generic"))
            schema = sys_data.get("character_sheet_schema")
        except Exception as e:
            logger.error(f"Error inesperado: {e}", exc_info=True)

    if not schema:
        # Fallback genérico si no hay schema
        for key, val in char.items():
            with dpg.group(horizontal=False, parent="char_content"):
                dpg.add_text(str(key).replace("_", " ").upper(), color=list(C_GOLD_DIM))
                if isinstance(val, dict):
                    for k2, v2 in val.items():
                        dpg.add_text(f"  {k2}: {v2}", color=list(C_TEXT), wrap=160)
                elif isinstance(val, list):
                    dpg.add_text(", ".join(str(x) for x in val), color=list(C_TEXT), wrap=160)
                else:
                    dpg.add_text(str(val), color=list(C_TEXT), wrap=160)
                add_spacer(4)
        return

    rendered: set = set()
    archetype_key = schema.get("archetype_key", "")
    archetype_val = str(char.get(archetype_key, "")).lower().strip() if archetype_key else ""
    stat_formula = schema.get("stat_modifier_formula")

    # Secciones base
    for section in schema.get("base_sections", []):
        _render_section(section, char, "char_content", rendered, stat_formula)

    # Secciones condicionales según clan/clase/tipo
    if archetype_val:
        cond = schema.get("conditional_sections", {})
        for cond_key, sections in cond.items():
            if cond_key.lower() == archetype_val:
                for section in sections:
                    _render_section(section, char, "char_content", rendered, stat_formula)
                break

    # Extras: campos que el LLM generó fuera del schema
    extras = {k: v for k, v in char.items() if k not in rendered}
    if extras:
        dpg.add_text("OTROS", color=list(C_GOLD_DIM), parent="char_content")
        for key, val in extras.items():
            _render_field(
                label=key.replace("_", " ").title(),
                value=val,
                display="default",
                ftype="string",
                max_val=5,
                parent="char_content",
            )
        dpg.add_spacer(height=4, parent="char_content")

# ─────────────────────────────────────────────
#  GUI — SESSION LOG
# ─────────────────────────────────────────────
def refresh_log():
    try:
        dpg.delete_item("log_content", children_only=True)
        for entry in state["session_log"][-20:]:
            dpg.add_text(entry, parent="log_content", color=list(C_TEXT_DIM), wrap=160)
            dpg.add_spacer(height=2, parent="log_content")
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)

# ─────────────────────────────────────────────
#  GUI — ESTADO (relojes de frentes) — Sprint 3
# ─────────────────────────────────────────────
def _clock_bar(tick: int, max_ticks: int) -> str:
    """Genera una barra ASCII de progreso para el reloj de un frente."""
    filled = min(tick, max_ticks)
    bar = "█" * filled + "░" * (max_ticks - filled)
    return f"[{bar}] {filled}/{max_ticks}"

def _get_ideas_inbox() -> IdeasInbox:
    vault_path = str(_orchestrator.retriever.vault_path) if (_AGENT_MODE and _orchestrator) \
        else str(resolve_path("vault"))
    return IdeasInbox(vault_path=vault_path)

def capture_idea_callback():
    """Anota el último mensaje del jugador como idea suelta (Fase 6)."""
    last_user = next(
        (m["content"] for m in reversed(state["messages"]) if m.get("role") == "user"), ""
    )
    if not last_user:
        append_to_chat("system", "No hay un mensaje reciente para anotar como idea.")
        return
    titulo = last_user.strip()[:60]
    try:
        _get_ideas_inbox().create(titulo, contenido=last_user.strip())
        append_to_chat("system", f"💡 Idea anotada: \"{titulo}\"")
    except Exception as e:
        logger.error(f"Error anotando idea: {e}", exc_info=True)
        append_to_chat("system", "⚠ No se pudo anotar la idea.")
    refresh_estado_panel()

def _promote_idea_callback(idea_path, tipo: str):
    try:
        target = _get_ideas_inbox().promote(idea_path, tipo=tipo)
        append_to_chat("system", f"💡 Idea promovida a {tipo}: {target.stem}")
    except Exception as e:
        logger.error(f"Error promoviendo idea: {e}", exc_info=True)
        append_to_chat("system", "⚠ No se pudo promover la idea.")
    refresh_estado_panel()

def refresh_estado_panel():
    try:
        dpg.delete_item("estado_content", children_only=True)
    except Exception as e:
        return

    # Número de sesión
    dpg.add_text(
        f"Sesión #{state.get('session_number', 1)}",
        parent="estado_content",
        color=list(C_GOLD),
    )
    dpg.add_separator(parent="estado_content")
    dpg.add_spacer(height=4, parent="estado_content")

    # Sistema
    sys_name = state.get("system_name", "") or "—"
    dpg.add_text(f"Sistema:", parent="estado_content", color=list(C_TEXT_DIM))
    dpg.add_text(sys_name, parent="estado_content", color=list(C_TEXT), wrap=155)
    dpg.add_spacer(height=6, parent="estado_content")

    # Relojes de frentes
    if _AGENT_MODE and _orchestrator:
        try:
            fronts = _orchestrator.retriever.get_fronts_with_clocks()
        except Exception as e:
            fronts = []
    else:
        fronts = []

    if fronts:
        dpg.add_text("FRENTES:", parent="estado_content", color=list(C_GOLD_DIM))
        dpg.add_spacer(height=4, parent="estado_content")
        for f in fronts:
            dpg.add_text(f["nombre"], parent="estado_content", color=list(C_TEXT), wrap=155)
            bar = _clock_bar(f["tick"], f["max"])
            estado_color = list(C_RED_BRIGHT) if f["estado"] != "latente" else list(C_TEXT_DIM)
            dpg.add_text(bar, parent="estado_content", color=estado_color)
            if f.get("escasez"):
                dpg.add_text(f"  {f['escasez']}", parent="estado_content",
                             color=list(C_TEXT_DIM), wrap=155)
            dpg.add_spacer(height=4, parent="estado_content")
    else:
        dpg.add_text("Sin frentes activos.", parent="estado_content", color=list(C_TEXT_DIM))
        dpg.add_text("Construí el vault primero.", parent="estado_content",
                     color=list(C_TEXT_DIM), wrap=155)

    # Escenas (C2)
    if _AGENT_MODE and _orchestrator:
        try:
            escenas = _orchestrator.scenes.get_status_summary()
        except Exception:
            escenas = ""
        if escenas:
            dpg.add_spacer(height=6, parent="estado_content")
            dpg.add_text("ESCENAS:", parent="estado_content", color=list(C_GOLD_DIM))
            for line in escenas.splitlines():
                color = list(C_GOLD) if line.startswith("▶") else list(C_TEXT_DIM)
                dpg.add_text(line, parent="estado_content", color=color, wrap=155)

    # Ideas pendientes (Fase 6 — Ideas Inbox)
    try:
        ideas = _get_ideas_inbox().list_by_state("raw_idea") + _get_ideas_inbox().list_by_state("developing")
    except Exception as e:
        logger.error(f"Error listando ideas: {e}", exc_info=True)
        ideas = []

    dpg.add_spacer(height=8, parent="estado_content")
    dpg.add_separator(parent="estado_content")
    dpg.add_spacer(height=4, parent="estado_content")
    dpg.add_text("IDEAS PENDIENTES:", parent="estado_content", color=list(C_GOLD_DIM))
    if ideas:
        for idea in ideas[:5]:
            titulo = idea["meta"].get("titulo", idea["path"].stem)
            with dpg.group(parent="estado_content"):
                dpg.add_text(f"- {titulo}", color=list(C_TEXT), wrap=155)
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="→ NPC", width=70,
                        callback=lambda s, a, p=idea["path"]: _promote_idea_callback(p, "npc"),
                    )
                    dpg.add_button(
                        label="→ Locación", width=90,
                        callback=lambda s, a, p=idea["path"]: _promote_idea_callback(p, "locacion"),
                    )
            dpg.add_spacer(height=3, parent="estado_content")
    else:
        dpg.add_text("Sin ideas anotadas.", parent="estado_content", color=list(C_TEXT_DIM))

    dpg.add_spacer(height=4, parent="estado_content")
    dpg.add_button(
        label="💡 Anotar último mensaje como idea", width=-1, parent="estado_content",
        callback=lambda: capture_idea_callback(),
    )

# ─────────────────────────────────────────────
#  MULTI-PDF — carga suplementos adicionales
# ─────────────────────────────────────────────
def add_supplement_callback(sender, app_data):
    """Carga un PDF adicional y acumula su texto en manual_text."""
    if not app_data or "file_path_name" not in app_data:
        return
    path = app_data["file_path_name"]
    name = Path(path).name

    def process():
        text = extract_pdf_text(path, max_chars=8000)
        if not text:
            _ui(lambda n=name: append_to_chat(
                "system", f"⚠ No pude leer el suplemento: {n}. Revisá logs."))
            return
        separator = f"\n\n{'='*60}\n=== SUPLEMENTO: {name} ===\n{'='*60}\n\n"
        with state_lock:
            state["manual_text"] += separator + text
            state["manual_names"].append(name)
            names_str = ", ".join(state["manual_names"])
        _ui(lambda ns=names_str, n=name: (
            dpg.set_value("manual_status", f"✓ {ns}"),
            append_to_chat("system", f"Suplemento añadido: {n}"),
        ))

    threading.Thread(target=process, daemon=True).start()


# ─────────────────────────────────────────────
#  EXPORTAR LOG DE SESIÓN
# ─────────────────────────────────────────────
def export_session_log(silent: bool = False) -> str:
    """Exporta el historial de chat completo como Markdown. Devuelve la ruta."""
    session_n = state.get("session_number", 1)
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Sesion_{session_n:02d}_export_{date_str}.md"
    export_path = session_manager.save_dir / filename

    lines = [
        f"# Sesión {session_n} — {datetime.now().strftime('%Y-%m-%d')}",
        f"**Sistema:** {state.get('system_name', '—')}",
        f"**Manual:** {state.get('manual_name', '—')}",
        "",
        "---",
        "",
        "## Transcripción",
        "",
    ]

    for msg in state["messages"]:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"**Jugador:** {content}")
        elif role == "assistant":
            lines.append(f"**Narrador:** {content}")
        lines.append("")

    if state["session_log"]:
        lines += ["---", "", "## Log de Eventos", ""]
        lines += [f"- {e}" for e in state["session_log"]]

    if state.get("character"):
        lines += [
            "", "---", "", "## Hoja de Personaje (snapshot)", "",
            "```json",
            json.dumps(state["character"], ensure_ascii=False, indent=2),
            "```",
        ]

    if _AGENT_MODE and _orchestrator:
        clocks = _orchestrator.state.get_clocks_summary()
        if clocks:
            lines += ["", "---", "", "## Estado de Frentes", "", "```", clocks, "```"]

    export_path.write_text("\n".join(lines), encoding="utf-8")

    if _AGENT_MODE and _orchestrator:
        sessions_dir = _orchestrator.retriever.vault_path / "Sesiones"
        if sessions_dir.exists():
            import shutil
            shutil.copy(export_path, sessions_dir / filename)

    if not silent:
        append_to_chat("system", f"Log exportado: {export_path}")
    return str(export_path)


# ─────────────────────────────────────────────
#  EDITOR DE HOJA DE PERSONAJE
# ─────────────────────────────────────────────
def refresh_character_editor():
    """Actualiza el editor JSON con los datos actuales del personaje."""
    try:
        json_str = json.dumps(state["character"], ensure_ascii=False, indent=2)
        dpg.set_value("char_json_editor", json_str)
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)

def apply_character_edits():
    """Lee el JSON del editor, valida y aplica al estado."""
    try:
        raw = dpg.get_value("char_json_editor")
        data = json.loads(raw)
        if isinstance(data, dict):
            state["character"] = data
            refresh_character_panel()
            refresh_character_editor()
            append_to_chat("system", "Hoja de personaje actualizada.")
        else:
            append_to_chat("system", "⚠ El JSON debe ser un objeto {}.")
    except json.JSONDecodeError as e:
        append_to_chat("system", f"⚠ JSON inválido: {e}")


def _save_session_with_memory() -> str:
    """Guarda la sesión sincronizando antes la memoria episódica al estado."""
    state["memoria_episodica"] = _memory.to_dict()
    return session_manager.save_session(state)


# ─────────────────────────────────────────────
#  NUEVA SESIÓN
# ─────────────────────────────────────────────
def new_session_callback():
    """Exporta el log, resetea el estado de sesión y reconstruye el chat."""
    export_session_log(silent=True)
    state.update({"messages": [], "character": {},
                  "session_log": [], "phase": "idle",
                  "last_dice_result": None,
                  "tirada_sugerida": None,
                  "session_number": state.get("session_number", 1) + 1})
    _memory.reset()
    if _AGENT_MODE and _orchestrator:
        _orchestrator.pacing_agent.reset_session()
    # delete_item borra TAMBIÉN streaming_group (vive dentro de chat_scroll):
    # hay que recrearlo o el próximo mensaje rompe el streaming.
    dpg.delete_item("chat_scroll", children_only=True)
    _add_streaming_group()
    refresh_character_panel()
    refresh_log()
    refresh_estado_panel()
    refresh_dice_suggestion()
    _save_session_with_memory()
    append_to_chat("system", f"Nueva sesión iniciada: #{state['session_number']}")

    # Retomar el flujo guiado: si el manual sigue cargado solo falta la
    # planilla; si no, se arranca desde la elección del juego.
    if state.get("manual_text"):
        state["phase"] = "setup_sheet"
        append_to_chat(
            "system",
            f"Manual conservado ({state.get('manual_name', '')}). "
            "Adjuntá la planilla de tu personaje para esta sesión (PDF).",
        )
        dpg.show_item("sheet_dialog")
    else:
        start_onboarding()


# ─────────────────────────────────────────────
#  WORLD AGENT — avance autónomo del mundo
# ─────────────────────────────────────────────
def run_world_agent():
    """Lanza el WorldAgent en un hilo secundario."""
    if not _AGENT_MODE or not _orchestrator:
        append_to_chat("system", "⚠ Modo agentes no disponible.")
        return

    try:
        dpg.disable_item("world_advance_btn")
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
    _ui(lambda: _proc_start("Avanzando el mundo entre sesiones..."))

    def on_progress(msg: str):
        _ui(lambda m=msg: _proc_step(m))

    def run():
        try:
            llm = LLMClient(model=state["model"])
            agent = WorldAgent(
                llm=llm,
                retriever=_orchestrator.retriever,
                state=_orchestrator.state,
            )
            result = agent.run(
                system_slug=state.get("system_slug", "generic"),
                session_number=state.get("session_number", 1),
                on_progress=on_progress,
            )
            for adv in result.get("advances", []):
                nombre = adv.get("nombre", "")
                ticks = adv.get("ticks", 1)
                razon = adv.get("razon", "")
                if not nombre:
                    continue
                # Registrar el frente si no existe: antes ambas llamadas eran
                # no-ops (relojes YAML y world_state.json siempre vacíos) y
                # solo los checkboxes del MD avanzaban.
                _orchestrator.state.add_front(nombre, razon)
                _orchestrator.state.advance_front_clock(nombre, ticks)
                if _orchestrator.world_sim.get_front_stage(nombre) is None:
                    _orchestrator.world_sim.initialize_front(
                        nombre, razon, initial_stage=0, max_stage=6)
                _orchestrator.world_sim.advance_front(nombre, ticks)
            summary = (
                f"Mundo avanzado: {result['frentes_avanzados']} frentes, "
                f"{result['npcs_simulados']} NPCs simulados.\n\n"
                f"{result['narrativa']}"
            )
            _ui(lambda s=summary: (_proc_done(s), refresh_estado_panel()))
        except Exception as e:
            _ui(lambda err=str(e): _proc_done(f"Error en World Agent: {err}"))
        finally:
            _ui(lambda: dpg.enable_item("world_advance_btn"))

    threading.Thread(target=run, daemon=True).start()


# ─────────────────────────────────────────────
#  GUI — PDF LOADER
# ─────────────────────────────────────────────
def load_pdf_callback(sender, app_data):
    if not app_data or "file_path_name" not in app_data:
        return

    path = app_data["file_path_name"]
    name = Path(path).name

    dpg.set_value("manual_status", f"Cargando {name}...")

    def process():
        text = extract_pdf_text(path)
        if not text:
            _ui(lambda n=name: (
                dpg.set_value("manual_status", f"✗ Error leyendo {n}"),
                append_to_chat("system", f"⚠ No pude leer el PDF: {n}. Revisá logs."),
            ))
            return
        system_name, system_slug = detect_system(text)
        with state_lock:
            state["manual_text"] = text
            state["manual_name"] = name
            state["manual_names"] = [name]
            state["system_name"] = system_name
            state["system_slug"] = system_slug
            # La creación de personaje in-app está pospuesta (roadmap Fase A):
            # el siguiente paso del flujo es adjuntar la planilla del jugador.
            state["phase"] = "setup_sheet"

        def _update(sn=system_name, n=name):
            dpg.set_value("manual_status", f"✓ {n}")
            dpg.set_value("system_detected", sn)
            try:
                dpg.enable_item("build_vault_btn")
                dpg.enable_item("add_pdf_btn")
            except Exception as e:
                logger.error(f"Error inesperado: {e}", exc_info=True)
            append_to_chat(
                "system",
                f"Manual cargado: {n}\nSistema detectado: {sn}\n\n"
                "Ahora adjuntá la planilla de tu personaje (PDF).",
            )
            dpg.show_item("sheet_dialog")

        _ui(_update)

    threading.Thread(target=process, daemon=True).start()

# ─────────────────────────────────────────────
#  GUI — PLANILLA DEL JUGADOR (PDF adjunto → LLM → hoja)
# ─────────────────────────────────────────────
def load_sheet_callback(sender, app_data):
    """Carga la planilla del jugador: extrae el texto del PDF y la
    estructura vía LLM para poblar la hoja de personaje."""
    if not app_data or "file_path_name" not in app_data:
        return
    path = app_data["file_path_name"]
    name = Path(path).name
    _proc_start(f"Leyendo planilla: {name}")

    def process():
        text = extract_pdf_text(path, max_chars=15000)
        if not text:
            _ui(lambda n=name: _proc_done(f"⚠ No pude leer la planilla: {n}. Revisá logs."))
            return
        _ui(lambda: _proc_step("Estructurando la planilla con el LLM..."))
        char = parse_character_sheet(
            text, LLMClient(model=state["model"]),
            system_name=state.get("system_name", ""),
        )
        if not char:
            _ui(lambda: _proc_done(
                "⚠ No pude estructurar la planilla. Probá con otro PDF "
                "o cargá los datos a mano en 'Editar (JSON)'."))
            return
        with state_lock:
            state["character"] = char
            state["phase"] = "play"

        def _done(n=name, c=char):
            refresh_character_panel()
            refresh_character_editor()
            _proc_done(f"Planilla cargada: {n} — personaje: {c.get('nombre', '(sin nombre)')}.")
            _begin_adventure()

        _ui(_done)

    threading.Thread(target=process, daemon=True).start()


def _begin_adventure():
    """Primer turno: el narrador abre la aventura con el personaje cargado."""
    nombre = state["character"].get("nombre", "mi personaje")
    sistema = state.get("system_name") or state.get("declared_game") or "el sistema cargado"
    send_message(
        f"Ya cargué el manual ({sistema}) y la planilla de mi personaje, {nombre}. "
        "Comenzá la aventura: presentá una escena inicial atmosférica acorde al sistema, "
        "sin crear ni modificar mi personaje, y terminá preguntándome qué hago."
    )


# ─────────────────────────────────────────────
#  GUI — VAULT BUILDER
# ─────────────────────────────────────────────
def build_vault_callback():
    if not state.get("manual_text"):
        append_to_chat("system", "⚠ Primero cargá un manual PDF.")
        return
    if not _AGENT_MODE:
        append_to_chat("system", "⚠ Modo agentes no disponible.")
        return

    try:
        dpg.disable_item("build_vault_btn")
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
    _ui(lambda: _proc_start("Construyendo vault del sistema..."))

    def on_progress(msg: str):
        _ui(lambda m=msg: _proc_step(m))

    def run():
        try:
            llm = LLMClient(model=state["model"])
            pb = PromptBuilder()
            extractor = ExtractorAgent(llm=llm, builder=pb)

            config = _orchestrator.config if _orchestrator else {}
            # Rutas ya resueltas contra PROJECT_ROOT
            vault_path = str(_orchestrator.retriever.vault_path) if _orchestrator \
                else str(resolve_path("vault"))
            template_path = str(resolve_path(
                config.get("vault", {}).get("template_path", "data/vault_template")))

            result = extractor.run(
                pdf_text=state["manual_text"],
                system_slug=state["system_slug"],
                system_name=state["system_name"],
                vault_path=vault_path,
                template_path=template_path,
                on_progress=on_progress,
            )
            # El retriever cacheó un índice vacío antes de que existiera
            # el vault: sin esto, la búsqueda semántica queda muerta
            # hasta reiniciar la app.
            _orchestrator.retriever.invalidate_cache()
            summary = (
                f"Vault construido: {result['npcs']} NPCs, "
                f"{result['locaciones']} locaciones, "
                f"{result['facciones']} facciones, "
                f"{result['frentes']} frentes.\n"
                f"Abri vault/ en Obsidian para explorar."
            )
            _ui(lambda s=summary: (_proc_done(s), refresh_estado_panel()))
        except Exception as e:
            _ui(lambda err=str(e): _proc_done(f"Error construyendo vault: {err}"))
        finally:
            _ui(lambda: dpg.enable_item("build_vault_btn"))

    threading.Thread(target=run, daemon=True).start()

# ─────────────────────────────────────────────
#  GUI — QUICK ACTIONS
# ─────────────────────────────────────────────
QUICK_ACTIONS = [
    ("Atacar", "Quiero atacar al enemigo más cercano."),
    ("Investigar", "Examino el entorno en busca de pistas o peligros ocultos."),
    ("Negociar", "Intento hablar y negociar con el PNJ."),
    ("Huir", "Intento escapar de la situación actual."),
    ("Descansar", "El grupo se detiene a descansar y recuperarse."),
    ("Situacion", "¿Qué está pasando exactamente? Describí la escena."),
]

# ─────────────────────────────────────────────
#  GUI — THEME
# ─────────────────────────────────────────────
def apply_theme():
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, C_BG)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, C_SURFACE)
            dpg.add_theme_color(dpg.mvThemeCol_Border, C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, C_INPUT_BG)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, C_HOVER)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, C_ACTIVE)
            dpg.add_theme_color(dpg.mvThemeCol_Button, C_SURFACE)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, C_HOVER)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, C_ACTIVE)
            dpg.add_theme_color(dpg.mvThemeCol_Header, C_SURFACE)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, C_HOVER)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, C_ACTIVE)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, C_SURFACE)
            dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, C_BG)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, C_GOLD_DIM)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, C_GOLD)
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, C_GOLD)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, C_GOLD)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, C_GOLD)
            dpg.add_theme_color(dpg.mvThemeCol_Text, C_TEXT)
            dpg.add_theme_color(dpg.mvThemeCol_Separator, C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_SeparatorHovered, C_GOLD_DIM)
            dpg.add_theme_color(dpg.mvThemeCol_Tab, C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, C_HOVER)
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, C_SURFACE)

            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 3)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 3)
            dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 3)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 5)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 10)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, 10)

    dpg.bind_theme(global_theme)

    with dpg.theme() as dice_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, C_RED)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, C_RED_BRIGHT)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (210, 70, 78, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (230, 230, 240, 255))
    state["dice_theme"] = dice_theme

    with dpg.theme() as send_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, C_GOLD_DIM)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, C_GOLD)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (120, 175, 230, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text, C_BG)
    state["send_theme"] = send_theme

    with dpg.theme() as action_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (18, 26, 40, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, C_HOVER)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, C_ACTIVE)
            dpg.add_theme_color(dpg.mvThemeCol_Text, C_GOLD)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 2)
    state["action_theme"] = action_theme

# ─────────────────────────────────────────────
#  GUI — LAYOUT RESPONSIVE
# ─────────────────────────────────────────────
COL_L = 195   # ancho columna izquierda (personaje + dados)
COL_R = 190   # ancho columna derecha (log + estado)

def _rewrap_texts(item, wrap_w: int):
    """Reajusta el wrap de todos los textos ya renderizados en el chat."""
    for child in dpg.get_item_children(item, 1) or []:
        if dpg.get_item_type(child) == "mvAppItemType::mvText":
            if dpg.get_item_configuration(child).get("wrap", -1) not in (-1, None):
                dpg.configure_item(child, wrap=wrap_w)
        else:
            _rewrap_texts(child, wrap_w)

def _relayout():
    """Reajusta el layout al tamaño REAL del viewport.

    Se llama al construir la GUI, en cada resize del viewport y al
    mostrar/ocultar la barra de progreso. Garantiza que el input del chat
    y todos los botones queden siempre visibles (antes las alturas se
    calculaban una sola vez al maximizar y los paneles desbordaban).
    """
    global _CHAT_WRAP_W
    try:
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        chat_w = max(320, w - COL_L - COL_R - 20)
        panel_h = max(300, h - 68)
        _CHAT_WRAP_W = chat_w - 32

        dpg.configure_item("left_panel", height=panel_h)
        dpg.configure_item("center_panel", width=chat_w, height=panel_h)
        dpg.configure_item("right_panel", height=panel_h)

        # Centro: reservar alto fijo para acciones rápidas + input (+ barra
        # de progreso si está visible) y darle el resto al scroll del chat.
        proc_visible = (dpg.does_item_exist("proc_bar_group")
                        and dpg.is_item_shown("proc_bar_group"))
        chat_h = max(120, panel_h - 132 - (44 if proc_visible else 0))
        dpg.configure_item("chat_scroll", height=chat_h)
        dpg.configure_item("user_input", width=chat_w - 92)
        btn_w = max(80, (chat_w - 12) // len(QUICK_ACTIONS))
        for i in range(len(QUICK_ACTIONS)):
            if dpg.does_item_exist(f"qa_btn_{i}"):
                dpg.configure_item(f"qa_btn_{i}", width=btn_w)

        # Laterales: reservar el alto de sus botones inferiores.
        dpg.configure_item("char_content", height=max(80, panel_h - 292))
        dpg.configure_item("log_content", height=max(80, panel_h - 215))
        dpg.configure_item("estado_content", height=max(80, panel_h - 188))

        # Textos ya renderizados: reajustar wrap al nuevo ancho.
        _rewrap_texts("chat_scroll", _CHAT_WRAP_W)
        if dpg.does_item_exist("streaming_label"):
            dpg.configure_item("streaming_label", wrap=_CHAT_WRAP_W)
    except Exception as e:
        logger.error(f"Error en relayout: {e}", exc_info=True)

# ─────────────────────────────────────────────
#  GUI — MAIN WINDOW
# ─────────────────────────────────────────────
def build_gui():
    global _CHAT_WRAP_W
    dpg.create_context()
    dpg.create_viewport(title=APP_TITLE, min_width=900, min_height=600, resizable=True)
    apply_theme()
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.maximize_viewport()
    dpg.render_dearpygui_frame()   # deja que el maximize tome efecto

    W = dpg.get_viewport_client_width()
    H = dpg.get_viewport_client_height()

    # Tamaños iniciales; _relayout() los recalcula al final del build
    # y en cada resize del viewport.
    CHAT_W  = max(320, W - COL_L - COL_R - 20)
    _CHAT_WRAP_W = CHAT_W - 32
    PANEL_H = max(300, H - 68)

    # ── File dialogs ──────────────────────────────────────────
    dpg.add_file_dialog(
        tag="pdf_dialog", directory_selector=False, show=False,
        callback=load_pdf_callback, width=700, height=450, modal=True,
    )
    dpg.add_file_extension(".pdf", parent="pdf_dialog", color=list(C_GOLD))
    dpg.add_file_extension(".PDF", parent="pdf_dialog", color=list(C_GOLD))

    dpg.add_file_dialog(
        tag="pdf_supplement_dialog", directory_selector=False, show=False,
        callback=add_supplement_callback, width=700, height=450, modal=True,
    )
    dpg.add_file_extension(".pdf", parent="pdf_supplement_dialog", color=list(C_GOLD_DIM))
    dpg.add_file_extension(".PDF", parent="pdf_supplement_dialog", color=list(C_GOLD_DIM))

    dpg.add_file_dialog(
        tag="sheet_dialog", directory_selector=False, show=False,
        callback=load_sheet_callback, width=700, height=450, modal=True,
    )
    dpg.add_file_extension(".pdf", parent="sheet_dialog", color=list(C_GOLD))
    dpg.add_file_extension(".PDF", parent="sheet_dialog", color=list(C_GOLD))

    # ── Ventana de progreso flotante ──────────────────────────
    with dpg.window(tag="proc_detail_window",
                    label="Proceso en segundo plano",
                    show=False, width=480, height=370, no_close=False,
                    pos=[W // 2 - 240, H // 2 - 185]):
        dpg.add_text("", tag="proc_detail_header", color=list(C_GOLD))
        dpg.add_separator()
        dpg.add_spacer(height=4)
        dpg.add_text(
            "Este proceso corre en segundo plano.\n"
            "Podes seguir jugando mientras tanto.",
            color=list(C_TEXT_DIM), wrap=440,
        )
        dpg.add_spacer(height=6)
        with dpg.child_window(tag="proc_log_area", height=220, border=True,
                              horizontal_scrollbar=False):
            dpg.add_text("En espera...", color=list(C_TEXT_DARK))
        dpg.add_spacer(height=6)
        dpg.add_button(label="Ocultar", width=-1,
                       callback=lambda: dpg.configure_item("proc_detail_window", show=False))

    # ── Ventana principal ─────────────────────────────────────
    with dpg.window(tag="main_window", no_title_bar=True, no_move=True,
                    no_resize=True, no_scrollbar=True):

        # ── HEADER ───────────────────────────────────────────
        with dpg.group(horizontal=True):
            dpg.add_text("AI NARRATOR", color=list(C_GOLD))
            dpg.add_spacer(width=10)
            dpg.add_text("Modelo:", color=list(C_TEXT_DIM))
            models = LLMClient().get_models()
            state["models"] = models
            if not models:
                models = ["(sin Ollama)"]
            dpg.add_combo(tag="model_selector", items=models,
                          default_value=models[0], width=170,
                          callback=lambda s, a: state.update({"model": a}))
            dpg.add_spacer(width=8)
            dpg.add_text("Manual:", color=list(C_TEXT_DIM))
            dpg.add_text("(ninguno)", tag="manual_status", color=list(C_TEXT_DIM))
            dpg.add_button(label="Cargar PDF",
                           callback=lambda: dpg.show_item("pdf_dialog"))
            dpg.add_button(tag="add_pdf_btn", label="+ Supl.",
                           callback=lambda: dpg.show_item("pdf_supplement_dialog"),
                           enabled=False)
            dpg.add_button(label="Planilla",
                           callback=lambda: dpg.show_item("sheet_dialog"))
            dpg.add_spacer(width=8)
            dpg.add_text("Sistema:", color=list(C_TEXT_DIM))
            dpg.add_text("--", tag="system_detected", color=list(C_TEXT_DIM))
            dpg.add_spacer(width=8)
            dpg.add_button(tag="build_vault_btn", label="Vault",
                           callback=build_vault_callback, enabled=False)
            dpg.add_button(label="Guardar",
                           callback=lambda: (_save_session_with_memory(),
                                             append_to_chat("system", "Sesion guardada.")))

        dpg.add_separator()
        dpg.add_spacer(height=2)

        # ── LAYOUT 3 COLUMNAS ────────────────────────────────
        with dpg.group(horizontal=True):

            # ══ IZQUIERDA: personaje + dados ══
            with dpg.child_window(width=COL_L, height=PANEL_H, border=True,
                                  tag="left_panel"):
                dpg.add_spacer(height=4)
                with dpg.tab_bar():

                    with dpg.tab(label="Personaje"):
                        dpg.add_spacer(height=4)
                        with dpg.child_window(tag="char_content",
                                              height=PANEL_H - 230,
                                              border=False):
                            dim_text("Sin personaje.")
                        dpg.add_spacer(height=4)
                        dpg.add_button(label="Actualizar hoja", width=-1,
                                       callback=refresh_character_panel)
                        dpg.add_separator()
                        dpg.add_spacer(height=3)
                        dim_text("Editar (JSON):")
                        dpg.add_input_text(
                            tag="char_json_editor", multiline=True,
                            width=-1, height=100,
                            hint='{"nombre": "...", ...}',
                        )
                        dpg.add_spacer(height=3)
                        dpg.add_button(label="Aplicar cambios", width=-1,
                                       callback=apply_character_edits)

                    with dpg.tab(label="Dados") as tab_dados:
                        dpg.add_spacer(height=4)
                        build_dice_panel(tab_dados)

            dpg.add_spacer(width=4)

            # ══ CENTRO: chat ══
            with dpg.child_window(width=CHAT_W, height=PANEL_H, border=True,
                                  tag="center_panel"):

                # Quick actions — una sola fila
                btn_w = max(80, (CHAT_W - 12) // len(QUICK_ACTIONS))
                with dpg.group(horizontal=True):
                    for i, (lbl, msg) in enumerate(QUICK_ACTIONS):
                        btn = dpg.add_button(
                            tag=f"qa_btn_{i}",
                            label=lbl, width=btn_w,
                            callback=lambda s, a, m=msg: send_message(m),
                        )
                        dpg.bind_item_theme(btn, state["action_theme"])
                dpg.add_separator()

                # Barra de progreso (oculta hasta que haya proceso activo)
                with dpg.group(tag="proc_bar_group", show=False):
                    dpg.add_spacer(height=2)
                    with dpg.group(horizontal=True):
                        dpg.add_text("[...]", color=list(C_GOLD))
                        dpg.add_spacer(width=4)
                        dpg.add_text("", tag="proc_bar_text", color=list(C_TEXT_DIM))
                        dpg.add_spacer(width=6)
                        dpg.add_button(
                            label="Detalles",
                            callback=lambda: dpg.configure_item(
                                "proc_detail_window", show=True),
                        )
                        dpg.add_button(
                            label=" x ",
                            callback=lambda: dpg.configure_item(
                                "proc_bar_group", show=False),
                        )
                    dpg.add_spacer(height=2)
                    dpg.add_separator()

                # Scroll de chat
                CHAT_H = PANEL_H - 100
                with dpg.child_window(tag="chat_scroll", height=CHAT_H,
                                      border=False, horizontal_scrollbar=False):
                    dpg.add_text(
                        "Bienvenido al AI Narrator.",
                        color=list(C_TEXT_DIM), wrap=_CHAT_WRAP_W,
                    )
                    dpg.add_separator()
                _add_streaming_group()

                dpg.add_spacer(height=3)

                # Input
                with dpg.group(horizontal=True):
                    dpg.add_input_text(
                        tag="user_input",
                        hint="Escribe tu accion o pregunta...",
                        width=CHAT_W - 92,
                        height=46,
                        multiline=False,
                        on_enter=True,
                        callback=lambda s, a: send_message(),
                    )
                    send_btn = dpg.add_button(
                        tag="send_btn", label="Enviar",
                        width=84, height=46,
                        # lambda sin args: DPG pasa sender al primer parámetro
                        # de la callback → send_message recibiría "send_btn".
                        callback=lambda: send_message(),
                    )
                    dpg.bind_item_theme(send_btn, state["send_theme"])

            dpg.add_spacer(width=4)

            # ══ DERECHA: log + estado ══
            with dpg.child_window(width=COL_R, height=PANEL_H, border=True,
                                  tag="right_panel"):
                dpg.add_spacer(height=4)
                with dpg.tab_bar():

                    with dpg.tab(label="Log"):
                        dpg.add_spacer(height=4)
                        dpg.add_separator()
                        dpg.add_spacer(height=3)
                        with dpg.child_window(tag="log_content",
                                              height=PANEL_H - 160,
                                              border=False):
                            dim_text("Sin eventos.")
                        dpg.add_spacer(height=4)
                        dpg.add_button(label="Exportar log", width=-1,
                                       callback=lambda: export_session_log())
                        dpg.add_spacer(height=3)
                        dpg.add_button(
                            label="Limpiar log", width=-1,
                            callback=lambda: (state["session_log"].clear(),
                                             refresh_log()),
                        )
                        dpg.add_spacer(height=3)
                        dpg.add_button(
                            label="Nueva sesion", width=-1,
                            callback=lambda: new_session_callback(),
                        )

                    with dpg.tab(label="Estado"):
                        dpg.add_spacer(height=4)
                        dpg.add_separator()
                        dpg.add_spacer(height=3)
                        with dpg.child_window(tag="estado_content",
                                              height=PANEL_H - 160,
                                              border=False):
                            dim_text("Cargando estado...")
                        dpg.add_spacer(height=4)
                        dpg.add_button(label="Actualizar", width=-1,
                                       callback=refresh_estado_panel)
                        dpg.add_spacer(height=3)
                        dpg.add_button(tag="world_advance_btn",
                                       label="Avanzar Mundo", width=-1,
                                       callback=run_world_agent)

    dpg.set_primary_window("main_window", True)
    dpg.set_viewport_resize_callback(lambda: _relayout())
    _relayout()
    refresh_estado_panel()

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def _init_vault_writer():
    global _vault_writer
    if not _AGENT_MODE:
        return
    try:
        config = _orchestrator.config if _orchestrator else {}
        vault_path = str(_orchestrator.retriever.vault_path) if _orchestrator \
            else str(resolve_path("vault"))
        live = config.get("vault", {}).get("live_updates", True)
        if not live:
            return
        _vault_writer = VaultWriter(vault_path=vault_path)
        session_n = state.get("session_number", 1)
        _vault_writer.start_session(
            session_number=session_n,
            system_name=state.get("system_name", ""),
            campaign_name=state.get("campaign_name", ""),
        )
        print(f"✓ Vault writer activo — vault/Sesiones/Sesion_{session_n:02d}_*.md")
    except Exception as e:
        print(f"⚠ Vault writer no disponible: {e}")


def main():
    print("╔══════════════════════════════════╗")
    print("║       AI NARRATOR v0.2           ║")
    print("║  Motor de Rol con Agentes+Ollama ║")
    print("╚══════════════════════════════════╝")
    print()

    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"✓ Ollama conectado. Modelos: {', '.join(models) if models else 'ninguno'}")
        if models:
            state["model"] = models[0]
    except Exception as e:
        print("⚠ No se encontró Ollama en localhost:11434")
        print("  Instalar: https://ollama.com")
        print("  Luego: ollama pull llama3.2")
        print()

    if session_manager.load_session(state):
        _memory.from_dict(state.get("memoria_episodica", {}))
        print("✓ Sesión anterior cargada")

    _init_vault_writer()

    build_gui()

    # Re-render de la sesión restaurada: antes el estado se cargaba pero la
    # GUI quedaba vacía (chat en blanco, "Sin personaje") mientras el LLM
    # "recordaba" el historial completo.
    if state["messages"]:
        for m in state["messages"]:
            if m.get("role") in ("user", "assistant"):
                append_to_chat(m["role"], m.get("content", ""))
        append_to_chat("system", f"Sesión #{state.get('session_number', 1)} restaurada "
                                 f"({len(state['messages'])} mensajes).")
    if state["character"]:
        refresh_character_panel()
        refresh_character_editor()
    if state["session_log"]:
        refresh_log()

    # Sesión nueva (sin historial): el sistema conduce el inicio.
    if not state["messages"]:
        start_onboarding()
    elif state.get("phase") in SETUP_PHASES or state.get("phase") == "char_creation":
        # Fase de setup guardada de una sesión vieja: el manual no persiste
        # entre ejecuciones, así que se retoma el flujo desde el principio.
        start_onboarding()

    while dpg.is_dearpygui_running():
        while True:
            try:
                fn = _ui_queue.get_nowait()
            except _queue_mod.Empty:
                break
            try:
                fn()
            except Exception as e:
                # Un callback encolado roto no debe matar el render loop.
                logger.error(f"Error en callback de UI encolado: {e}", exc_info=True)
        dpg.render_dearpygui_frame()

    dpg.destroy_context()
    print("Sesión finalizada.")
