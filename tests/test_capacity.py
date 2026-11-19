from app.services import capacity


def test_capacity_uses_peak_and_reserves_headroom(monkeypatch):
    hour = 1800000000 // 3600 * 3600
    monkeypatch.setattr(capacity.time, "time", lambda: hour)
    hosts = [{"hostid": str(i), "name": name}
             for i, name in enumerate(("Origem", "Destino", "Histórico curto"), 1)]
    records = {"overview": {"hosts": hosts}}
    for i, size in enumerate((32, 16, 64), 1):
        records[f"host:{i}"] = {
            "gauges": {"memory": {"itemid": str(i), "value": 20}},
            "specs": {"ram_bytes": size * capacity.GIB},
            "items": [{"itemid": str(i + 10), "key_": "vm.memory.size[total]"}],
        }
    monkeypatch.setattr(capacity.cache, "get", records.get)
    start = hour - capacity.HOURS * 3600
    stamps = range(start, hour, 3600)
    rows = []
    for itemid, peak, size in (("1", 37.5, 32), ("2", 90, 16), ("3", 10, 64)):
        rows.extend({"itemid": itemid, "clock": stamp, "value_min": "5", "value_max": peak}
                    for stamp in (list(stamps)[:12] if itemid == "3" else stamps))
        rows.extend({"itemid": str(int(itemid) + 10), "clock": stamp,
                     "value_min": size * capacity.GIB, "value_max": size * capacity.GIB}
                    for stamp in stamps)
    monkeypatch.setattr(capacity.zabbix, "call", lambda method, params: rows)
    report = capacity.report()
    assert report["hosts"][0]["peak_gib"] == 12
    assert report["hosts"][0]["releasable_gib"] == 14
    assert report["hosts"][2]["releasable_gib"] == 0
    assert report["suggestions"] == [{"from": "Origem", "to": "Destino", "gib": 2}]
