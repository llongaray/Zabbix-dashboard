"""Application factory: compõe HTTP, PostgreSQL e transporte Socket.IO."""
import os

from flask import Flask, request

from app.db import init_database
from app.services import cache
from app.realtime import socketio
from app.routes import bp


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    init_database()
    cache.ensure_schema()
    app.register_blueprint(bp)
    socketio.init_app(app)

    @app.after_request
    def disable_beta_asset_cache(response):
        """Evita módulos JS antigos após atualizar o Docker local."""
        if request.path.startswith("/static/") and request.path.endswith(
            (".js", ".css")
        ):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    return app
