"""Small, dependency-light DTO validation for the HTTP boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SchemaError(ValueError):
    pass


def _string(value: Any, name: str, *, max_length: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{name} must be a non-empty string")
    value = value.strip()
    if len(value) > max_length:
        raise SchemaError(f"{name} exceeds maximum length")
    return value


@dataclass(frozen=True)
class CreateSessionRequest:
    campaign: str = "default"
    system: str = "generic"

    @classmethod
    def from_dict(cls, data: Any) -> "CreateSessionRequest":
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise SchemaError("JSON body must be an object")
        campaign = _string(data.get("campaign", "default"), "campaign", max_length=120)
        system = _string(data.get("system", "generic"), "system", max_length=80)
        return cls(campaign=campaign, system=system)


@dataclass(frozen=True)
class TurnRequest:
    text: str
    session_id: str

    @classmethod
    def from_dict(cls, data: Any) -> "TurnRequest":
        if not isinstance(data, dict):
            raise SchemaError("JSON body must be an object")
        return cls(
            text=_string(data.get("text"), "text", max_length=12000),
            session_id=_string(data.get("session_id"), "session_id", max_length=128),
        )


@dataclass(frozen=True)
class RollRequest:
    session_id: str
    action_text: str
    rolls: list[int]
    sides: int
    system_slug: str
    character: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any) -> "RollRequest":
        if not isinstance(data, dict):
            raise SchemaError("JSON body must be an object")
        session_id = _string(data.get("session_id"), "session_id", max_length=128)
        action_text = _string(data.get("action_text"), "action_text", max_length=4000)
        system_slug = _string(data.get("system_slug", "generic"), "system_slug", max_length=80)
        rolls = data.get("rolls")
        if not isinstance(rolls, list) or not rolls or len(rolls) > 100:
            raise SchemaError("rolls must be a non-empty list with at most 100 values")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in rolls):
            raise SchemaError("rolls must contain integers")
        sides = data.get("sides")
        if not isinstance(sides, int) or sides not in {4, 6, 8, 10, 12, 20, 100}:
            raise SchemaError("unsupported dice sides")
        character = data.get("character", {})
        if not isinstance(character, dict):
            raise SchemaError("character must be an object")
        return cls(session_id, action_text, rolls, sides, system_slug, character)


def error_payload(code: str, message: str, *, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}
