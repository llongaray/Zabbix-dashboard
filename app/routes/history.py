"""Histórico por recurso: cache rápido e consulta oficial sob demanda."""
from flask import jsonify, request

from app.routes import bp
from app.routes.decorators import protected
from app.services.history_series import host_series


@bp.get("/api/history/series/<host_id>/<kind>")
@protected
def metric_history(host_id, kind):
    """Retorna até 5 séries separadas, limitado a quatro tipos de gráfico."""
    try:
        days = int(request.args.get("days", "1"))
    except ValueError as exc:
        raise ValueError("Período inválido.") from exc
    response = jsonify(host_series(host_id, kind, days))
    response.headers["Cache-Control"] = "no-store"
    return response
