"""Controle de acesso e verificação de origem para endpoints do painel."""
from functools import wraps

from flask import jsonify, request, session


def protected(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return jsonify(
                error="Sessão administrativa expirada ou inválida.",
                code="SESSION_EXPIRED",
            ), 401
        return function(*args, **kwargs)
    return wrapper


def same_origin():
    """Bloqueia escritas iniciadas por outra origem no navegador."""
    origin = request.headers.get("Origin")
    if origin:
        from urllib.parse import urlsplit
        origin_host = urlsplit(origin).netloc.lower()
        if origin_host != request.host.lower():
            return False
    return True
