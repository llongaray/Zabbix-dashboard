"""Contrato JSON-RPC: API token, auth Bearer e armazenamento seguro."""
import pytest

from app.services import zabbix


class FakeResponse:
    status_code = 200
    def __init__(self, result=None, error=None):
        self.payload = {"jsonrpc": "2.0", "id": 1}
        if error:
            self.payload["error"] = error
        else:
            self.payload["result"] = result

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_api_token_uses_bearer_without_username_or_password(monkeypatch):
    observed = {}

    def post(url, **kwargs):
        observed.update(url=url, **kwargs)
        return FakeResponse(result=[{"hostid": "10084"}])

    monkeypatch.setattr(zabbix.requests, "post", post)
    monkeypatch.setenv("ZABBIX_URL", "https://monitor.example.org")
    result = zabbix.call("host.get", {"output": ["hostid"]}, token="abc-token")

    assert result == [{"hostid": "10084"}]
    assert observed["url"] == "https://monitor.example.org/api_jsonrpc.php"
    assert observed["headers"]["Authorization"] == "Bearer abc-token"
    assert "username" not in str(observed["json"])
    assert "password" not in str(observed["json"])


def test_api_version_does_not_send_bearer(monkeypatch):
    observed = {}

    def post(url, **kwargs):
        observed.update(kwargs)
        return FakeResponse(result="7.0.23")

    monkeypatch.setenv("ZABBIX_URL", "https://monitor.example.org")
    monkeypatch.setattr(zabbix.requests, "post", post)
    assert zabbix.api_version() == "7.0.23"
    assert "Authorization" not in observed["headers"]


def test_zabbix_api_error_does_not_become_flask_401(monkeypatch):
    monkeypatch.setenv("ZABBIX_URL", "https://monitor.example.org")
    monkeypatch.setattr(
        zabbix.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            error={"code": -32602, "message": "Not authorized.", "data": ""}
        ),
    )
    with pytest.raises(zabbix.ZabbixError) as info:
        zabbix.verify_token("invalid-token")
    assert info.value.status == 502


def test_no_write_methods_exposed():
    with pytest.raises(zabbix.ZabbixError):
        zabbix.call("host.delete", {}, token="token")
