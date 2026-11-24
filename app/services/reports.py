"""Consultas de relatórios na API Zabbix 7.0."""
from collections import Counter
from statistics import mean
import time

from app.services import cache, zabbix

EVENT_LIMIT = 5000


def incidents(days, group_id=None, severity=None, tag=None):
    now = int(time.time())
    params = {
        "source": 0, "object": 0, "value": [1],
        "time_from": now - days * 86400, "time_till": now,
        "output": ["eventid", "objectid", "clock", "name", "severity", "r_eventid"],
        "selectAcknowledges": ["clock", "action"],
        "selectHosts": ["hostid", "name"],
        "sortfield": "eventid", "sortorder": "DESC", "limit": EVENT_LIMIT + 1,
    }
    if group_id:
        params["groupids"] = [group_id]
    if severity is not None:
        params["severities"] = [severity]
    if tag:
        params["tags"] = [{"tag": tag, "operator": 4}]
    events = zabbix.call("event.get", params)
    events, truncated = events[:EVENT_LIMIT], len(events) > EVENT_LIMIT
    recovery_ids = list(dict.fromkeys(
        event["r_eventid"] for event in events if event["r_eventid"] != "0"
    ))
    recovery_times = {}
    for offset in range(0, len(recovery_ids), 500):
        result = zabbix.call("event.get", {
            "source": 0, "object": 0, "value": [0],
            "eventids": recovery_ids[offset:offset + 500], "output": ["eventid", "clock"],
        })
        recovery_times.update((row["eventid"], int(row["clock"])) for row in result)
    rows = []
    for event in events:
        start = int(event["clock"])
        recovery = recovery_times.get(event["r_eventid"])
        ack = min((int(a["clock"]) for a in event.get("acknowledges", [])
                   if int(a["action"]) & 2), default=None)
        rows.append({
            "id": event["eventid"], "name": event["name"],
            "hosts": ", ".join(host["name"] for host in event.get("hosts", [])),
            "severity": int(event["severity"]), "opened_at": start,
            "resolved": event["r_eventid"] != "0",
            "recovery_seconds": recovery - start if recovery is not None and recovery >= start else None,
            "ack_seconds": ack - start if ack is not None and ack >= start else None,
        })
    resolved = sum(row["resolved"] for row in rows)
    durations = [row["recovery_seconds"] for row in rows if row["recovery_seconds"] is not None]
    counts = Counter(event["objectid"] for event in events)
    names = {event["objectid"]: event["name"] for event in reversed(events)}
    return {"rows": rows, "truncated": truncated, "open": len(rows) - resolved,
            "resolved": resolved, "mean_recovery_seconds": round(mean(durations)) if durations else None,
            "recurring": [{"name": names[key], "count": count} for key, count in counts.most_common(5)]}


def sla_catalog():
    return zabbix.call("sla.get", {
        "output": ["slaid", "name", "slo", "period", "timezone"],
        "filter": {"status": 1}, "sortfield": "name",
    })


def availability(sla_id):
    result = zabbix.call("sla.getsli", {"slaid": sla_id, "periods": 6})
    service_ids = result["serviceids"]
    services = zabbix.call("service.get", {
        "serviceids": service_ids, "output": ["serviceid", "name"],
    }) if service_ids else []
    names = {str(row["serviceid"]): row["name"] for row in services}
    return [
        {"service": names.get(str(service_id), str(service_id)), **period, **result["sli"][i][j]}
        for i, period in enumerate(result["periods"])
        for j, service_id in enumerate(service_ids)
    ]


def collection_health():
    unsupported = zabbix.call("item.get", {
        "output": ["itemid", "name"], "filter": {"state": 1, "status": 0},
        "monitored": True, "selectHosts": ["name"], "limit": 201,
    })
    scenarios = zabbix.call("httptest.get", {
        "output": ["httptestid", "name", "hostid"], "filter": {"status": 0},
        "limit": 201,
    })
    web_items = zabbix.call("item.get", {
        "output": ["name", "lastvalue", "lastclock"], "webitems": True,
        "search": {"key_": "web.test.fail["}, "startSearch": True,
        "monitored": True, "selectHosts": ["name"], "limit": 201,
    })
    web_failures = [row for row in web_items[:200]
                    if row["lastvalue"].isdigit() and int(row["lastvalue"]) > 0]
    stale_hosts = []
    for host in (cache.get("overview") or {}).get("hosts", []):
        gauges = (cache.get("host:" + str(host["hostid"])) or {}).get("gauges", {})
        stale_metrics = [metric for metric, gauge in gauges.items()
                         if gauge and int(gauge["lastclock"]) < time.time() - 3600]
        if stale_metrics:
            stale_hosts.append({"name": host.get("name") or host["host"], "metrics": stale_metrics})
    return {"unsupported": unsupported[:200], "scenarios": scenarios[:200],
            "web_failures": web_failures, "stale_hosts": stale_hosts[:200],
            "truncated": any(len(rows) > 200 for rows in (unsupported, scenarios, web_items, stale_hosts))}
