from narrator.web.app import create_app
from narrator.web.session_store import SessionStore


class FakeNarrator:
    def world_status(self):
        return "ok"

    def resolve_roll(self, **kwargs):
        return {"success": True}


def _app():
    from narrator.web.service import WebApplicationService
    return create_app(web_service=WebApplicationService(FakeNarrator(), SessionStore()))


def test_health_is_public_and_versioned():
    client = _app().test_client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json["api_version"] == "v1"


def test_session_is_server_owned():
    client = _app().test_client()
    response = client.post("/api/v1/sessions", json={"campaign": "demo", "system": "generic"})
    assert response.status_code == 201
    session_id = response.json["session_id"]
    assert len(session_id) >= 32


def test_unknown_session_is_rejected():
    client = _app().test_client()
    response = client.get("/api/v1/sessions/nope/world")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "not_found"


def test_invalid_roll_payload_is_rejected():
    client = _app().test_client()
    response = client.post("/api/v1/rolls/resolve", json={
        "session_id": "nope",
        "action_text": "golpe",
        "rolls": [20],
        "sides": 7,
    })
    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_request"


def test_request_id_is_returned_in_error_payload():
    client = _app().test_client()
    response = client.post("/api/v1/sessions", json={"campaign": ""})
    assert response.status_code == 400
    assert response.json["error"]["request_id"]


def test_production_requires_api_key(monkeypatch):
    monkeypatch.setenv("NARRATOR_ENV", "production")
    monkeypatch.delenv("NARRATOR_API_KEY", raising=False)
    try:
        create_app(web_service=None, narrator_service=FakeNarrator())
    except RuntimeError as exc:
        assert "NARRATOR_API_KEY" in str(exc)
    else:
        raise AssertionError("production app must require NARRATOR_API_KEY")


def test_bearer_key_is_enforced(monkeypatch):
    monkeypatch.setenv("NARRATOR_API_KEY", "test-secret")
    app = _app()
    client = app.test_client()
    response = client.get("/api/v1/sessions/nope/world")
    assert response.status_code == 401
    response = client.get(
        "/api/v1/sessions/nope/world",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 404


# ── Persistencia, identidad, turnos y límites (Fase K) ─────────
class _TurnNarrator(FakeNarrator):
    def run_turn(self, app_state, text, llm, on_chunk=None, **kwargs):
        if on_chunk:
            on_chunk("Hola ")
            on_chunk("mundo")
        app_state["messages"].append({"role": "user", "content": text})
        return {"text": "Hola mundo", "intent": "player_action", "proposal_result": None,
                "leaks": [], "contract": {"turn_id": "t1", "errors": []}}


def _store_app(tmp_path, monkeypatch, **env):
    from narrator.web.service import WebApplicationService
    from narrator.web.store import WebStore

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    store = WebStore(tmp_path / "web.db")
    app = create_app(web_service=WebApplicationService(_TurnNarrator(), store, llm=object()))
    return app, store


def test_store_persists_sessions_and_api_keys(tmp_path):
    from narrator.web.store import WebStore

    store = WebStore(tmp_path / "web.db")
    session = store.crear_sesion(campaign="c", system="vtm_v20", owner="ana")
    store.actualizar_sesion(session.session_id, {"owner": "ana", "app_state": {"messages": [1]}})
    reopened = WebStore(tmp_path / "web.db")
    assert reopened.obtener_sesion(session.session_id).data["app_state"] == {"messages": [1]}
    key_id, token = reopened.crear_clave("ana")
    assert reopened.owner_de_clave(token) == "ana"
    new_id, new_token = reopened.rotar_clave(key_id)
    assert reopened.owner_de_clave(token) is None
    assert reopened.owner_de_clave(new_token) == "ana"
    assert reopened.revocar_clave(new_id) and reopened.owner_de_clave(new_token) is None


def test_multiuser_keys_isolate_sessions(tmp_path, monkeypatch):
    monkeypatch.delenv("NARRATOR_API_KEY", raising=False)
    app, store = _store_app(tmp_path, monkeypatch)
    _, ana = store.crear_clave("ana")
    _, beto = store.crear_clave("beto")
    client = app.test_client()
    assert client.post("/api/v1/sessions", json={}).status_code == 401
    created = client.post("/api/v1/sessions", json={"campaign": "c"},
                          headers={"Authorization": f"Bearer {ana}"})
    sid = created.json["session_id"]
    other = client.get(f"/api/v1/sessions/{sid}/world", headers={"Authorization": f"Bearer {beto}"})
    assert other.status_code == 404
    mine = client.get("/api/v1/sessions", headers={"Authorization": f"Bearer {ana}"})
    assert [s["session_id"] for s in mine.json["sessions"]] == [sid]


def test_turn_endpoint_runs_engine_and_persists_history(tmp_path, monkeypatch):
    monkeypatch.delenv("NARRATOR_API_KEY", raising=False)
    app, store = _store_app(tmp_path, monkeypatch)
    client = app.test_client()
    sid = client.post("/api/v1/sessions", json={"campaign": "c"}).json["session_id"]
    response = client.post("/api/v1/turns", json={"session_id": sid, "text": "Entro"})
    assert response.status_code == 200
    assert response.json["text"] == "Hola mundo" and response.json["turn_id"] == "t1"
    assert store.obtener_sesion(sid).data["app_state"]["messages"][0]["content"] == "Entro"


def test_turn_stream_uses_server_sent_events(tmp_path, monkeypatch):
    monkeypatch.delenv("NARRATOR_API_KEY", raising=False)
    app, _ = _store_app(tmp_path, monkeypatch)
    client = app.test_client()
    sid = client.post("/api/v1/sessions", json={"campaign": "c"}).json["session_id"]
    response = client.post("/api/v1/turns/stream", json={"session_id": sid, "text": "Entro"})
    body = response.get_data(as_text=True)
    assert response.mimetype == "text/event-stream"
    assert body.count("event: chunk") == 2 and "event: done" in body


def test_rate_limit_returns_429(tmp_path, monkeypatch):
    monkeypatch.delenv("NARRATOR_API_KEY", raising=False)
    app, _ = _store_app(tmp_path, monkeypatch, NARRATOR_RATE_LIMIT="2")
    client = app.test_client()
    codes = [client.get("/api/v1/sessions").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert client.get("/api/v1/health").status_code == 200  # health no consume cupo


def test_web_ui_is_served_with_strict_csp():
    client = _app().test_client()
    page = client.get("/")
    assert page.status_code == 200
    assert b'<script src="/static/app.js" defer>' in page.data
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    assert client.get("/static/app.js").status_code == 200
    assert b"<script>" not in page.data  # sin JS inline: compatible con la CSP


def test_unknown_route_is_404_not_500_and_oversized_body_is_413(monkeypatch):
    monkeypatch.setenv("NARRATOR_MAX_REQUEST_BYTES", "1024")
    client = _app().test_client()
    missing = client.get("/static/..%2f..%2fconfig%2fconfig.yaml")
    assert missing.status_code == 404
    assert missing.json["error"]["code"] == "not_found"
    assert client.post("/api/v1/turns", data="x" * 5000).status_code == 413
