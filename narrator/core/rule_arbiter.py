"""Rule Arbiter — resolución mecánica determinística de tiradas.

El LLM no calcula reglas. El arbiter mapea la acción del jugador a un
atributo/habilidad de la planilla (JSON cargado en Fase A), aplica la
mecánica declarada en la sección ``resolution`` del YAML del sistema y
produce un veredicto YA RESUELTO que el narrador solo describe.

Mecánicas soportadas:
- ``d20_vs_dc``   D&D 5e / Pathfinder 2e: d20 + modificador vs CD.
- ``pool_d10``    VtM V20: pool de d10 vs dificultad, éxitos netos (los 1 restan).
- ``percentil``   CoC 7e: tirada por debajo del valor (normal/difícil/extremo).
- ``ratio``       Genérico: bandas PbtA-like por ratio del máximo.

La dificultad sale de la escalera estándar del YAML según keywords del
contexto; el jugador puede forzarla escribiéndola (ej. "CD 18").
"""

import re

from narrator.logger import logger

# Bandas compatibles con MasterMoveEngine ('10+' / '7-9' / '6-')
_BANDA_EXITO = "10+"
_BANDA_PARCIAL = "7-9"
_BANDA_FALLO = "6-"

_MECHANIC_SIDES = {
    "d20_vs_dc": {20},
    "pool_d10": {10},
    "percentil": {100},
}

_RE_DIFICULTAD_EXPLICITA = re.compile(r"\b(?:cd|dc|dificultad)\s*:?\s*(\d{1,3})\b", re.IGNORECASE)


def _buscar_valor(data, key: str):
    """Busca ``key`` (case-insensitive) en un dict anidado; devuelve int o None."""
    if not isinstance(data, dict) or not key:
        return None
    key = key.lower()
    for k, v in data.items():
        if str(k).lower() == key:
            try:
                return int(v)
            except (TypeError, ValueError):
                return None
    for v in data.values():
        if isinstance(v, dict):
            found = _buscar_valor(v, key)
            if found is not None:
                return found
    return None


class RuleArbiter:
    """Resuelve tiradas contra la planilla y la mecánica del sistema."""

    def __init__(self, builder):
        # PromptBuilder: reutiliza su load_system() cacheado.
        self.builder = builder

    # ── API principal ─────────────────────────────────────────
    def resolve(self, action_text: str, character: dict, system_slug: str,
                rolls: "list[int]", sides: int) -> "dict | None":
        """Devuelve {"veredicto", "detalle", "banda"} o None si no aplica.

        None significa "sin resolución mecánica": el pipeline sigue con la
        heurística previa (banda por ratio), nunca se corta el flujo.
        """
        try:
            if not rolls or not isinstance(sides, int) or sides <= 0:
                return None
            if any(not isinstance(roll, int) or roll < 1 or roll > sides for roll in rolls):
                logger.warning("RuleArbiter: tirada fuera de rango rechazada")
                return None
            system = self.builder.load_system(system_slug) or {}
            res = system.get("resolution") or {}
            if not res:
                return None
            mecanica = res.get("mecanica", "ratio")
            expected_sides = _MECHANIC_SIDES.get(mecanica)
            expected_count = 1 if mecanica in {"d20_vs_dc", "percentil"} else None
            if expected_count is not None and len(rolls) != expected_count:
                logger.warning(
                    "RuleArbiter: cantidad de dados incompatible con mecanica %s: %s",
                    mecanica,
                    len(rolls),
                )
                return None
            if expected_sides and sides not in expected_sides:
                logger.warning(
                    "RuleArbiter: dado incompatible con mecánica %s: d%s",
                    mecanica,
                    sides,
                )
                return None
            if mecanica == "d20_vs_dc":
                result = self._d20_vs_dc(action_text, character or {}, res, rolls, sides)
            elif mecanica == "pool_d10":
                result = self._pool_d10(action_text, character or {}, res, rolls)
            elif mecanica == "percentil":
                result = self._percentil(action_text, character or {}, res, rolls, sides)
            else:
                result = self._ratio(res, rolls, sides)

            if result is None:
                return None

            accion = self._elegir_accion(action_text, res)
            result.update({
                "system_slug": system_slug,
                "mecanica": mecanica,
                "accion": accion.get("etiqueta", "Acción"),
                "atributo": accion.get("atributo", ""),
                "rolls": list(rolls),
                "sides": sides,
                "rule_source": f"data/systems/{system_slug}.yaml:resolution",
                "roll_validation": {"valid": True, "sides_compatible": True, "count": len(rolls)},
            })
            if mecanica != "ratio":
                dificultad, dificultad_label = self._elegir_dificultad(action_text, res)
                result["dificultad"] = dificultad
                result["dificultad_label"] = dificultad_label
            return result
        except Exception as e:
            logger.error(f"RuleArbiter.resolve: {e}", exc_info=True)
            return None

    # ── Selección de acción y dificultad ──────────────────────
    @staticmethod
    def _elegir_accion(action_text: str, res: dict) -> dict:
        t = (action_text or "").lower()
        for accion in res.get("acciones", []):
            if any(kw in t for kw in accion.get("keywords", [])):
                return accion
        default = res.get("atributo_default", "")
        return {"atributo": default, "etiqueta": default.replace("_", " ").title() or "Acción"}

    @staticmethod
    def _elegir_dificultad(action_text: str, res: dict) -> "tuple[int, str]":
        t = (action_text or "").lower()
        difs = res.get("dificultades", {}) or {}
        m = _RE_DIFICULTAD_EXPLICITA.search(t)
        if m:
            return int(m.group(1)), "declarada"
        for nivel, kws in (res.get("keywords_dificultad") or {}).items():
            if nivel in difs and any(kw in t for kw in kws):
                return difs[nivel], nivel
        default = res.get("dificultad_default", "normal")
        return difs.get(default, 15), default

    # ── Mecánicas ─────────────────────────────────────────────
    def _d20_vs_dc(self, action_text, character, res, rolls, sides):
        accion = self._elegir_accion(action_text, res)
        dc, dc_label = self._elegir_dificultad(action_text, res)
        attr = accion.get("atributo", "")
        score = _buscar_valor(character, attr)

        mod, mod_txt = 0, ""
        if score is not None:
            # Score de atributo (16 → +3) o modificador directo (+2)
            mod = (score - 10) // 2 if 6 <= score <= 30 else int(score)
            mod_txt = f" {mod:+d} ({attr} {score})"

        dado = sum(rolls)
        total = dado + mod
        natural = rolls[0] if len(rolls) == 1 else None

        if natural == 20 and sides == 20:
            veredicto, banda = "ÉXITO CRÍTICO (20 natural)", _BANDA_EXITO
        elif natural == 1 and sides == 20:
            veredicto, banda = "FALLO CRÍTICO (1 natural)", _BANDA_FALLO
        elif total >= dc:
            veredicto, banda = "ÉXITO", _BANDA_EXITO
        elif dc - total <= 2:
            veredicto, banda = "FALLO POR POCO", _BANDA_PARCIAL
        else:
            veredicto, banda = "FALLO", _BANDA_FALLO

        detalle = (f"{accion.get('etiqueta', 'Acción')}: {dado}{mod_txt} = {total} "
                   f"vs CD {dc} ({dc_label}) → {veredicto}")
        return {"veredicto": veredicto, "detalle": detalle, "banda": banda}

    def _pool_d10(self, action_text, character, res, rolls):
        accion = self._elegir_accion(action_text, res)
        dif, dif_label = self._elegir_dificultad(action_text, res)
        exitos = sum(1 for r in rolls if r >= dif)
        unos = sum(1 for r in rolls if r == 1)
        netos = exitos - unos

        if exitos == 0 and unos > 0:
            veredicto, banda = "FRACASO (botch)", _BANDA_FALLO
        elif netos <= 0:
            veredicto, banda = "FALLO", _BANDA_FALLO
        elif netos <= 2:
            veredicto, banda = f"ÉXITO PARCIAL ({netos} éxitos netos)", _BANDA_PARCIAL
        else:
            veredicto, banda = f"ÉXITO ({netos} éxitos netos)", _BANDA_EXITO

        attr = accion.get("atributo", "")
        valor = _buscar_valor(character, attr)
        pool_txt = f", {attr} en planilla: {valor}" if valor is not None else ""
        detalle = (f"{accion.get('etiqueta', 'Acción')} (pool {len(rolls)}d10{pool_txt}) "
                   f"vs dificultad {dif} ({dif_label}): {exitos} éxitos, {unos} unos "
                   f"→ {veredicto}")
        return {"veredicto": veredicto, "detalle": detalle, "banda": banda}

    def _percentil(self, action_text, character, res, rolls, sides):
        accion = self._elegir_accion(action_text, res)
        divisor, dif_label = self._elegir_dificultad(action_text, res)
        attr = accion.get("atributo", "")
        skill = _buscar_valor(character, attr)
        if skill is None:
            # Sin valor en la planilla no hay resolución percentil posible.
            return None

        tirada = sum(rolls) if sides == 100 else rolls[0]
        if dif_label == "declarada":
            # El jugador declaró un umbral absoluto (ej. "dificultad 40").
            umbral = max(1, divisor)
        else:
            umbral = max(1, skill // max(1, divisor))

        if tirada >= 96 and skill < 50:
            veredicto, banda = "PIFIA", _BANDA_FALLO
        elif tirada > umbral:
            veredicto, banda = "FALLO", _BANDA_FALLO
        elif tirada <= max(1, skill // 5):
            veredicto, banda = "ÉXITO EXTREMO", _BANDA_EXITO
        elif tirada <= max(1, skill // 2):
            veredicto, banda = "ÉXITO DURO", _BANDA_EXITO
        else:
            veredicto, banda = "ÉXITO", _BANDA_EXITO

        detalle = (f"{accion.get('etiqueta', 'Acción')} ({attr} {skill}%, "
                   f"dificultad {dif_label}, umbral {umbral}): tirada {tirada} → {veredicto}")
        return {"veredicto": veredicto, "detalle": detalle, "banda": banda}

    @staticmethod
    def _ratio(res, rolls, sides):
        bandas = res.get("bandas", {}) or {}
        umbral_exito = bandas.get("exito", 0.8)
        umbral_parcial = bandas.get("parcial", 0.5)
        total = sum(rolls)
        ratio = total / (len(rolls) * sides)
        if ratio >= umbral_exito:
            veredicto, banda = "ÉXITO", _BANDA_EXITO
        elif ratio >= umbral_parcial:
            veredicto, banda = "ÉXITO PARCIAL", _BANDA_PARCIAL
        else:
            veredicto, banda = "FALLO", _BANDA_FALLO
        detalle = (f"Tirada {len(rolls)}d{sides}: {total}/{len(rolls) * sides} "
                   f"(ratio {ratio:.0%}) → {veredicto}")
        return {"veredicto": veredicto, "detalle": detalle, "banda": banda}
