"""Application service facade used by HTTP routes.

No Flask objects are allowed here. This keeps the web adapter replaceable and
makes authorization/session checks explicit at the boundary.
"""
from __future__ import annotations

from typing import Any

from narrator.core.narrator_service import NarratorService
from narrator.web.session_store import SessionStore, WebSession


class WebApplicationService:
    def __init__(
        self,
        narrator_service: NarratorService,
        sessions: SessionStore | None = None,
    ) -> None:
        self.narrator = narrator_service
        self.sessions = sessions or SessionStore()

    def create_session(self, *, campaign: str, system: str) -> WebSession:
        return self.sessions.create(campaign=campaign, system=system)

    def require_session(self, session_id: str) -> WebSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise LookupError("session not found")
        return session

    def world_status(self, session_id: str) -> str:
        self.require_session(session_id)
        return self.narrator.world_status()

    def resolve_roll(self, request: Any) -> dict[str, Any] | None:
        self.require_session(request.session_id)
        return self.narrator.resolve_roll(
            action_text=request.action_text,
            character=request.character,
            system_slug=request.system_slug,
            rolls=request.rolls,
            sides=request.sides,
        )
