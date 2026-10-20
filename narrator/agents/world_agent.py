"""
World Agent — simula el avance autónomo del mundo entre sesiones.
Lee los Frentes del vault, decide cuáles avanzan sus relojes, simula
acciones de NPCs de alta amenaza, y genera un informe de downtime narrativo.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from narrator.core.llm_client import LLMClient
from narrator.core.retriever import VaultRetriever
from narrator.core.state_manager import StateManager
from narrator.logger import logger

_ADVANCE_FRONTS_PROMPT = """Sos el Game Master de una crónica de rol. Pasaron días desde la última sesión.
Decidí qué Frentes activos avanzan su reloj y cuánto.

FRENTES ACTIVOS:
{fronts_summary}

NPCs DE ALTA AMENAZA:
{npcs_summary}

ESTADO ACTUAL: {world_state}

Reglas:
- Solo avanzan Frentes cuya lógica interna lo justifica.
- Máximo 3 Frentes avanzan por downtime.
- Los ticks van de 1 a 2 (1 = señal menor, 2 = escalación real).
- Si ningún Frente debe avanzar, devolvé [].

Para cada Frente que avance, devolvé un JSON con:
- nombre: nombre exacto del Frente tal como aparece arriba
- ticks: entero (1 o 2)
- razon: una oración que describa qué ocurrió en el mundo

Devolvé SOLO un array JSON válido. Sin texto adicional.

JSON:"""

_DOWNTIME_NARRATIVE_PROMPT = """Sos el narrador de una crónica de rol. Escribí un resumen atmosférico del período entre sesiones.

FRENTES QUE AVANZARON:
{advances_summary}

ACCIONES DE NPCs:
{npc_actions_summary}

Escribí 2-3 párrafos narrativos en segunda persona o tercera persona, describiendo cómo el mundo se movió mientras los personajes descansaban. Usá el tono apropiado para el sistema: {system_slug}.
No uses listas. Solo prosa atmosférica. Máximo 200 palabras."""


class WorldAgent:
    def __init__(
        self,
        llm: LLMClient,
        retriever: VaultRetriever,
        state: StateManager,
    ):
        self.llm = llm
        self.retriever = retriever
        self.state = state

    def _call(self, prompt: str, max_tokens: int = 400) -> str:
        return self.llm.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )

    # ── Lectura de frentes ────────────────────────────────────
    def _get_fronts_data(self) -> list[dict]:
        """Lee todos los frentes del vault con su estado de reloj."""
        return self.retriever.get_fronts_with_clocks()

    def _format_fronts_summary(self, fronts: list[dict]) -> str:
        lines = []
        for f in fronts:
            bar = "█" * f["tick"] + "░" * (f["max"] - f["tick"])
            estado = f.get("estado", "latente")
            lines.append(
                f"- {f['nombre']} [{bar} {f['tick']}/{f['max']}] "
                f"[{estado}] escasez: {f.get('escasez', '?')}"
            )
        return "\n".join(lines) if lines else "Sin frentes activos."

    # ── Avance de relojes en archivos MD ─────────────────────
    def _advance_clock_in_file(self, front_path: Path, ticks: int) -> int:
        """
        Reemplaza 'ticks' ocurrencias de '[ ]' por '[x]' en el archivo MD.
        Devuelve cuántos ticks se aplicaron realmente.
        """
        try:
            content = front_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return 0

        applied = 0
        for _ in range(ticks):
            new_content = content.replace("[ ]", "[x]", 1)
            if new_content == content:
                break  # no quedan casillas vacías
            content = new_content
            applied += 1

        if applied:
            front_path.write_text(content, encoding="utf-8")
        return applied

    def _find_front_file(self, nombre: str) -> Optional[Path]:
        """Busca el archivo MD de un frente por nombre (aproximado)."""
        fronts_dir = self.retriever.vault_path / "Frentes"
        if not fronts_dir.exists():
            return None
        nombre_norm = nombre.lower().replace(" ", "_")
        for f in fronts_dir.glob("*.md"):
            if nombre_norm in f.stem.lower() or f.stem.lower() in nombre_norm:
                return f
        # fallback: buscar por cualquier parte del nombre
        for f in fronts_dir.glob("*.md"):
            words = nombre.lower().split()
            if any(w in f.stem.lower() for w in words if len(w) > 3):
                return f
        return None

    # ── Decisión de qué frentes avanzan ──────────────────────
    def decide_front_advances(
        self,
        fronts: list[dict],
        system_slug: str,
        on_progress: Callable[[str], None] = None,
    ) -> list[dict]:
        """
        Llama al LLM para decidir qué frentes avanzan y cuánto.
        Devuelve lista de {"nombre", "ticks", "razon"}.
        """
        if not fronts:
            return []

        npcs = self.retriever.get_by_type("npc", max_files=8)
        npcs_summary = "\n".join(
            f"- {n['meta'].get('nombre','?')} [{n['meta'].get('amenaza','?')}]: {n['meta'].get('rol','?')}"
            for n in npcs
            if n["meta"].get("amenaza") in ("alta", "media")
        ) or "Sin NPCs de alta amenaza."

        world_state = (
            f"Sesión {self.state.get_session_number()}. "
            f"Locación: {self.state.get_location() or 'desconocida'}."
        )

        prompt = _ADVANCE_FRONTS_PROMPT.format(
            fronts_summary=self._format_fronts_summary(fronts),
            npcs_summary=npcs_summary,
            world_state=world_state,
        )

        on_progress and on_progress("  Consultando al LLM sobre avance de frentes...")
        response = self._call(prompt, max_tokens=400)

        # Parsear JSON
        for pattern in [r'```json\s*(\[.*?\])\s*```', r'```\s*(\[.*?\])\s*```', r'(\[.*?\])']:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group(1))
                    if isinstance(result, list):
                        return result[:3]
                except json.JSONDecodeError:
                    continue
        try:
            result = json.loads(response.strip())
            return result[:3] if isinstance(result, list) else []
        except Exception as e:
            logger.warning("WorldAgent: respuesta del LLM no es JSON válido: %s", e)
            return []

    # ── Aplicar avances al vault ──────────────────────────────
    def apply_advances(
        self,
        advances: list[dict],
        on_progress: Callable[[str], None] = None,
    ) -> list[dict]:
        """
        Aplica los avances de reloj a los archivos MD del vault.
        Devuelve lista de avances realmente aplicados con info adicional.
        """
        applied = []
        for adv in advances:
            nombre = adv.get("nombre", "")
            ticks = int(adv.get("ticks", 1))
            razon = adv.get("razon", "")

            front_path = self._find_front_file(nombre)
            if not front_path:
                on_progress and on_progress(f"  ⚠ No encontré archivo para: {nombre}")
                continue

            ticks_aplicados = self._advance_clock_in_file(front_path, ticks)
            if ticks_aplicados:
                on_progress and on_progress(
                    f"  ⏰ {nombre}: +{ticks_aplicados} tick(s) — {razon}"
                )
                applied.append({
                    "nombre": nombre,
                    "ticks": ticks_aplicados,
                    "razon": razon,
                    "path": str(front_path),
                })
            else:
                on_progress and on_progress(f"  ✓ {nombre}: reloj ya completo.")

        return applied

    # ── Narrativa de downtime ─────────────────────────────────
    def generate_downtime_narrative(
        self,
        advances: list[dict],
        npc_actions: list[dict],
        system_slug: str,
    ) -> str:
        """Genera prosa narrativa del período de downtime."""
        if not advances and not npc_actions:
            return "El mundo permanece en calma tensa. Nada se mueve en la oscuridad... todavía."

        advances_summary = "\n".join(
            f"- {a['nombre']}: {a['razon']}" for a in advances
        ) or "Ningún frente avanzó."

        npc_summary = "\n".join(
            f"- {n.get('npc','?')}: {n.get('description', n.get('action','?'))}"
            for n in npc_actions
        ) or "Sin actividad NPC relevante."

        prompt = _DOWNTIME_NARRATIVE_PROMPT.format(
            advances_summary=advances_summary,
            npc_actions_summary=npc_summary,
            system_slug=system_slug,
        )
        return self._call(prompt, max_tokens=350)

    # ── Escribir informe de downtime ──────────────────────────
    def write_downtime_report(
        self,
        session_number: int,
        narrative: str,
        advances: list[dict],
        npc_actions: list[dict],
    ) -> Path:
        """Escribe el informe de downtime en vault/Sesiones/."""
        sessions_dir = self.retriever.vault_path / "Sesiones"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        path = sessions_dir / f"Downtime_Sesion_{session_number:02d}_{date_str}.md"

        fronts_section = ""
        for a in advances:
            fronts_section += f"- **{a['nombre']}** (+{a['ticks']} tick): {a['razon']}\n"

        npcs_section = ""
        for n in npc_actions:
            npcs_section += f"- **{n.get('npc','?')}**: {n.get('description', n.get('action','?'))}\n"

        content = (
            f"---\n"
            f"tipo: downtime\n"
            f"sesion: {session_number}\n"
            f'fecha: "{date_str}"\n'
            f'tags: ["downtime", "entre-sesiones"]\n'
            f"---\n\n"
            f"# Downtime — Entre Sesiones {session_number} y {session_number + 1}\n\n"
            f"## Narrativa\n\n{narrative}\n\n"
            f"## Frentes Avanzados\n\n{fronts_section or '_Ninguno._'}\n\n"
            f"## Acciones de NPCs\n\n{npcs_section or '_Sin actividad relevante._'}\n"
        )
        path.write_text(content, encoding="utf-8")
        return path

    # ── Pipeline completo ─────────────────────────────────────
    def run(
        self,
        system_slug: str = "generic",
        session_number: int = 1,
        on_progress: Callable[[str], None] = None,
    ) -> dict:
        """
        Pipeline completo de downtime entre sesiones.
        Devuelve resumen de lo que ocurrió.
        """
        on_progress and on_progress("Iniciando avance del mundo entre sesiones...")

        # 1. Leer frentes actuales
        fronts = self._get_fronts_data()
        on_progress and on_progress(f"  {len(fronts)} frentes encontrados en el vault.")

        # 2. Decidir cuáles avanzan
        advances_planned = self.decide_front_advances(fronts, system_slug, on_progress)
        on_progress and on_progress(f"  {len(advances_planned)} frentes seleccionados para avanzar.")

        # 3. Aplicar avances en los archivos MD
        advances_applied = self.apply_advances(advances_planned, on_progress)

        # 4. Simular acciones de NPCs
        on_progress and on_progress("  Simulando acciones de NPCs...")
        npc_entries = self.retriever.get_by_type("npc", max_files=10)
        npcs_to_simulate = [
            e for e in npc_entries
            if e["meta"].get("amenaza") in ("alta", "media")
        ]

        npc_actions = []
        for entry in npcs_to_simulate[:4]:  # máximo 4 NPCs por downtime
            meta = entry["meta"]
            nombre = meta.get("nombre", "?")
            rol = meta.get("rol", "actúa según su agenda")
            agenda = meta.get("agenda", "")
            action_text = f"{rol}. {agenda}"[:120] if agenda else rol
            npc_actions.append({"npc": nombre, "action": "agendas", "description": action_text})
            self.state.add_active_npc(nombre, action_text)
            on_progress and on_progress(f"  NPC simulado: {nombre}")

        # 5. Generar narrativa
        on_progress and on_progress("  Generando narrativa de downtime...")
        narrative = self.generate_downtime_narrative(advances_applied, npc_actions, system_slug)

        # 6. Escribir informe
        report_path = self.write_downtime_report(
            session_number, narrative, advances_applied, npc_actions
        )
        on_progress and on_progress(f"  Informe escrito: {report_path.name}")

        # 7. Guardar estado
        self.state.add_session_summary(
            resumen=f"Downtime: {len(advances_applied)} frentes avanzaron.",
            consecuencias=[a["razon"] for a in advances_applied],
        )
        self.state.clear_downtime()
        self.state.save()

        on_progress and on_progress("¡Mundo avanzado!")

        return {
            "frentes_avanzados": len(advances_applied),
            "npcs_simulados": len(npc_actions),
            "informe": str(report_path),
            "narrativa": narrative,
            "advances": advances_applied,
        }
