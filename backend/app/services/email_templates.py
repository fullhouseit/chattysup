"""Rendering of notification emails.

Deliberately hand-rolled instead of a template engine: there are two emails, and
inline styles with a table layout are what mail clients actually render. Every
interpolated value goes through :func:`html.escape`.
"""
from __future__ import annotations

from datetime import datetime
from html import escape

from ..config import settings

#: A single message preview is truncated to keep the mail readable and to avoid
#: shipping an entire conversation into an inbox.
PREVIEW_LIMIT = 1200

BRAND = "#1F93FF"
INK = "#1F2937"
MUTED = "#6B7280"
LINE = "#E5E7EB"


def app_url(path: str = "") -> str:
    return f"{settings.base_url.rstrip('/')}{path}"


def conversation_url(conversation_id: int) -> str:
    """Deep link an agent can click straight from the mail.

    Signed-out recipients land on the login screen, which sends them back here
    afterwards — the SPA's ProtectedRoute appends ``?next=``.
    """
    return app_url(f"/conversations/{conversation_id}")


def _truncate(text: str, limit: int = PREVIEW_LIMIT) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def _body_html(content: str) -> str:
    """Escaped message text with newlines preserved."""
    return escape(_truncate(content)).replace("\n", "<br>")


def _button(url: str, label: str) -> str:
    return f"""
      <table role="presentation" cellpadding="0" cellspacing="0" border="0">
        <tr><td align="center" bgcolor="{BRAND}" style="border-radius:8px;">
          <a href="{escape(url)}"
             style="display:inline-block;padding:12px 24px;font-family:-apple-system,
                    Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:15px;
                    font-weight:600;color:#ffffff;text-decoration:none;border-radius:8px;">
            {escape(label)}
          </a>
        </td></tr>
      </table>"""


def _shell(*, title: str, inner: str, footer: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:#F3F4F6;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:#F3F4F6;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="max-width:560px;background:#ffffff;border:1px solid {LINE};
                    border-radius:12px;overflow:hidden;
                    font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
        {inner}
      </table>
      <div style="max-width:560px;margin:16px auto 0;font-family:-apple-system,Segoe UI,
                  Roboto,Helvetica,Arial,sans-serif;font-size:12px;color:{MUTED};
                  text-align:center;line-height:1.6;">
        {footer}
      </div>
    </td></tr>
  </table>
</body></html>"""


def render_new_message(
    *,
    contact_name: str,
    inbox_name: str,
    content: str,
    conversation_id: int,
    attachments: list[str] | None = None,
    is_private_note: bool = False,
    author_name: str | None = None,
    sent_at: datetime | None = None,
) -> tuple[str, str, str]:
    """Return ``(subject, text_body, html_body)`` for one new message."""
    app = settings.app_name
    who = author_name or contact_name
    url = conversation_url(conversation_id)
    attachments = attachments or []

    kind = "New private note" if is_private_note else "New message"
    subject = f"[{app}] {kind} from {who}"
    preview = _truncate(content) if content.strip() else "(no text)"

    attachment_line = ""
    if attachments:
        names = ", ".join(attachments[:5])
        if len(attachments) > 5:
            names += f" and {len(attachments) - 5} more"
        attachment_line = f"Attachments: {names}"

    # --- plain text -----------------------------------------------------
    text_lines = [
        f"{kind} from {who}",
        f"Inbox: {inbox_name}",
        "",
        preview,
    ]
    if attachment_line:
        text_lines += ["", attachment_line]
    text_lines += [
        "",
        f"Open the conversation: {url}",
        "",
        f"— {app}",
        f"Turn these emails off: {app_url('/profile')}",
    ]
    text_body = "\n".join(text_lines)

    # --- html -----------------------------------------------------------
    stamp = sent_at.strftime("%d %b %Y, %H:%M UTC") if sent_at else ""
    attachment_html = (
        f"""<p style="margin:12px 0 0;font-size:13px;color:{MUTED};">
              📎 {escape(attachment_line)}</p>"""
        if attachment_line
        else ""
    )
    bubble_bg = "#FEF3C7" if is_private_note else "#F9FAFB"

    inner = f"""
        <tr><td style="padding:20px 24px;border-bottom:1px solid {LINE};">
          <span style="font-size:15px;font-weight:700;color:{INK};">{escape(app)}</span>
          <span style="float:right;font-size:12px;color:{MUTED};">{escape(inbox_name)}</span>
        </td></tr>
        <tr><td style="padding:24px;">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td width="40" valign="top">
                <div style="width:40px;height:40px;border-radius:20px;background:#E0F2FE;
                            color:{BRAND};font-size:14px;font-weight:700;line-height:40px;
                            text-align:center;">{escape(_initials(who))}</div>
              </td>
              <td style="padding-left:12px;" valign="top">
                <div style="font-size:15px;font-weight:600;color:{INK};">{escape(who)}</div>
                <div style="font-size:12px;color:{MUTED};">{escape(stamp)}</div>
              </td>
            </tr>
          </table>

          <div style="margin-top:16px;padding:14px 16px;background:{bubble_bg};
                      border:1px solid {LINE};border-radius:10px;font-size:15px;
                      line-height:1.55;color:{INK};white-space:normal;">
            {_body_html(content) if content.strip() else
             f'<span style="color:{MUTED};">(no text)</span>'}
          </div>
          {attachment_html}

          <div style="margin-top:24px;">{_button(url, "Open conversation")}</div>
        </td></tr>"""

    footer = (
        f'You receive this because email notifications are on for your account.<br>'
        f'<a href="{escape(app_url("/profile"))}" style="color:{MUTED};">'
        f"Manage notification settings</a>"
    )
    return subject, text_body, _shell(title=subject, inner=inner, footer=footer)


def render_test_email(*, recipient_name: str) -> tuple[str, str, str]:
    """A message an admin can send to prove the SMTP settings work."""
    app = settings.app_name
    subject = f"[{app}] Test email"
    url = app_url("/admin/settings")

    text_body = "\n".join(
        [
            f"Hi {recipient_name},",
            "",
            f"This is a test email from {app}. If you are reading it, your SMTP "
            "settings work and notifications can be delivered.",
            "",
            f"Settings: {url}",
            "",
            f"— {app}",
        ]
    )

    inner = f"""
        <tr><td style="padding:20px 24px;border-bottom:1px solid {LINE};">
          <span style="font-size:15px;font-weight:700;color:{INK};">{escape(app)}</span>
        </td></tr>
        <tr><td style="padding:24px;">
          <div style="font-size:15px;color:{INK};line-height:1.6;">
            Hi {escape(recipient_name)},<br><br>
            This is a test email from <strong>{escape(app)}</strong>. If you are
            reading it, your SMTP settings work and notifications can be delivered.
          </div>
          <div style="margin-top:24px;">{_button(url, "Open settings")}</div>
        </td></tr>"""

    return subject, text_body, _shell(
        title=subject, inner=inner, footer=f"Sent by {escape(app)}."
    )
