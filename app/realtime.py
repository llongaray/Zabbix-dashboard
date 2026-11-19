"""Canal Socket.IO autenticado para atualizações de monitoramento.

Zabbix não fornece WebSocket neste fluxo: o backend consulta JSON-RPC e envia
as alterações a todos os navegadores autorizados. Um worker por container.
"""
import os
import re
import threading
import time

from flask import request, session
from flask_socketio import SocketIO

from app.services import monitoring, zabbix

socketio = SocketIO(async_mode="threading", cors_allowed_origins=None)
_lock = threading.Lock()
_wake = threading.Event()
_started = False
_last_refresh = 0.0
_watchers = {}
_last_snapshot = None


def request_refresh():
    _wake.set()


def _poll():
    global _last_snapshot
    interval = max(15, min(120, int(os.getenv("POLL_INTERVAL", "25"))))
    while True:
        try:
            if not zabbix.stored_token():
                socketio.emit("integration_status", {
                    "connected": False,
                    "message": "Cadastre o token da API em Configurações.",
                })
            else:
                payload = monitoring.snapshot()
                _last_snapshot = payload
                socketio.emit("snapshot", payload)
                socketio.emit("integration_status", {
                    "connected": True, "message": "Zabbix conectado.",
                })
                with _lock:
                    watchers = list(_watchers.items())
                by_host = {}
                for sid, host_id in watchers:
                    try:
                        if host_id not in by_host:
                            data = zabbix.items(host_id)
                            by_host[host_id] = {
                                "hostid": host_id,
                                "items": data,
                                "gauges": monitoring.gauge_metrics(data),
                            }
                        socketio.emit("host_items", by_host[host_id], to=sid)
                    except zabbix.ZabbixError as exc:
                        socketio.emit("host_error", {"message": str(exc)}, to=sid)
        except Exception as exc:
            # Não altera sessão administrativa por falhas externas do Zabbix.
            message = str(exc) if isinstance(exc, zabbix.ZabbixError) else (
                "Falha interna no coletor. Consulte os logs."
            )
            socketio.emit("integration_status", {
                "connected": False, "message": message,
            })
        _wake.wait(interval)
        _wake.clear()


@socketio.on("connect")
def connect(auth=None):
    global _started
    if not session.get("admin"):
        return False
    if _last_snapshot is not None:
        socketio.emit("snapshot", _last_snapshot, to=request.sid)
    with _lock:
        if not _started:
            _started = True
            socketio.start_background_task(_poll)
    request_refresh()


@socketio.on("disconnect")
def disconnect():
    with _lock:
        _watchers.pop(request.sid, None)


@socketio.on("refresh")
def refresh():
    global _last_refresh
    if not session.get("admin"):
        return False
    with _lock:
        if time.monotonic() - _last_refresh < 8:
            return
        _last_refresh = time.monotonic()
    request_refresh()


@socketio.on("watch_host")
def watch_host(payload):
    if not session.get("admin"):
        return False
    host_id = str((payload or {}).get("hostid", ""))
    if not re.fullmatch(r"[0-9]{1,20}", host_id):
        socketio.emit("host_error", {"message": "ID de host inválido."}, to=request.sid)
        return
    with _lock:
        _watchers[request.sid] = host_id
    request_refresh()
