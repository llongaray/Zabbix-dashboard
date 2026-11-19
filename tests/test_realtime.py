"""Socket.IO deve aceitar apenas sessões administrativas Flask."""
import pytest
from flask import Flask

from app import realtime


@pytest.fixture()
def app(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "temporary-test-key"
    # Evita iniciar o coletor infinito nos testes de handshake.
    monkeypatch.setattr(realtime, "_started", True)
    realtime.socketio.init_app(app)
    yield app


def test_socket_rejects_anonymous_session(app):
    socket_client = realtime.socketio.test_client(app)
    assert not socket_client.is_connected()


def test_socket_accepts_authenticated_session(app):
    browser = app.test_client()
    with browser.session_transaction() as session:
        session["admin"] = True
    socket_client = realtime.socketio.test_client(
        app, flask_test_client=browser
    )
    assert socket_client.is_connected()
    socket_client.disconnect()
