"""Configuração administrativa e teste de entrega SMTP."""
import base64
import hashlib
import json
import secrets
import smtplib
import time
from hmac import compare_digest
from urllib.parse import urlencode
from uuid import uuid4

from flask import flash, jsonify, redirect, request, session, url_for

from app import db
from app.routes import bp
from app.routes.decorators import protected, same_origin
from app.security import encrypt
from app.services import alerts, cache, mailing


def form_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Envie um objeto JSON com a configuração.")
    return data


def smtp_error(exc):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "O provedor recusou o acesso. Confira a credencial e a política de SMTP da conta."
    return "O provedor SMTP não aceitou a operação. Confira a conexão e tente novamente."


@bp.get("/api/smtp")
@protected
def smtp_config():
    response = jsonify(
        providers=[{"id": key, "label": value[0]} for key, value in mailing.PROVIDERS.items()],
        senders=[{key: account[key] for key in ("provider", "email", "oauth")}
                 for account in mailing.senders().values()],
        microsoft_oauth=all(mailing.oauth_settings()),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def sender_config(data):
    provider = data.get("provider")
    if provider not in ("gmail", "microsoft"):
        raise ValueError("Selecione um provedor de e-mail.")
    email = mailing.mailbox(data.get("email"))
    password = data.get("password")
    if password in (None, ""):
        stored = mailing.senders().get(email.lower())
        if stored and stored["provider"] == provider:
            return stored
    if not isinstance(password, str) or not password.strip() or len(password) > 1024:
        raise ValueError("Informe a senha SMTP.")
    if provider == "gmail":
        password = password.replace(" ", "")
        if len(password) != 16 or not password.isascii() or not password.isalnum():
            raise ValueError("Informe a senha de app do Google, com 16 caracteres.")
    elif not password.isascii():
        raise ValueError("Para esta conta, use a autorização da Microsoft.")
    return {"provider": provider, "email": email, "secret": encrypt(password), "oauth": False}


@bp.post("/api/smtp")
@bp.post("/api/smtp/validate")
@protected
def configure_smtp():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
    config = sender_config(form_body())
    try:
        mailing.verify_credentials(config["provider"], config["email"],
                                   mailing.sender_credentials(config), config["oauth"])
    except OSError as exc:
        return jsonify(error=smtp_error(exc)), 502
    if request.path == "/api/smtp":
        mailing.save_sender(config)
    return jsonify(ok=True)


@bp.post("/api/smtp/test")
@protected
def test_smtp():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
    data = form_body()
    config = sender_config(data)
    destination = mailing.mailbox(data.get("destination"))
    try:
        mailing.send_report(destination, "Teste de envio do Zabbix Dashboard",
                            "O servidor SMTP aceitou esta mensagem de teste.", config=config)
    except OSError as exc:
        return jsonify(error=smtp_error(exc)), 502
    return jsonify(ok=True, email=destination)


@bp.get("/api/alert-groups")
@protected
def alert_groups():
    response = jsonify(recipients=list(alerts.recipients().values()), groups=alerts.groups(),
                       delivery=alerts.delivery_status(),
                       hosts=(cache.get("overview") or {}).get("hosts", []))
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/api/alert-recipients")
@protected
def save_alert_recipient():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
    email = mailing.mailbox(form_body().get("email"))
    db.put_setting("alert_recipient:" + email.lower(), email)
    return jsonify(ok=True)


@bp.post("/api/alert-groups")
@protected
def save_alert_group():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
    data = form_body()
    name, sender, scope = data.get("name"), data.get("sender"), data.get("scope")
    addresses, hosts = data.get("recipients"), data.get("hosts")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError("Informe um nome para o grupo com até 100 caracteres.")
    if not isinstance(sender, str) or sender not in mailing.senders():
        raise ValueError("Selecione um remetente cadastrado.")
    directory = alerts.recipients()
    if (not isinstance(addresses, list) or not addresses
            or any(not isinstance(address, str) or address not in directory for address in addresses)):
        raise ValueError("Selecione pelo menos um destinatário cadastrado.")
    if scope == "selected":
        visible = {str(h["hostid"]) for h in (cache.get("overview") or {}).get("hosts", [])}
        if (not isinstance(hosts, list) or not hosts
                or any(not isinstance(host, str) or host not in visible for host in hosts)):
            raise ValueError("Selecione pelo menos um servidor disponível.")
    elif scope == "all":
        hosts = []
    else:
        raise ValueError("Escolha o escopo de servidores do grupo.")
    group_id = data.get("id") or uuid4().hex
    if not isinstance(group_id, str) or len(group_id) != 32 or any(c not in "0123456789abcdef" for c in group_id):
        raise ValueError("Grupo inválido.")
    key = "alert_group:" + group_id
    group = {"id": group_id, "name": name.strip(), "sender": sender, "scope": scope,
             "recipients": sorted(set(addresses)), "hosts": sorted(set(hosts)),
             "enabled": data.get("enabled") is True}
    previous = json.loads(db.get_setting(key) or "{}")
    routing_fields = ("sender", "scope", "recipients", "hosts", "enabled")
    if previous and all(previous[field] == group[field] for field in routing_fields):
        group["starts_at"] = previous["starts_at"]
    else:
        group["starts_at"] = int(time.time()) + 1
    db.put_setting(key, json.dumps(group))
    return jsonify(ok=True, group=group)


@bp.post("/api/smtp/microsoft/authorize")
@protected
def authorize_smtp():
    if not same_origin():
        return jsonify(error="Origem não autorizada."), 403
    client_id, client_secret, redirect_uri = mailing.oauth_settings()
    if not all((client_id, client_secret, redirect_uri)):
        return jsonify(error="A autorização Microsoft depende da configuração do app Entra."), 503
    data = form_body()
    provider = data.get("provider")
    if provider != "microsoft":
        raise ValueError("Selecione um provedor Microsoft.")
    email = mailing.mailbox(data.get("email"))
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    session["smtp_oauth"] = {
        "state": state, "verifier": verifier, "provider": provider, "email": email,
        "expires": time.time() + 600,
    }
    query = urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri,
        "scope": mailing.SMTP_SCOPE, "state": state, "response_mode": "query",
        "code_challenge": challenge.decode().rstrip("="), "code_challenge_method": "S256",
        "login_hint": email, "prompt": "select_account",
    })
    return jsonify(url=mailing.oauth_endpoint(provider) + "/authorize?" + query)


@bp.get("/smtp/microsoft/callback")
@protected
def smtp_callback():
    pending = session.get("smtp_oauth")
    state = request.args.get("state", "")
    if (not pending or pending["expires"] < time.time() or not state.isascii()
            or not compare_digest(pending["state"], state)):
        flash("A autorização SMTP expirou ou é inválida.", "smtp-error")
        return redirect(url_for("dashboard.home", view="settings", _anchor="smtp"))
    session.pop("smtp_oauth")
    code = request.args.get("code")
    if not code:
        flash("A autorização Microsoft não foi concluída.", "smtp-error")
        return redirect(url_for("dashboard.home", view="settings", _anchor="smtp"))
    provider, email = pending["provider"], pending["email"]
    if provider != "microsoft":
        return redirect(url_for("dashboard.home", view="settings", _anchor="smtp"))
    try:
        tokens = mailing.exchange_token(provider, grant_type="authorization_code", code=code,
                                        redirect_uri=mailing.oauth_settings()[2],
                                        code_verifier=pending["verifier"])
        if not tokens.get("access_token") or not tokens.get("refresh_token"):
            raise ValueError("A Microsoft não retornou a autorização SMTP necessária.")
        mailing.verify_credentials(provider, email, tokens["access_token"], oauth=True)
        mailing.save_sender({"provider": provider, "email": email,
                             "secret": encrypt(tokens["refresh_token"]), "oauth": True})
    except ValueError as exc:
        flash(str(exc), "smtp-error")
    except OSError as exc:
        flash(smtp_error(exc), "smtp-error")
    else:
        flash("Conta de e-mail conectada.", "smtp-ok")
    return redirect(url_for("dashboard.home", view="settings", _anchor="smtp"))
