"""Agregação compacta de indicadores para o dashboard."""
from datetime import datetime, timezone

from app.services import zabbix


def snapshot():
    """Uma coleta para todos os navegadores, sem chamadas por usuário."""
    hosts = zabbix.hosts()
    warning = None
    try:
        problems = zabbix.problems(80)
    except zabbix.ZabbixError as exc:
        problems = []
        warning = "Consulta de problemas indisponível: " + str(exc)
    return {
        "hosts": hosts,
        "problems": problems,
        "kpis": {
            "hosts": len(hosts),
            "enabled": sum(str(host.get("status")) == "0" for host in hosts),
            "active_problems": len(problems),
        },
        "warning": warning,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def gauge_metrics(items):
    """Identifica itens existentes. Não inventa métricas ausentes."""
    keys = {
        "cpu": ("system.cpu.util",),
        "memory": ("vm.memory.util", "vm.memory.size[pused]"),
        "disk": ("vfs.fs.size[",),
        "network_in": ("net.if.in[",),
        "network_out": ("net.if.out[",),
        "gpu": ("gpu.util", "nvidia.gpu.util", "gpu.usage"),
    }
    result = {}
    for kind, prefixes in keys.items():
        candidates = [
            item for item in items
            if any(str(item.get("key_", "")).lower().startswith(p) for p in prefixes)
        ]
        if kind == "disk":
            candidates = [
                it for it in candidates
                if "pused" in str(it.get("key_", "")).lower()
            ]
        chosen = next((it for it in candidates if it.get("lastclock") != "0"), None)
        if chosen is None:
            chosen = candidates[0] if candidates else None
        if chosen:
            result[kind] = {
                "name": chosen.get("name"),
                "value": chosen.get("lastvalue"),
                "units": chosen.get("units", ""),
                "itemid": chosen.get("itemid"),
                "lastclock": chosen.get("lastclock"),
            }
    return result
