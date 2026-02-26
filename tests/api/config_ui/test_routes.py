from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.config_ui import routes as config_routes


def _build_app(settings, initializer=None):
    app = FastAPI()
    app.include_router(config_routes.router)
    app.state.settings = settings
    app.state.initializer = initializer
    return app


def _localhost_headers():
    return {"X-Forwarded-For": "127.0.0.1"}


def test_config_ui_rejects_non_localhost(tmp_path, monkeypatch):
    monkeypatch.setattr(config_routes, "STATION_DIR", tmp_path)
    monkeypatch.setattr(config_routes, "RESTART_MARKER", tmp_path / ".restart")

    settings = SimpleNamespace(
        trusted_proxies="testclient",
        station_id="station-test",
        get_tier_config_by_tickets=lambda _: None,
    )

    app = _build_app(settings)
    client = TestClient(app)

    response = client.get("/api/config")
    assert response.status_code == 403


def test_save_config_can_clear_values(tmp_path, monkeypatch):
    monkeypatch.setattr(config_routes, "STATION_DIR", tmp_path)
    monkeypatch.setattr(config_routes, "RESTART_MARKER", tmp_path / ".restart")
    monkeypatch.setattr(config_routes.os, "kill", lambda *_: None)

    (tmp_path / "env.example").write_text(
        "OPENROUTER_MANAGEMENT_KEY=sk-or-v1-default\n"
        "# STATION_RELOAD=false\n"
    )

    settings = SimpleNamespace(
        trusted_proxies="testclient",
        station_id="station-test",
        get_tier_config_by_tickets=lambda _: None,
    )

    app = _build_app(settings)
    client = TestClient(app)

    response = client.put(
        "/api/config",
        headers=_localhost_headers(),
        json={"env": {"OPENROUTER_MANAGEMENT_KEY": "", "STATION_RELOAD": "true"}},
    )
    assert response.status_code == 200

    env_contents = (tmp_path / ".env").read_text()
    assert "# OPENROUTER_MANAGEMENT_KEY=" in env_contents
    assert "STATION_RELOAD=true" in env_contents


def test_runtime_does_not_expose_ticket_private_key(tmp_path, monkeypatch):
    monkeypatch.setattr(config_routes, "STATION_DIR", tmp_path)
    monkeypatch.setattr(config_routes, "TICKET_KEYS_FILE", tmp_path / "ticket_keys.json")

    config_routes.TICKET_KEYS_FILE.write_text(
        '{"public_key": "pub-key", "private_key": "priv-key"}'
    )

    settings = SimpleNamespace(
        trusted_proxies="testclient",
        station_id="station-test",
        get_tier_config_by_tickets=lambda n: {"credit_limit": 2.0, "duration_minutes": 60}
        if n in (1, 2, 3)
        else None,
    )
    initializer = SimpleNamespace(
        ticket_request_bearer_token="token-abc",
        identity=SimpleNamespace(is_loaded=True, public_key_hex="station-public"),
        ticket_issuance_service=object(),
        ticket_redemption_service=object(),
        ephemeral_key_cleanup_worker=None,
    )

    app = _build_app(settings, initializer=initializer)
    client = TestClient(app)

    response = client.get("/api/config/runtime", headers=_localhost_headers())
    assert response.status_code == 200
    payload = response.json()

    assert payload["ticket_public_key"] == "pub-key"
    assert "ticket_private_key" not in payload
