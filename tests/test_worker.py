"""Coletor não depende de sessões HTTP/WebSocket e agrupa itens por host."""
from app import worker


def test_cycle_persists_hosts_and_metrics_without_web_client(monkeypatch):
    written = {}
    hosts = [{"hostid": "101", "status": "0", "name": "a"},
             {"hostid": "102", "status": "0", "name": "b"}]
    monkeypatch.setattr(worker.zabbix, "hosts", lambda: hosts)
    monkeypatch.setattr(worker.zabbix, "items_for_hosts", lambda ids: [
        {"hostid": "101", "itemid": "1", "key_": "system.cpu.util",
         "value_type": "0", "lastclock": "100", "lastvalue": "50",
         "status": "0", "units": "%"}
    ])
    monkeypatch.setattr(worker.cache, "get", lambda key: None)
    monkeypatch.setattr(worker.cache, "save",
                        lambda key, data: written.update({key: data}))
    monkeypatch.setattr(worker.cache, "save_host",
                        lambda host, items, gauges, diagnostics:
                        written.update({"host_" + host: (items, gauges, diagnostics)}))
    monkeypatch.setattr(worker.cache, "cleanup", lambda *args: None)
    # tick=1 não consulta problem.get, que pode ter latência alta.
    cursor = worker.cycle(cursor=0, tick=1)
    assert cursor == 0
    assert written["overview"]["kpis"]["hosts"] == 2
    assert written["host_101"][1]["cpu"]["value"] == 50
    assert "host_102" in written
    assert written["host_102"][2]["gpu"]["available"] is False


def test_collector_does_not_require_socket_connection():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "app/worker.py").read_text()
    assert "socketio" not in source.lower()
    assert "def main()" in source
