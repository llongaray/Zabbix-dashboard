"""Teste PostgreSQL com banco descartável na CI; nunca o banco corporativo."""
import os
import time

import pytest

from app.db import init_database
from app.services import cache


@pytest.mark.skipif(os.getenv("INTEGRATION_DB") != "1",
                    reason="Executar somente com PostgreSQL de teste")
def test_postgres_cache_persists_snapshots_and_mini_history():
    init_database()
    cache.ensure_schema()
    cache.invalidate()
    cache.save("overview", {"hosts": [{"hostid": "777"}], "kpis": {}})
    assert cache.get("overview")["hosts"][0]["hostid"] == "777"
    now = int(time.time())
    cache.save_host("777", [], {"cpu": {
        "value": 57.2, "units": "%", "lastclock": now,
    }}, {"gpu": {"available": False}})
    assert cache.get("host:777")["gauges"]["cpu"]["value"] == 57.2
    cache.save_host("778", [], {})
    assert set(cache.host_summaries(["777", "778", "779"])) == {"777"}
    assert cache.samples("777")["cpu"][0]["value"] == 57.2
    # Reabrir sessão simula um novo request/worker conectado ao mesmo banco.
    assert cache.get("overview") is not None
    cache.invalidate()
    assert cache.get("overview") is None
    assert cache.samples("777") == {}
