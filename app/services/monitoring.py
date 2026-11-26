"""Coleta dos KPIs e descoberta conservadora de itens de hardware.

Selecionamos somente valores numéricos válidos; nenhuma métrica é inferida
pela posição na lista de itens do Zabbix. O monitoramento é somente leitura.
"""
from datetime import datetime, timezone
from functools import lru_cache
import math
import re
import time

from app.services import zabbix


@lru_cache(maxsize=1)
def cached_version():
    """Evita repetir a consulta da versão da API em todas as coletas."""
    return zabbix.api_version()


def snapshot():
    """Coleta única compartilhável entre navegadores conectados."""
    hosts = zabbix.hosts()
    warning = None
    try:
        version = cached_version()
    except zabbix.ZabbixError:
        version = None
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
            # Não representa 80 problemas como contagem exata se o limite foi atingido.
            "active_problems": None if warning else len(problems),
            "problems_limited": len(problems) >= 80,
        },
        "warning": warning,
        "version": version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _numeric_item(item):
    """Valida tipo, coleta e valor numérico do item, inclusive o zero."""
    if str(item.get("value_type", "")) not in ("0", "3"):
        return None
    try:
        if str(item.get("status", "0")) != "0":
            return None
        value = float(item.get("lastvalue", ""))
        clock = int(item.get("lastclock", 0))
    except (ValueError, TypeError):
        return None
    if clock <= 0 or not math.isfinite(value):
        return None
    return value, clock


def _network_rate(item, value):
    """Retorna Mbps apenas para taxa explícita em bits/s ou bytes/s.

    net.if.in[interface,dropped] e [interface,errors] não são uso de banda.
    Um contador acumulado com unidade B não é taxa e deve ser ignorado.
    """
    key = str(item.get("key_", "")).lower()
    if not re.match(r"^net\.if\.(?:in|out)\[", key):
        return None
    raw = key.split("[", 1)[-1].rsplit("]", 1)[0]
    # Identificadores podem conter vírgula quando estão entre aspas;
    # tokens conhecidos de modo devem ser filtrados também pelo nome.
    mode = raw.rsplit(",", 1)[-1].strip().strip('"')
    forbidden_modes = (
        "dropped", "drop", "discards", "errors", "packets", "overruns",
        "collisions", "carrier", "compressed", "multicast", "frame",
    )
    if any(mode == value_mode for value_mode in forbidden_modes):
        return None
    if "," in raw and mode not in ("", "bytes") and not raw.strip().startswith('"'):
        return None
    description = str(item.get("name") or "").lower()
    if any(term in description for term in (
        "discard", "descart", "dropped", "erro", "packet", "pacote",
        "collision", "colisão", "frame error",
    )):
        return None
    units = str(item.get("units") or "").strip()
    bit_units = {"bps": 1, "bit/s": 1, "bits/s": 1, "Kbps": 1000,
                 "Mbps": 1_000_000, "Gbps": 1_000_000_000}
    byte_units = {"Bps": 8, "B/s": 8, "byte/s": 8, "bytes/s": 8,
                  "KBps": 8000, "MBps": 8_000_000}
    factor = bit_units.get(units, byte_units.get(units))
    if factor is None:
        return None
    return round(value * factor / 1_000_000, 3)


def _kind(item):
    """Classifica itens conhecidos, sem adivinhar uso de hardware."""
    key = str(item.get("key_", "")).lower()
    if key == "system.cpu.util" or key.startswith("system.cpu.util["):
        # 'idle' representa CPU ociosa, não utilização.
        # Subtipos user/system não representam a utilização total.
        mode = key.partition("[")[2].rstrip("]")
        if not mode or mode in (",", ",,avg1", ",,avg5", ",,avg15"):
            return "cpu"
        return None
    if key in ("vm.memory.util", "vm.memory.utilization", "vm.memory.size[pused]"):
        return "memory"
    if key.startswith(("vfs.fs.size[", "vfs.fs.dependent.size[")) and (
        "pused" in key.rsplit(",", 1)[-1]
    ):
        return "disk"
    if key.startswith(("net.if.in[", "net.if.out[")):
        return "network_in" if key.startswith("net.if.in[") else "network_out"
    if key.startswith(("gpu.util", "nvidia.gpu.util", "gpu.usage")):
        return "gpu"
    return None


def _score(item, kind, clock):
    """Prefere amostras recentes e o volume raiz/C: no gauge resumido de disco.

    Todos os demais volumes (`D:`, `E:`, `/var`, etc.) são preservados em
    `storage.extract_storage()` para detalhamento completo por unidade.
    """
    key = str(item.get("key_", "")).lower()
    score = clock / 100_000_000
    if kind == "disk" and any(part in key for part in ("[c:", '[/,', '["c:', '[\"c:')):
        score += 20
    if kind == "cpu" and key in ("system.cpu.util", "system.cpu.util[]"):
        score += 10
    return score


def gauge_metrics(items):
    """Extrai CPU, RAM, disco, rede e GPU, explicitando dados ausentes."""
    selected = {}
    now = int(time.time())
    for item in items:
        kind = _kind(item)
        if not kind:
            continue
        reading = _numeric_item(item)
        if reading is None:
            continue
        value, clock = reading
        units = str(item.get("units") or "").strip()
        if kind in ("cpu", "memory", "disk", "gpu"):
            if not 0 <= value <= 100:
                continue
            # chaves percentuais conhecidas; GPU customizada requer unidade %
            if kind == "gpu" and units != "%":
                continue
            shown_value = round(value, 2)
            shown_units = "%"
        else:
            shown_value = _network_rate(item, value)
            if shown_value is None:
                continue
            shown_units = "Mbps"
        result = {
            "name": item.get("name") or item.get("key_"),
            "value": shown_value,
            "units": shown_units,
            "itemid": item.get("itemid"),
            "lastclock": clock,
            "stale": now - clock > 3600,
        }
        score = _score(item, kind, clock)
        if kind not in selected or score > selected[kind][0]:
            selected[kind] = (score, result)
    return {kind: result for kind, (_, result) in selected.items()}


def coverage_report(items, gauges):
    """Explica N/D sem inventar GPU, disco ou percentual de banda.

    Chamado pelo coletor uma vez por host e persistido junto com o cache.
    """
    hints = {
        "cpu": ("system.cpu.util", "Item CPU utilization com valor numérico."),
        "memory": ("vm.memory", "Item de utilização de RAM em porcentagem."),
        "disk": ("vfs.fs.", "Volume com vfs.fs.size[...,pused] ou "
                 "vfs.fs.dependent.size[...,pused]."),
        "gpu": ("gpu", "GPU requer item ou template específico de telemetria."),
        "network_in": ("net.if.in[", "Interface com taxa real, não descartes/erros."),
        "network_out": ("net.if.out[", "Interface com taxa real, não descartes/erros."),
    }
    report = {}
    for kind, (prefix, suggestion) in hints.items():
        if kind in gauges:
            report[kind] = {"available": True, "reason": None}
            continue
        candidates = [str(item.get("key_", "")) for item in items
                      if prefix in str(item.get("key_", "")).lower()]
        if not candidates:
            reason = "Item não monitorado pelo host/template Zabbix."
        else:
            reason = ("Existem itens relacionados, mas nenhum contém "
                      "uma leitura válida com unidades compatíveis.")
        report[kind] = {
            "available": False,
            "reason": reason,
            "suggestion": suggestion,
            "related_count": len(candidates),
            # Somente nomes de chave, sem dados/credenciais.
            "example_keys": candidates[:3],
        }
    return report
