"""History API seleciona history.get vs trend.get e limita a saída."""
from app.services import zabbix


def test_one_day_uses_history_get(monkeypatch):
    observed = []
    monkeypatch.setattr(zabbix, "call", lambda method, params: observed.append(
        (method, params)) or [{"clock": "1", "value": "25"}])
    result = zabbix.history("101", 0, 0, 86400)
    assert result["source"] == "history.get"
    assert observed[0][1]["history"] == 0


def test_seven_days_uses_hourly_trends(monkeypatch):
    observed = []
    monkeypatch.setattr(zabbix, "call", lambda method, params: observed.append(
        (method, params)) or [{"clock": "3600", "value_avg": "24"}])
    result = zabbix.history("101", 0, 0, 7 * 86400)
    assert result["source"] == "trend.get"
    assert observed[0][1]["time_till"] == 7 * 86400
    assert result["points"][0]["value_avg"] == "24"
