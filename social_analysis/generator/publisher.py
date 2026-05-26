import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
import httpx
from ..config import settings


def _publish_file(title: str, body: str) -> str:
    out_dir = Path("articles")
    out_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40]
    path = out_dir / f"{ts}_{safe_title}.md"
    path.write_text(body, encoding="utf-8")
    return str(path)


def _publish_webhook(title: str, body: str) -> str:
    if not settings.webhook_url:
        raise ValueError("WEBHOOK_URL 未設定")
    r = httpx.post(settings.webhook_url, json={"title": title, "body": body}, timeout=20)
    r.raise_for_status()
    return f"webhook:{r.status_code}"


def _publish_email(title: str, body: str) -> str:
    if not (settings.smtp_host and settings.email_to):
        raise ValueError("SMTP 設定不完整")
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = settings.smtp_user or "noreply@local"
    msg["To"] = settings.email_to
    msg.set_content(body)
    with smtplib.SMTP_SSL(settings.smtp_host, 465) as s:
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_pass)
        s.send_message(msg)
    return f"email:{settings.email_to}"


def publish(title: str, body: str, target: str | None = None) -> str:
    target = target or settings.publish_target
    if target == "file":
        return _publish_file(title, body)
    if target == "webhook":
        return _publish_webhook(title, body)
    if target == "email":
        return _publish_email(title, body)
    raise ValueError(f"Unknown publish target: {target}")
