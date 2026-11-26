"""Support tickets, emailed to the site owner from the server.

The recipient address and mail credentials live only in server settings
(environment variables or .streamlit/secrets.toml), never in the code or the
page, so visitors cannot see where tickets go:

    SUPPORT_EMAIL_TO   address that receives tickets
    SMTP_USER          account that sends them (e.g. a Gmail address)
    SMTP_PASSWORD      its app password (Gmail: Google Account > App passwords)
    SMTP_HOST          default smtp.gmail.com
    SMTP_PORT          default 465 (SSL)
"""

import logging
import os
import re
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr

logger = logging.getLogger(__name__)

CATEGORIES = ("problem", "pdf", "assistant", "suggestion", "other")
MAX_MESSAGE_CHARS = 3000
MIN_MESSAGE_CHARS = 10
MAX_NAME_CHARS = 80
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class TicketError(Exception):
    """A ticket that cannot be sent. kind: invalid_email, invalid_message,
    invalid_name, unavailable (not configured), send_failed."""

    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


def _setting(name, default=None):
    value = os.environ.get(name)
    if not value:
        try:
            import streamlit as st
            value = st.secrets.get(name)
        except (FileNotFoundError, KeyError, RuntimeError):
            value = None
    return value or default


def is_configured():
    return all(_setting(name) for name in ("SUPPORT_EMAIL_TO", "SMTP_USER", "SMTP_PASSWORD"))


def validate(contact_email, message, name=""):
    contact_email = str(contact_email or "").strip()
    message = str(message or "").strip()
    name = str(name or "").strip()
    if len(contact_email) > 254 or not _EMAIL.match(contact_email):
        raise TicketError("invalid_email")
    if not MIN_MESSAGE_CHARS <= len(message) <= MAX_MESSAGE_CHARS:
        raise TicketError("invalid_message")
    # Names go into an email header: refuse line breaks (header injection).
    if len(name) > MAX_NAME_CHARS or any(ch in name for ch in "\r\n"):
        raise TicketError("invalid_name")
    return contact_email, message, name


def send_ticket(category, contact_email, message, name="", context=None):
    """Validate and email a ticket. Returns its short reference id."""
    contact_email, message, name = validate(contact_email, message, name)
    category = category if category in CATEGORIES else "other"
    if not is_configured():
        logger.error("Support ticket not sent: email settings are missing.")
        raise TicketError("unavailable")

    ticket_id = uuid.uuid4().hex[:8].upper()
    sender = _setting("SMTP_USER")
    mail = EmailMessage()
    mail["Subject"] = f"[Cornell Notes] {category} #{ticket_id}"
    mail["From"] = formataddr(("Cornell Notes Support", sender))
    mail["To"] = _setting("SUPPORT_EMAIL_TO")
    mail["Reply-To"] = formataddr((name, contact_email)) if name else contact_email
    details = "\n".join(f"{key}: {value}" for key, value in (context or {}).items())
    mail.set_content(
        f"Ticket: #{ticket_id}\n"
        f"Time (UTC): {datetime.now(timezone.utc):%Y-%m-%d %H:%M}\n"
        f"Category: {category}\n"
        f"Name: {name or '-'}\n"
        f"Reply to: {contact_email}\n"
        f"{details}\n\n"
        f"{message}\n"
    )
    try:
        with smtplib.SMTP_SSL(_setting("SMTP_HOST", "smtp.gmail.com"),
                              int(_setting("SMTP_PORT", "465")),
                              context=ssl.create_default_context(), timeout=20) as server:
            server.login(sender, _setting("SMTP_PASSWORD"))
            server.send_message(mail)
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("Support ticket %s not sent: %s", ticket_id, type(exc).__name__)
        raise TicketError("send_failed") from exc
    logger.info("Support ticket %s sent (%s).", ticket_id, category)
    return ticket_id
