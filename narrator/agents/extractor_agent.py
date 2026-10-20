"""
Extractor Agent — convierte texto de PDF en un vault de campaña jugable.
Implementa las fases 0-2 del Prompt_Generador_Cronica.md de forma automática.

Pipeline:
  texto PDF → extrae NPCs → extrae Locaciones → extrae Facciones
            → genera Frentes → genera Dashboard → indexa semánticamente
"""

import json
import re
from pathlib import Path
from typing import Callable

from narrator.core import json_repair
from narrator.core.embedder import Embedder
from narrator.core.llm_client import LLMClient
from narrator.core.npc_psyche import validate_psyche
from narrator.core.prompt_builder import PromptBuilder

# ── Plantillas de frontmatter por tipo ────────────────────────────────────────

# Metadata de presentación (Fase 8) derivada de la amenaza — sin pedirle
# más campos al LLM extractor, que ya devuelve bastante por NPC.
_AMENAZA_COLOR = {"alta": "rojo", "media": "amarillo", "baja": "verde"}
_AMENAZA_ICONO = {"alta": "🔴", "media": "🟡", "baja": "🟢"}


def _npc_frontmatter(data: dict, system_slug: str) -> str:
    slug_tags = {
        "vtm_v20": ["npc", "vampiro"],
        "dnd_5e": ["npc", "personaje"],
        "coc_7e": ["npc", "investigador"],
        "pathfinder_2e": ["npc", "personaje"],
        "generic": ["npc"],
    }
    tags = slug_tags.get(system_slug, ["npc"])
    nombre = data.get("nombre", "NPC Desconocido")

    lines = [
        "---",
        "tipo: npc",
        f'nombre: "{nombre}"',
    ]
    for key in ["clan", "raza", "ancestro", "ocupacion"]:
        if data.get(key):
            lines.append(f'{key}: "{data[key]}"')
    for key in ["generacion", "nivel", "nivel_poder"]:
        if data.get(key) is not None:
            lines.append(f"{key}: {data[key]}")
    for key in ["faccion", "cofradia", "afiliacion"]:
        if data.get(key):
            lines.append(f'{key}: "[[{data[key]}]]"')
    if data.get("rol"):
        lines.append(f'rol: "{data["rol"]}"')
    if data.get("amenaza"):
        lines.append(f'amenaza: {data["amenaza"]}')
    # Metadata de token (Fase 8): color/icono por nivel de amenaza, estado
    # narrativo inicial y condiciones apilables — editables en juego, útiles
    # tanto en el resumen de NPCs activos como en un futuro modo visual.
    amenaza_val = str(data.get("amenaza", "")).lower()
    lines.append(f'color: "{_AMENAZA_COLOR.get(amenaza_val, "gris")}"')
    lines.append(f'icono: "{_AMENAZA_ICONO.get(amenaza_val, "⚪")}"')
    lines.append('estado: "vivo"')
    lines.append("condiciones: []")
    # Psicología (C1): arquetipo dominante + rasgos dimensionales validados
    arquetipo, rasgos = validate_psyche(data.get("arquetipo"), data.get("rasgos"))
    if arquetipo:
        lines.append(f'arquetipo: "{arquetipo}"')
    if rasgos:
        lines.append("rasgos:")
        lines += [f"  {k}: {v}" for k, v in rasgos.items()]
    lines.append(f"tags: {json.dumps(tags, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def _location_frontmatter(data: dict) -> str:
    nombre = data.get("nombre", "Locación")
    lines = [
        "---",
        "tipo: locacion",
        f'nombre: "{nombre}"',
    ]
    if data.get("distrito"):
        lines.append(f'distrito: "[[{data["distrito"]}]]"')
    if data.get("control"):
        lines.append(f'control: "[[{data["control"]}]]"')
    tension = data.get("tension", "media")
    lines += [
        f"tension: {tension}",
        "secretos: false",
        'tags: ["locacion"]',
        "---",
    ]
    return "\n".join(lines)


def _faction_frontmatter(data: dict) -> str:
    nombre = data.get("nombre", "Facción")
    lines = [
        "---",
        "tipo: cofradia",
        f'nombre: "{nombre}"',
    ]
    if data.get("lider"):
        lines.append(f'lider: "[[{data["lider"]}]]"')
    if data.get("territorio"):
        lines.append(f'territorio: "[[{data["territorio"]}]]"')
    # Fase 14 — modelo de organización más rico: metas/métodos/recursos/
    # influencia/relaciones, no solo lider+territorio.
    if data.get("agenda"):
        lines.append(f'metas: "{data["agenda"]}"')
    if data.get("metodos"):
        lines.append(f'metodos: "{data["metodos"]}"')
    recursos = data.get("recursos") or []
    if recursos:
        lines.append(f"recursos: {json.dumps(recursos, ensure_ascii=False)}")
    if data.get("influencia"):
        lines.append(f'influencia: "{data["influencia"]}"')
    relaciones = data.get("relaciones") or []
    if relaciones:
        lines.append(f"relaciones: {json.dumps(relaciones, ensure_ascii=False)}")
    lines += [
        'estado: "estable"',
        'tags: ["cofradia", "faccion"]',
        "---",
    ]
    return "\n".join(lines)


_EVENT_TYPES_VALIDOS = ("combate", "persecucion", "horror", "exploracion", "descanso")


def _front_frontmatter(data: dict) -> str:
    nombre = data.get("nombre", "Frente")
    lines = [
        "---",
        "tipo: frente",
        f'nombre: "{nombre}"',
        f'escasez: "{data.get("escasez", "seguridad")}"',
        'estado: "latente"',
    ]
    # Reactividad (C3): tipos de acción del jugador que aceleran el reloj
    reactivo = data.get("reactivo_a")
    if isinstance(reactivo, list):
        validos = [e for e in reactivo if e in _EVENT_TYPES_VALIDOS]
        if validos:
            lines.append(f"reactivo_a: {json.dumps(validos, ensure_ascii=False)}")
    lines += [
        'tags: ["frente", "amenaza"]',
        "---",
    ]
    return "\n".join(lines)


# ── Prompts de extracción ─────────────────────────────────────────────────────

_EXTRACT_NPCS_PROMPT = """Analizá este texto de manual de rol y extraé todos los personajes / NPCs importantes.

Para cada uno, devolvé un JSON con estos campos (usá null si no aparece):
- nombre (string)
- clan / raza / ocupacion (string, el que aplique al sistema)
- generacion / nivel (integer, si aplica)
- rol (string, 1 línea: qué papel cumple)
- agenda (string, qué quiere lograr)
- secreto (string, qué oculta)
- faccion (string, organización a la que pertenece)
- amenaza (string: "alta", "media" o "baja")
- descripcion (string, 2-3 oraciones de descripción)
- arquetipo (string, UNO de: self, persona, sombra, anima_animus, heroe, sabio, trickster, madre, padre, nino_divino, gobernante, rebelde — el que mejor capture su personalidad)
- rasgos (objeto con valores 0.0 a 1.0 para: extraversion, amabilidad, neuroticismo, impulsividad, agresividad, empatia)

Devolvé SOLO un array JSON válido. Sin texto adicional. Sin comillas extras. Sin markdown.

TEXTO:
{text}

JSON:"""

_REGENERATE_NPC_PROMPT = """Sos un generador de NPCs para un juego de rol{system_hint}.
Tenés este NPC existente:
{npc_json}

Regenerá el NPC completo, coherente y creíble, pero SIN MODIFICAR estos campos
(mantenelos EXACTAMENTE como están en el original): {locked_keys}

Devolvé el mismo formato de campos que el NPC existente (agregá los que falten:
nombre, clan/raza/ocupacion, generacion/nivel, rol, agenda, secreto, faccion,
amenaza, descripcion, arquetipo, rasgos).
Devolvé SOLO un objeto JSON válido. Sin texto adicional. Sin markdown.

JSON:"""

_EXTRACT_LOCATIONS_PROMPT = """Analizá este texto y extraé todas las locaciones / lugares importantes.

Para cada uno, devolvé un JSON con:
- nombre (string)
- distrito / zona (string, si aplica)
- control (string, quién controla el lugar)
- tension (string: "alta", "media" o "baja")
- descripcion (string, 2-3 oraciones atmosféricas)
- secreto (string, qué oculta)

Devolvé SOLO un array JSON válido. Sin texto adicional.

TEXTO:
{text}

JSON:"""

_EXTRACT_FACTIONS_PROMPT = """Analizá este texto y extraé todas las facciones / organizaciones / grupos importantes.

Para cada uno, devolvé un JSON con:
- nombre (string)
- lider (string, nombre del líder principal)
- territorio (string, donde operan)
- agenda (string, qué busca la facción)
- metodos (string, cómo persigue su agenda: diplomacia, violencia, infiltración, etc.)
- recursos (lista de strings: dinero, contactos, armamento, información, etc.)
- influencia (string: "alta", "media" o "baja")
- relaciones (lista de objetos {{faccion: string, tipo: "aliada"|"enemiga"}} con otras facciones mencionadas en el texto, si las hay)
- miembros_notables (lista de strings)
- descripcion (string, 2-3 oraciones)

Devolvé SOLO un array JSON válido. Sin texto adicional.

TEXTO:
{text}

JSON:"""

_GENERATE_FRONTS_PROMPT = """Sos un diseñador de crónicas de rol. Basándote en estos NPCs y facciones, generá 3-4 Frentes (amenazas activas que presionan el mundo).

NPCs y facciones disponibles:
{entities}

Para cada Frente, devolvé un JSON con:
- nombre (string, nombre evocador)
- escasez (string, qué recurso emocional se agota: seguridad, fe, verdad, control, etc.)
- descripcion (string, en qué consiste la amenaza)
- npcs_involucrados (lista de nombres de NPCs ya extraídos)
- perdicion (string, qué pasa si nadie actúa)
- reactivo_a (lista de tipos de acción del jugador que aceleran esta amenaza; elegí entre: combate, persecucion, horror, exploracion, descanso — ej. una cacería reacciona a "combate" y "persecucion")

Devolvé SOLO un array JSON válido. Sin texto adicional.

JSON:"""


# ── Funciones auxiliares ──────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r'\s+', "_", name.strip())
    return name[:80] or "sin_nombre"


def _strip_fence(text: str) -> str:
    """Quita un fence ```json/``` de apertura y/o cierre, aunque uno de los
    dos falte (respuesta cortada a mitad de generación por max_tokens)."""
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'```\s*$', '', text)
    return text.strip()


def _parse_json_response(text: str) -> list:
    for pattern in [
        r'```json\s*(\[.*?\])\s*```',
        r'```\s*(\[.*?\])\s*```',
        r'(\[.*?\])',
    ]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            result = json_repair.try_parse(match.group(1))
            if isinstance(result, list):
                return result

    result = json_repair.try_parse(_strip_fence(text))
    return result if isinstance(result, list) else []


def _parse_json_object_response(text: str) -> "dict | None":
    """Como _parse_json_response pero para un único objeto JSON (no array)."""
    for pattern in [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
        r'(\{.*\})',
    ]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            result = json_repair.try_parse(match.group(1))
            if isinstance(result, dict) and result:
                return result

    result = json_repair.try_parse(_strip_fence(text))
    return result if isinstance(result, dict) and result else None


def _build_npc_body(data: dict) -> str:
    nombre = data.get("nombre", "?")
    lines = [f"# {nombre}", ""]
    if data.get("descripcion"):
        lines += ["## Concepto", data["descripcion"], ""]
    if data.get("agenda"):
        lines += ["## Agenda", f"- **Objetivo:** {data['agenda']}", ""]
    if data.get("secreto"):
        lines += ["## Secretos", f"1. {data['secreto']}", ""]
    lines += ["## Notas de Sesión", ""]
    return "\n".join(lines)


def _build_location_body(data: dict) -> str:
    nombre = data.get("nombre", "?")
    lines = [f"# {nombre}", ""]
    if data.get("descripcion"):
        lines += ["## Descripción", data["descripcion"], ""]
    if data.get("control"):
        lines += [f"**Control:** [[{data['control']}]]", ""]
    if data.get("secreto"):
        lines += ["## Secretos", f"1. {data['secreto']}", ""]
    lines += ["## Notas de Sesión", ""]
    return "\n".join(lines)


def _build_faction_body(data: dict) -> str:
    nombre = data.get("nombre", "?")
    lines = [f"# {nombre}", ""]
    if data.get("descripcion"):
        lines += ["## Identidad", data["descripcion"], ""]
    if data.get("agenda"):
        lines += ["## Agenda Activa", f"- {data['agenda']}", ""]
    miembros = data.get("miembros_notables", [])
    if miembros:
        lines += ["## Miembros Notables"]
        for m in miembros:
            lines.append(f"- [[{m}]]")
        lines.append("")
    lines += ["## Notas de Sesión", ""]
    return "\n".join(lines)


def _build_front_body(data: dict) -> str:
    nombre = data.get("nombre", "?")
    lines = [
        f"# Frente: {nombre}", "",
        "## Escasez Fundamental",
        data.get("descripcion", ""), "",
        "## Presagios (Countdown)",
        "1. [ ] Señal menor",
        "2. [ ] Escalación",
        "3. [ ] Crisis",
        "4. [ ] Punto de no retorno",
        "5. [ ] Último recurso",
        f"6. [ ] **PERDICIÓN:** {data.get('perdicion', 'Consecuencia final')}",
        "",
        "## NPCs Involucrados",
    ]
    for npc in data.get("npcs_involucrados", []):
        lines.append(f"- [[{npc}]]")
    lines += ["", "## Registro de Avance", ""]
    return "\n".join(lines)


def _build_dashboard(
    npcs: list, locations: list, factions: list, fronts: list, system_name: str
) -> str:
    npc_links = " | ".join(f"[[{n.get('nombre', '?')}]]" for n in npcs[:10])
    loc_links = " | ".join(f"[[{loc.get('nombre', '?')}]]" for loc in locations[:8])
    faction_links = " | ".join(f"[[{f.get('nombre', '?')}]]" for f in factions[:6])
    front_links = " | ".join(f"[[Frente_{_safe_filename(f.get('nombre', '?'))}]]" for f in fronts)

    return f"""# Dashboard de Campaña

**Sistema:** {system_name}

---

## Estado de la Ciudad

> Campaña recién iniciada. Actualizá este bloque con el estado actual.

---

## NPCs Principales

{npc_links if npc_links else '_Sin NPCs extraídos_'}

---

## Locaciones

{loc_links if loc_links else '_Sin locaciones extraídas_'}

---

## Facciones

{faction_links if faction_links else '_Sin facciones extraídas_'}

---

## Frentes Activos

{front_links if front_links else '_Sin frentes generados_'}

---

## Prep de Próxima Sesión

- [ ] ¿Qué Frentes avanzaron?
- [ ] ¿Qué NPCs actuaron?
- [ ] Bangs preparados
- [ ] Story Circle: confort → necesidad → ir → encontrar → sufrir → cambio
"""


# ── Agente principal ──────────────────────────────────────────────────────────

class ExtractorAgent:
    def __init__(self, llm: LLMClient, builder: PromptBuilder):
        self.llm = llm
        self.builder = builder
        self._embedder = Embedder()

    def _call(self, prompt: str, max_tokens: int = 800) -> str:
        return self.llm.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )

    def _chunk_text(self, text: str, chunk_size: int = 3000, overlap: int = 200) -> list[str]:
        # El texto del manual es dato, no instrucciones (ver injection_guard).
        from narrator.core.injection_guard import sanitize_document_text

        text = sanitize_document_text(text).text
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - overlap if end < len(text) else end
        return chunks

    # ── Extracción por tipo ────────────────────────────────────────────────────

    def extract_npcs(self, text: str, on_progress: Callable[[str], None] = None) -> list[dict]:
        on_progress and on_progress("Extrayendo NPCs...")
        chunks = self._chunk_text(text, chunk_size=3500)
        all_npcs: dict[str, dict] = {}

        for i, chunk in enumerate(chunks):
            on_progress and on_progress(f"  Analizando chunk {i+1}/{len(chunks)} para NPCs...")
            prompt = _EXTRACT_NPCS_PROMPT.format(text=chunk)
            response = self._call(prompt, max_tokens=600)
            parsed = _parse_json_response(response)
            for npc in parsed:
                nombre = npc.get("nombre", "").strip()
                if nombre and nombre not in all_npcs:
                    all_npcs[nombre] = npc

        return list(all_npcs.values())

    def regenerate_npc(self, npc: dict, locked_fields: "dict | None" = None,
                        system_name: str = "") -> "dict | None":
        """Regenera un NPC existente vía LLM manteniendo `locked_fields` fijos
        (ej. {"clan": "Nosferatu"}). Los campos fijados se fuerzan al final
        por si el LLM los ignora. Devuelve None si no se pudo parsear."""
        locked_fields = locked_fields or {}
        hint = f" ({system_name})" if system_name else ""
        prompt = _REGENERATE_NPC_PROMPT.format(
            system_hint=hint,
            npc_json=json.dumps(npc, ensure_ascii=False, indent=2),
            locked_keys=", ".join(locked_fields.keys()) or "(ninguno)",
        )
        response = self._call(prompt, max_tokens=600)
        regenerated = _parse_json_object_response(response)
        if not regenerated:
            return None
        regenerated.update(locked_fields)
        return regenerated

    def extract_locations(self, text: str, on_progress: Callable[[str], None] = None) -> list[dict]:
        on_progress and on_progress("Extrayendo locaciones...")
        chunks = self._chunk_text(text, chunk_size=3500)
        all_locs: dict[str, dict] = {}

        for i, chunk in enumerate(chunks):
            on_progress and on_progress(f"  Analizando chunk {i+1}/{len(chunks)} para locaciones...")
            prompt = _EXTRACT_LOCATIONS_PROMPT.format(text=chunk)
            response = self._call(prompt, max_tokens=500)
            parsed = _parse_json_response(response)
            for loc in parsed:
                nombre = loc.get("nombre", "").strip()
                if nombre and nombre not in all_locs:
                    all_locs[nombre] = loc

        return list(all_locs.values())

    def extract_factions(self, text: str, on_progress: Callable[[str], None] = None) -> list[dict]:
        on_progress and on_progress("Extrayendo facciones...")
        chunks = self._chunk_text(text, chunk_size=3500)
        all_factions: dict[str, dict] = {}

        for i, chunk in enumerate(chunks):
            on_progress and on_progress(f"  Analizando chunk {i+1}/{len(chunks)} para facciones...")
            prompt = _EXTRACT_FACTIONS_PROMPT.format(text=chunk)
            response = self._call(prompt, max_tokens=500)
            parsed = _parse_json_response(response)
            for f in parsed:
                nombre = f.get("nombre", "").strip()
                if nombre and nombre not in all_factions:
                    all_factions[nombre] = f

        return list(all_factions.values())

    def generate_fronts(
        self, npcs: list[dict], factions: list[dict],
        on_progress: Callable[[str], None] = None,
    ) -> list[dict]:
        on_progress and on_progress("Generando Frentes (amenazas activas)...")
        entity_summary = ""
        for n in npcs[:8]:
            entity_summary += f"NPC: {n.get('nombre','?')} — {n.get('rol','?')} — agenda: {n.get('agenda','?')}\n"
        for f in factions[:5]:
            entity_summary += f"Facción: {f.get('nombre','?')} — {f.get('agenda','?')}\n"

        prompt = _GENERATE_FRONTS_PROMPT.format(entities=entity_summary)
        response = self._call(prompt, max_tokens=700)
        return _parse_json_response(response)

    # ── Escritura de archivos ──────────────────────────────────────────────────

    def _init_vault_structure(self, vault_path: Path, template_path: Path):
        if template_path.exists():
            for item in template_path.iterdir():
                dest = vault_path / item.name
                if item.is_dir() and not dest.exists():
                    dest.mkdir(parents=True, exist_ok=True)
        else:
            for folder in ["NPCs", "Locaciones", "Cofradias", "Frentes",
                           "Misterios", "Recursos", "Sesiones", "Notas"]:
                (vault_path / folder).mkdir(parents=True, exist_ok=True)

    def _write_file(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_npcs(self, npcs: list[dict], vault_path: Path, system_slug: str) -> int:
        written = 0
        for npc in npcs:
            nombre = npc.get("nombre", "").strip()
            if not nombre:
                continue
            fm = _npc_frontmatter(npc, system_slug)
            body = _build_npc_body(npc)
            filename = _safe_filename(nombre) + ".md"
            self._write_file(vault_path / "NPCs" / filename, fm + "\n\n" + body)
            written += 1
        return written

    def write_locations(self, locations: list[dict], vault_path: Path) -> int:
        written = 0
        for loc in locations:
            nombre = loc.get("nombre", "").strip()
            if not nombre:
                continue
            fm = _location_frontmatter(loc)
            body = _build_location_body(loc)
            filename = _safe_filename(nombre) + ".md"
            self._write_file(vault_path / "Locaciones" / filename, fm + "\n\n" + body)
            written += 1
        return written

    def write_factions(self, factions: list[dict], vault_path: Path) -> int:
        written = 0
        for faction in factions:
            nombre = faction.get("nombre", "").strip()
            if not nombre:
                continue
            fm = _faction_frontmatter(faction)
            body = _build_faction_body(faction)
            filename = _safe_filename(nombre) + ".md"
            self._write_file(vault_path / "Cofradias" / filename, fm + "\n\n" + body)
            written += 1
        return written

    def write_fronts(self, fronts: list[dict], vault_path: Path) -> int:
        written = 0
        for front in fronts:
            nombre = front.get("nombre", "").strip()
            if not nombre:
                continue
            fm = _front_frontmatter(front)
            body = _build_front_body(front)
            filename = "Frente_" + _safe_filename(nombre) + ".md"
            self._write_file(vault_path / "Frentes" / filename, fm + "\n\n" + body)
            written += 1
        return written

    def write_dashboard(
        self, npcs: list, locations: list, factions: list, fronts: list,
        vault_path: Path, system_name: str,
    ):
        content = _build_dashboard(npcs, locations, factions, fronts, system_name)
        self._write_file(vault_path / "00_Dashboard.md", content)

    def _build_semantic_index(self, vault_path: Path, on_progress=None) -> None:
        """Indexa semánticamente todos los archivos del vault recién creado."""
        if not self._embedder.is_available():
            return
        on_progress and on_progress("Indexando vault para búsqueda semántica...")
        index = self._embedder.build_index_for_vault(vault_path, on_progress)
        if index:
            on_progress and on_progress(f"  Índice semántico: {len(index)} archivos.")

    # ── Pipeline completo ──────────────────────────────────────────────────────

    def run(
        self,
        pdf_text: str,
        system_slug: str,
        system_name: str,
        vault_path: str = "./vault",
        template_path: str = "./data/vault_template",
        on_progress: Callable[[str], None] = None,
    ) -> dict:
        """
        Pipeline completo: texto PDF → vault jugable → índice semántico.
        Devuelve un resumen con conteos de lo generado.
        """
        vp = Path(vault_path)
        tp = Path(template_path)

        on_progress and on_progress("Inicializando estructura del vault...")
        self._init_vault_structure(vp, tp)

        npcs = self.extract_npcs(pdf_text, on_progress)
        locations = self.extract_locations(pdf_text, on_progress)
        factions = self.extract_factions(pdf_text, on_progress)
        fronts = self.generate_fronts(npcs, factions, on_progress)

        on_progress and on_progress("Escribiendo archivos del vault...")
        n_npcs = self.write_npcs(npcs, vp, system_slug)
        n_locs = self.write_locations(locations, vp)
        n_facs = self.write_factions(factions, vp)
        n_fronts = self.write_fronts(fronts, vp)
        self.write_dashboard(npcs, locations, factions, fronts, vp, system_name)

        self._build_semantic_index(vp, on_progress)

        on_progress and on_progress("¡Vault construido!")

        return {
            "npcs": n_npcs,
            "locaciones": n_locs,
            "facciones": n_facs,
            "frentes": n_fronts,
            "vault_path": str(vp.resolve()),
        }
