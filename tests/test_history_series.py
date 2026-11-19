"""Séries reais e limites seguros (80/90/100) do histórico."""
from app.services import history_series


def metric(itemid, key, value="40", units="%"):
    return {
        "itemid": itemid, "key_": key, "value_type": "0",
        "lastvalue": value, "lastclock": "1800000000",
        "units": units, "status": "0",
    }


def test_alert_boundaries():
    assert history_series.severity(79.99) == "normal"
    assert history_series.severity(80) == "warning"
    assert history_series.severity(90) == "critical"
    assert history_series.severity(100) == "maximum"
    assert history_series.severity(None) == "unavailable"


def test_cpu_history_uses_zabbix_and_percent_thresholds(monkeypatch):
    cpu = metric("10", "system.cpu.util")
    monkeypatch.setattr(history_series.cache, "get", lambda key: {
        "items": [cpu], "gauges": {"cpu": {"itemid": "10"}},
    })
    called = []
    def fake_history(itemid, value_type, since, until):
        called.append((itemid, value_type, since, until))
        return {"source": "trend.get", "points": [
            {"clock": "1770000000", "value_avg": "85.5"},
        ]}
    monkeypatch.setattr(history_series.zabbix, "history", fake_history)
    result = history_series.host_series("10084", "cpu", 365)
    assert called and called[0][0] == "10"
    assert result["series"][0]["points"][0]["value"] == 85.5
    assert [t["level"] for t in result["thresholds"]] == [80, 90, 100]


def test_network_without_interface_speed_never_invents_percent(monkeypatch):
    rx = metric("20", "net.if.in[eth0,bytes]", "100000", "bps")
    monkeypatch.setattr(history_series.cache, "get", lambda key: {
        "items": [rx], "gauges": {"network_in": {"itemid": "20"}},
    })
    monkeypatch.setattr(history_series.zabbix, "history", lambda *args: {
        "source": "history.get",
        "points": [{"clock": "1770000000", "value": "100000"}],
    })
    result = history_series.host_series("10084", "network", 1)
    assert result["series"][0]["points"][0]["value"] == 0.1
    assert result["thresholds"] == []
    assert result["capacity_mbps"] is None


def test_network_limits_require_matching_interface_speed(monkeypatch):
    rx = metric("20", "net.if.in[eth0,bytes]", "100000", "bps")
    speed = metric("30", "net.if.speed[eth0]", "1000000000", "bps")
    monkeypatch.setattr(history_series.cache, "get", lambda key: {
        "items": [rx, speed],
        "gauges": {"network_in": {"itemid": "20"}},
    })
    monkeypatch.setattr(history_series.zabbix, "history", lambda *args: {
        "source": "history.get", "points": [
            {"clock": "1770000000", "value": "400000000"}],
    })
    result = history_series.host_series("10084", "network", 1)
    assert result["capacity_mbps"] == 1000
    assert [t["value"] for t in result["thresholds"]] == [800, 900, 1000]


def test_gpu_missing_is_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr(history_series.cache, "get", lambda key: {
        "items": [], "gauges": {},
    })
    result = history_series.host_series("10084", "gpu", 7)
    assert result["series"] == []
    assert "Sem item monitorado" in result["message"]


def test_network_cross_interface_capacity_not_shared(monkeypatch):
    rx = metric("20", "net.if.in[eth0,bytes]", "100000", "bps")
    tx = metric("21", "net.if.out[eth1,bytes]", "120000", "bps")
    speed = metric("30", "net.if.speed[eth0]", "1000000000", "bps")
    monkeypatch.setattr(history_series.cache, "get", lambda key: {
        "items": [rx, tx, speed],
        "gauges": {"network_in": {"itemid": "20"},
                   "network_out": {"itemid": "21"}},
    })
    monkeypatch.setattr(history_series.zabbix, "history", lambda *args: {
        "source": "history.get", "points": [
            {"clock": "1770000000", "value": "100000"}],
    })
    result = history_series.host_series("10084", "network", 1)
    assert result["capacity_mbps"] is None
    assert result["thresholds"] == []
