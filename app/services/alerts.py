"""Encaminha novos problemas do Zabbix aos grupos cadastrados."""
import json
import logging
import time

from sqlalchemy import text

from app import db
from app.services import cache, mailing, zabbix

LOG = logging.getLogger("zabbix.alerts")


def recipients():
    return {row.removeprefix("alert_recipient:"): address
            for row, address in db.settings_with_prefix("alert_recipient:").items()}


def groups():
    return [json.loads(value)
            for value in db.settings_with_prefix("alert_group:").values()]


def claim_delivery(key):
    with db.Session.begin() as session:
        return session.execute(text("""
            INSERT INTO alert_deliveries(event_id, sender, recipient, next_attempt)
            VALUES(:event_id, :sender, :recipient, now() + interval '5 minutes')
            ON CONFLICT(event_id, sender, recipient) DO UPDATE
            SET next_attempt=EXCLUDED.next_attempt
            WHERE NOT alert_deliveries.sent AND alert_deliveries.next_attempt <= now()
            RETURNING event_id
        """), key).scalar_one_or_none() is not None


def mark_sent(key):
    with db.Session.begin() as session:
        session.execute(text("""
            UPDATE alert_deliveries SET sent=TRUE
            WHERE event_id=:event_id AND sender=:sender AND recipient=:recipient
        """), key)


def delivery_status():
    with db.Session() as session:
        row = session.execute(text("""
            SELECT count(*) FILTER (WHERE sent) AS sent,
                   count(*) FILTER (WHERE NOT sent) AS unconfirmed
            FROM alert_deliveries WHERE next_attempt >= now() - interval '24 hours'
        """)).mappings().one()
    return {**row, "collector": cache.get("alert_status")}


def dispatch():
    rules = [group for group in groups() if group["enabled"]]
    if not rules:
        return
    accounts = mailing.senders()
    directory = recipients()
    snapshot = cache.get("overview") or {}
    visible = {str(host["hostid"]) for host in snapshot.get("hosts", [])}
    if not visible:
        return
    since = max(int(time.time()) - 86400, min(group["starts_at"] for group in rules))
    events = zabbix.call("problem.get", {
        "output": ["eventid", "objectid", "name", "clock", "severity"],
        "source": 0, "object": 0, "recent": True, "suppressed": False, "time_from": since,
        "hostids": sorted(visible), "sortfield": "eventid", "sortorder": "ASC",
    })
    if not events:
        return
    triggers = zabbix.call("trigger.get", {
        "triggerids": sorted({event["objectid"] for event in events}),
        "output": ["triggerid"], "selectHosts": ["hostid", "name"],
    })
    by_trigger = {trigger["triggerid"]: trigger["hosts"] for trigger in triggers}
    attempts = 0
    for event in events:
        hosts = {str(host["hostid"]): host["name"]
                 for host in by_trigger.get(event["objectid"], []) if str(host["hostid"]) in visible}
        for rule in rules:
            sender = accounts.get(rule["sender"])
            matched = set(hosts) if rule["scope"] == "all" else set(hosts).intersection(rule["hosts"])
            if not sender or not matched or int(event["clock"]) < rule["starts_at"]:
                continue
            for recipient in rule["recipients"]:
                if recipient not in directory:
                    continue
                key = {"event_id": event["eventid"], "sender": rule["sender"], "recipient": recipient}
                if not claim_delivery(key):
                    continue
                attempts += 1
                try:
                    mailing.send_report(
                        directory[recipient], f"Zabbix: novo problema #{event['eventid']}",
                        f"Problema: {event['name']}\n"
                        f"Servidor(es): {', '.join(hosts[host] for host in sorted(matched))}\n"
                        f"Severidade Zabbix: {event['severity']}\n",
                        config=sender,
                    )
                except Exception as exc:
                    LOG.warning("Falha de envio no evento %s (%s). Nova tentativa em cinco minutos.",
                                event["eventid"], type(exc).__name__)
                else:
                    mark_sent(key)
                if attempts >= 5:
                    return


def run(interval):
    while True:
        ok = True
        try:
            dispatch()
            with db.Session.begin() as session:
                session.execute(text("""
                    DELETE FROM alert_deliveries WHERE next_attempt < now() - interval '2 days'
                """))
        except Exception:
            ok = False
            LOG.exception("Falha ao processar alertas")
        try:
            cache.save("alert_status", {"ok": ok, "checked_at": int(time.time())})
        except Exception:
            LOG.exception("Falha ao registrar o estado dos alertas")
        time.sleep(interval)
