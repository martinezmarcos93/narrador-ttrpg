"""
Prompt Builder — construye prompts de sistema desde configuración YAML + contexto del vault.
Mantiene el contexto total dentro de un budget de palabras para modelos pequeños.
"""

import json
from narrator.logger import logger
from narrator.core.resolution_schema import ResolutionSchemaError, validate_resolution
from narrator.core.system_pack import SystemPack
import yaml
from pathlib import Path


NARRATIVE_PRINCIPLES = """PRINCIPIOS NARRATIVOS:
- La historia EMERGE de las decisiones del jugador. Nunca está pre-escrita.
- Cada escena tiene tensión: física, emocional, moral, psicológica o existencial.
- Los fallos SIEMPRE avanzan la historia con complicaciones. Nunca bloquean.
- El mundo recuerda: las consecuencias persisten entre sesiones.
- Mostrar, nunca explicar. ("Los guardias dejan de sonreír cuando pasa el carruaje.")
- Dosificar información: el misterio parcial es más poderoso que la revelación total.
- Si se pide tirada de dados: indicá qué habilidad aplica y qué dados lanzar."""

DICE_RESOLUTION_RULES = """RESOLUCIÓN DE TIRADAS:
- Éxito total: la acción sale, narrá con riqueza cinématica.
- Éxito parcial (PbtA 7-9): ofrecé una elección difícil.
- Fallo: complicación interesante, la historia avanza igual."""

NARRATIVE_PROPOSAL_RULES = """PROPUESTAS ESTRUCTURADAS DE ESTADO (bloque técnico opcional):
- Solo emití este bloque si durante este turno ocurrió un cambio persistente que el sistema deba recordar.
- No inventes hechos, consecuencias, NPCs, locaciones o cambios mecánicos que no estén respaldados por la ficción o por la resolución del sistema.
- El bloque debe usar exactamente el formato `json-proposal` y solo estas claves: facts, events, npc_presence, npcs, locations, consequences, character_changes, scene_changes, clock_changes, relations.
- Omití claves vacías.
- facts contiene hechos persistentes como pares clave/valor.
- events contiene eventos ya ocurridos, no intenciones futuras.
- consequences contiene objetos con text y opcionalmente trigger/due/effects. Los effects permitidos son fact, flag, npc_presence, scene_location, clock_delta, event, queue_consequence, world_fact, character_fact y player_fact.
- character_changes contiene field + delta o value + reason opcional.
- clock_changes contiene name + delta.
- scene_changes puede contener locacion o turno_narrativo_delta.
- queue_consequence debe declarar consequence y puede declarar trigger/due/effects para encadenar una consecuencia posterior. event emite un hecho explícito que puede activar otra consecuencia. world_fact es verdad objetiva; character_fact y player_fact conceden conocimiento explícito y no deben confundirse entre sí. relation modifica una arista social existente o crea una nueva entre entidades; front_clock_delta mueve un reloj causal de frente. No uses este bloque para repetir información puramente narrativa."""


ENTITY_AUTO_SAVE_RULES = """AUTO-GUARDADO DE ENTIDADES Y ESTADO (instrucciones técnicas, NUNCA visibles para el jugador):
- Si en la narración aparece un NPC o Locación NUEVO que no está en el contexto, declaralo al final de tu respuesta:
  [[NUEVO_NPC]]
  NOMBRE: <nombre>
  ROL: <una línea>
  AMENAZA: <alta/media/baja>
  [[/NUEVO_NPC]]
  (para locaciones nuevas: [[NUEVA_LOCACION]] ... NOMBRE: <nombre> ... [[/NUEVA_LOCACION]])
- Si el personaje jugador sufre un cambio de estado mecánico (HP, condiciones, recursos), indicalo en el punto exacto de la narración con:
  [state: field=<campo> delta=<±número> reason=<motivo breve>]
  (usá "value=<nuevo valor>" en vez de "delta" si no es un cambio numérico incremental)
- Estas etiquetas son para el sistema, no literatura: el jugador NUNCA debe verlas ni se las debés mencionar. Se eliminan automáticamente antes de mostrarse."""


class PromptBuilder:
    def __init__(self, systems_path: str = "data/systems"):
        self.systems_path = Path(systems_path)
        self._cache: dict[str, dict] = {}

    # ── Sistema ───────────────────────────────────────────────
    def load_system(self, slug: str) -> dict:
        if slug in self._cache:
            return self._cache[slug]
        path = self.systems_path / f"{slug}.yaml"
        if not path.exists():
            path = self.systems_path / "generic.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Contrato ejecutable: todos los sistemas deben declarar cómo se
        # enruta su conocimiento. El contenido histórico sigue siendo un
        # dict para mantener compatibilidad con el resto del código.
        try:
            SystemPack.from_dict(
                data,
                expected_slug=None if path.name == "generic.yaml" else slug,
            )
        except ValueError as exc:
            logger.error(f"System Pack inválido '{slug}': {exc}")
            raise

        # Validación del bloque resolution (Fase 10): se registra el error
        # apenas se carga el sistema, sin frenar el turno en curso — el
        # RuleArbiter ya degrada con gracia si "resolution" viene vacío.
        if "resolution" in data:
            try:
                validate_resolution(data["resolution"], system_slug=slug)
            except ResolutionSchemaError as e:
                logger.error(f"YAML de sistema '{slug}' con resolution inválida: {e}")

        self._cache[slug] = data
        return data

    def detect_system_from_text(self, text: str) -> str:
        """Auto-detecta el sistema desde texto de PDF/manual."""
        t = text.lower()
        if any(w in t for w in ["vampiro", "mascarada", "brujah", "camarilla", "malkavian", "sabbat", "toreador", "nosferatu"]):
            return "vtm_v20"
        if any(w in t for w in ["hombre lobo", "garou", "apocalipsis", "tribus garou", "werewolf"]):
            return "vtm_v20"  # WtA usa base VtM por ahora
        if any(w in t for w in ["pathfinder", "golarion", "paizo", "starfinder", "absalom"]):
            return "pathfinder_2e"
        if any(w in t for w in ["dungeon", "dungeons & dragons", "d&d", "cleric", "paladin", "warlock", "tiefling", "druid"]):
            return "dnd_5e"
        if any(w in t for w in ["call of cthulhu", "investigador", "cordura", "mythos", "cthulhu", "keeper", "lovecraft"]):
            return "coc_7e"
        if any(w in t for w in ["apocalypse world", "pbta", "powered by the apocalypse", "maestro de ceremonias", "movimientos"]):
            return "generic"
        return "generic"

    # ── Prompt principal del narrador ─────────────────────────
    def build_narrator_prompt(
        self,
        system_slug: str,
        vault_context: str = "",
        brain_context: str = "",
        character: dict = None,
        last_session: str = "",
        scene_location: str = "",
        active_npcs: str = "",
        active_fronts: str = "",
        clocks_summary: str = "",
        pacing_instruction: str = "",
        master_move: dict = None,
        world_status: str = "",
        investigation_hint: str = "",
        mechanical_resolution: str = "",
        scenes_info: str = "",
        forced_event: str = "",
        combat_status: str = "",
        state_context: str = "",
    ) -> str:
        sys = self.load_system(system_slug)
        base_prompt = sys.get("llm_system_prompt", "Eres un narrador de juego de rol.")
        voc = sys.get("vocabulario", {})

        sections = [base_prompt, NARRATIVE_PRINCIPLES, DICE_RESOLUTION_RULES, ENTITY_AUTO_SAVE_RULES, NARRATIVE_PROPOSAL_RULES]

        if mechanical_resolution:
            # Veredicto del Rule Arbiter: la matemática ya está resuelta en
            # Python; el LLM solo narra el resultado, nunca lo recalcula.
            sections.append(
                "RESOLUCIÓN MECÁNICA DE LA ÚLTIMA TIRADA "
                "(calculada por el sistema — NO la recalcules ni la contradigas; "
                "narrá exactamente este resultado):\n"
                f"{mechanical_resolution}"
            )

        if voc:
            voc_lines = []
            if voc.get("grupo_pc"):
                voc_lines.append(f"- Grupo de personajes: '{voc['grupo_pc']}'")
            if voc.get("eje_horror"):
                voc_lines.append(f"- Eje dramático: {voc['eje_horror']}")
            if voc.get("mecanica_moral"):
                voc_lines.append(f"- Mecánica moral: {voc['mecanica_moral']}")
            if voc_lines:
                sections.append("VOCABULARIO DEL SISTEMA:\n" + "\n".join(voc_lines))

        if state_context:
            sections.append(
                "ESTADO MUTABLE DE LA CAMPAÑA (fuente autoritativa; no lo inventes ni lo contradigas):\n"
                + state_context
            )

        if scene_location:
            sections.append(f"LOCACIÓN ACTUAL: {scene_location}")

        if last_session:
            sections.append(f"ÚLTIMA SESIÓN:\n{last_session}")

        if combat_status:
            sections.append(
                "COMBATE EN CURSO — respetá el orden de turnos, es el turno "
                f"de quien se indica a continuación:\n{combat_status}"
            )

        if clocks_summary:
            sections.append(f"RELOJES DE FRENTES:\n{clocks_summary}")

        if active_fronts:
            sections.append(f"FRENTES ACTIVOS:\n{active_fronts}")

        if active_npcs:
            sections.append(
                "NPCS EN EL MUNDO (si un NPC tiene 'psique', respetala en sus "
                "diálogos y decisiones — es su personalidad):\n"
                f"{active_npcs}"
            )

        if world_status:
            sections.append(f"ESTADO DEL MUNDO:\n{world_status}")

        if investigation_hint:
            sections.append(f"INVESTIGACIÓN:\n{investigation_hint}")

        if scenes_info:
            sections.append(f"ESCENAS DE LA AVENTURA:\n{scenes_info}")

        if forced_event:
            # Fronts reactivos (C3): el reloj se llenó por las acciones del
            # jugador — la amenaza estalla AHORA, no en downtime.
            sections.append(
                f"EVENTO FORZOSO — el reloj del frente '{forced_event}' se llenó "
                "por las acciones recientes del jugador. INTERRUMPÍ la escena "
                "actual EN ESTE TURNO con la consecuencia de esa amenaza "
                "(refuerzos, derrumbe, descubrimiento, estallido social — según "
                "el frente). No lo pospongas."
            )

        if pacing_instruction:
            sections.append(f"RITMO Y TONO:\n{pacing_instruction}")

        if master_move:
            move_text = f"{master_move.get('name', '')}: {master_move.get('instruction', '')}"
            sections.append(f"MOVIMIENTO DEL MÁSTER SUGERIDO:\n{move_text}")

        if brain_context:
            sections.append(
                "CEREBRO ROLISTICO — conocimiento general y conexiones relevantes "
                "(no sustituye reglas específicas del manual):\n" + brain_context
            )

        if vault_context:
            sections.append(f"CONTEXTO RECUPERADO (con procedencia):\n{vault_context}")

        if character:
            char_str = json.dumps(character, ensure_ascii=False, indent=2)
            sections.append(f"HOJA DEL PERSONAJE JUGADOR:\n{char_str}")

        return "\n\n".join(sections)

    # ── Prompt de creación de personaje ──────────────────────
    def build_char_creation_prompt(
        self,
        system_slug: str,
        manual_excerpt: str = "",
        brain_context: str = "",
    ) -> str:
        sys = self.load_system(system_slug)
        base_prompt = sys.get("llm_system_prompt", "Eres un narrador de juego de rol.")
        voc = sys.get("vocabulario", {})
        schema = sys.get("character_sheet_schema", {})

        sections = [
            base_prompt,
            "MODO ACTIVO: Creación de Personaje",
            f"Tu tarea es guiar al jugador para crear un {voc.get('personaje_term', 'personaje')} paso a paso.",
            "Instrucciones:",
            "- Presentá opciones numeradas con sabor narrativo, no solo mecánico.",
            "- Preguntá de a UNA sección por vez. No abrumés con demasiadas preguntas.",
            "- Cuando tengas datos concretos, incluilos en un bloque ```json``` al final de tu respuesta.",
            "- Adaptá el tono al sistema y al personaje que está emergiendo.",
        ]

        # Inyectar estructura esperada del JSON desde el schema
        if schema:
            schema_lines = ["ESTRUCTURA ESPERADA DEL JSON DEL PERSONAJE:"]
            for sec in schema.get("base_sections", []):
                keys = ", ".join(f["key"] for f in sec.get("fields", []))
                schema_lines.append(f"  {sec['name']}: {keys}")
            archetype_key = schema.get("archetype_key", "")
            cond = schema.get("conditional_sections", {})
            if archetype_key and cond:
                archetypes = ", ".join(cond.keys())
                schema_lines.append(
                    f"  Secciones adicionales según {archetype_key}: {archetypes}"
                )
                schema_lines.append(
                    f"  (incluí los campos de la sección correspondiente al {archetype_key} elegido)"
                )
            sections.append("\n".join(schema_lines))

        if brain_context:
            sections.append(
                "CEREBRO ROLISTICO — conceptos generales para orientar la creación "
                "sin reemplazar las reglas específicas del manual:\n" + brain_context
            )

        if manual_excerpt:
            sections.append(f"EXTRACTO DEL MANUAL (referencia específica):\n{manual_excerpt[:2000]}")

        return "\n\n".join(sections)

    # ── Prompt de decisión de NPC ─────────────────────────────
    def build_npc_action_prompt(
        self,
        system_slug: str,
        npc_data: dict,
        world_state: str,
    ) -> str:
        sys = self.load_system(system_slug)
        action_pool = sys.get("npc_acciones", [
            "observar y esperar",
            "reunirse con aliados",
            "avanzar agenda propia",
            "recolectar información",
        ])
        acciones_str = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(action_pool))

        npc_name = npc_data.get("nombre", "NPC desconocido")
        npc_agenda = npc_data.get("agenda", npc_data.get("rol", "agenda desconocida"))
        npc_faction = npc_data.get("clan", npc_data.get("faccion", npc_data.get("afiliacion", "")))

        return (
            f"Simulador de comportamiento de personaje.\n\n"
            f"NPC: {npc_name}"
            + (f" ({npc_faction})" if npc_faction else "")
            + f"\nAgenda: {npc_agenda}\n"
            f"Estado del mundo: {world_state}\n\n"
            f"Elegí UNA acción de la lista y explicá brevemente cómo la ejecuta este NPC:\n"
            f"{acciones_str}\n\n"
            f"Respondé EXACTAMENTE con este formato:\n"
            f"ACCIÓN: [nombre de la acción] | DESCRIPCIÓN: [cómo la ejecuta, máximo 25 palabras]"
        )
