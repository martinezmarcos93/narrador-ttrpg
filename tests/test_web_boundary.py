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
