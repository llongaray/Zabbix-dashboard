"""Worker independente: consulta o Zabbix sem esperar usuários conectarem.

Executado por Docker Compose com `python -m app.worker`. O servidor web apenas
consome o PostgreSQL; não consulta o Zabbix ao abrir a página.
"""
import logging
import os
import threading
import time
from datetime import datetime, timezone

from app.db import init_database
from app.services import alerts, cache, host_specs, monitoring, storage, zabbix

LOG = logging.getLogger("zabbix.collector")


def cycle(cursor=0, tick=0):
    """Faz descoberta completa e atualiza lotes pequenos de hosts por ciclo."""
    hosts = zabbix.hosts()
    count = max(1, min(24, int(os.getenv("HOSTS_PER_CYCLE", "8"))))
    start = cursor % max(1, len(hosts))
    batch = [hosts[(start + index) % len(hosts)] for index in
             range(min(count, len(hosts)))] if hosts else []
    if batch:
        hostids = [str(h["hostid"]) for h in batch]
        inventories = {str(host["hostid"]): host.get("inventory") for host in batch}
        try:
            all_items = zabbix.items_for_hosts(hostids)
            grouped = {host_id: [] for host_id in hostids}
            for item in all_items:
                group = grouped.get(str(item.get("hostid")))
                if group is not None:
                    group.append(item)
            for host_id, host_items in grouped.items():
                gauges = monitoring.gauge_metrics(host_items)
                diagnostics = monitoring.coverage_report(host_items, gauges)
                specs = host_specs.specifications(host_items, inventories[host_id])
                storage_data = storage.extract_storage(host_items)
                cache.save_host(
                    host_id, host_items, gauges, diagnostics,
                    specs=specs, storage_data=storage_data,
                )
        except zabbix.ZabbixError as exc:
            LOG.warning("Falha na coleta de itens (lote de hosts): %s", exc)

    summaries = cache.host_summaries([str(host["hostid"]) for host in hosts])
    available = [{**host, "summary": summaries[str(host["hostid"])]}
                 for host in hosts if str(host["hostid"]) in summaries]
    prior = cache.get("overview") or {}
    payload = {
        "hosts": available,
        "discovered_host_count": len(hosts),
        "problems": prior.get("problems", []),
        "kpis": {
            "hosts": len(available),
            "enabled": sum(str(h.get("status")) == "0" for h in available),
            "active_problems": prior.get("kpis", {}).get("active_problems"),
            "problems_limited": prior.get("kpis", {}).get("problems_limited", False),
        },
        "warning": prior.get("warning"),
        "version": prior.get("version"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
    }
    # Não bloqueia a primeira lista de servidores em consultas de problemas.
    cache.save("overview", payload)
    cache.save("worker_status", {"status": "online",
                                  "message": "Coleta de hosts atualizada."})

    # Consulta mais cara só a cada 6 ciclos, preservando última leitura válida.
    if tick % 6 == 0:
        try:
            problems = zabbix.problems(80)
            payload["problems"] = problems
            payload["kpis"]["active_problems"] = len(problems)
            payload["kpis"]["problems_limited"] = len(problems) >= 80
            payload["warning"] = None
        except zabbix.ZabbixError as exc:
            payload["warning"] = "Problemas indisponíveis: " + str(exc)
        try:
            payload["version"] = monitoring.cached_version()
        except zabbix.ZabbixError:
            pass
        cache.save("overview", payload)
    if tick % 20 == 0:
        cache.cleanup(int(os.getenv("CACHE_RETENTION_HOURS", "72")))
    return (start + len(batch)) % max(1, len(hosts))


def main():
    """Executa polling com estado gravado em disco e retentativa automática."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_database()
    cache.ensure_schema()
    cursor = 0
    tick = 0
    interval = max(15, min(300, int(os.getenv("POLL_INTERVAL", "30"))))
    threading.Thread(target=alerts.run, args=(interval,), daemon=True, name="email-alerts").start()
    warmup = cache.get("overview") is None
    warmed = 0
    LOG.info("Coletor iniciado: intervalo=%ds; lote=%s hosts", interval,
             os.getenv("HOSTS_PER_CYCLE", "8"))
    while True:
        started = time.monotonic()
        try:
            if zabbix.stored_token():
                cursor = cycle(cursor, tick)
                tick += 1
                cache.save("worker_status", {"status": "online", "tick": tick})
                if warmup:
                    found = (cache.get("overview") or {}).get("discovered_host_count", 0)
                    warmed += max(1, min(24, int(os.getenv("HOSTS_PER_CYCLE", "8"))))
                    warmup = found > 0 and warmed < found
            else:
                cache.save("worker_status", {
                    "status": "no_token",
                    "message": "Configure o token no .env ou na interface.",
                })
        except Exception:
            LOG.exception("Coleta falhou; preservando último cache válido")
            cache.save("worker_status", {
                "status": "error",
                "message": "Falha na coleta. Consulte logs do collector.",
            })
        # Em instalação nova, preenche a lista em lotes com pequenas pausas.
        # Nos ciclos seguintes, volta ao intervalo configurado para poupar CPU.
        effective_interval = 6 if warmup else interval
        time.sleep(max(1, effective_interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
