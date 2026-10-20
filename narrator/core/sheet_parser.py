"""Parser de planillas de personaje: texto extraído de un PDF → dict vía LLM.

El jugador adjunta su planilla en PDF; el texto se extrae con PyMuPDF y el
LLM lo estructura a un JSON plano que puebla la hoja de personaje. La
creación de personaje in-app queda fuera de alcance (ver roadmap Fase A).
"""

import re

from narrator.core import json_repair
from narrator.logger import logger

_PROMPT_TEMPLATE = """Sos un extractor de datos para un juego de rol{system_hint}.
El siguiente texto proviene del PDF de la planilla de un personaje.
Convertilo a UN único objeto JSON en español con claves en snake_case
(ej.: nombre, clan, clase, atributos, habilidades, disciplinas, equipo, trasfondo).
- Usá números para los valores numéricos.
- Agrupá atributos y habilidades en objetos anidados.
- NO inventes datos que no estén en la planilla.
- Respondé SOLO con el bloque JSON, sin texto adicional.

=== PLANILLA ===
{sheet_text}
"""


def extract_json_block(raw: str) -> "dict | None":
    """Extrae el primer objeto JSON válido de una respuesta del LLM."""
    if not raw:
        return None
    candidates = []
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    brace = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for cand in candidates:
        data = json_repair.try_parse(cand)
        if isinstance(data, dict) and data:
            return data
    return None


def extract_form_fields(pdf_path: str) -> dict:
    """Extrae campos de formulario rellenable (AcroForm) de un PDF vía
    PyMuPDF (Fase 17) — vía alternativa a texto+LLM cuando el jugador tiene
    la ficha oficial en PDF rellenable: más rápida y sin depender del LLM.
    Devuelve {} si el PDF no tiene campos (no es un formulario) o falla."""
    import pymupdf as fitz

    fields: dict = {}
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error(f"No se pudo abrir el PDF para extraer campos: {e}", exc_info=True)
        return fields
    try:
        for page in doc:
            for widget in (page.widgets() or []):
                if widget.field_name:
                    fields[widget.field_name] = widget.field_value
    finally:
        doc.close()
    return fields


def map_form_fields(fields: dict, field_map: dict) -> dict:
    """Renombra campos crudos del PDF (ej. 'Str-1') a claves de la ficha de
    personaje (ej. 'fuerza') según `field_map` {nombre_pdf: clave_ficha}.
    Los campos sin mapeo o sin valor se descartan — no se inventan claves."""
    result = {}
    for pdf_name, value in fields.items():
        key = field_map.get(pdf_name)
        if key and value not in (None, ""):
            result[key] = value
    return result


def parse_character_sheet(sheet_text: str, llm, system_name: str = "") -> "dict | None":
    """Estructura el texto de una planilla como dict de personaje.

    Devuelve None si el LLM falla o la respuesta no contiene JSON válido.
    """
    hint = f" ({system_name})" if system_name else ""
    prompt = _PROMPT_TEMPLATE.format(system_hint=hint, sheet_text=sheet_text[:12000])
    try:
        raw = llm.chat([{"role": "user", "content": prompt}])
    except Exception as e:
        logger.error(f"Error llamando al LLM para parsear planilla: {e}", exc_info=True)
        return None
    char = extract_json_block(raw or "")
    if char is None:
        logger.error(f"Planilla no parseable; respuesta del LLM: {(raw or '')[:400]}")
    return char
