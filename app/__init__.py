"""Application factory: compõe HTTP, PostgreSQL e transporte Socket.IO."""
import os

from flask import Flask

from app.db import init_database
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
    app.register_blueprint(bp)
    socketio.init_app(app)
    return app
