"""Alarm delivery: e-mail via SMTP, SMS via SMSAPI.pl. Channels without config are skipped (status not_configured)."""
import os
import ssl
import smtplib
from email.message import EmailMessage

import requests

SMSAPI_URL = "https://api.smsapi.pl/sms.do"


def email_configured() -> bool:
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"))


def sms_configured() -> bool:
    return bool(os.environ.get("SMSAPI_TOKEN") and os.environ.get("SMSAPI_FROM"))


def send_email(to: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.environ["SMTP_FROM"], to, subject
    msg.set_content(body)
    host, port, ctx = os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"]), ssl.create_default_context()
    if os.environ.get("SMTP_USE_SSL", "false").lower() == "true":
        smtp = smtplib.SMTP_SSL(host, port, timeout=20, context=ctx)
    else:
        smtp = smtplib.SMTP(host, port, timeout=20)
        smtp.ehlo()
        smtp.starttls(context=ctx)
        smtp.ehlo()
    with smtp:
        smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)


def send_sms(to: str, text: str):
    r = requests.post(SMSAPI_URL, headers={"Authorization": f"Bearer {os.environ['SMSAPI_TOKEN']}"}, timeout=(5, 20),
                      data={"to": to.lstrip("+"), "from": os.environ["SMSAPI_FROM"], "message": text[:670],
                            "encoding": "utf-8", "format": "json"})
    payload = r.json()
    if r.status_code != 200 or payload.get("error"):
        raise RuntimeError(f"SMSAPI error {payload.get('error')}: {payload.get('message')}")


def deliver(channel: str, to: str, subject: str, body: str) -> tuple:
    """Returns (status, error) where status is sent | failed | not_configured."""
    if not (email_configured() if channel == "email" else sms_configured()):
        return "not_configured", None
    try:
        send_email(to, subject, body) if channel == "email" else send_sms(to, f"{subject}: {body}")
        return "sent", None
    except Exception as e:
        return "failed", str(e)[:200]
