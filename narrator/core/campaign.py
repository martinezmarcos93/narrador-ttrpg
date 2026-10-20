"""Manifiesto de campaña y cargador (Fase G).

Un manifiesto YAML declara todo lo necesario para empezar a jugar:

    meta: {nombre, sistema, ciudad}
    personajes: [{nombre, ...ficha}]          # el primero es el protagonista
    npcs: [{nombre, rol, amenaza, faccion}]
    locaciones: [{nombre, distrito, descripcion}]
    facciones: [{slug, nombre, agenda}]
    frentes: [{nombre, faccion, objetivo, segmentos, umbrales, al_llenarse, avance_por_sesion}]
    relaciones: [{source, target, relation, strength}]
    secretos: [{id, tema, verdad, pistas, sobre: {tipo, nombre}}]
    consecuencias: [{texto, trigger, due, effects}]
    escena_inicial: {locacion, npcs_presentes}
    reglas_casa: [{nombre, texto}]
    manuales: [ruta/al/manual.pdf]            # opcional, informativo

``validate_manifest`` devuelve errores sin tocar nada; ``load_campaign`` aplica
todo en un único batch del StateManager (si algo falla, no queda a medias).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from narrator.core import secrets
from narrator.core.entity_registry import fold_name
from narrator.logger import logger

SECTIONS = {
    "meta", "personajes", "npcs", "locaciones", "facciones", "frentes", "relaciones",
    "secretos", "consecuencias", "escena_inicial", "reglas_casa", "manuales",
}


def read_manifest(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("el manifiesto debe ser un mapa YAML")
    return data


def validate_manifest(data: dict, systems_path: str | Path = "data/systems") -> list[str]:
    errors: list[str] = []
    unknown = set(data) - SECTIONS
    if unknown:
        errors.append(f"secciones desconocidas: {sorted(unknown)}")
    meta = data.get("meta") or {}
    if not meta.get("nombre"):
        errors.append("meta.nombre es obligatorio")
    system = str(meta.get("sistema") or "generic")
    if not (Path(systems_path) / f"{system}.yaml").exists():
        errors.append(f"meta.sistema '{system}' no tiene System Pack")

    def names(section: str) -> set[str]:
        return {fold_name(x.get("nombre")) for x in data.get(section) or [] if isinstance(x, dict)}

    for section in ("personajes", "npcs", "locaciones", "frentes"):
        items = data.get(section) or []
        if not isinstance(items, list):
            errors.append(f"{section} debe ser una lista")
            continue
        seen = set()
        for i, item in enumerate(items):
            if not isinstance(item, dict) or not str(item.get("nombre") or "").strip():
                errors.append(f"{section}[{i}] requiere nombre")
                continue
            key = fold_name(item["nombre"])
            if key in seen:
                errors.append(f"{section}: nombre repetido '{item['nombre']}'")
            seen.add(key)

    factions = {fold_name(f.get("slug") or f.get("nombre")) for f in data.get("facciones") or []
                if isinstance(f, dict)}
    factions |= {fold_name(f.get("nombre")) for f in data.get("facciones") or [] if isinstance(f, dict)}
    fronts = names("frentes")
    for front in data.get("frentes") or []:
        if not isinstance(front, dict):
            continue
        if front.get("faccion") and fold_name(front["faccion"]) not in factions:
            errors.append(f"frente '{front.get('nombre')}' usa facción inexistente '{front['faccion']}'")
        for link in front.get("al_llenarse") or []:
            if fold_name(link.get("frente")) not in fronts:
                errors.append(f"frente '{front.get('nombre')}' empuja a frente inexistente '{link.get('frente')}'")
        segments = int(front.get("segmentos", 6) or 6)
        for value in (front.get("umbrales") or {}):
            if not 0 < int(value) <= segments:
                errors.append(f"frente '{front.get('nombre')}': umbral {value} fuera de 1..{segments}")

    known = names("npcs") | names("personajes") | factions
    for rel in data.get("relaciones") or []:
        for end in ("source", "target"):
            if fold_name(rel.get(end)) not in known:
                errors.append(f"relación con entidad desconocida '{rel.get(end)}'")
        if not -100 <= int(rel.get("strength", 0)) <= 100:
            errors.append(f"relación {rel.get('source')}->{rel.get('target')}: fuerza fuera de rango")

    entity_names = {"npc": names("npcs"), "locacion": names("locaciones"), "faccion": factions}
    ids = set()
    for sec in data.get("secretos") or []:
        sid = str(sec.get("id") or "")
        if not sid or sid in ids:
            errors.append(f"secreto con id vacío o repetido: '{sid}'")
        ids.add(sid)
        if not sec.get("pistas"):
            errors.append(f"secreto '{sid}' sin pistas")
        about = sec.get("sobre") or {}
        if about.get("tipo") and fold_name(about.get("nombre")) not in entity_names.get(about["tipo"], set()):
            errors.append(f"secreto '{sid}' sobre entidad desconocida '{about.get('nombre')}'")

    scene = data.get("escena_inicial") or {}
    if scene.get("locacion") and fold_name(scene["locacion"]) not in names("locaciones"):
        errors.append(f"escena_inicial.locacion '{scene['locacion']}' no está en locaciones")
    for npc in scene.get("npcs_presentes") or []:
        if fold_name(npc) not in names("npcs"):
            errors.append(f"escena_inicial: NPC desconocido '{npc}'")
    return errors


def _write_note(path: Path, front: dict, body: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
    path.write_text(f"---\n{head}---\n\n{body}\n", encoding="utf-8")


def load_campaign(data: dict, state, vault_path: str | Path, *,
                  systems_path: str | Path = "data/systems") -> dict[str, Any]:
    """Valida y carga el manifiesto. Lanza ValueError si es inválido."""
    errors = validate_manifest(data, systems_path)
    if errors:
        raise ValueError("manifiesto inválido: " + "; ".join(errors))
    vault = Path(vault_path)
    from narrator.core.vault_writer import _safe_filename

    summary: dict[str, Any] = {}
    state.begin_batch()
    try:
        meta = data["meta"]
        state.data["meta"].update({
            "campana": meta["nombre"], "sistema": meta.get("sistema", "generic"),
            "ciudad": meta.get("ciudad", ""),
        })
        for faction in data.get("facciones") or []:
            slug = faction.get("slug") or faction["nombre"]
            state.add_faction(slug, faction["nombre"], description=faction.get("descripcion", ""),
                              agenda=faction.get("agenda", ""))
            _write_note(vault / "Cofradias" / f"{_safe_filename(faction['nombre'])}.md",
                        {"tipo": "faccion", "nombre": faction["nombre"]},
                        faction.get("agenda", ""))
        for front in data.get("frentes") or []:
            state.add_front(
                front["nombre"], front.get("descripcion", ""), int(front.get("segmentos", 6)),
                faction=front.get("faccion", ""), goal=front.get("objetivo", ""),
                priority=int(front.get("prioridad", 0)), thresholds=front.get("umbrales"),
                on_full=front.get("al_llenarse"),
                advance_per_session=int(front.get("avance_por_sesion", 0) or 0),
            )
        for npc in data.get("npcs") or []:
            front = {"tipo": "npc", "nombre": npc["nombre"], "estado": "vivo"}
            front.update({k: v for k, v in npc.items() if k not in {"nombre", "descripcion"}})
            _write_note(vault / "NPCs" / f"{_safe_filename(npc['nombre'])}.md", front,
                        npc.get("descripcion", ""))
        for loc in data.get("locaciones") or []:
            front = {"tipo": "locacion", "nombre": loc["nombre"]}
            front.update({k: v for k, v in loc.items() if k not in {"nombre", "descripcion"}})
            _write_note(vault / "Locaciones" / f"{_safe_filename(loc['nombre'])}.md", front,
                        loc.get("descripcion", ""))
        for rule in data.get("reglas_casa") or []:
            _write_note(vault / "Reglas" / f"{_safe_filename(rule['nombre'])}.md",
                        {"tipo": "regla_casa", "nombre": rule["nombre"]}, rule.get("texto", ""))
        for rel in data.get("relaciones") or []:
            state.set_relation(rel["source"], rel["target"], rel["relation"],
                               int(rel.get("strength", 0)), reason=rel.get("reason", "manifiesto"))
        for sec in data.get("secretos") or []:
            about = sec.get("sobre") or {}
            secrets.add_secret(state, sec["id"], tema=sec["tema"], verdad=sec["verdad"],
                               pistas=sec["pistas"], sobre_tipo=about.get("tipo", ""),
                               sobre_nombre=about.get("nombre", ""))
        for cons in data.get("consecuencias") or []:
            state.add_pending_consequence(cons["texto"], trigger=cons.get("trigger", ""),
                                          due=cons.get("due", ""), effects=cons.get("effects"))
        scene = data.get("escena_inicial") or {}
        if scene.get("locacion"):
            state.set_location(scene["locacion"])
        state.data["escena_actual"]["npcs_presentes"] = list(scene.get("npcs_presentes") or [])
        state.end_batch()
    except Exception:
        logger.error("Fallo cargando la campaña; se descarta el batch", exc_info=True)
        state.rollback_batch()
        raise
    personajes = data.get("personajes") or []
    summary.update({
        "campana": data["meta"]["nombre"], "sistema": data["meta"].get("sistema", "generic"),
        "protagonista": dict(personajes[0]) if personajes else {},
        "npcs": len(data.get("npcs") or []), "locaciones": len(data.get("locaciones") or []),
        "frentes": len(data.get("frentes") or []), "secretos": len(data.get("secretos") or []),
        "consecuencias": len(data.get("consecuencias") or []),
    })
    return summary
