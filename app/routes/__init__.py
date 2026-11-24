"""Blueprint e composição dos módulos de rotas do dashboard."""
from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from app.services.zabbix import ZabbixError

bp = Blueprint("dashboard", __name__)


@bp.errorhandler(Exception)
def api_error(exc):
    """Respostas JSON úteis sem expor traceback ou credenciais ao navegador."""
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description), exc.code
    if not request.path.startswith("/api/"):
        current_app.logger.exception("Erro ao servir página web")
        return "Falha interna no dashboard.", 500
    if isinstance(exc, ZabbixError):
        return jsonify(error=str(exc), code="ZABBIX_ERROR"), exc.status
    if isinstance(exc, ValueError):
        return jsonify(error=str(exc), code="INVALID_REQUEST"), 400
    current_app.logger.exception("Falha interna em %s", request.path)
    return jsonify(
        error="Falha interna na aplicação. Verifique os logs do container.",
        code="INTERNAL_ERROR",
    ), 500


# Os imports registram rotas no blueprint. Não importá-los antes de criar bp.
from app.routes import analytics, auth, history, monitoring, settings, smtp  # noqa: E402,F401
