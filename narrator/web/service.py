"""Application service facade used by HTTP routes.

No Flask objects are allowed here. This keeps the web adapter replaceable and
makes authorization/session checks explicit at the boundary.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable

from narrator.core.narrator_service import NarratorService
from narrator.web.session_store import SessionStore, WebSession

ADMIN = "admin"


class WebApplicationService:
    def __init__(
        self,
        narrator_service: NarratorService,
        sessions: SessionStore | None = None,
        llm=None,
    ) -> None:
        self.narrator = narrator_service
        self.sessions = sessions or SessionStore()
        self._llm = llm
        # El motor comparte un único estado de campaña: los turnos se serializan.
        self._turn_lock = threading.Lock()

    @property
    def llm(self):
        if self._llm is None:
            from narrator.core.llm_client import LLMClient

            self._llm = LLMClient(model=os.getenv("NARRATOR_MODEL", "qwen3:1.7b"))
        return self._llm

    def create_session(self, *, campaign: str, system: str, owner: str = "local") -> WebSession:
        return self.sessions.create(campaign=campaign, system=system, owner=owner)

    def require_session(self, session_id: str, owner: str | None = None) -> WebSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise LookupError("session not found")
        # Una sesión ajena se reporta como inexistente (no se revela que existe).
        if owner not in (None, ADMIN) and session.data.get("owner", "local") != owner:
            raise LookupError("session not found")
        return session

    def list_sessions(self, owner: str) -> list[dict[str, Any]]:
        sessions = self.sessions.listar_sesiones(None if owner == ADMIN else owner)
        return [{"session_id": s.session_id, "campaign": s.campaign, "system": s.system}
                for s in sessions]

    def delete_session(self, session_id: str, owner: str | None = None) -> None:
        self.require_session(session_id, owner)
        self.sessions.delete(session_id)

    def world_status(self, session_id: str, owner: str | None = None) -> str:
        self.require_session(session_id, owner)
        return self.narrator.world_status()

    def resolve_roll(self, request: Any, owner: str | None = None) -> dict[str, Any] | None:
        self.require_session(request.session_id, owner)
        return self.narrator.resolve_roll(
            action_text=request.action_text,
            character=request.character,
            system_slug=request.system_slug,
            rolls=request.rolls,
            sides=request.sides,
        )

    def submit_turn(self, session_id: str, text: str, owner: str | None = None,
                    on_chunk: Callable[[str], None] | None = None) -> dict[str, Any]:
        session = self.require_session(session_id, owner)
        app_state = session.data.setdefault("app_state", {
            "system_slug": session.system, "messages": [], "character": {},
        })
        with self._turn_lock:
            result = self.narrator.run_turn(app_state, text, self.llm, on_chunk=on_chunk)
        session.data["app_state"] = app_state
        self.sessions.save(session)
        contract = result.get("contract") or {}
        return {
            "session_id": session_id,
            "turn_id": contract.get("turn_id", ""),
            "text": result["text"],
            "intent": result.get("intent", ""),
            "proposal_applied": bool((result.get("proposal_result") or {}).get("applied")),
            "leaks": len(result.get("leaks") or []),
            "errors": contract.get("errors", []),
        }
