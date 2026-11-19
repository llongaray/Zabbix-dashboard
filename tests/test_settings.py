"""Configuração dinâmica não faz logout e não grava token inválido."""
import pytest
from flask import Flask

from app.routes import bp
from app.routes import settings
from app.services import zabbix


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "safe-test-password")
    monkeypatch.setenv("FERNET_KEY", "key-for-mocked-encryption")
    app = Flask(__name__)
    app.secret_key = "test-session-secret"
    app.register_blueprint(bp)
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        response = test_client.post(
            "/login", data={"password": "safe-test-password"}
        )
        assert response.status_code == 302
        yield test_client


def test_valid_token_persists_without_logout(client, monkeypatch):
    saved = {}
    monkeypatch.setattr(settings.zabbix, "verify_token", lambda token: {
        "validated": True, "latency_ms": 21, "host_accessible": True,
    })
    monkeypatch.setattr(settings, "encrypt", lambda raw: "encrypted:" + raw)
    monkeypatch.setattr(settings, "put_setting", lambda name, value: saved.update(
        {name: value}
    ))
    monkeypatch.setattr(settings.socketio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(settings, "request_refresh", lambda: None)

    response = client.post("/api/config", json={"token": "secret-token"})
    assert response.status_code == 200
    assert response.json["ok"] is True
    assert saved == {"zabbix_token": "encrypted:secret-token"}
    assert client.get("/api/session").json == {"authenticated": True}


def test_invalid_token_does_not_replace_existing(client, monkeypatch):
    saved = []
    def reject(_token):
        raise zabbix.ZabbixError("Token rejeitado pelo Zabbix.", 502)
    monkeypatch.setattr(settings.zabbix, "verify_token", reject)
    monkeypatch.setattr(settings, "put_setting", lambda *a: saved.append(a))

    response = client.post("/api/config", json={"token": "bad"})
    assert response.status_code == 502
    assert response.json["code"] == "ZABBIX_ERROR"
    assert not saved
    assert client.get("/api/session").json["authenticated"] is True
