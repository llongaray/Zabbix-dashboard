"""O navegador nunca deve iniciar requisição remota ao abrir um host."""
from flask import Flask

from app.routes import bp, monitoring as monitor_routes


def test_snapshot_and_items_are_served_from_postgres_cache(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-only"
    app.register_blueprint(bp)
    app.config["TESTING"] = True

    overview = {"hosts": [{"hostid": "10084"}], "kpis": {"hosts": 1},
                "problems": [], "status": "ready"}
    host = {"hostid": "10084", "items": [{"itemid": "1", "name": "CPU"}],
            "gauges": {"cpu": {"value": 25.4, "units": "%"}}}
    monkeypatch.setattr(monitor_routes.cache, "get", lambda key: {
        "overview": overview, "host:10084": host,
    }.get(key))
    monkeypatch.setattr(monitor_routes.zabbix, "hosts", lambda: (_ for _ in ())
                        .throw(AssertionError("remote host.get must not run")))
    monkeypatch.setattr(monitor_routes.zabbix, "items", lambda host_id: (
        _ for _ in ()).throw(AssertionError("remote item.get must not run")))

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["admin"] = True
        response = client.get("/api/snapshot")
        assert response.status_code == 200
        assert response.json["hosts"][0]["hostid"] == "10084"
        items = client.get("/api/hosts/10084/items?include_gauges=1")
        assert items.status_code == 200
        assert items.json["gauges"]["cpu"]["value"] == 25.4


def test_missing_first_batch_is_pending_not_500(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "local-test"
    app.register_blueprint(bp)
    monkeypatch.setattr(monitor_routes.cache, "get", lambda key: None)
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["admin"] = True
        response = client.get("/api/hosts/10084/items?include_gauges=1")
        assert response.status_code == 200
        assert response.json["pending"] is True
        assert response.json["items"] == []
