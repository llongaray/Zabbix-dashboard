"""Socket.IO somente distribui cache PostgreSQL; nunca consulta a API Zabbix.

A coleta é independente em app.worker. Uma conexão nova recebe os últimos
valores já salvos, sem bloquear a renderização nem iniciar coleta remota.
"""
import re
import threading
import time

from flask import request, session
from flask_socketio import SocketIO

from app.services import cache

socketio = SocketIO(async_mode="threading", cors_allowed_origins=None)
_lock = threading.Lock()
_wake = threading.Event()
_started = False
_watchers = {}
_connections = {}


def revoke_session(login_id):
    if not login_id:
        return
    with _lock:
        sockets = [sid for sid, (owner, _) in _connections.items() if owner == login_id]
    for sid in sockets:
        socketio.server.disconnect(sid, namespace="/")

_last_snapshot_stamp = None
_last_hosts_stamps = {}


def request_refresh():
    """Acorda distribuidor de cache; o worker coleta no próprio intervalo."""
    _wake.set()


def _broadcast_cache():
    """Emite alterações de cache sem carregar dados diretamente do Zabbix."""
    global _last_snapshot_stamp
    while True:
        try:
            now = time.time()
            with _lock:
                expired = [sid for sid, (_, expires) in _connections.items() if expires <= now]
            for sid in expired:
                socketio.server.disconnect(sid, namespace="/")
            overview = cache.get("overview")
            if overview and overview.get("cached_at") != _last_snapshot_stamp:
                _last_snapshot_stamp = overview["cached_at"]
                socketio.emit("snapshot", overview)
            worker = cache.get("worker_status")
            if worker:
                socketio.emit("collector_status", worker)
            with _lock:
                watchers = list(_watchers.items())
            for sid, host_id in watchers:
                payload = cache.get("host:" + host_id)
                if not payload:
                    continue
                version = payload.get("cached_at")
                if _last_hosts_stamps.get(sid) != (host_id, version):
                    _last_hosts_stamps[sid] = (host_id, version)
                    socketio.emit("host_items", payload, to=sid)
        except Exception:
            # Falha transitória na leitura do banco não derruba a sessão do navegador.
            socketio.emit("collector_status", {
                "status": "error", "message": "Cache indisponível no momento.",
            })
        _wake.wait(timeout=4)
        _wake.clear()


@socketio.on("connect")
def connect(auth=None):
    global _started
    if not session.get("admin"):
        return False
    # Uso de PostgreSQL apenas; dados antigos ficam disponíveis imediatamente.
    try:
        snapshot = cache.get("overview")
        if snapshot:
            socketio.emit("snapshot", snapshot, to=request.sid)
        worker = cache.get("worker_status")
        if worker:
            socketio.emit("collector_status", worker, to=request.sid)
    except Exception:
        pass
    with _lock:
        if session.get("login_id"):
            _connections[request.sid] = (session["login_id"], session["login_expires"])
        if not _started:
            _started = True
            socketio.start_background_task(_broadcast_cache)
    request_refresh()


@socketio.on("disconnect")
def disconnect():
    with _lock:
        _connections.pop(request.sid, None)
        _watchers.pop(request.sid, None)
        _last_hosts_stamps.pop(request.sid, None)


@socketio.on("refresh")
def refresh():
    if not session.get("admin"):
        return False
    request_refresh()


@socketio.on("watch_host")
def watch_host(payload):
    if not session.get("admin"):
        return False
    host_id = str((payload or {}).get("hostid", ""))
    if not re.fullmatch(r"[0-9]{1,20}", host_id):
        socketio.emit("host_error", {"message": "ID de host inválido."},
                      to=request.sid)
        return
    with _lock:
        _watchers[request.sid] = host_id
        _last_hosts_stamps.pop(request.sid, None)
    # A consulta abaixo é somente local; não faz qualquer I/O com o Zabbix.
    latest = cache.get("host:" + host_id)
    if latest:
        socketio.emit("host_items", latest, to=request.sid)
    else:
        socketio.emit("host_pending", {
            "hostid": host_id,
            "message": "Coleta em andamento no worker; aguardando primeiro lote.",
        }, to=request.sid)
    request_refresh()
