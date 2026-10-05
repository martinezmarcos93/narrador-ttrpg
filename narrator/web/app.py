"""Flask application factory.

HTTP is an adapter: validation, session ownership and error translation happen
here; game-state mutations remain behind NarratorService.
"""
from __future__ import annotations

import os
from uuid import uuid4

from flask import Flask, jsonify, request

from narrator.core.narrator_service import NarratorService
from narrator.web.schemas import (
    CreateSessionRequest,
    RollRequest,
    SchemaError,
    TurnRequest,
    error_payload,
)
from narrator.web.service import WebApplicationService


def create_app(
    *,
    narrator_service: NarratorService | None = None,
    web_service: WebApplicationService | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=int(os.getenv("NARRATOR_MAX_REQUEST_BYTES", str(256 * 1024))),
        JSON_SORT_KEYS=False,
    )
    service = web_service or WebApplicationService(
        narrator_service or NarratorService(
            config_path=os.getenv("NARRATOR_CONFIG_PATH", "./config/config.yaml")
        )
    )

    @app.before_request
    def assign_request_id() -> None:
        request.request_id = request.headers.get("X-Request-ID") or uuid4().hex

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/api/v1/health")
    def health():
        return jsonify({"ok": True, "service": "narrator", "api_version": "v1"})

    @app.post("/api/v1/sessions")
    def create_session():
        payload = CreateSessionRequest.from_dict(request.get_json(silent=True))
        session = service.create_session(campaign=payload.campaign, system=payload.system)
        return jsonify({
            "session_id": session.session_id,
            "campaign": session.campaign,
            "system": session.system,
        }), 201

    @app.get("/api/v1/sessions/<session_id>/world")
    def world_status(session_id: str):
        return jsonify({
            "session_id": session_id,
            "status": service.world_status(session_id),
        })

    @app.post("/api/v1/rolls/resolve")
    def resolve_roll():
        payload = RollRequest.from_dict(request.get_json(silent=True))
        result = service.resolve_roll(payload)
        return jsonify({"session_id": payload.session_id, "result": result})

    @app.post("/api/v1/turns")
    def submit_turn():
        # The first API contract deliberately validates and owns the session.
        # LLM streaming is added only after the non-streaming contract is stable.
        payload = TurnRequest.from_dict(request.get_json(silent=True))
        service.require_session(payload.session_id)
        return jsonify({
            "session_id": payload.session_id,
            "accepted": True,
            "status": "queued_for_turn_engine",
            "text": payload.text,
        }), 202

    @app.errorhandler(SchemaError)
    def schema_error(exc):
        return jsonify(error_payload(
            "invalid_request", str(exc), request_id=request.request_id
        )), 400

    @app.errorhandler(LookupError)
    def not_found_error(exc):
        return jsonify(error_payload(
            "not_found", str(exc), request_id=request.request_id
        )), 404

    @app.errorhandler(413)
    def too_large(_exc):
        return jsonify(error_payload(
            "payload_too_large", "request body exceeds configured limit",
            request_id=request.request_id,
        )), 413

    @app.errorhandler(Exception)
    def unexpected_error(_exc):
        # Do not expose stack traces, paths, provider errors or internal state.
        app.logger.exception("Unhandled API exception request_id=%s", request.request_id)
        return jsonify(error_payload(
            "internal_error", "internal server error", request_id=request.request_id
        )), 500

    return app
