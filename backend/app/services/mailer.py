"""SMTP transport.

The only thing in the codebase that talks to a mail server. Configuration comes
from the environment (``SMTP_*``); whether a given notification is *sent* is
decided elsewhere, in :mod:`app.services.notifications`.
"""
from __future__ import annotations

import logging
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import aiosmtplib

from ..config import settings

logger = logging.getLogger(__name__)


class MailError(RuntimeError):
    """The message could not be handed to the SMTP server."""


def is_configured() -> bool:
    return settings.smtp_configured


def describe() -> dict[str, object]:
    """Non-secret view of the SMTP configuration, for the admin screen."""
    return {
        "configured": settings.smtp_configured,
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "security": settings.smtp_security,
        "username": settings.smtp_username,
        "from_email": settings.sender_email,
        "from_name": settings.smtp_from_name or settings.app_name,
        # Never expose the password, not even masked length.
        "has_password": bool(settings.smtp_password),
    }


def build_message(
    *, to: str, subject: str, text_body: str, html_body: str | None = None
) -> EmailMessage:
    """Assemble a ``multipart/alternative`` message with a plain-text part.

    The text part is not decoration: many clients and most spam filters treat a
    HTML-only message as a bad signal.
    """
    sender = settings.sender_email
    if not sender:  # pragma: no cover - guarded by is_configured()
        raise MailError("No sender address configured (SMTP_FROM_EMAIL)")

    message = EmailMessage()
    message["From"] = formataddr((settings.smtp_from_name or settings.app_name, sender))
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid()
    # Notifications are transactional; keep them out of vacation-responder and
    # list-unsubscribe machinery that would otherwise reply to them.
    message["Auto-Submitted"] = "auto-generated"
    message["X-Auto-Response-Suppress"] = "All"

    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    return message


async def send(message: EmailMessage) -> None:
    """Deliver one message. Raises :class:`MailError` on any failure."""
    if not settings.smtp_configured:
        raise MailError(
            "SMTP is not configured — set SMTP_HOST and SMTP_FROM_EMAIL (or a "
            "SMTP_USERNAME that is an address)"
        )

    security = settings.smtp_security
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            use_tls=security == "ssl",
            start_tls=True if security == "starttls" else None,
            timeout=settings.smtp_timeout,
        )
    except aiosmtplib.SMTPException as exc:
        raise MailError(f"{type(exc).__name__}: {exc}") from exc
    except OSError as exc:
        # Connection refused / DNS failure / TLS handshake — aiosmtplib lets
        # these through untouched, and they often stringify to nothing useful.
        raise MailError(
            f"cannot reach {settings.smtp_host}:{settings.smtp_port} "
            f"({security}) — {type(exc).__name__}: {exc or 'no detail'}"
        ) from exc


async def send_email(
    *, to: str, subject: str, text_body: str, html_body: str | None = None
) -> None:
    # Check the whole configuration up front: building the message first would
    # surface only the missing sender and hide that SMTP_HOST is unset too.
    if not settings.smtp_configured:
        raise MailError(
            "SMTP is not configured — set SMTP_HOST and SMTP_FROM_EMAIL (or a "
            "SMTP_USERNAME that is an address)"
        )
    await send(
        build_message(to=to, subject=subject, text_body=text_body, html_body=html_body)
    )
