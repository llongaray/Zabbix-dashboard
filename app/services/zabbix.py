"""Cliente Zabbix JSON-RPC, somente leitura e autenticação Bearer.

Credenciais nunca são expostas ao navegador ou incluídas nos logs.
"""
import math
import os
import time
from urllib.parse import urlsplit

import requests

from app.db import get_setting
from app.security import decrypt
from app.services.catalog import ALLOWED_METHODS, PROBES


class ZabbixError(Exception):
    """Falha controlada de conexão, permissão ou protocolo Zabbix."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def base_url():
    """URL é definida pelo deployment, não pelo usuário do dashboard.

    A substituição do placeholder antigo evita conexão acidental com example.com.
    """
    configured = os.getenv("ZABBIX_URL", "").strip().rstrip("/")
    if not configured or "zabbix.example.com" in configured:
        configured = "https://zabbix.avansat.com.br"
    parsed = urlsplit(configured)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        raise ZabbixError("ZABBIX_URL deve ser uma URL HTTPS válida.", 400)
    return configured


def stored_token():
    encrypted = get_setting("zabbix_token")
    if encrypted:
        try:
            return decrypt(encrypted)
        except Exception as exc:
            raise ZabbixError(
                "Não foi possível descriptografar o token. Verifique FERNET_KEY.", 500
            ) from exc
    return os.getenv("ZABBIX_API_TOKEN", "").strip()


def call(method, params=None, *, token=None):
    """Consulta um método permitido, com autenticação opcional para apiinfo.version."""
    if method not in ALLOWED_METHODS:
        raise ZabbixError("Método da API não autorizado pelo dashboard.", 400)
    if method != "apiinfo.version":
        token = token if token is not None else stored_token()
        if not token:
            raise ZabbixError("Cadastre um API Token para iniciar o monitoramento.", 409)
    headers = {"Content-Type": "application/json-rpc"}
    if method != "apiinfo.version":
        headers["Authorization"] = "Bearer " + token
    try:
        response = requests.post(
            base_url() + "/api_jsonrpc.php",
            headers=headers,
            json={"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1},
            timeout=(5, 15),
            allow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            raise ZabbixError("Endpoint Zabbix redirecionou a requisição; revise a URL.")
        if response.status_code in (401, 403):
            raise ZabbixError(
                "Zabbix recusou o token ou não permitiu a operação.", 502
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise ZabbixError(
                "Zabbix retornou HTML ou texto, não JSON. Verifique /api_jsonrpc.php."
            ) from exc
    except requests.exceptions.SSLError as exc:
        raise ZabbixError("Falha na validação do certificado HTTPS do Zabbix.") from exc
    except requests.exceptions.Timeout as exc:
        raise ZabbixError("A API Zabbix não respondeu dentro do prazo.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise ZabbixError("Não foi possível conectar ao Zabbix (DNS ou rede).") from exc
    except requests.exceptions.HTTPError as exc:
        raise ZabbixError(
            "API Zabbix retornou HTTP " + str(response.status_code)
        ) from exc

    if not isinstance(payload, dict):
        raise ZabbixError("Resposta JSON-RPC em formato inesperado.")
    if "error" in payload:
        err = payload["error"]
        message = str(err.get("message", "Erro da API"))
        details = str(err.get("data", ""))
        # Evita repassar conteúdo arbitrariamente longo.
        raise ZabbixError(("Zabbix: " + message + " " + details)[:250], 502)
    if "result" not in payload:
        raise ZabbixError("Resposta da API sem campo result.")
    return payload["result"]


def verify_token(candidate):
    """Valida token com host.get antes de substituir a credencial criptografada."""
    if not candidate or not isinstance(candidate, str) or len(candidate) > 4096:
        raise ZabbixError("Informe um API Token válido.", 400)
    started = time.monotonic()
    hosts_result = call(
        "host.get",
        {"output": ["hostid", "name"], "limit": 1},
        token=candidate.strip(),
    )
    if not isinstance(hosts_result, list):
        raise ZabbixError("Resposta host.get inesperada.")
    latency = round((time.monotonic() - started) * 1000)
    try:
        version = api_version()
    except ZabbixError:
        version = None  # Falha em apiinfo.version não invalida um token já verificado.
    return {
        "validated": True,
        "latency_ms": latency,
        "host_accessible": bool(hosts_result),
        "version": version,
    }


def api_version():
    return str(call("apiinfo.version"))


def hosts():
    return call("host.get", {
        "output": ["hostid", "host", "name", "status"],
        "sortfield": "host",
    })


def items(host_id):
    if not str(host_id).isdigit():
        raise ZabbixError("ID de host inválido.", 400)
    return call("item.get", {
        "hostids": [str(host_id)],
        "output": ["itemid", "name", "key_", "lastvalue", "units",
                   "value_type", "lastclock", "status"],
        "filter": {"status": 0},
    })


def problems(limit=100):
    return call("problem.get", {
        "output": ["eventid", "name", "severity", "clock"],
        "recent": False,
        "sortfield": "eventid",
        "sortorder": "DESC",
        "limit": min(limit, 200),
    })


def history(item_id, value_type, since, until):
    """Tendências para períodos longos; saída limitada para economizar RAM."""
    if not str(item_id).isdigit() or int(value_type) not in (0, 3):
        raise ZabbixError("Histórico disponível somente para itens numéricos.", 400)
    method = "trend.get" if until - since > 7 * 86400 else "history.get"
    params = {
        "itemids": [str(item_id)], "time_from": since,
        "time_till": until, "sortfield": "clock",
        "sortorder": "DESC", "limit": 9000,
    }
    if method == "history.get":
        params["history"] = int(value_type)
    else:
        params["output"] = ["clock", "value_min", "value_avg", "value_max"]
    points = call(method, params)
    points.reverse()
    stride = max(1, math.ceil(len(points) / 600))
    sampled = points[::stride]
    if points and (not sampled or sampled[-1] is not points[-1]):
        sampled.append(points[-1])
    return {"source": method, "points": sampled, "total": len(points)}


def check_permissions():
    """Probes pontuais, sem executar escrita nem requisitar grandes volumes."""
    results = {}
    for method, params in PROBES.items():
        started = time.monotonic()
        try:
            call(method, params)
            results[method] = {
                "status": "ok", "latency_ms": round((time.monotonic()-started)*1000)
            }
        except ZabbixError as exc:
            results[method] = {"status": "error", "message": str(exc)}
    return results
