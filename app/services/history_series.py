"""Normaliza históricos oficiais do Zabbix para gráficos Chart.js.

CPU, RAM, GPU são percentuais; rede é Mbps. Nenhuma ocupação percentual
é estimada para rede sem velocidade nominal da interface monitorada.
"""
import math
import re

from app.services import cache, zabbix

METRICS = {
    "cpu": ("CPU", "%"),
    "memory": ("Memória RAM", "%"),
    "gpu": ("GPU", "%"),
    "network": ("Rede RX / TX", "Mbps"),
}

UNITS = {
    "bps": 1, "bit/s": 1, "bits/s": 1,
    "Kbps": 1000, "Mbps": 1_000_000, "Gbps": 1_000_000_000,
    "Bps": 8, "B/s": 8, "byte/s": 8,
    "KBps": 8000, "MBps": 8_000_000,
}


def normalized(value, units):
    """Converte valores de tráfego para Mbps, nunca confunde B com Bps."""
    factor = UNITS.get(str(units).strip())
    if factor is None:
        return None
    return round(float(value) * factor / 1_000_000, 4)


def interface_name(key):
    """Extrai uma interface da chave net.if.* (com aspas quando existirem)."""
    if "[" not in key:
        return None
    inside = key.split("[", 1)[1].rsplit("]", 1)[0].strip()
    match = re.match(r'^"([^"]+)"', inside)
    return (match.group(1) if match else inside.split(",", 1)[0]).strip()


def link_capacity(items, selected):
    """Encontra velocidade da MESMA interface usada nos dados RX/TX."""
    if not selected:
        return None
    name = interface_name(str(selected.get("key_") or ""))
    if not name:
        return None
    speeds = [
        item for item in items
        if str(item.get("key_", "")).lower().startswith("net.if.speed[")
        and interface_name(str(item["key_"])) == name
    ]
    for item in speeds:
        try:
            speed = normalized(item["lastvalue"], item.get("units", ""))
            if speed is not None and speed > 0:
                return speed
        except (ValueError, TypeError):
            continue
    return None


def severity(value):
    """Régua de estados para métricas realmente percentuais."""
    if value is None or not math.isfinite(value):
        return "unavailable"
    if value >= 100:
        return "maximum"
    if value >= 90:
        return "critical"
    if value >= 80:
        return "warning"
    return "normal"


def _history(item, kind, days):
    value_type = int(item.get("value_type", 0))
    now = int(__import__("time").time())
    result = zabbix.history(item["itemid"], value_type, now - days * 86400, now)
    points = []
    for point in result["points"]:
        try:
            value = float(point.get("value_avg", point.get("value")))
            if kind.startswith("network"):
                value = normalized(value, item.get("units", ""))
            if value is None or not math.isfinite(value):
                continue
            if kind in ("cpu", "memory", "gpu") and not 0 <= value <= 100:
                continue
            points.append({"clock": int(point["clock"]), "value": round(value, 4)})
        except (TypeError, ValueError, KeyError):
            continue
    return result["source"], points


def host_series(host_id, kind, days):
    """Usa itemid conhecido no cache e consulta histórico oficial do Zabbix."""
    if kind not in METRICS or not str(host_id).isdigit():
        raise ValueError("Host ou métrica inválida.")
    if days not in (1, 7, 30, 90, 365):
        raise ValueError("Período inválido.")
    record = cache.get("host:" + str(host_id))
    if not record:
        return {
            "kind": kind, "source": "not_cached", "series": [],
            "message": "Host ainda não foi coletado pelo worker.",
        }
    items = record.get("items") or []
    gauges = record.get("gauges") or {}
    kinds = ("network_in", "network_out") if kind == "network" else (kind,)
    output = []
    speed = None
    for metric_kind in kinds:
        metric = gauges.get(metric_kind)
        if not metric:
            continue
        item = next((i for i in items
                     if str(i.get("itemid")) == str(metric.get("itemid"))), None)
        if item is None:
            continue
        try:
            source, points = _history(item, metric_kind, days)
        except zabbix.ZabbixError as exc:
            output.append({
                "name": metric_kind, "points": [], "error": str(exc),
            })
            continue
        output.append({
            "name": metric_kind, "points": points, "source": source,
            "itemid": str(item["itemid"]),
        })
        if metric_kind == "network_in":
            speed = link_capacity(items, item)
    if kind == "network" and speed is None:
        outgoing = gauges.get("network_out")
        if outgoing:
            item = next((i for i in items if str(i.get("itemid")) ==
                         str(outgoing.get("itemid"))), None)
            speed = link_capacity(items, item)
    return {
        "kind": kind, "title": METRICS[kind][0], "hostid": str(host_id),
        "units": METRICS[kind][1], "series": output,
        "capacity_mbps": speed,
        "thresholds": ([{"level": 80, "severity": "warning"},
                        {"level": 90, "severity": "critical"},
                        {"level": 100, "severity": "maximum"}]
                       if kind != "network" else
                       ([{"level": level, "value": round(speed * level / 100, 3),
                          "severity": sev}
                         for level, sev in ((80, "warning"), (90, "critical"),
                                            (100, "maximum"))] if speed else [])),
        "message": ("Sem item monitorado compatível no Zabbix."
                    if not output else (
                        "Velocidade da interface desconhecida; sem limites "
                        "percentuais para a rede." if kind == "network" and
                        speed is None else None)),
    }
