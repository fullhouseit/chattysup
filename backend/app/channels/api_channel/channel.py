"""Generic **API** channel — Chatwoot's ``Channel::Api`` equivalent.

An API inbox has no upstream provider of its own. Instead:

* **inbound** messages arrive over the Client (Public) API,
  ``POST /public/api/v1/inboxes/{inbox_identifier}/…`` (see
  :mod:`app.api.chatwoot.client`);
* **outbound** messages are pushed to the operator's ``webhook_url`` as a
  Chatwoot ``message_created`` body, signed exactly like Chatwoot signs its own
  webhooks (``lib/webhooks/trigger.rb``).

Three distinct tokens live in the inbox config, and conflating them is the
classic Chatwoot integration bug:

``inbox_identifier``
    Public, appears in every Client API URL. Identifies the inbox.
``hmac_token``
    Key for **inbound** contact identity validation (``identifier_hash``).
``secret``
    Key for the **outbound** ``X-Chatwoot-Signature`` header.

All three are server generated; the operator only ever supplies ``webhook_url``.
"""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import (
    ContactInbox,
    ContentType,
    Conversation,
    Inbox,
    Message,
    MessageStatus,
    MessageType,
    SenderType,
    Team,
    User,
)
from ..base import (
    BaseChannel,
    ChannelConfigError,
    ChannelError,
    FieldSpec,
    InboundEvent,
    OutboundMessage,
    SendResult,
    register,
)

logger = logging.getLogger(__name__)

#: Chatwoot's ``has_secure_token`` produces a 24 character Base58 string.
_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TOKEN_LENGTH = 24

#: Chatwoot fires the API-inbox webhook once with a five second timeout and
#: never retries it; a failure marks the message ``failed`` instead.
WEBHOOK_TIMEOUT = 5.0


def generate_token(length: int = TOKEN_LENGTH) -> str:
    """A Base58 token shaped like Rails' ``has_secure_token``."""
    return "".join(secrets.choice(_BASE58) for _ in range(length))


# ---------------------------------------------------------------------------
# Ambient session
# ---------------------------------------------------------------------------
#: The outgoing payload needs the *whole* conversation graph, but
#: :meth:`BaseChannel.send_message` only receives the upstream chat id. The
#: caller that owns the transaction publishes its session here so the channel
#: can read rows that are flushed but not yet committed — a second connection
#: would not see them. When it is unset (a caller that predates this channel)
#: we degrade gracefully: the conversation is read through a fresh session and
#: the message is rendered from the outbound payload alone.
_ambient_session: ContextVar[AsyncSession | None] = ContextVar(
    "api_channel_session", default=None
)


@asynccontextmanager
async def use_session(session: AsyncSession):
    """Lend ``session`` to any API channel delivery made inside the block."""
    token = _ambient_session.set(session)
    try:
        yield session
    finally:
        _ambient_session.reset(token)


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------
@register
class ApiChannel(BaseChannel):
    """A programmable inbox driven entirely over HTTP."""

    key = "api"
    display_name = "API"
    description = (
        "A programmable inbox. Customers write through the Client API, agent "
        "replies are POSTed to your webhook URL in Chatwoot's format."
    )
    icon = "webhook"
    color = "#6C5CE7"

    supports_polling = False
    supports_webhook = True
    supports_proxy = False
    #: Honest capability set: the channel relays JSON, nothing more. Media
    #: travels as URLs inside the payload and replies carry ``in_reply_to``;
    #: there is no upstream to react to, edit, delete or type into.
    capabilities = {"media", "reply"}

    config_fields = [
        FieldSpec(
            key="webhook_url",
            label="Webhook URL",
            kind="url",
            placeholder="https://example.com/chatwoot-webhook",
            help_text=(
                "Agent replies are POSTed here as a Chatwoot 'message_created' "
                "payload. Leave empty to disable outbound delivery."
            ),
        ),
        FieldSpec(
            key="inbox_identifier",
            label="Inbox identifier",
            kind="text",
            help_text=(
                "Public id used in the Client API URLs. Generated automatically."
            ),
        ),
        FieldSpec(
            key="hmac_token",
            label="HMAC token",
            kind="password",
            secret=True,
            help_text=(
                "Key for inbound contact identity validation (identifier_hash). "
                "Generated automatically."
            ),
        ),
        FieldSpec(
            key="secret",
            label="Webhook signing secret",
            kind="password",
            secret=True,
            help_text=(
                "Key for the outbound X-Chatwoot-Signature header. Generated "
                "automatically."
            ),
        ),
        FieldSpec(
            key="hmac_mandatory",
            label="Require identity validation",
            kind="boolean",
            default=False,
            help_text="Reject Client API contact calls without an identifier_hash.",
        ),
        FieldSpec(
            key="agent_reply_time_window",
            label="Agent reply window (hours)",
            kind="number",
            help_text="Hours after the last customer message during which agents may reply.",
        ),
    ]

    # -- lifecycle -------------------------------------------------------
    @classmethod
    async def validate_config(
        cls, config: dict[str, Any], *, proxy: str | None = None
    ) -> dict[str, Any]:
        """Mint the three tokens and normalise the operator supplied fields."""
        config = await super().validate_config(config, proxy=proxy)
        data = dict(config)

        url = str(data.get("webhook_url") or "").strip()
        if url and not url.startswith(("http://", "https://")):
            raise ChannelConfigError("Webhook URL must start with http:// or https://")
        data["webhook_url"] = url or None

        # Stable across updates: the identifier is a public URL segment and
        # rotating it would break every configured client.
        for key in ("inbox_identifier", "hmac_token", "secret"):
            if not str(data.get(key) or "").strip():
                data[key] = generate_token()

        data["hmac_mandatory"] = bool(data.get("hmac_mandatory", False))

        window = data.get("agent_reply_time_window")
        if window in ("", None):
            data["agent_reply_time_window"] = None
        else:
            try:
                window = int(window)
            except (TypeError, ValueError) as exc:
                raise ChannelConfigError(
                    "Agent reply window must be a whole number of hours"
                ) from exc
            if window <= 0:
                raise ChannelConfigError("Agent reply window must be greater than 0")
            data["agent_reply_time_window"] = window
        return data

    async def setup(self) -> dict[str, Any]:
        return {
            "inbox_identifier": self.config.get("inbox_identifier"),
            "webhook_url": self.config.get("webhook_url"),
        }

    async def health_check(self) -> dict[str, Any]:
        """Reachability probe of ``webhook_url``.

        A plain ``GET`` — the endpoint may legitimately answer 404/405 to it, so
        *any* HTTP response counts as reachable; only a transport failure is an
        error. Nothing is delivered by this probe.
        """
        url = self.config.get("webhook_url")
        result: dict[str, Any] = {
            "status": "ok",
            "inbox_identifier": self.config.get("inbox_identifier"),
            "webhook_url": url,
        }
        if not url:
            result["status"] = "warning"
            result["warning"] = (
                "No webhook URL configured: agent replies are stored but never "
                "pushed anywhere."
            )
            return result

        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise ChannelError(f"Webhook URL is unreachable: {exc}") from exc
        result["webhook_status"] = response.status_code
        return result

    # -- inbound ---------------------------------------------------------
    async def fetch_updates(
        self, cursor: str | None
    ) -> tuple[list[InboundEvent], str | None]:
        """Nothing to poll — customers push through the Client API.

        Returns empty rather than raising so an inbox accidentally left in
        polling mode idles quietly instead of flapping the supervisor.
        """
        return [], cursor

    # -- outbound --------------------------------------------------------
    async def send_message(
        self, chat_source_id: str, message: OutboundMessage
    ) -> SendResult:
        """POST the Chatwoot ``message_created`` body to ``webhook_url``."""
        url = self.config.get("webhook_url")
        if not url:
            raise ChannelError("This API inbox has no webhook URL configured")

        payload, message_id = await self._build_payload(chat_source_id, message)
        body = json.dumps(payload, default=str).encode("utf-8")
        delivery_id = str(uuid.uuid4())

        # Same header construction as our Chatwoot-format webhook dispatcher:
        # HMAC-SHA256 over "{timestamp}.{raw_body}", prefixed with "sha256=".
        from ...services.webhooks import chatwoot_headers

        headers = chatwoot_headers(self.config.get("secret"), body, delivery_id)

        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
                response = await client.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ChannelError(f"Webhook delivery failed: {exc}") from exc

        if not response.is_success:
            raise ChannelError(
                f"Webhook URL returned HTTP {response.status_code}"
            )

        remote_id = _remote_message_id(response)
        return SendResult(
            source_id=remote_id or (str(message_id) if message_id else delivery_id),
            attributes={
                "api": {
                    "delivery_id": delivery_id,
                    "status_code": response.status_code,
                    "webhook_url": url,
                }
            },
        )

    # -- payload ---------------------------------------------------------
    async def _build_payload(
        self, chat_source_id: str, message: OutboundMessage
    ) -> tuple[dict[str, Any], int | None]:
        session = _ambient_session.get()
        if session is not None:
            return await self._payload_from(session, chat_source_id, message)

        from ...db import SessionLocal

        async with SessionLocal() as fresh:
            return await self._payload_from(fresh, chat_source_id, message)

    async def _payload_from(
        self, db: AsyncSession, chat_source_id: str, message: OutboundMessage
    ) -> tuple[dict[str, Any], int | None]:
        from ...compat import chatwoot

        conversation = await db.scalar(
            select(Conversation)
            .where(
                Conversation.inbox_id == self.inbox.id,
                Conversation.source_id == str(chat_source_id),
            )
            .order_by(desc(Conversation.last_activity_at))
            .limit(1)
        )

        row: Message | None = None
        sender: User | None = None
        contact_inbox: ContactInbox | None = None
        team: Team | None = None

        if conversation is not None:
            # The message being delivered is the newest outgoing, non-private
            # one that has not been given an upstream id yet — delivery is what
            # assigns that id.
            row = await db.scalar(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.message_type == MessageType.OUTGOING.value,
                    Message.private.is_(False),
                    Message.source_id.is_(None),
                )
                .order_by(desc(Message.id))
                .limit(1)
            )
            if conversation.contact_inbox_id:
                contact_inbox = await db.get(
                    ContactInbox, conversation.contact_inbox_id
                )
            if conversation.team_id:
                team = await db.get(Team, conversation.team_id)

        if row is None:
            row = self._transient_message(conversation, message)
        if row.sender_type == SenderType.USER.value and row.sender_id:
            sender = await db.get(User, row.sender_id)

        inbox = conversation.inbox if conversation is not None else self.inbox
        body = chatwoot.build_event(
            "message_created",
            message=row,
            conversation=conversation,
            inbox=inbox,
            sender=sender,
            contact=conversation.contact if conversation is not None else None,
            assignee=conversation.assignee if conversation is not None else None,
            team=team,
            contact_inbox=contact_inbox,
        )
        return body, row.id

    def _transient_message(
        self, conversation: Conversation | None, message: OutboundMessage
    ) -> Message:
        """A stand-in row for callers whose transaction we cannot read.

        Never added to the session — it exists only so the payload keeps the
        Chatwoot key set instead of collapsing to a hand-rolled shape.
        """
        return Message(
            conversation_id=conversation.id if conversation is not None else None,
            inbox_id=self.inbox.id,
            content=message.content,
            content_type=ContentType.TEXT.value,
            message_type=MessageType.OUTGOING.value,
            private=False,
            status=MessageStatus.SENT.value,
            sender_type=SenderType.BOT.value,
            content_attributes=dict(message.attributes or {}),
        )


def _remote_message_id(response: httpx.Response) -> str | None:
    """Honour an id echoed back by the receiver, when it sends one."""
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("source_id", "message_id", "id"):
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def api_inbox_query():
    """Select statement matching every inbox served by this channel."""
    return select(Inbox).where(Inbox.channel_type == ApiChannel.key)
