"""Planejamento de RAM baseado nos máximos horários do Zabbix."""
from collections import defaultdict
import math
import time

from app.services import cache, zabbix

GIB = 1024 ** 3
DAYS = 30
HOURS = DAYS * 24
MIN_COVERAGE = 90
DONOR_LIMIT = 70
RECEIVER_THRESHOLD = 90
RECEIVER_TARGET = 80
MIN_DONOR_GIB = 4


def trends(item_ids, start, end):
    series = defaultdict(dict)
    for row in zabbix.call("trend.get", {
        "itemids": sorted(set(item_ids)), "time_from": start, "time_till": end,
        "output": ["itemid", "clock", "value_min", "value_max"],
    }) if item_ids else []:
        low, high = float(row["value_min"]), float(row["value_max"])
        if math.isfinite(low) and math.isfinite(high) and low <= high:
            series[row["itemid"]][int(row["clock"])] = (low, high)
    return series


def suggest(rows):
    """Não compromete a mesma folga física em mais de uma sugestão."""
    donors = sorted((row for row in rows if row["releasable_gib"]),
                    key=lambda row: row["releasable_gib"], reverse=True)
    receivers = sorted((row for row in rows if row["needed_gib"]),
                       key=lambda row: row["peak_pct"], reverse=True)
    available = {row["hostid"]: row["releasable_gib"] for row in donors}
    proposals = []
    for receiver in receivers:
        remaining = receiver["needed_gib"]
        for donor in donors:
            quantity = min(remaining, available[donor["hostid"]])
            if not quantity:
                continue
            proposals.append({"from": donor["name"], "to": receiver["name"], "gib": quantity})
            available[donor["hostid"]] -= quantity
            remaining -= quantity
            if not remaining:
                break
    return proposals


def report():
    hour = int(time.time()) // 3600 * 3600
    start = hour - HOURS * 3600
    hosts = (cache.get("overview") or {}).get("hosts", [])
    sources = []
    item_ids = []
    for host in hosts:
        record = cache.get("host:" + str(host["hostid"])) or {}
        gauge = record.get("gauges", {}).get("memory") or {}
        capacity = (record.get("specs") or {}).get("ram_bytes")
        total_item = next((item["itemid"] for item in record.get("items", [])
                           if item["key_"] == "vm.memory.size[total]"), None)
        sources.append((host, gauge, capacity, total_item))
        if gauge.get("itemid") and total_item and capacity:
            item_ids.extend((str(gauge["itemid"]), str(total_item)))
    series = trends(item_ids, start, hour - 1)
    rows = []
    for host, gauge, capacity, total_item in sources:
        samples = {stamp: high for stamp, (low, high) in series[str(gauge.get("itemid"))].items()
                   if 0 <= low <= high <= 100}
        totals = series[str(total_item)]
        peak = max(samples.values(), default=None)
        coverage = len(samples) * 100 / HOURS
        capacity_gib = capacity / GIB if capacity else None
        peak_gib = None
        status = "Apto para análise"
        releasable = needed = 0
        if (not capacity_gib or coverage < MIN_COVERAGE or not samples or
                max(samples) < hour - 6 * 3600 or gauge.get("stale")):
            status = "Histórico ou leitura insuficiente"
        elif (not totals or min(totals) > start + 2 * 86400 or max(totals) < hour - 2 * 86400
              or any(low != capacity or high != capacity for low, high in totals.values())):
            status = "RAM total histórica não confirmada"
        else:
            planning_peak = max(peak, gauge["value"])
            peak_gib = capacity_gib * peak / 100
            planning_gib = capacity_gib * planning_peak / 100
            retained = max(MIN_DONOR_GIB, planning_gib / (DONOR_LIMIT / 100))
            releasable = max(0, math.floor(capacity_gib - retained))
            if planning_peak >= RECEIVER_THRESHOLD:
                needed = max(0, math.ceil(planning_gib / (RECEIVER_TARGET / 100) - capacity_gib))
        rows.append({
            "hostid": str(host["hostid"]), "name": host.get("name") or host["host"],
            "total_gib": capacity_gib, "peak_pct": peak,
            "peak_gib": peak_gib,
            "coverage_pct": round(coverage, 1), "status": status,
            "releasable_gib": releasable, "needed_gib": needed,
        })
    return {
        "days": DAYS, "min_coverage": MIN_COVERAGE, "donor_limit": DONOR_LIMIT,
        "min_donor_gib": MIN_DONOR_GIB,
        "receiver_threshold": RECEIVER_THRESHOLD, "receiver_target": RECEIVER_TARGET,
        "hosts": rows, "suggestions": suggest(rows),
    }
