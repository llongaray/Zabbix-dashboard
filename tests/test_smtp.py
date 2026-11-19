from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock

from cryptography.fernet import Fernet
from flask import Flask

from app.routes import bp
from app.services import mailing


def test_gmail_saves_encrypted_password_and_sends_test(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(bp)
    client = app.test_client()
    assert client.get("/api/smtp").status_code == 401
    with client.session_transaction() as session:
        session["admin"] = True

    stored = {}
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(mailing, "get_setting", stored.get)
    monkeypatch.setattr(mailing, "settings_with_prefix",
                        lambda prefix: {k: v for k, v in stored.items() if k.startswith(prefix)})
    monkeypatch.setattr(mailing, "put_setting", stored.__setitem__)
    transport = MagicMock()
    smtp = transport.return_value.__enter__.return_value
    monkeypatch.setattr(mailing.smtplib, "SMTP", transport)
    payload = {
        "provider": "gmail", "email": "admin@example.com", "password": "abcd efgh ijkl mnop",
    }
    assert client.post("/api/smtp/validate", json=payload).status_code == 200
    assert not stored
    transport.assert_called_once_with("smtp.gmail.com", 587, timeout=12)
    assert [call[0] for call in smtp.method_calls] == ["starttls", "login"]
    smtp.login.assert_called_once_with("admin@example.com", "abcdefghijklmnop")
    assert client.post("/api/smtp", json=payload).status_code == 200
    assert "abcdefghijklmnop" not in stored["smtp_sender:admin@example.com"]
    assert client.get("/api/smtp").json["senders"] == [{
        "provider": "gmail", "email": "admin@example.com", "oauth": False,
    }]
    assert client.post("/api/smtp/test", json={
        **payload, "password": "", "destination": "recebedor@example.com",
    }).status_code == 200
    message = smtp.send_message.call_args.args[0]
    assert message["From"] == "admin@example.com"
    assert message["To"] == "recebedor@example.com"

    smtp.login.side_effect = mailing.smtplib.SMTPAuthenticationError(535, b"sensitive")
    previous = stored.copy()
    result = client.post("/api/smtp", json=payload)
    assert result.status_code == 502
    assert "sensitive" not in result.json["error"]
    assert stored == previous


def test_microsoft_callback_requires_state_and_verifies_oauth(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    callback = "http://localhost:5000/smtp/microsoft/callback"
    monkeypatch.setattr(mailing, "oauth_settings", lambda: ("client", "secret", callback))
    exchange = MagicMock(return_value={"access_token": "access", "refresh_token": "refresh"})
    verify = MagicMock()
    save = MagicMock()
    monkeypatch.setattr(mailing, "exchange_token", exchange)
    monkeypatch.setattr(mailing, "verify_credentials", verify)
    monkeypatch.setattr(mailing, "save_sender", save)
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    response = client.post("/api/smtp/microsoft/authorize", json={
        "provider": "microsoft", "email": "admin@example.com",
    })
    parsed = urlsplit(response.json["url"])
    assert parsed.path.startswith("/organizations/")
    query = parse_qs(parsed.query)
    assert query["code_challenge_method"] == ["S256"]
    assert "secret" not in query
    client.get("/smtp/microsoft/callback?code=code&state=invalid")
    exchange.assert_not_called()
    result = client.get("/smtp/microsoft/callback", query_string={
        "code": "code", "state": query["state"][0],
    })
    assert result.location == "/#smtp"
    verify.assert_called_once_with("microsoft", "admin@example.com", "access", oauth=True)
    saved = save.call_args.args[0]
    assert saved["oauth"] and mailing.decrypt(saved["secret"]) == "refresh"
