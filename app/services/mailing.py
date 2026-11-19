"""Envio SMTP autenticado com STARTTLS e verificação de certificado."""
import json
import os
import smtplib
import ssl
from contextlib import contextmanager
from email.errors import HeaderParseError
from email.headerregistry import Address
from email.message import EmailMessage

import requests

from app.db import get_setting, put_setting, settings_with_prefix
from app.security import decrypt

PROVIDERS = {
    "microsoft": ("Microsoft 365", "smtp.office365.com"),
    "gmail": ("Gmail", "smtp.gmail.com"),
}
MICROSOFT_AUTH = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
SMTP_SCOPE = "https://outlook.office.com/SMTP.Send offline_access"


def mailbox(value):
    if not isinstance(value, str) or not value.isascii() or len(value) > 254:
        raise ValueError("Informe um endereço de e-mail válido.")
    try:
        address = Address(addr_spec=value.strip())
        if address.username and "." in address.domain:
            return address.addr_spec
    except (ValueError, HeaderParseError):
        pass
    raise ValueError("Informe um endereço de e-mail válido.")


def saved_config():
    value = get_setting("smtp_config")
    return json.loads(value) if value else None


def senders():
    accounts = {name.removeprefix("smtp_sender:"): json.loads(value)
                for name, value in settings_with_prefix("smtp_sender:").items()}
    legacy = saved_config()
    if legacy and legacy["provider"] in PROVIDERS:
        accounts.setdefault(legacy["email"].lower(), legacy)
    return accounts


def save_sender(config):
    put_setting("smtp_sender:" + config["email"].lower(), json.dumps(config))


def oauth_settings():
    return tuple(os.getenv(key, "").strip() for key in (
        "SMTP_MICROSOFT_CLIENT_ID", "SMTP_MICROSOFT_CLIENT_SECRET",
        "SMTP_MICROSOFT_REDIRECT_URI",
    ))


def oauth_endpoint(provider):
    if provider != "microsoft":
        raise ValueError("Selecione Microsoft 365 para usar OAuth.")
    return MICROSOFT_AUTH.format(tenant="organizations")


def exchange_token(provider, **data):
    client_id, client_secret, _ = oauth_settings()
    if not client_id or not client_secret:
        raise ValueError("Configure o aplicativo Microsoft Entra para usar OAuth.")
    try:
        response = requests.post(oauth_endpoint(provider) + "/token", data={
            "client_id": client_id, "client_secret": client_secret, "scope": SMTP_SCOPE, **data,
        }, timeout=12, allow_redirects=False)
    except requests.RequestException:
        raise ValueError("Não foi possível conectar ao serviço de autorização Microsoft.") from None
    if not response.ok:
        raise ValueError("A autorização Microsoft falhou. Conecte novamente a conta.")
    return response.json()


@contextmanager
def authenticated(host, port, email, secret, oauth=False):
    with smtplib.SMTP(host, port, timeout=12) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if oauth:
            smtp.auth("XOAUTH2", lambda challenge=None: (
                f"user={email}\x01auth=Bearer {secret}\x01\x01" if challenge is None else ""
            ))
        else:
            smtp.login(email, secret)
        yield smtp


def verify_credentials(provider, email, secret, oauth=False):
    with authenticated(PROVIDERS[provider][1], 587, email, secret, oauth):
        pass


def sender_credentials(config):
    secret = decrypt(config["secret"])
    if config["oauth"]:
        secret = exchange_token(config["provider"], grant_type="refresh_token",
                                refresh_token=secret)["access_token"]
    return secret


def send_report(destination, subject, content, *, config=None):
    config = config or saved_config()
    if config:
        provider = config["provider"]
        host, port, user = PROVIDERS[provider][1], 587, config["email"]
        secret, oauth = sender_credentials(config), config["oauth"]
    else:
        host = get_setting("smtp_host") or "smtp.office365.com"
        port = int(get_setting("smtp_port") or 587)
        user, secret = get_setting("smtp_user"), get_setting("smtp_password")
        if not user or not secret:
            raise ValueError("Configure o envio de e-mail antes de testar.")
        secret, oauth = decrypt(secret), False
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = mailbox(destination)
    msg["Subject"] = subject
    msg.set_content(content)
    with authenticated(host, port, user, secret, oauth) as smtp:
        smtp.send_message(msg)
