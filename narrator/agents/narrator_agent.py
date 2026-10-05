"""
Narrator Agent — procesamiento post-respuesta del narrador.
Detecta tiradas de dados, extracciones de JSON, eventos importantes.
"""

import re

from narrator.core import json_repair


class NarratorAgent:
    _DICE_PATTERNS = [
        r"\b\d+[dD]\d+\b",
        r"tirá\s+\d+\s*[dD]\d+",
        r"lanzá\s+\d+\s*dado",
        r"roll\s+\d+[dD]\d+",
    ]

    _EVENT_KEYWORDS = [
        "tirada", "dado", "d20", "d10", "d6", "d8",
        "éxito", "fallo", "fracaso", "consecuencia",
        "herido", "muerto", "muere", "descubrió", "reveló",
        "traición", "acuerdo", "alianza", "emboscada",
    ]

    def extract_dice_request(self, text: str) -> str | None:
        for pat in self._DICE_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(0)
        return None

    # Sugerencia de tirada con notación explícita (ej. "tirá 5d10", "1D20+3").
    # Solo cuenta/caras — el atributo lo infiere el RuleArbiter por keywords.
    _RE_DICE_SUGGESTION = re.compile(r"\b(\d{1,2})\s*[dD]\s*(\d{1,3})\b")
    _VALID_DICE_SIDES = {4, 6, 8, 10, 12, 20, 100}

    def extract_dice_suggestion(self, text: str) -> "tuple[int, int] | None":
        """Extrae (cantidad, caras) de una sugerencia de tirada del narrador.
        Devuelve None si no hay match o si las caras no son un tipo de dado
        soportado por el panel (D4/D6/D8/D10/D12/D20/D100)."""
        m = self._RE_DICE_SUGGESTION.search(text)
        if not m:
            return None
        n, sides = int(m.group(1)), int(m.group(2))
        if sides not in self._VALID_DICE_SIDES or not (1 <= n <= 20):
            return None
        return n, sides

    def extract_narrative_proposal(self, text: str) -> dict | None:
        """Extrae exclusivamente el bloque técnico json-proposal."""
        match = re.search(r"\`\`\`json-proposal\\s*(.*?)\\s*\`\`\`", text, re.DOTALL | re.IGNORECASE)
        if not match:
            return None
        data = json_repair.try_parse(match.group(1))
        return data if isinstance(data, dict) else None

    def extract_character_json(self, text: str) -> dict | None:
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if not match:
            return None
        data = json_repair.try_parse(match.group(1))
        return data if isinstance(data, dict) else None

    # ── Auto-guardado de entidades + mutación de estado (Fase 11) ────
    # Convención de etiquetas técnicas emitidas por el narrador (ver
    # PromptBuilder.ENTITY_AUTO_SAVE_RULES) — nunca deben llegar al jugador,
    # se limpian con strip_system_tags() antes de mostrar/guardar el mensaje.
    _RE_ENTITY_BLOCK = re.compile(
        r"\[\[(NUEVO_NPC|NUEVA_LOCACION)\]\](.*?)\[\[/\1\]\]", re.DOTALL | re.IGNORECASE
    )
    _RE_STATE_TAG = re.compile(r"\[state:\s*([^\]]+)\]", re.IGNORECASE)
    # Pares clave=valor separados por espacios (no coma): el valor puede
    # contener espacios (ej. "reason=herida de espada") — cada match se
    # extiende hasta justo antes de la siguiente "palabra=" o el final.
    _RE_STATE_KV = re.compile(r"(\w+)=([^=]*?)(?=\s+\w+=|$)")

    def extract_new_entities(self, text: str) -> "list[tuple[str, dict]]":
        """Bloques [[NUEVO_NPC]]/[[NUEVA_LOCACION]] con líneas CLAVE: valor.
        Devuelve [(tipo, datos), ...] — tipo es 'npc' o 'locacion'; se
        descartan los bloques sin 'nombre'."""
        results = []
        for m in self._RE_ENTITY_BLOCK.finditer(text):
            tipo = "npc" if m.group(1).upper() == "NUEVO_NPC" else "locacion"
            data = {}
            for line in m.group(2).strip().splitlines():
                line = line.strip()
                if not line or ":" not in line:
                    continue
                key, _, value = line.partition(":")
                data[key.strip().lower()] = value.strip()
            if data.get("nombre"):
                results.append((tipo, data))
        return results

    def extract_state_mutations(self, text: str) -> "list[dict]":
        """Tags [state: field=hp delta=-3 reason=herida de espada] embebidos
        en la narración. Devuelve una lista de dicts {field, delta|value,
        reason}; descarta los tags sin 'field'."""
        mutations = []
        for m in self._RE_STATE_TAG.finditer(text):
            inner: dict = {}
            for key, value in self._RE_STATE_KV.findall(m.group(1).strip()):
                inner[key.strip().lower()] = value.strip()
            if inner.get("field"):
                mutations.append(inner)
        return mutations

    @staticmethod
    def character_field_specs(schema: dict | None) -> dict[str, dict]:
        """Extrae campos permitidos del schema, incluidos bloques condicionales."""
        specs = {}
        if not isinstance(schema, dict):
            return specs
        for section in schema.get("base_sections", []) or []:
            for field in section.get("fields", []) or []:
                if field.get("key"):
                    specs[field["key"]] = field
        for section_group in (schema.get("conditional_sections", {}) or {}).values():
            for section in section_group or []:
                for field in section.get("fields", []) or []:
                    if field.get("key"):
                        specs[field["key"]] = field
        return specs

    def apply_state_mutations(
        self,
        character: dict,
        mutations: "list[dict]",
        allowed_fields: "dict[str, dict] | None" = None,
    ) -> "list[str]":
        """Aplica propuestas del LLM solo sobre campos declarados por el schema.

        El LLM puede proponer un cambio narrativo, pero Python decide si el
        campo existe y normaliza límites numéricos declarados por el sistema.
        """
        specs = allowed_fields or {}
        changelog = []
        for mut in mutations:
            field = (mut.get("field") or "").strip()
            if not field or (specs and field not in specs):
                continue
            before = character.get(field)
            spec = specs.get(field, {})
            if "delta" in mut:
                try:
                    delta = int(mut["delta"])
                    current = int(before) if before is not None else 0
                    after = current + delta
                except (TypeError, ValueError):
                    continue
            elif "value" in mut:
                after = mut["value"]
                if spec.get("type") == "int":
                    try:
                        after = int(after)
                    except (TypeError, ValueError):
                        continue
            else:
                continue

            if spec.get("type") == "int":
                try:
                    after = int(after)
                except (TypeError, ValueError):
                    continue
                if spec.get("min") is not None:
                    after = max(int(spec["min"]), after)
                if spec.get("max") is not None:
                    after = min(int(spec["max"]), after)

            character[field] = after
            reason = mut.get("reason", "")
            reason_str = f" ({reason})" if reason else ""
            changelog.append(f"{field}: {before} → {after}{reason_str}")
        return changelog

    def strip_system_tags(self, text: str) -> str:
        """Quita las etiquetas técnicas del texto — son instrucciones para
        el sistema, el jugador nunca debe verlas en el chat. Normaliza el
        espacio en blanco que dejan al sacarlas (doble espacio inline,
        líneas en blanco de más donde iba un bloque de entidad)."""
        text = self._RE_ENTITY_BLOCK.sub("", text)
        text = self._RE_STATE_TAG.sub("", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def is_important_event(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in self._EVENT_KEYWORDS)

    def build_log_entry(self, text: str, timestamp: str) -> str:
        first_sentence = re.split(r"[.!?\n]", text.strip())[0]
        return f"[{timestamp}] {first_sentence[:120]}"
