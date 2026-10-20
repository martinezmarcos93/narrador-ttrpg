"""Minimal server-side session registry.

This is intentionally not a production auth/session backend. It prevents the HTTP
layer from trusting arbitrary session state supplied by the browser and provides a
single seam for Redis/database-backed sessions later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from secrets import token_urlsafe
from threading import RLock
from time import time
from typing import Any


@dataclass
class WebSession:
    session_id: str
    campaign: str
    system: str
    created_at: float = field(default_factory=time)
    data: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, WebSession] = {}
        self._lock = RLock()

    def create(self, *, campaign: str, system: str, owner: str = "local") -> WebSession:
        with self._lock:
            session_id = token_urlsafe(32)
            session = WebSession(session_id=session_id, campaign=campaign, system=system)
            session.data["owner"] = owner
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> WebSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def save(self, session: WebSession) -> None:
        """En memoria la sesión ya es el objeto vivo; existe por simetría con WebStore."""

    def listar_sesiones(self, owner: str | None = None) -> list[WebSession]:
        with self._lock:
            return [s for s in self._sessions.values()
                    if owner is None or s.data.get("owner") == owner]

    def hay_claves_activas(self) -> bool:
        return False

    def owner_de_clave(self, token: str) -> str | None:
        return None
