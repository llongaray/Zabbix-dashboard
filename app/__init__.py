"""Application factory e composição de módulos."""
import os
from flask import Flask
from app.db import init_database
from app.routes import bp


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ["FLASK_SECRET_KEY"]
    init_database()
    app.register_blueprint(bp)
    return app
