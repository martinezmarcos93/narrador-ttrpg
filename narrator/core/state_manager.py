"""
State Manager — gestiona estado_campana.yaml.
Relojes de frentes, flags de eventos, historial de sesiones, escena actual.
"""

import yaml
from narrator.logger import logger
from narrator.core.initiative import InitiativeQueue
from pathlib import Path
from datetime import datetime
from typing import Any, Optional


class StateManager:
    def __init__(self, state_path: str = "./estado_campana.yaml"):
        self.path = Path(state_path)
        self.data: dict = self._default()
        self._batch_depth = 0
        self._save_pending = False

    def _default(self) -> dict:
        return {
            "meta": {
                "sistema": "generic",
                "campana": "Sin nombre",
                "ciudad": "",
                "sesion_actual": 0,
                "fecha_inicio": None,
                "ultima_sesion": None,
            },
            "escena_actual": {
                "locacion": None,
                "npcs_presentes": [],
                "turno_narrativo": 0,
            },
            "relojes": {},
            "facciones": {},
            "frentes": {},
            "flags": {},
            "escenas": {},
            "downtime": {"pendiente": [], "npcs_activos": []},
            "historial": [],
            "turnos": [],
            "eventos": [],
            "consecuencias_pendientes": [],
            "hechos_conocidos": {},
            # Conocimiento por perspectiva: nunca mezclar verdad objetiva con
            # lo que sabe el personaje o el jugador.
            "relaciones": {},
            "provenance": [],
            "conocimiento": {
                "mundo": {},
                "personajes": {},
                "jugador": {},
            },
        }

    # ── Grafo social y provenance ─────────────────────────────
    def set_relation(
        self,
        source: str,
        target: str,
        relation: str,
        strength: int = 0,
        *,
        source_type: str = "npc",
        target_type: str = "npc",
        reason: str = "",
    ) -> None:
        """Persiste una arista social dirigida entre dos entidades."""
        source = str(source).strip()
        target = str(target).strip()
        relation = str(relation).strip()
        if not source or not target or not relation:
            return
        key = f"{source}::{target}"
        self.data.setdefault("relaciones", {})[key] = {
            "source": source,
            "target": target,
            "source_type": source_type,
            "target_type": target_type,
            "relation": relation,
            "strength": max(-100, min(100, int(strength))),
            "reason": reason,
            "sesion": self.get_session_number(),
        }
        self.save()

    def get_relations(self, entity: str = "", *, relation: str = "") -> list[dict]:
        result = []
        for item in self.data.get("relaciones", {}).values():
            if entity and entity not in {item.get("source"), item.get("target")}:
                continue
            if relation and item.get("relation") != relation:
                continue
            result.append(dict(item))
        return result

    def get_relation_graph_text(self, entities: list[str] | None = None, max_edges: int = 12) -> str:
        allowed = set(entities or [])
        edges = []
        for item in self.get_relations():
            if allowed and item.get("source") not in allowed and item.get("target") not in allowed:
                continue
            edges.append(
                f"{item.get('source')} --[{item.get('relation')}, {item.get('strength', 0)}]--> {item.get('target')}"
            )
        return "\n".join(edges[:max_edges])

    def record_provenance(
        self,
        *,
        kind: str,
        source: str,
        turn_id: str = "",
        detail: str = "",
        parent_id: str = "",
    ) -> str:
        """Registra causalidad técnica sin guardar prompts completos."""
        entry = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "kind": str(kind),
            "source": str(source),
            "turn_id": str(turn_id),
            "detail": str(detail),
            "parent_id": str(parent_id),
            "timestamp": datetime.now().isoformat(),
        }
        self.data.setdefault("provenance", []).append(entry)
        del self.data["provenance"][:-500]
        self.save()
        return entry["id"]

    def get_recent_provenance(self, limit: int = 20) -> list[dict]:
        return list(self.data.get("provenance", [])[-max(0, int(limit)):])

    # ── Persistencia ──────────────────────────────────────────
    def load(self) -> bool:
        if not self.path.exists():
            return False
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            # Merge recursivo: un estado antiguo puede carecer de subclaves
            # nuevas sin destruir los defaults anidados.
            merged = self._default()

            def merge_dict(base: dict, incoming: dict) -> dict:
                for key, val in incoming.items():
                    if isinstance(val, dict) and isinstance(base.get(key), dict):
                        merge_dict(base[key], val)
                    else:
                        base[key] = val
                return base

            self.data = merge_dict(merged, loaded)
            return True
        except Exception as e:
            # Estado corrupto: backup antes de que el próximo save() lo pise.
            logger.error(f"estado_campana.yaml corrupto o ilegible: {e}", exc_info=True)
            backup = self.path.with_name(
                f"{self.path.stem}.corrupto-{datetime.now():%Y%m%d-%H%M%S}{self.path.suffix}"
            )
            try:
                self.path.rename(backup)
                logger.error(f"Backup del estado corrupto guardado en: {backup}")
            except OSError as be:
                logger.error(f"No pude hacer backup del estado corrupto: {be}")
            return False

    @property
    def batch_depth(self) -> int:
        """Cantidad de fronteras de persistencia actualmente abiertas."""
        return self._batch_depth

    def begin_batch(self) -> None:
        """Agrupa múltiples mutaciones en una única persistencia."""
        self._batch_depth += 1

    def end_batch(self) -> None:
        """Cierra un lote; solo el lote exterior escribe en disco."""
        if self._batch_depth <= 0:
            return
        self._batch_depth -= 1
        if self._batch_depth == 0 and self._save_pending:
            self._save_pending = False
            self._save_now()

    def rollback_batch(self) -> None:
        """Cancela el lote actual sin persistir sus escrituras pendientes.

        La restauración del estado en memoria la realiza el llamador que posee
        el snapshot transaccional. Este método solo cierra la frontera de batch
        y elimina la intención de persistencia pendiente.
        """
        if self._batch_depth <= 0:
            self._save_pending = False
            return
        self._batch_depth -= 1
        if self._batch_depth == 0:
            self._save_pending = False

    def _save_now(self) -> None:
        """Escribe el estado mediante reemplazo atómico del archivo final."""
        import os
        import tempfile

        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.dump(
                    self.data,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                )
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
    def save(self):
        if self._batch_depth > 0:
            self._save_pending = True
            return
        self._save_now()

    def get_turn_context_text(self) -> str:
        """Resumen determinista del estado mutable que puede afectar este turno.

        Esta capa tiene precedencia sobre conocimiento recuperado: representa
        el estado vivo de la campaña, no una fuente de lore.
        """
        meta = self.data.get("meta", {})
        escena = self.data.get("escena_actual", {})
        flags = self.data.get("flags", {})
        lines = [
            f"Sistema: {meta.get('sistema', 'generic')}",
            f"Campaña: {meta.get('campana', 'Sin nombre')}",
            f"Sesión: {meta.get('sesion_actual', 0)}",
            f"Locación: {escena.get('locacion') or 'No definida'}",
            f"NPCs presentes: {', '.join(escena.get('npcs_presentes', [])) or 'ninguno'}",
            f"Turno narrativo: {escena.get('turno_narrativo', 0)}",
        ]
        if flags:
            compact_flags = []
            for name, entry in list(flags.items())[:12]:
                if isinstance(entry, dict):
                    compact_flags.append(f"{name}={entry.get('valor')}")
                else:
                    compact_flags.append(f"{name}={entry}")
            lines.append("Flags: " + ", ".join(compact_flags))
        active_fronts = self.get_active_fronts()
        if active_fronts:
            lines.append("Frentes activos:\n" + "\n".join(
                f"  - {item['nombre']}: {item.get('llenos', 0)}/{item.get('segmentos', 6)}"
                + (f" | facción: {item.get('faccion')}" if item.get('faccion') else "")
                for item in active_fronts[:8]
            ))
        clocks = self.get_clocks_summary()
        if clocks:
            lines.append("Relojes:\n" + clocks)
        pending = self.get_pending_consequences()
        if pending:
            lines.append("Consecuencias pendientes:\n" + "\n".join(
                f"  - {item.get('consecuencia')} (trigger: {item.get('trigger') or 'no definido'})"
                for item in pending[:8]
            ))
        events = self.data.get("eventos", [])
        if events:
            lines.append("Eventos recientes:\n" + "\n".join(
                f"  - {item.get('evento')}" for item in events[-5:]
            ))
        facts = self.data.get("hechos_conocidos", {})
        if facts:
            lines.append("Hechos conocidos:\n" + ", ".join(
                f"{key}={entry.get('valor') if isinstance(entry, dict) else entry}"
                for key, entry in list(facts.items())[-12:]
            ))
        combat = self.get_combat_status_text()
        if combat:
            lines.append("Combate: " + combat)
        return "\n".join(lines)

    # ── Continuidad y causalidad ─────────────────────────────────
    def record_event(self, event: str, *, actor: str = "", location: str = "") -> None:
        """Registra un evento factual que puede afectar turnos posteriores."""
        if not str(event).strip():
            return
        self.data.setdefault("eventos", []).append({
            "sesion": self.get_session_number(),
            "turno": self.data.get("escena_actual", {}).get("turno_narrativo", 0),
            "evento": str(event).strip(),
            "actor": actor,
            "locacion": location,
            "timestamp": datetime.now().isoformat(),
        })
        del self.data["eventos"][:-200]
        self.save()

    def add_pending_consequence(self, consequence: str, *, trigger: str = "", due: str = "") -> None:
        """Planta una consecuencia futura sin resolverla prematuramente."""
        if not str(consequence).strip():
            return
        self.data.setdefault("consecuencias_pendientes", []).append({
            "consecuencia": str(consequence).strip(),
            "trigger": trigger,
            "due": due,
            "estado": "pendiente",
            "sesion_creacion": self.get_session_number(),
        })
        self.save()

    def resolve_pending_consequence(self, index: int, outcome: str = "") -> dict:
        pending = self.data.setdefault("consecuencias_pendientes", [])
        if index < 0 or index >= len(pending):
            return {}
        entry = pending[index]
        entry["estado"] = "resuelta"
        if outcome:
            entry["resultado"] = outcome
        self.save()
        return dict(entry)

    def get_pending_consequences(self) -> list[dict]:
        return [
            dict(item) for item in self.data.get("consecuencias_pendientes", [])
            if item.get("estado", "pendiente") == "pendiente"
        ]

    def _set_perspective_fact(self, perspective: str, key: str, value: Any, *, source: str = "", subject: str = "") -> None:
        if not str(key).strip():
            return
        bucket = self.data.setdefault("conocimiento", {}).setdefault(perspective, {})
        if perspective == "personajes":
            bucket = bucket.setdefault(str(subject).strip() or "protagonista", {})
        bucket[str(key).strip()] = {
            "valor": value,
            "fuente": source,
            "sesion": self.get_session_number(),
        }

    def set_world_fact(self, key: str, value: Any, *, source: str = "") -> None:
        """Registra verdad objetiva de campaña; no implica que nadie la conozca."""
        self._set_perspective_fact("mundo", key, value, source=source)
        self.save()

    def set_character_fact(self, character: str, key: str, value: Any, *, source: str = "") -> None:
        """Registra un hecho conocido por un personaje concreto."""
        self._set_perspective_fact("personajes", key, value, source=source, subject=character)
        self.save()

    def set_player_fact(self, key: str, value: Any, *, source: str = "") -> None:
        """Registra información explícitamente conocida por el jugador."""
        self._set_perspective_fact("jugador", key, value, source=source)
        self.save()

    def get_world_fact(self, key: str, default: Any = None) -> Any:
        entry = self.data.get("conocimiento", {}).get("mundo", {}).get(key)
        return entry.get("valor", default) if isinstance(entry, dict) else default

    def get_character_fact(self, character: str, key: str, default: Any = None) -> Any:
        bucket = self.data.get("conocimiento", {}).get("personajes", {}).get(character, {})
        entry = bucket.get(key)
        return entry.get("valor", default) if isinstance(entry, dict) else default

    def get_player_fact(self, key: str, default: Any = None) -> Any:
        entry = self.data.get("conocimiento", {}).get("jugador", {}).get(key)
        return entry.get("valor", default) if isinstance(entry, dict) else default

    def get_knowledge_snapshot(self, *, character: str = "", include_player: bool = True) -> dict:
        """Devuelve perspectivas separadas; el llamador decide qué puede llegar al prompt."""
        knowledge = self.data.get("conocimiento", {})
        character_bucket = knowledge.get("personajes", {}).get(character, {}) if character else {}
        return {
            "world": dict(knowledge.get("mundo", {})),
            "character": dict(character_bucket),
            "player": dict(knowledge.get("jugador", {})) if include_player else {},
        }

    def get_character_knowledge_text(self, *, character: str = "", include_player: bool = True) -> str:
        """Renderiza solo conocimiento autorizado para la perspectiva narrativa."""
        snap = self.get_knowledge_snapshot(character=character, include_player=include_player)
        lines = []
        for label, bucket in (("Conocimiento del personaje", snap["character"]),
                              ("Información conocida por el jugador", snap["player"])):
            if not bucket:
                continue
            values = ", ".join(
                f"{key}={entry.get('valor') if isinstance(entry, dict) else entry}"
                for key, entry in list(bucket.items())[-16:]
            )
            lines.append(f"{label}: {values}")
        return "\n".join(lines)

    def set_known_fact(self, key: str, value: Any, *, source: str = "") -> None:
        """Persiste un hecho conocido sin mezclarlo con reglas del sistema."""
        if not str(key).strip():
            return
        self.data.setdefault("hechos_conocidos", {})[str(key).strip()] = {
            "valor": value,
            "fuente": source,
            "sesion": self.get_session_number(),
        }
        self.save()

    def get_known_fact(self, key: str, default: Any = None) -> Any:
        entry = self.data.get("hechos_conocidos", {}).get(key)
        return entry.get("valor", default) if isinstance(entry, dict) else default

    # ── Trazabilidad de turnos ─────────────────────────────────
    def record_turn(self, contract: dict) -> None:
        """Persiste un resumen técnico del turno sin almacenar el prompt completo."""
        if not isinstance(contract, dict) or not contract.get("turn_id"):
            return
        entry = {
            "turn_id": contract["turn_id"],
            "created_at": contract.get("created_at", ""),
            "completed_at": contract.get("completed_at", ""),
            "system": contract.get("system", self.data.get("meta", {}).get("sistema", "generic")),
            "stage": contract.get("stage", ""),
            "intent": contract.get("intent", ""),
            "rule_need": contract.get("rule_need", ""),
            "mechanical_resolution": contract.get("mechanical_resolution"),
            "retrieval_metrics": contract.get("retrieval_metrics", {}),
            "causal_metrics": contract.get("causal_metrics", {}),
            "state_delta": contract.get("state_delta", {}),
            "provenance": contract.get("provenance", []),
            "errors": contract.get("errors", []),
        }
        turns = self.data.setdefault("turnos", [])
        turns.append(entry)
        del turns[:-200]
        self.save()

    def get_recent_turns(self, limit: int = 20) -> list[dict]:
        """Devuelve los últimos resúmenes técnicos, sin prompts ni respuestas LLM."""
        return list(self.data.get("turnos", [])[-max(0, int(limit)):])

    # ── Aplicación atómica de propuestas ────────────────────────
    def apply_proposal(self, proposal) -> dict:
        """Aplica una propuesta ya validada y persiste una sola vez.

        Este método no interpreta texto libre ni llama a métodos que vuelvan
        a guardar el archivo. Todas las mutaciones quedan en memoria y se
        serializan al final del lote.
        """
        changes = []

        for key, value in proposal.facts.items():
            before = self.get_known_fact(key, None)
            self.data.setdefault("hechos_conocidos", {})[str(key).strip()] = {
                "valor": value,
                "fuente": "narrative_proposal",
                "sesion": self.get_session_number(),
            }
            changes.append(f"fact:{key} {before!r} -> {value!r}")

        for event in proposal.events:
            text = str(event).strip()
            if not text:
                continue
            self.data.setdefault("eventos", []).append({
                "sesion": self.get_session_number(),
                "turno": self.data.get("escena_actual", {}).get("turno_narrativo", 0),
                "evento": text,
                "actor": "",
                "locacion": self.get_location() or "",
                "timestamp": datetime.now().isoformat(),
            })
            changes.append(f"event:{text}")
        del self.data["eventos"][:-200]

        escena = self.data.setdefault("escena_actual", {})
        present = escena.setdefault("npcs_presentes", [])
        for name, desired in proposal.npc_presence.items():
            name = str(name).strip()
            if desired and name and name not in present:
                present.append(name)
                changes.append(f"npc:+{name}")
            elif not desired and name in present:
                present.remove(name)
                changes.append(f"npc:-{name}")

        for item in getattr(proposal, "relations", []) or []:
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            relation = str(item.get("relation") or "").strip()
            if source and target and relation:
                self.set_relation(
                    source,
                    target,
                    relation,
                    int(item.get("strength", 0)),
                    source_type=str(item.get("source_type") or "npc"),
                    target_type=str(item.get("target_type") or "npc"),
                    reason=str(item.get("reason") or "narrative_proposal"),
                )
                changes.append(f"relation:{source}->{target}:{relation}")

        for item in proposal.consequences:
            consequence = str(item.get("text") or item.get("consequence") or "").strip()
            if consequence:
                self.data.setdefault("consecuencias_pendientes", []).append({
                    "consecuencia": consequence,
                    "trigger": str(item.get("trigger") or ""),
                    "due": str(item.get("due") or ""),
                    "estado": "pendiente",
                    "sesion_creacion": self.get_session_number(),
                })
                changes.append(f"consequence:+{consequence}")
        del self.data["consecuencias_pendientes"][:-200]

        for item in proposal.clock_changes:
            name = str(item.get("name") or "").strip()
            if not name or name not in self.data.get("relojes", {}):
                continue
            try:
                delta = int(item.get("delta", 0))
            except (TypeError, ValueError):
                continue
            clock = self.data["relojes"][name]
            before = clock.get("llenos", 0)
            clock["llenos"] = min(max(0, before + delta), clock.get("segmentos", 6))
            changes.append(f"clock:{name} {before} -> {clock['llenos']}")

        for key, value in proposal.scene_changes.items():
            if key == "locacion":
                before = escena.get("locacion")
                escena["locacion"] = str(value) if value is not None else ""
                changes.append(f"scene:locacion {before!r} -> {escena['locacion']!r}")
            elif key == "turno_narrativo_delta":
                try:
                    delta = int(value)
                except (TypeError, ValueError):
                    delta = 0
                escena["turno_narrativo"] = max(
                    0, int(escena.get("turno_narrativo", 0)) + delta
                )
                changes.append(f"scene:turno_narrativo delta={delta}")

        self.save()
        return {"applied": True, "changes": changes}

    def apply_causal_activation(self, index: int, *, outcome: str = "", effects=None) -> dict:
        """Resuelve una consecuencia y aplica únicamente efectos declarativos permitidos."""
        pending = self.data.setdefault("consecuencias_pendientes", [])
        if index < 0 or index >= len(pending):
            return {"applied": False, "changes": []}
        entry = pending[index]
        if entry.get("estado", "pendiente") != "pendiente":
            return {"applied": False, "changes": []}

        changes = []
        entry["estado"] = "resuelta"
        if outcome:
            entry["resultado"] = outcome
        changes.append(f"consequence:resolved:{entry.get('consecuencia', '')}")

        escena = self.data.setdefault("escena_actual", {})
        for effect in effects or []:
            if not isinstance(effect, dict):
                continue
            kind = str(effect.get("type") or "").strip().lower()
            if kind == "fact" and str(effect.get("key") or "").strip():
                key = str(effect["key"]).strip()
                self.data.setdefault("hechos_conocidos", {})[key] = {
                    "valor": effect.get("value"),
                    "fuente": "causality_engine",
                    "sesion": self.get_session_number(),
                }
                changes.append(f"causal:fact:{key}")
            elif kind == "flag" and str(effect.get("name") or "").strip():
                name = str(effect["name"]).strip()
                self.data.setdefault("flags", {})[name] = {
                    "valor": effect.get("value"),
                    "descripcion": str(effect.get("description") or ""),
                    "sesion": self.get_session_number(),
                }
                changes.append(f"causal:flag:{name}")
            elif kind == "npc_presence" and str(effect.get("name") or "").strip():
                name = str(effect["name"]).strip()
                present = escena.setdefault("npcs_presentes", [])
                desired = bool(effect.get("present"))
                if desired and name not in present:
                    present.append(name)
                elif not desired and name in present:
                    present.remove(name)
                changes.append(f"causal:npc_presence:{name}={desired}")
            elif kind == "scene_location":
                value = str(effect.get("value") or "").strip()
                if value:
                    escena["locacion"] = value
                    changes.append(f"causal:scene_location:{value}")
            elif kind == "clock_delta" and str(effect.get("name") or "").strip():
                name = str(effect["name"]).strip()
                clock = self.data.setdefault("relojes", {}).get(name)
                if clock is None:
                    continue
                try:
                    delta = int(effect.get("delta", 0))
                except (TypeError, ValueError):
                    continue
                before = int(clock.get("llenos", 0))
                clock["llenos"] = min(max(0, before + delta), int(clock.get("segmentos", 6)))
                changes.append(f"causal:clock:{name} {before}->{clock['llenos']}")

        self.data.setdefault("eventos", []).append({
            "sesion": self.get_session_number(),
            "turno": escena.get("turno_narrativo", 0),
            "evento": f"Consecuencia activada: {entry.get('consecuencia', '')}",
            "actor": "CausalityEngine",
            "locacion": self.get_location() or "",
            "timestamp": datetime.now().isoformat(),
        })
        del self.data["eventos"][:-200]
        self.save()
        return {"applied": True, "changes": changes}

    # ── Escena actual ─────────────────────────────────────────
    def set_location(self, loc: str):
        self.data["escena_actual"]["locacion"] = loc

    def get_location(self) -> Optional[str]:
        return self.data["escena_actual"].get("locacion")

    def add_npc_to_scene(self, name: str):
        present = self.data["escena_actual"].setdefault("npcs_presentes", [])
        if name not in present:
            present.append(name)

    def clear_scene(self):
        self.data["escena_actual"]["npcs_presentes"] = []
        self.data["escena_actual"]["turno_narrativo"] = 0

    def increment_turn(self):
        sc = self.data["escena_actual"]
        sc["turno_narrativo"] = sc.get("turno_narrativo", 0) + 1

    # ── Combate (cola de iniciativa) ──────────────────────────
    def start_combat(self, combatientes: "list[tuple[str, int]]") -> None:
        """Inicia un combate. `combatientes`: [(nombre, iniciativa), ...]."""
        q = InitiativeQueue()
        for nombre, iniciativa in combatientes:
            q.add(nombre, iniciativa)
        self.data["escena_actual"]["combate"] = q.to_dict()
        self.save()

    def get_combat_queue(self) -> "InitiativeQueue | None":
        data = self.data["escena_actual"].get("combate")
        if not data:
            return None
        return InitiativeQueue.from_dict(data)

    def advance_combat_turn(self) -> "str | None":
        """Avanza al siguiente combatiente activo y persiste el nuevo estado."""
        q = self.get_combat_queue()
        if not q:
            return None
        resultado = q.next_turn()
        self.data["escena_actual"]["combate"] = q.to_dict()
        self.save()
        return resultado

    def end_combat(self) -> None:
        self.data["escena_actual"]["combate"] = None
        self.save()

    def is_in_combat(self) -> bool:
        return bool(self.data["escena_actual"].get("combate"))

    def get_combat_status_text(self) -> str:
        """Texto compacto del combate en curso para el prompt del narrador."""
        q = self.get_combat_queue()
        if not q or not q.is_active():
            return ""
        lines = [f"Ronda {q.round()}. Orden de iniciativa: {', '.join(q.order())}."]
        actual = q.current_name()
        if actual:
            lines.append(f"Turno activo: {actual}.")
        return " ".join(lines)

    # ── Relojes (Fronts clocks) ───────────────────────────────
    def add_clock(self, name: str, segments: int = 6, description: str = ""):
        self.data["relojes"][name] = {
            "segmentos": segments,
            "llenos": 0,
            "descripcion": description,
        }
        self.save()

    def advance_clock(self, name: str, n: int = 1) -> dict:
        """Avanza un reloj n segmentos. Devuelve estado actual."""
        clock = self.data["relojes"].get(name)
        if not clock:
            return {}
        clock["llenos"] = min(clock["llenos"] + n, clock["segmentos"])
        self.save()
        return clock

    def is_clock_full(self, name: str) -> bool:
        clock = self.data["relojes"].get(name, {})
        return clock.get("llenos", 0) >= clock.get("segmentos", 6)

    def get_clocks_summary(self) -> str:
        """Texto compacto de todos los relojes para el contexto."""
        relojes = self.data.get("relojes", {})
        if not relojes:
            return ""
        lines = []
        for name, c in relojes.items():
            bar = "█" * c.get("llenos", 0) + "░" * (c.get("segmentos", 6) - c.get("llenos", 0))
            lines.append(f"  {name}: [{bar}] {c.get('descripcion', '')}")
        return "\n".join(lines)

    # ── Flags de eventos ──────────────────────────────────────
    def set_flag(self, name: str, value: Any, description: str = ""):
        self.data["flags"][name] = {
            "valor": value,
            "descripcion": description,
            "sesion": self.data["meta"].get("sesion_actual", 0),
        }
        self.save()

    def get_flag(self, name: str, default: Any = None) -> Any:
        entry = self.data["flags"].get(name)
        return entry["valor"] if entry else default

    # ── Escenas (C2 — patrón contenido/estado de rage_war) ────
    # El contenido de cada escena vive en el vault (Escenas/*.md);
    # acá solo se persiste su estado: bloqueada → disponible → jugada.
    def get_scene_state(self, name: str) -> dict:
        return self.data.setdefault("escenas", {}).get(
            name, {"estado": "bloqueada", "desbloqueada_por": ""})

    def set_scene_state(self, name: str, estado: str, por: str = ""):
        escenas = self.data.setdefault("escenas", {})
        entry = escenas.setdefault(name, {"estado": "bloqueada", "desbloqueada_por": ""})
        entry["estado"] = estado
        if por:
            entry["desbloqueada_por"] = por
        self.save()

    def get_scenes_by_state(self, estado: str) -> "list[str]":
        return [n for n, e in self.data.get("escenas", {}).items()
                if e.get("estado") == estado]

    # ── Historial de sesiones ─────────────────────────────────
    def start_session(self):
        self.data["meta"]["sesion_actual"] = self.data["meta"].get("sesion_actual", 0) + 1
        self.data["meta"]["ultima_sesion"] = datetime.now().isoformat()
        self.save()

    def add_session_summary(
        self,
        resumen: str,
        decisiones: list[str] = None,
        consecuencias: list[str] = None,
    ):
        self.data["historial"].append({
            "sesion": self.data["meta"].get("sesion_actual", 0),
            "resumen": resumen,
            "decisiones_clave": decisiones or [],
            "consecuencias_plantadas": consecuencias or [],
        })
        self.save()

    def get_last_session_summary(self) -> str:
        hist = self.data.get("historial", [])
        if not hist:
            return ""
        last = hist[-1]
        return f"Sesión {last['sesion']}: {last['resumen']}"

    def get_session_number(self) -> int:
        return self.data["meta"].get("sesion_actual", 0)

    # ── Facciones y frentes ──────────────────────────────────
    def add_faction(
        self,
        slug: str,
        name: str = "",
        description: str = "",
        *,
        agenda: str = "",
        status: str = "activa",
    ) -> None:
        slug = str(slug).strip()
        if not slug:
            return
        self.data.setdefault("facciones", {})[slug] = {
            "slug": slug,
            "nombre": str(name).strip() or slug,
            "descripcion": str(description).strip(),
            "agenda": str(agenda).strip(),
            "estado": str(status).strip() or "activa",
        }
        self.save()

    def get_faction(self, slug: str) -> dict:
        return dict(self.data.get("facciones", {}).get(str(slug).strip(), {}))

    def get_active_factions(self) -> list[dict]:
        return [
            dict(item)
            for item in self.data.get("facciones", {}).values()
            if item.get("estado", "activa") in {"activa", "activo", "active"}
        ]

    # ── Frentes (gestión programática) ───────────────────────
    def add_front(
        self,
        name: str,
        description: str = "",
        max_stage: int = 6,
        *,
        faction: str = "",
        goal: str = "",
        status: str = "activo",
        priority: int = 0,
    ) -> None:
        """Registra un frente formal y mantiene compatibilidad con relojes antiguos."""
        name = str(name).strip()
        if not name:
            return
        self.data.setdefault("frentes", {}).setdefault(name, {
            "nombre": name,
            "faccion": str(faction).strip(),
            "objetivo": str(goal).strip(),
            "estado": str(status).strip() or "activo",
            "prioridad": int(priority),
            "descripcion": str(description).strip(),
            "reloj": name,
        })
        if name not in self.data.setdefault("relojes", {}):
            self.data["relojes"][name] = {
                "segmentos": max(1, int(max_stage)),
                "llenos": 0,
                "descripcion": description,
            }
        self.save()

    def get_front(self, name: str) -> dict:
        return dict(self.data.get("frentes", {}).get(str(name).strip(), {}))

    def get_active_fronts(self) -> list[dict]:
        fronts = []
        for name, item in self.data.get("frentes", {}).items():
            if item.get("estado", "activo") in {"activo", "active", "en_marcha"}:
                front = dict(item)
                front["nombre"] = front.get("nombre") or name
                clock = self.data.get("relojes", {}).get(front.get("reloj", name), {})
                front["llenos"] = int(clock.get("llenos", 0))
                front["segmentos"] = int(clock.get("segmentos", 6))
                fronts.append(front)
        return sorted(fronts, key=lambda x: (-int(x.get("prioridad", 0)), x["nombre"]))

    def advance_front_clock(self, name: str, ticks: int = 1) -> None:
        """Avanza el reloj de un frente registrado."""
        clock = self.data.setdefault("relojes", {}).get(name)
        if clock:
            clock["llenos"] = min(
                max(0, int(clock.get("llenos", 0)) + int(ticks)),
                int(clock.get("segmentos", 6)),
            )
            self.save()

    # ── Downtime entre sesiones ───────────────────────────────
    def add_downtime_action(self, actor: str, action: str):
        self.data["downtime"].setdefault("pendiente", []).append({
            "actor": actor, "accion": action
        })
        self.save()

    def add_active_npc(self, npc_name: str, action: str):
        self.data["downtime"].setdefault("npcs_activos", []).append({
            "npc": npc_name, "accion": action
        })
        self.save()

    def clear_downtime(self):
        self.data["downtime"] = {"pendiente": [], "npcs_activos": []}
        self.save()
