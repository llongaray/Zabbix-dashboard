"""Cache persistente de monitoramento no PostgreSQL.

O navegador lê somente snapshots previamente coletados. Tokens não são gravados
nas tabelas de cache. Toda escrita é transacional e usa parâmetros SQL.
"""
import json
import time

from sqlalchemy import text

from app import db
from app.services import host_specs

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS monitor_cache (
        cache_key TEXT PRIMARY KEY,
        payload JSONB NOT NULL,
        updated_at BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS monitor_samples (
        host_id TEXT NOT NULL,
        metric TEXT NOT NULL,
        sample_time BIGINT NOT NULL,
        value DOUBLE PRECISION NOT NULL,
        units TEXT NOT NULL,
        PRIMARY KEY(host_id, metric, sample_time)
    )""",
    """CREATE INDEX IF NOT EXISTS ix_monitor_samples_age
       ON monitor_samples(sample_time)""",
)


def ensure_schema():
    """Cria tabelas de forma idempotente, sem alterar dados preexistentes."""
    with db.Session.begin() as session:
        db.lock_schema(session)
        for statement in SCHEMA:
            session.execute(text(statement))


def get(key):
    """Retorna snapshot anterior, mesmo após reiniciar o container."""
    with db.Session() as session:
        row = session.execute(
            text("SELECT payload, updated_at FROM monitor_cache WHERE cache_key=:key"),
            {"key": key},
        ).first()
    if row is None:
        return None
    result = dict(row[0])
    if key.startswith("host:") and not result.get("specs"):
        result["specs"] = host_specs.specifications(result.get("items", []), None)
    result["cached_at"] = int(row[1])
    return result


def host_summaries(host_ids):
    if not host_ids:
        return {}
    with db.Session() as session:
        rows = session.execute(text("""
            SELECT cache_key, payload FROM monitor_cache
            WHERE cache_key = ANY(:keys)
              AND jsonb_typeof(payload->'gauges') = 'object'
              AND payload->'gauges' <> '{}'::jsonb
        """), {"keys": ["host:" + host_id for host_id in host_ids]})
        now = int(time.time())
        return {key.removeprefix("host:"): host_specs.overview_summary(payload, now)
                for key, payload in rows}


def save(key, payload):
    """Persistência independente da requisição HTTP e da conexão Socket.IO."""
    stamp = time.time_ns()
    with db.Session.begin() as session:
        session.execute(text(
            "INSERT INTO monitor_cache(cache_key, payload, updated_at) "
            "VALUES(:key, CAST(:payload AS JSONB), :stamp) "
            "ON CONFLICT (cache_key) DO UPDATE SET "
            "payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at"
        ), {"key": key, "payload": json.dumps(payload), "stamp": stamp})
    return stamp


def save_host(host_id, items, gauges, diagnostics=None, *, specs=None):
    """Salva inventário e amostras recentes em uma única transação."""
    stamp = int(time.time())
    payload = {"hostid": str(host_id), "items": items, "gauges": gauges,
               "diagnostics": diagnostics or {}, "specs": specs or {}}
    with db.Session.begin() as session:
        session.execute(text(
            "INSERT INTO monitor_cache(cache_key, payload, updated_at) "
            "VALUES(:key, CAST(:payload AS JSONB), :stamp) "
            "ON CONFLICT(cache_key) DO UPDATE SET "
            "payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at"
        ), {
            "key": "host:" + str(host_id),
            "payload": json.dumps(payload),
            "stamp": stamp,
        })
        for kind, metric in gauges.items():
            try:
                value = float(metric["value"])
                sample_time = int(metric["lastclock"])
            except (KeyError, TypeError, ValueError):
                continue
            session.execute(text(
                "INSERT INTO monitor_samples(host_id,metric,sample_time,value,units) "
                "VALUES(:host,:metric,:stamp,:value,:units) "
                "ON CONFLICT(host_id,metric,sample_time) DO UPDATE "
                "SET value=EXCLUDED.value, units=EXCLUDED.units"
            ), {
                "host": str(host_id), "metric": kind, "stamp": sample_time,
                "value": value, "units": str(metric.get("units", "")),
            })
    return stamp


def samples(host_id, days=2, max_points=600):
    """Mini-histórico limitado, sempre vindo do PostgreSQL."""
    oldest = int(time.time()) - int(days) * 86400
    with db.Session() as session:
        rows = session.execute(text(
            "SELECT metric,sample_time,value,units FROM monitor_samples "
            "WHERE host_id=:host AND sample_time>=:oldest "
            "ORDER BY sample_time DESC LIMIT :limit"
        ), {
            "host": str(host_id), "oldest": oldest,
            "limit": min(10000, max(600, int(max_points) * 6)),
        }).all()
    data = {}
    for kind, stamp, value, units in reversed(rows):
        data.setdefault(kind, []).append({
            "clock": int(stamp), "value": float(value), "units": units,
        })
    for kind, points in data.items():
        if len(points) > max_points:
            stride = max(1, len(points) // max_points)
            data[kind] = points[::stride][-max_points:]
    return data


def cleanup(retention_hours=72):
    """Limita espaço em disco e evita crescimento indefinido do histórico."""
    cutoff = int(time.time()) - int(retention_hours) * 3600
    with db.Session.begin() as session:
        session.execute(
            text("DELETE FROM monitor_samples WHERE sample_time < :cutoff"),
            {"cutoff": cutoff},
        )


def invalidate():
    """Evita exibir dados antigos após substituir token e permissões."""
    with db.Session.begin() as session:
        session.execute(text("DELETE FROM monitor_cache"))
        session.execute(text("DELETE FROM monitor_samples"))
