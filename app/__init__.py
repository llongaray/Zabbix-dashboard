"""Application factory: compõe HTTP, PostgreSQL e transporte Socket.IO."""
from datetime import timedelta
from hmac import compare_digest
import os
from secrets import token_urlsafe

from flask import Flask, jsonify, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

from app.db import init_database
from app.services import cache
from app.realtime import socketio
from app.routes import bp


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
        SESSION_COOKIE_NAME="zabbix_dashboard_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "").lower() in ("1", "true"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=128 * 1024,
    )
    init_database()
    cache.ensure_schema()
    app.register_blueprint(bp)
    socketio.init_app(app)
    if os.getenv("TRUST_NGINX_PROXY") == "true":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_prefix=1)

    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = token_urlsafe(32)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def check_csrf():
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            # Let protected API routes return their usual unauthenticated response.
            if request.path.startswith("/api/") and not session.get("admin"):
                return None
            expected = session.get("_csrf")
            supplied = request.headers.get("X-CSRF-Token") or request.form.get("_csrf", "")
            if not expected or not compare_digest(expected.encode(), supplied.encode()):
                return jsonify(error="Sessão do formulário inválida. Atualize a página.", code="INVALID_CSRF"), 403
        return None

    @app.after_request
    def disable_beta_asset_cache(response):
        """Evita módulos JS antigos após atualizar o Docker local."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://cdn.socket.io; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        if request.path.startswith("/static/") and request.path.endswith(
            (".js", ".css")
        ):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    return app
