"""Login local do Flask, independente das credenciais do Zabbix."""
import os
from hmac import compare_digest

from flask import jsonify, redirect, render_template, request, session

from app.routes import bp
from app.routes.decorators import same_origin


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not same_origin():
            return render_template("login.html", error="Origem não autorizada."), 403
        password = request.form.get("password", "")
        expected = os.getenv("ADMIN_PASSWORD", "")
        if expected and compare_digest(password, expected):
            session.clear()
            session["admin"] = True
            return redirect("/")
        return render_template("login.html", error="Senha administrativa inválida."), 401
    return render_template("login.html")


@bp.post("/logout")
def logout():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
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
