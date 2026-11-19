"""Rotas de consulta com filtros explícitos, sem expor métodos arbitrários."""
import time

from flask import jsonify, request

from app.routes import bp
from app.routes.decorators import protected
from app.services import monitoring, zabbix


@bp.get("/api/hosts")
@protected
def hosts():
    return jsonify(zabbix.hosts())


@bp.get("/api/hosts/<host_id>/items")
@protected
def items(host_id):
    data = zabbix.items(host_id)
    # Compatível com o cliente antigo; permite transferir itens + gauges em
    # apenas uma consulta à API Zabbix durante o fallback HTTP.
    if request.args.get("include_gauges") == "1":
        return jsonify({
            "hostid": host_id,
            "items": data,
            "gauges": monitoring.gauge_metrics(data),
        })
    return jsonify(data)


@bp.get("/api/hosts/<host_id>/gauges")
@protected
def gauges(host_id):
    return jsonify(monitoring.gauge_metrics(zabbix.items(host_id)))


@bp.get("/api/snapshot")
@protected
def snapshot():
    return jsonify(monitoring.snapshot())


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
    return jsonify(zabbix.problems())


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
