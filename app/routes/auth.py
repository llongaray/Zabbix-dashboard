"""Login local do Flask, independente das credenciais do Zabbix."""
from collections import OrderedDict
import os
from threading import Lock
from secrets import token_urlsafe
import time
from hmac import compare_digest

from flask import jsonify, redirect, render_template, request, session

from app.routes import bp
from app.routes.decorators import same_origin
from app.realtime import revoke_session


_login_attempts = OrderedDict()
_login_lock = Lock()


def allow_login(address):
    """Conta tentativas por origem durante uma janela fixa de cinco minutos."""
    now = time.monotonic()
    with _login_lock:
        count, expires = _login_attempts.get(address, (0, now + 300))
        if expires <= now:
            count, expires = 0, now + 300
        if count >= 10:
            return False
        _login_attempts[address] = (count + 1, expires)
        _login_attempts.move_to_end(address)
        if len(_login_attempts) > 4096:
            _login_attempts.popitem(last=False)
        return True


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not same_origin():
            return render_template("login.html", error="Origem não autorizada."), 403
        if not allow_login(request.remote_addr):
            return render_template("login.html", error="Muitas tentativas. Aguarde alguns minutos."), 429
        password = request.form.get("password", "")
        expected = os.getenv("ADMIN_PASSWORD", "")
        if expected and compare_digest(password.encode("utf-8"), expected.encode("utf-8")):
            revoke_session(session.get("login_id"))
            session.clear()
            session.permanent = True
            session["admin"] = True
            session["login_id"] = token_urlsafe(32)
            session["login_expires"] = time.time() + 8 * 3600
            return redirect("/")
        return render_template("login.html", error="Senha administrativa inválida."), 401
    return render_template("login.html")


@bp.post("/logout")
def logout():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
    revoke_session(session.get("login_id"))
    session.clear()
    return redirect("/login")


@bp.get("/")
def home():
    if not session.get("admin"):
        return redirect("/login")
    return render_template("dashboard.html")


@bp.get("/api/session")
def session_status():
    if not session.get("admin"):
        return jsonify(authenticated=False, code="SESSION_EXPIRED"), 401
    response = jsonify(authenticated=True)
    response.headers["Cache-Control"] = "no-store"
    return response
