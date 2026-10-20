"""Persistencia de la capa web en SQLite (K): sesiones y claves de API.

- Sesiones con dueño (``owner``): una clave solo ve sus sesiones; el admin ve todas.
- Claves de API: se guarda solo el hash SHA-256; el texto plano se muestra una
  vez al crearla o rotarla. Revocar es inmediato.

Verbos CRUD en castellano (convención del proyecto). ``create``/``get``/``delete``
quedan como alias del protocolo de ``SessionStore`` en memoria.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from narrator.web.session_store import WebSession

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sesiones (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    campaign TEXT NOT NULL,
    system TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sesiones_owner ON sesiones(owner);
CREATE TABLE IF NOT EXISTS claves_api (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class WebStore:
    def __init__(self, path: str | Path = "data/web/narrador_web.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── Sesiones ──────────────────────────────────────────────
    @staticmethod
    def _row_to_session(row) -> WebSession:
        session = WebSession(session_id=row["id"], campaign=row["campaign"], system=row["system"])
        session.data = json.loads(row["data"] or "{}")
        session.data.setdefault("owner", row["owner"])
        return session

    def crear_sesion(self, *, campaign: str, system: str, owner: str = "local") -> WebSession:
        session_id = secrets.token_urlsafe(32)
        now = _now()
        data = {"owner": owner}
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO sesiones (id, owner, campaign, system, created_at, updated_at, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, owner, campaign, system, now, now, json.dumps(data)),
            )
        session = WebSession(session_id=session_id, campaign=campaign, system=system)
        session.data = data
        return session

    def obtener_sesion(self, session_id: str) -> WebSession | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM sesiones WHERE id = ?", (session_id,)).fetchone()
        return self._row_to_session(row) if row else None

    def listar_sesiones(self, owner: str | None = None) -> list[WebSession]:
        query, params = "SELECT * FROM sesiones", ()
        if owner is not None:
            query, params = query + " WHERE owner = ?", (owner,)
        with self._conn() as conn:
            rows = conn.execute(query + " ORDER BY created_at", params).fetchall()
        return [self._row_to_session(r) for r in rows]

    def actualizar_sesion(self, session_id: str, data: dict[str, Any]) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE sesiones SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(data, ensure_ascii=False, default=str), _now(), session_id),
            )

    def eliminar_sesion(self, session_id: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM sesiones WHERE id = ?", (session_id,))

    def existe_sesion(self, session_id: str) -> bool:
        return self.obtener_sesion(session_id) is not None

    # Alias del protocolo SessionStore
    def create(self, *, campaign: str, system: str, owner: str = "local") -> WebSession:
        return self.crear_sesion(campaign=campaign, system=system, owner=owner)

    def get(self, session_id: str) -> WebSession | None:
        return self.obtener_sesion(session_id)

    def delete(self, session_id: str) -> None:
        self.eliminar_sesion(session_id)

    def save(self, session: WebSession) -> None:
        self.actualizar_sesion(session.session_id, session.data)

    # ── Claves de API ─────────────────────────────────────────
    def crear_clave(self, owner: str) -> tuple[str, str]:
        """Crea una clave; devuelve (id, texto plano). El texto no se guarda."""
        if not str(owner).strip():
            raise ValueError("la clave necesita un dueño")
        key_id = secrets.token_hex(6)
        token = f"nrr_{secrets.token_urlsafe(32)}"
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO claves_api (id, owner, key_hash, created_at) VALUES (?, ?, ?, ?)",
                (key_id, owner.strip(), hash_key(token), _now()),
            )
        return key_id, token

    def listar_claves(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, owner, created_at, revoked_at FROM claves_api ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def revocar_clave(self, key_id: str) -> bool:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "UPDATE claves_api SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (_now(), key_id),
            )
        return cur.rowcount > 0

    def rotar_clave(self, key_id: str) -> tuple[str, str]:
        """Revoca la clave y emite una nueva para el mismo dueño."""
        with self._conn() as conn:
            row = conn.execute("SELECT owner FROM claves_api WHERE id = ?", (key_id,)).fetchone()
        if row is None:
            raise LookupError(f"clave inexistente: {key_id}")
        self.revocar_clave(key_id)
        return self.crear_clave(row["owner"])

    def hay_claves_activas(self) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM claves_api WHERE revoked_at IS NULL LIMIT 1"
            ).fetchone()
        return row is not None

    def owner_de_clave(self, token: str) -> str | None:
        if not token:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT owner FROM claves_api WHERE key_hash = ? AND revoked_at IS NULL",
                (hash_key(token),),
            ).fetchone()
        return row["owner"] if row else None
