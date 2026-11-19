"""Configuração dinâmica: usuário informa APENAS o API Token Zabbix."""
import os

from flask import jsonify, request

from app.db import get_setting, put_setting
from app.realtime import request_refresh, socketio
from app.routes import bp
from app.routes.decorators import protected, same_origin
from app.security import encrypt
from app.services import zabbix
from app.services.catalog import methods


@bp.get("/api/config")
@protected
def config():
    response = jsonify({
        "zabbix_url": zabbix.base_url(),
        "token_configured": bool(get_setting("zabbix_token") or
                                 os.getenv("ZABBIX_API_TOKEN")),
        "auth_mode": "API Token (Bearer)",
        "username_required": False,
        "poll_interval": int(os.getenv("POLL_INTERVAL", "25")),
    })
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/api/config")
@protected
def save_config():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
    if not request.is_json:
        return jsonify(error="Envie JSON no corpo da requisição."), 400
    body = request.get_json(silent=True) or {}
    candidate = str(body.get("token") or body.get("zabbix_token") or "").strip()
    if not candidate:
        return jsonify(error="Informe um token para validar e salvar."), 400
    if not os.getenv("FERNET_KEY"):
        return jsonify(error="FERNET_KEY ausente no .env do container."), 422

    # A conexão é validada ANTES de substituir a credencial existente.
    report = zabbix.verify_token(candidate)
    put_setting("zabbix_token", encrypt(candidate))
    # Não retornar ou transmitir o token.
    socketio.emit("token_validated", report)
    request_refresh()
    return jsonify(ok=True, token_configured=True, validation=report)


@bp.post("/api/config/test")
@protected
def test_connection():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
    report = zabbix.verify_token(zabbix.stored_token())
    return jsonify(connected=True, **report)


@bp.get("/api/catalog")
@protected
def catalog():
    return jsonify({
        "endpoint": zabbix.base_url() + "/api_jsonrpc.php",
        "transport": "HTTP POST JSON-RPC 2.0",
        "authentication": "Bearer API Token",
        "methods": methods(),
    })


@bp.post("/api/catalog/check")
@protected
def check_catalog():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
    return jsonify(results=zabbix.check_permissions())
