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

from narrator.core import character_sheet
from narrator.core.entity_registry import fold_name
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
_RE_FUERZA_VOLUNTAD = re.compile(r"\b(?:gasto|uso|usando|gastando)\b.{0,20}\bvoluntad\b", re.IGNORECASE)
_RE_DESVENTAJA = re.compile(r"\bdesventaja\b", re.IGNORECASE)
_RE_VENTAJA = re.compile(r"(?<!des)\bventaja\b", re.IGNORECASE)


def _tiene_especialidad(character: dict, *rasgos: str) -> str:
    """Devuelve el rasgo con especialidad declarada en la ficha, o ''."""
    especialidades = character.get("especialidades") if isinstance(character, dict) else None
    if not isinstance(especialidades, dict):
        return ""
    declaradas = {fold_name(k) for k, v in especialidades.items() if str(v or "").strip()}
    for rasgo in rasgos:
        if rasgo and fold_name(rasgo) in declaradas:
            return rasgo
    return ""


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
            if mecanica == "d20_vs_dc" and len(rolls) == 2 and (
                _RE_VENTAJA.search(action_text or "") or _RE_DESVENTAJA.search(action_text or "")
            ):
                expected_count = 2  # ventaja/desventaja: se tiran dos d20
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
                result = self._pool_d10(action_text, character or {}, res, rolls, system)
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
                "habilidad": accion.get("habilidad", ""),
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
        t = fold_name(action_text)
        for accion in res.get("acciones", []):
            if any(fold_name(kw) in t for kw in accion.get("keywords", [])):
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
    @staticmethod
    def _bono_competencia(character: dict) -> int:
        """D&D 5e: +2 en niveles 1-4, +3 en 5-8, ... (+6 en 17-20)."""
        nivel = _buscar_valor(character, "nivel")
        if nivel is None:
            return 0
        return 2 + (max(1, min(20, nivel)) - 1) // 4

    def _d20_vs_dc(self, action_text, character, res, rolls, sides):
        accion = self._elegir_accion(action_text, res)
        dc, dc_label = self._elegir_dificultad(action_text, res)
        attr = accion.get("atributo", "")
        habilidad = accion.get("habilidad", "")
        score = _buscar_valor(character, attr)

        mod, mod_txt = 0, ""
        if score is not None:
            # Score de atributo (16 → +3) o modificador directo (+2)
            mod = (score - 10) // 2 if 6 <= score <= 30 else int(score)
            mod_txt = f" {mod:+d} ({attr} {score})"

        competencias = character.get("competencias") if isinstance(character, dict) else None
        if habilidad and isinstance(competencias, list) and fold_name(habilidad) in {
            fold_name(c) for c in competencias
        }:
            bono = self._bono_competencia(character)
            if bono:
                mod += bono
                mod_txt += f" {bono:+d} (competencia {habilidad})"

        modo = ""
        if len(rolls) == 2:
            if _RE_DESVENTAJA.search(action_text or ""):
                natural, modo = min(rolls), " con desventaja"
            else:
                natural, modo = max(rolls), " con ventaja"
            dado = natural
        else:
            dado = sum(rolls)
            natural = rolls[0] if len(rolls) == 1 else None
        total = dado + mod

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

        detalle = (f"{accion.get('etiqueta', 'Acción')}{modo}: {dado}{mod_txt} = {total} "
                   f"vs CD {dc} ({dc_label}) → {veredicto}")
        return {"veredicto": veredicto, "detalle": detalle, "banda": banda}

    def _pool_d10(self, action_text, character, res, rolls, system=None):
        """Mundo de Tinieblas 20 aniversario.

        - pool esperado = atributo + habilidad + penalizador por heridas;
        - con especialidad en el rasgo, cada 10 cuenta como dos éxitos;
        - gastar Fuerza de Voluntad da un éxito automático que los 1 no anulan
          (y evita el fracaso); el gasto se devuelve como costo a aplicar.
        """
        accion = self._elegir_accion(action_text, res)
        dif, dif_label = self._elegir_dificultad(action_text, res)
        attr = accion.get("atributo", "")
        habilidad = accion.get("habilidad", "")
        valor_attr = _buscar_valor(character, attr)
        valor_hab = _buscar_valor(character, habilidad) if habilidad else None

        schema = (system or {}).get("character_sheet_schema") or {}
        penalizador = character_sheet.wound_penalty(schema, character) if schema else 0
        pool_esperado = None
        if valor_attr is not None:
            pool_esperado = max(0, valor_attr + (valor_hab or 0) + penalizador)

        especialidad = _tiene_especialidad(character, habilidad, attr)
        dieces = sum(1 for r in rolls if r == 10)
        exitos = sum(1 for r in rolls if r >= dif)
        if especialidad:
            exitos += dieces  # cada 10 suma un éxito extra
        unos = sum(1 for r in rolls if r == 1)
        netos = max(0, exitos - unos)

        costos = []
        voluntad_txt = ""
        fv_temp = _buscar_valor(character, "fuerza_voluntad_temp")
        if _RE_FUERZA_VOLUNTAD.search(action_text or ""):
            if fv_temp and fv_temp > 0:
                netos += 1
                costos.append({
                    "field": "fuerza_voluntad_temp", "delta": -1,
                    "reason": "gasto de Fuerza de Voluntad en una tirada",
                })
                voluntad_txt = ", +1 éxito por Fuerza de Voluntad"
            else:
                voluntad_txt = ", sin Fuerza de Voluntad disponible para gastar"

        if exitos == 0 and unos > 0 and not costos:
            veredicto, banda = "FRACASO (botch)", _BANDA_FALLO
        elif netos <= 0:
            veredicto, banda = "FALLO", _BANDA_FALLO
        elif netos <= 2:
            veredicto, banda = f"ÉXITO PARCIAL ({netos} éxitos netos)", _BANDA_PARCIAL
        else:
            veredicto, banda = f"ÉXITO ({netos} éxitos netos)", _BANDA_EXITO

        partes = []
        if valor_attr is not None:
            partes.append(f"{attr} {valor_attr}")
        if habilidad:
            partes.append(f"{habilidad} {valor_hab or 0}")
        if penalizador:
            partes.append(f"heridas {penalizador:+d}")
        pool_txt = (" = ".join([" + ".join(partes), str(pool_esperado)])
                    if pool_esperado is not None else "")
        espec_txt = f", especialidad en {especialidad} (10 = 2 éxitos)" if especialidad else ""
        detalle = (f"{accion.get('etiqueta', 'Acción')} (pool {len(rolls)}d10"
                   f"{'; esperado ' + pool_txt if pool_txt else ''}) "
                   f"vs dificultad {dif} ({dif_label}): {exitos} éxitos, {unos} unos"
                   f"{espec_txt}{voluntad_txt} → {veredicto}")
        result = {"veredicto": veredicto, "detalle": detalle, "banda": banda}
        if pool_esperado is not None:
            result["pool_esperado"] = pool_esperado
            if pool_esperado != len(rolls):
                result["advertencias"] = [
                    f"se tiraron {len(rolls)} dados; la ficha indica un pool de {pool_esperado}"
                ]
        if costos:
            result["costos"] = costos
        return result

    def suggest_roll(self, action_text: str, character: dict, system_slug: str) -> dict | None:
        """Sugiere cuántos dados y de qué tipo tirar para una acción, sin tirarlos."""
        system = self.builder.load_system(system_slug) or {}
        res = system.get("resolution") or {}
        mecanica = res.get("mecanica")
        if not mecanica:
            return None
        accion = self._elegir_accion(action_text, res)
        if mecanica == "pool_d10":
            attr = _buscar_valor(character, accion.get("atributo", ""))
            hab = _buscar_valor(character, accion.get("habilidad", "")) if accion.get("habilidad") else 0
            schema = system.get("character_sheet_schema") or {}
            pen = character_sheet.wound_penalty(schema, character) if schema else 0
            dados = max(1, (attr or 1) + (hab or 0) + pen)
            return {"dados": min(dados, 20), "lados": 10, "accion": accion.get("etiqueta", "")}
        if mecanica == "d20_vs_dc":
            dobles = bool(_RE_VENTAJA.search(action_text or "") or _RE_DESVENTAJA.search(action_text or ""))
            return {"dados": 2 if dobles else 1, "lados": 20, "accion": accion.get("etiqueta", "")}
        if mecanica == "percentil":
            return {"dados": 1, "lados": 100, "accion": accion.get("etiqueta", "")}
        return None

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
