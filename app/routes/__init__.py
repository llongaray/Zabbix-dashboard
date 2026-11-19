"""Endpoints de configuração e monitoramento."""
import os
import time
from functools import wraps
from hmac import compare_digest
from flask import Blueprint, request, jsonify, session, render_template, redirect, current_app
from app.db import get_setting, put_setting
from app.security import encrypt
from app.services import zabbix

bp = Blueprint("dashboard", __name__)


@bp.errorhandler(Exception)
def api_error(exc):
    """Retorna JSON em endpoints API e evita HTML em fetch()."""
    if not request.path.startswith("/api/"):
        raise exc
    current_app.logger.exception("Falha em %s", request.path)
    if isinstance(exc, ValueError):
        return jsonify(error=str(exc)), 400
    return jsonify(error="Falha interna ao consultar o serviço. Consulte os logs."), 500



def protected(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return jsonify(error="Autenticação necessária"), 401
        return fn(*args, **kwargs)
    return wrapper


@bp.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if compare_digest(request.form.get("password", ""), os.environ["ADMIN_PASSWORD"]):
            session.clear()
            session["admin"] = True
            return redirect("/")
        return render_template("login.html", error="Senha administrativa inválida."), 401
    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect("/login")


@bp.get("/")
def home():
    return render_template("dashboard.html") if session.get("admin") else redirect("/login")


@bp.get("/api/hosts")
@protected
def hosts():
    return jsonify(zabbix.hosts())


@bp.get("/api/hosts/<host_id>/items")
@protected
def items(host_id):
    return jsonify(zabbix.items(host_id))


@bp.get("/api/history/<item_id>")
@protected
def history(item_id):
    period = min(max(int(request.args.get("days", "1")),1),365)
    value_type = int(request.args.get("value_type", "0"))
    now = int(time.time())
    return jsonify(zabbix.history(item_id,value_type,now-period*86400,now))


@bp.get("/api/config")
@protected
def config():
    return jsonify({"zabbix_url":get_setting("zabbix_url") or os.getenv("ZABBIX_URL", ""), "smtp_host":get_setting("smtp_host") or "", "smtp_port":get_setting("smtp_port") or "", "smtp_user":get_setting("smtp_user") or "", "token_configured":bool(get_setting("zabbix_token"))})


@bp.post("/api/config")
@protected
def save_config():
    data = request.get_json(silent=True) or {}
    for key in ("zabbix_url","smtp_host","smtp_port","smtp_user"):
        if key in data:
            put_setting(key,str(data[key]))
    for key in ("zabbix_token","smtp_password"):
        if data.get(key):
            put_setting(key,encrypt(str(data[key])))
    return jsonify(ok=True)
