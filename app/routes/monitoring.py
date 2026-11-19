"""Rotas de consulta com filtros explícitos, sem expor métodos arbitrários."""
import time

from flask import jsonify, request

from app.routes import bp
from app.routes.decorators import protected
from app.services import cache, capacity, zabbix


@bp.get("/api/hosts")
@protected
def hosts():
    return jsonify((cache.get("overview") or {}).get("hosts", []))


@bp.get("/api/capacity")
@protected
def capacity_report():
    response = jsonify(capacity.report())
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/hosts/<host_id>/items")
@protected
def items(host_id):
    if not host_id.isdigit():
        raise ValueError("ID de host inválido.")
    data = cache.get("host:" + host_id)
    if not data:
        data = {"hostid": host_id, "items": [], "gauges": {},
                "pending": True,
                "message": "Aguardando a primeira coleta do worker para este host."}
    if request.args.get("include_gauges") == "1":
        return jsonify(data)
    return jsonify(data["items"])


@bp.get("/api/hosts/<host_id>/gauges")
@protected
def gauges(host_id):
    if not host_id.isdigit():
        raise ValueError("ID de host inválido.")
    return jsonify((cache.get("host:" + host_id) or {}).get("gauges", {}))


@bp.get("/api/snapshot")
@protected
def snapshot():
    data = cache.get("overview")
    if data is None:
        data = {"hosts": [], "problems": [],
                "kpis": {"hosts": None, "enabled": None,
                         "active_problems": None},
                "status": "warming_up",
                "warning": "Aguardando a primeira coleta independente do worker."}
    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/collector/status")
@protected
def collector_status():
    return jsonify(cache.get("worker_status") or {
        "status": "starting",
        "message": "Worker ainda não registrou uma coleta.",
    })


@bp.get("/api/history/local/<host_id>")
@protected
def local_history(host_id):
    if not host_id.isdigit():
        raise ValueError("Host inválido.")
    try:
        days = max(1, min(3, int(request.args.get("days", "2"))))
    except ValueError as exc:
        raise ValueError("Período inválido.") from exc
    return jsonify({"hostid": host_id, "source": "postgresql",
                    "series": cache.samples(host_id, days=days)})


@bp.get("/api/history/<item_id>")
@protected
def history(item_id):
    try:
        days = int(request.args.get("days", "1"))
        value_type = int(request.args.get("value_type", "0"))
    except ValueError as exc:
        raise ValueError("Período ou tipo numérico inválido.") from exc
    if not 1 <= days <= 365:
        raise ValueError("Selecione um período entre 1 e 365 dias.")
    end = int(time.time())
    return jsonify(zabbix.history(item_id, value_type, end - days * 86400, end))


@bp.get("/api/problems")
@protected
def problems():
    return jsonify((cache.get("overview") or {}).get("problems", []))


@bp.get("/api/groups")
@protected
def groups():
    return jsonify(zabbix.call("hostgroup.get", {
        "output": ["groupid", "name"], "sortfield": "name",
    }))


@bp.get("/api/hosts/<host_id>/graphs")
@protected
def graphs(host_id):
    if not host_id.isdigit():
        raise ValueError("ID do host inválido.")
    return jsonify(zabbix.call("graph.get", {
        "hostids": [host_id],
        "output": ["graphid", "name"],
        "sortfield": "name",
    }))
