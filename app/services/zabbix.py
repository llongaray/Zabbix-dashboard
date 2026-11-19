"""Cliente JSON-RPC para a API nativa do Zabbix."""
import os
import requests
from app.db import get_setting
from app.security import decrypt


def credentials():
    url = get_setting("zabbix_url") or os.getenv("ZABBIX_URL", "")
    encrypted = get_setting("zabbix_token")
    token = decrypt(encrypted) if encrypted else os.getenv("ZABBIX_API_TOKEN", "")
    if not url or not token:
        raise ValueError("Configure URL e token do Zabbix")
    return url, token


def call(method, params=None):
    url, token = credentials()
    response = requests.post(url.rstrip("/") + "/api_jsonrpc.php", json={"jsonrpc":"2.0","method":method,"params":params or {},"id":1}, headers={"Authorization":"Bearer " + token, "Content-Type":"application/json-rpc"}, timeout=20)
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise ValueError(result["error"].get("data", "Erro na API Zabbix"))
    return result["result"]


def hosts():
    return call("host.get", {"output":["hostid","host","name","status"], "sortfield":"host"})


def items(host_id):
    return call("item.get", {"hostids":[str(host_id)],"output":["itemid","name","key_","lastvalue","units","value_type","lastclock"],"filter":{"status":0}})


def history(item_id, value_type, since, until):
    method = "trend.get" if until - since > 7 * 86400 and int(value_type) in (0,3) else "history.get"
    params = {"itemids":[str(item_id)],"time_from":since,"time_till":until,"sortfield":"clock","sortorder":"ASC","limit":2000}
    if method == "history.get":
        params["history"] = int(value_type)
    return {"source":method,"points":call(method,params)}
