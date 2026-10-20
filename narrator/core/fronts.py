"""Frentes: umbrales, avance por sesión e interacción entre frentes (Fase D).

Definición en ``estado.frentes[<nombre>]`` (todas opcionales)::

    umbrales: {2: "El culto secuestra a un testigo", 4: "Se abre la grieta"}
    al_llenarse: [{frente: "Guardia", delta: 2}]   # interacción entre frentes
    avance_por_sesion: 1                             # reloj que corre solo

``change_clock`` es el ÚNICO punto que mueve un reloj: recorta al rango,
registra eventos de umbral y de frente lleno (que alimentan la causalidad) y
propaga ``al_llenarse`` con profundidad acotada para impedir ciclos.
"""

from __future__ import annotations

MAX_FRONT_CASCADE = 3


def _thresholds(front: dict) -> dict[int, str]:
    result = {}
    for key, text in (front.get("umbrales") or {}).items():
        try:
            result[int(key)] = str(text)
        except (TypeError, ValueError):
            continue
    return result


def change_clock(state, name: str, delta: int, *, actor: str = "frentes", depth: int = 0) -> list[str]:
    """Aplica ``delta`` al reloj ``name``; devuelve los eventos producidos."""
    clock = state.data.get("relojes", {}).get(name)
    if clock is None:
        return []
    before = int(clock.get("llenos", 0) or 0)
    maximum = int(clock.get("segmentos", 6) or 6)
    after = min(max(0, before + int(delta)), maximum)
    clock["llenos"] = after
    events = [f"reloj {name}: {before}->{after}"]
    if after == before:
        return events

    front = state.data.get("frentes", {}).get(name) or {}
    notable = []
    for value, text in sorted(_thresholds(front).items()):
        if before < value <= after:
            notable.append(f"frente {name} umbral {value}: {text}")
    if before < maximum <= after:
        notable.append(f"frente {name} lleno")
    for event in notable:
        state._append_event(event, actor=actor)
    events.extend(notable)

    if before < maximum <= after and depth < MAX_FRONT_CASCADE:
        for link in front.get("al_llenarse") or []:
            if not isinstance(link, dict):
                continue
            target = str(link.get("frente") or "").strip()
            try:
                link_delta = int(link.get("delta", 1))
            except (TypeError, ValueError):
                continue
            if target and target != name:
                events.extend(change_clock(state, target, link_delta, actor=actor, depth=depth + 1))
    return events


def session_advance(state) -> list[str]:
    """Avanza los frentes activos con ``avance_por_sesion`` (el mundo no espera)."""
    events = []
    for name, front in (state.data.get("frentes") or {}).items():
        if front.get("estado", "activo") not in {"activo", "active", "en_marcha"}:
            continue
        try:
            step = int(front.get("avance_por_sesion", 0) or 0)
        except (TypeError, ValueError):
            continue
        if step:
            events.extend(change_clock(state, front.get("reloj", name), step))
    return events
