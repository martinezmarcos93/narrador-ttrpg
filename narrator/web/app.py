"""Flask application factory.

HTTP is an adapter: validation, session ownership and error translation happen
here; game-state mutations remain behind NarratorService.
"""
from __future__ import annotations

import hmac
import json
import os
import queue
import threading
import time
from collections import defaultdict, deque
from uuid import uuid4

from flask import Flask, Response, jsonify, request, stream_with_context

from narrator.core.narrator_service import NarratorService
from narrator.web.schemas import (
    CreateSessionRequest,
    RollRequest,
    SchemaError,
    TurnRequest,
    error_payload,
)
from narrator.web.service import ADMIN, WebApplicationService


class RateLimiter:
    """Ventana deslizante en memoria por identidad (clave o IP)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, identity: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits[identity]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True


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
    if web_service is None:
        store = None
        db_path = os.getenv("NARRATOR_WEB_DB", "").strip()
        if db_path:
            from narrator.web.store import WebStore

            store = WebStore(db_path)
        web_service = WebApplicationService(
            narrator_service or NarratorService(
                config_path=os.getenv("NARRATOR_CONFIG_PATH", "./config/config.yaml")
            ),
            store,
        )
    service = web_service
    limiter = RateLimiter(int(os.getenv("NARRATOR_RATE_LIMIT", "120")))

    api_key = os.getenv("NARRATOR_API_KEY", "").strip()
    environment = os.getenv("NARRATOR_ENV", "development").strip().lower()
    if environment == "production" and not api_key:
        raise RuntimeError("NARRATOR_API_KEY is required in production")
    allowed_origins = {
        item.strip()
        for item in os.getenv("NARRATOR_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    }

    @app.before_request
    def assign_request_id() -> None:
        request.request_id = request.headers.get("X-Request-ID") or uuid4().hex
        if request.path == "/api/v1/health":
            return
        supplied = request.headers.get("Authorization", "")
        token = supplied[7:].strip() if supplied.startswith("Bearer ") else ""
        stored_keys = service.sessions.hay_claves_activas()
        if api_key and token and hmac.compare_digest(token, api_key):
            request.owner = ADMIN
        elif stored_keys and (owner := service.sessions.owner_de_clave(token)):
            request.owner = owner
        elif api_key or stored_keys:
            return jsonify(error_payload(
                "unauthorized", "authentication required",
                request_id=request.request_id,
            )), 401
        else:
            request.owner = "local"  # desarrollo local sin claves configuradas
        identity = request.owner if request.owner != "local" else (request.remote_addr or "local")
        if not limiter.allow(identity):
            return jsonify(error_payload(
                "rate_limited", "too many requests", request_id=request.request_id,
            )), 429
        origin = request.headers.get("Origin")
        if origin and allowed_origins and origin not in allowed_origins:
            return jsonify(error_payload(
                "forbidden_origin", "origin is not allowed",
                request_id=request.request_id,
            )), 403

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
        session = service.create_session(
            campaign=payload.campaign, system=payload.system, owner=request.owner
        )
        return jsonify({
            "session_id": session.session_id,
            "campaign": session.campaign,
            "system": session.system,
        }), 201

    @app.get("/api/v1/sessions")
    def list_sessions():
        return jsonify({"sessions": service.list_sessions(request.owner)})

    @app.delete("/api/v1/sessions/<session_id>")
    def delete_session(session_id: str):
        service.delete_session(session_id, request.owner)
        return "", 204

    @app.get("/api/v1/sessions/<session_id>/world")
    def world_status(session_id: str):
        return jsonify({
            "session_id": session_id,
            "status": service.world_status(session_id, request.owner),
        })

    @app.post("/api/v1/rolls/resolve")
    def resolve_roll():
        payload = RollRequest.from_dict(request.get_json(silent=True))
        result = service.resolve_roll(payload, request.owner)
        return jsonify({"session_id": payload.session_id, "result": result})

    @app.post("/api/v1/turns")
    def submit_turn():
        payload = TurnRequest.from_dict(request.get_json(silent=True))
        return jsonify(service.submit_turn(payload.session_id, payload.text, request.owner))

    @app.post("/api/v1/turns/stream")
    def stream_turn():
        """Server-Sent Events: 'chunk' por fragmento y 'done' con el resultado final."""
        payload = TurnRequest.from_dict(request.get_json(silent=True))
        owner = request.owner
        service.require_session(payload.session_id, owner)
        events: queue.Queue = queue.Queue()

        def worker():
            try:
                result = service.submit_turn(
                    payload.session_id, payload.text, owner,
                    on_chunk=lambda chunk: events.put(("chunk", {"text": chunk})),
                )
                events.put(("done", result))
            except Exception:
                app.logger.exception("Turno en streaming falló")
                events.put(("error", {"code": "internal_error"}))

        threading.Thread(target=worker, daemon=True).start()

        def generate():
            while True:
                kind, data = events.get()
                yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if kind in {"done", "error"}:
                    break

        return Response(stream_with_context(generate()), mimetype="text/event-stream")

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
