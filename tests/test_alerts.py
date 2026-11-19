from unittest.mock import Mock

from app.services import alerts


def test_alert_matches_hosts_and_deduplicates_overlapping_groups(monkeypatch):
    sender = {"email": "monitor@example.com"}
    first = "first@example.com"
    second = "second@example.com"
    started = int(alerts.time.time()) - 15
    common = {"enabled": True, "sender": sender["email"], "starts_at": started}
    monkeypatch.setattr(alerts, "groups", lambda: [
        {**common, "scope": "selected", "hosts": ["1"], "recipients": [first]},
        {**common, "scope": "all", "hosts": [], "recipients": [first, second]},
        {**common, "scope": "selected", "hosts": ["2"], "recipients": ["other@example.com"]},
    ])
    monkeypatch.setattr(alerts, "recipients", lambda: {
        address: address for address in (first, second, "other@example.com")
    })
    monkeypatch.setattr(alerts.mailing, "senders", lambda: {sender["email"]: sender})
    monkeypatch.setattr(alerts.cache, "get", lambda _: {"hosts": [{"hostid": "1"}, {"hostid": "2"}]})
    monkeypatch.setattr(alerts.zabbix, "call", Mock(side_effect=[
        [{"eventid": "10", "objectid": "123", "name": "Disk full",
          "clock": str(started + 1), "severity": "3"}],
        [{"triggerid": "123", "hosts": [{"hostid": "1", "name": "Servidor A"}]}],
    ]))
    claimed = set()

    def claim(key):
        value = tuple(key.values())
        if value in claimed:
            return False
        claimed.add(value)
        return True

    monkeypatch.setattr(alerts, "claim_delivery", claim)
    mark = Mock()
    send = Mock()
    monkeypatch.setattr(alerts, "mark_sent", mark)
    monkeypatch.setattr(alerts.mailing, "send_report", send)
    alerts.dispatch()
    assert [call.args[0] for call in send.call_args_list] == [first, second]
    assert all(call.kwargs["config"] is sender for call in send.call_args_list)
    assert mark.call_count == 2
