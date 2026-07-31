"""Telegram Bot API channel (Bot API 9.x).

Supports both long polling and webhooks, private chats and groups, the full
media matrix (photo, voice, audio, video, video note, animation, sticker,
document, location, venue, contact, poll), message edits, reactions, typing
indicators and inline keyboard callbacks.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ...config import settings
from ...core import storage
from ...models import AttachmentType, ContentType, Inbox, InboxMode
from ..base import (
    BaseChannel,
    ChannelConfigError,
    ChannelError,
    FieldSpec,
    InboundEvent,
    NormalizedAttachment,
    NormalizedContact,
    NormalizedMessage,
    OutboundMessage,
    SendResult,
    register,
)
from .api import MAX_DOWNLOAD_BYTES, TelegramApi

logger = logging.getLogger(__name__)

#: Update types we ask Telegram for. Anything else is silently dropped.
ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "message_reaction",
    "callback_query",
    "my_chat_member",
    "business_message",
]

#: Bot API payload limits.
MAX_TEXT_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024
#: How long ``getUpdates`` is allowed to hold the connection open.
POLL_TIMEOUT = 25

#: Emoji Telegram accepts in ``setMessageReaction`` (Bot API 9.x).
SUPPORTED_REACTIONS = {
    "👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", "🤬", "😢",
    "🎉", "🤩", "🤮", "💩", "🙏", "👌", "🕊", "🤡", "🥱", "🥴", "😍", "🐳",
    "❤‍🔥", "🌚", "🌭", "💯", "🤣", "⚡", "🍌", "🏆", "💔", "🤨", "😐", "🍓",
    "🍾", "💋", "🖕", "😈", "😴", "😭", "🤓", "👻", "👨‍💻", "👀", "🎃", "🙈",
    "😇", "😨", "🤝", "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪", "🗿",
    "🆒", "💘", "🙉", "🦄", "😘", "💊", "🙊", "😎", "👾", "🤷‍♂", "🤷", "🤷‍♀",
    "😡",
}
FALLBACK_REACTION = "👍"

#: ``AttachmentType`` -> (Bot API method, multipart/JSON field name).
_SEND_METHODS: dict[str, tuple[str, str]] = {
    AttachmentType.IMAGE.value: ("sendPhoto", "photo"),
    AttachmentType.VOICE.value: ("sendVoice", "voice"),
    AttachmentType.AUDIO.value: ("sendAudio", "audio"),
    AttachmentType.VIDEO.value: ("sendVideo", "video"),
    AttachmentType.VIDEO_NOTE.value: ("sendVideoNote", "video_note"),
    AttachmentType.ANIMATION.value: ("sendAnimation", "animation"),
    AttachmentType.STICKER.value: ("sendSticker", "sticker"),
    AttachmentType.FILE.value: ("sendDocument", "document"),
}
#: Attachment types that do not accept a ``caption``.
_CAPTIONLESS = {AttachmentType.VIDEO_NOTE.value, AttachmentType.STICKER.value}
#: Attachment types that can travel together in a ``sendMediaGroup``.
_ALBUM_TYPES = {AttachmentType.IMAGE.value: "photo", AttachmentType.VIDEO.value: "video"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def chunk_text(text: str, limit: int = MAX_TEXT_LENGTH) -> list[str]:
    """Split ``text`` into Telegram sized chunks, preferring clean break points.

    Splits on the last newline (then the last space) inside the window so words
    and lines survive; falls back to a hard cut for unbroken blobs.
    """
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _full_name(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    parts = [user.get("first_name") or "", user.get("last_name") or ""]
    return " ".join(p for p in parts if p).strip()


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):  # pragma: no cover - defensive
        return None


def _reaction_emojis(reactions: list[dict[str, Any]] | None) -> list[str]:
    """Flatten a Telegram ``ReactionType`` list into plain strings."""
    out: list[str] = []
    for reaction in reactions or []:
        emoji = reaction.get("emoji") or reaction.get("custom_emoji_id")
        if emoji:
            out.append(emoji)
    return out


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------
@register
class TelegramChannel(BaseChannel):
    """A Telegram bot exposed as a ChattySup inbox."""

    key = "telegram"
    display_name = "Telegram"
    description = "Connect a Telegram bot via long polling or webhooks."
    icon = "send"
    color = "#2AABEE"

    supports_polling = True
    supports_webhook = True
    supports_proxy = True
    capabilities = {
        "reactions",
        "typing",
        "edit",
        "delete",
        "voice",
        "stickers",
        "media",
        "reply",
    }

    config_fields = [
        FieldSpec(
            key="bot_token",
            label="Bot token",
            kind="password",
            required=True,
            secret=True,
            placeholder="123456:ABC-DEF…",
            help_text="Issued by @BotFather.",
        ),
        FieldSpec(
            key="bot_username",
            label="Bot username",
            kind="text",
            help_text="Filled automatically once the token is verified.",
        ),
        FieldSpec(
            key="allowed_updates",
            label="Allowed updates",
            kind="text",
            help_text="Comma separated update types. Leave empty for the defaults.",
        ),
        FieldSpec(
            key="download_media",
            label="Download media",
            kind="boolean",
            default=True,
            help_text="Store incoming files locally. Disable to keep only file ids.",
        ),
        FieldSpec(
            key="skip_old_updates",
            label="Skip old updates",
            kind="boolean",
            default=True,
            help_text="Ignore the backlog accumulated while the inbox was offline.",
        ),
    ]

    def __init__(self, inbox: Inbox) -> None:
        super().__init__(inbox)
        self._api: TelegramApi | None = None

    # -- infrastructure --------------------------------------------------
    @property
    def api(self) -> TelegramApi:
        """The lazily created HTTP client for this inbox."""
        if self._api is None:
            token = self.config.get("bot_token")
            if not token:
                raise ChannelConfigError("Telegram inbox has no bot token")
            self._api = TelegramApi(
                token,
                proxy=self.inbox.proxy_url or settings.http_proxy,
                timeout=30.0,
            )
        return self._api

    async def close(self) -> None:
        if self._api is not None:
            await self._api.aclose()
            self._api = None

    @property
    def allowed_updates(self) -> list[str]:
        """Update types configured for this inbox, defaulting to :data:`ALLOWED_UPDATES`."""
        raw = (self.config.get("allowed_updates") or "").strip()
        if not raw:
            return list(ALLOWED_UPDATES)
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def download_media(self) -> bool:
        return bool(self.config.get("download_media", True))

    @property
    def webhook_url(self) -> str:
        return (
            f"{settings.base_url.rstrip('/')}"
            f"/api/v1/webhooks/telegram/{self.inbox.webhook_token}"
        )

    # -- lifecycle -------------------------------------------------------
    @classmethod
    async def validate_config(
        cls, config: dict[str, Any], *, proxy: str | None = None
    ) -> dict[str, Any]:
        """Check the token against ``getMe`` and enrich the config with bot identity."""
        config = await super().validate_config(config, proxy=proxy)
        token = str(config.get("bot_token") or "").strip()
        if not token:
            raise ChannelConfigError("Field 'Bot token' is required")

        # Validate through the same proxy the inbox will use at runtime.
        api = TelegramApi(token, proxy=proxy or settings.http_proxy, timeout=15.0)
        try:
            me = await api.call("getMe")
        except ChannelError as exc:
            raise ChannelConfigError(str(exc)) from exc
        finally:
            await api.aclose()

        return {
            **config,
            "bot_token": token,
            "bot_username": me.get("username"),
            "bot_id": me.get("id"),
            "bot_name": me.get("first_name"),
            "download_media": bool(config.get("download_media", True)),
            "skip_old_updates": bool(config.get("skip_old_updates", True)),
        }

    async def setup(self) -> dict[str, Any]:
        """Register or drop the webhook depending on the inbox mode."""
        if self.inbox.mode == InboxMode.WEBHOOK.value:
            await self.api.call(
                "setWebhook",
                url=self.webhook_url,
                secret_token=self.inbox.webhook_token,
                allowed_updates=self.allowed_updates,
                drop_pending_updates=bool(self.config.get("skip_old_updates", True)),
                max_connections=40,
            )
            return {"mode": "webhook", "webhook_url": self.webhook_url}

        await self.api.call("deleteWebhook", drop_pending_updates=False)
        return {"mode": "polling"}

    async def teardown(self) -> None:
        """Remove the webhook so the bot can be reused elsewhere."""
        try:
            await self.api.call("deleteWebhook", drop_pending_updates=False)
        except ChannelError as exc:  # pragma: no cover - best effort
            logger.info("teardown of inbox %s failed: %s", self.inbox.id, exc)

    async def health_check(self) -> dict[str, Any]:
        me = await self.api.call("getMe")
        return {
            "status": "ok",
            "username": me.get("username"),
            "id": me.get("id"),
            "name": me.get("first_name"),
        }

    # -- inbound ---------------------------------------------------------
    async def fetch_updates(
        self, cursor: str | None
    ) -> tuple[list[InboundEvent], str | None]:
        """Long poll ``getUpdates`` and normalise everything it returns."""
        offset: int | None = None
        if cursor:
            try:
                offset = int(cursor) + 1
            except ValueError:
                logger.warning("invalid telegram cursor %r, restarting", cursor)
        elif self.config.get("skip_old_updates", True):
            # First run: acknowledge the backlog so agents are not flooded with
            # everything that happened while the inbox was offline.
            skipped = await self.api.call("getUpdates", offset=-1, timeout=0)
            if skipped:
                return [], str(skipped[-1]["update_id"])

        updates = await self.api.call(
            "getUpdates",
            offset=offset,
            timeout=POLL_TIMEOUT,
            allowed_updates=self.allowed_updates,
            # Give the socket more room than the long-poll window itself.
            http_timeout=POLL_TIMEOUT + 15,
        )

        events: list[InboundEvent] = []
        next_cursor = cursor
        for update in updates or []:
            next_cursor = str(update["update_id"])
            try:
                events.extend(self._to_events(update))
            except Exception:  # pragma: no cover - never lose the cursor
                logger.exception("failed to normalise telegram update %s", next_cursor)
        return events, next_cursor

    async def parse_webhook(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> list[InboundEvent]:
        """Verify the secret header and normalise a single webhook update."""
        lowered = {k.lower(): v for k, v in (headers or {}).items()}
        secret = lowered.get("x-telegram-bot-api-secret-token")
        if not self.inbox.webhook_token or secret != self.inbox.webhook_token:
            raise ChannelError("Invalid Telegram webhook secret token")
        return self._to_events(payload or {})

    # -- normalisation ---------------------------------------------------
    def _to_events(self, update: dict[str, Any]) -> list[InboundEvent]:
        """Translate one raw Telegram ``Update`` into normalised events."""
        if "message" in update or "business_message" in update:
            message = update.get("message") or update["business_message"]
            return self._message_events(update, message, kind="message")

        if "edited_message" in update:
            return self._message_events(
                update, update["edited_message"], kind="message_edited"
            )

        if "message_reaction" in update:
            return self._reaction_events(update)

        if "callback_query" in update:
            return self._callback_events(update)

        if "my_chat_member" in update:
            self._log_membership(update["my_chat_member"])
            return []

        # channel_post, poll answers, inline queries… are out of scope.
        return []

    def _log_membership(self, member_update: dict[str, Any]) -> None:
        status = (member_update.get("new_chat_member") or {}).get("status")
        chat = (member_update.get("chat") or {}).get("id")
        if status in {"kicked", "left"}:
            logger.info("bot removed from telegram chat %s (status=%s)", chat, status)

    def _contact(self, chat: dict[str, Any], user: dict[str, Any] | None) -> NormalizedContact:
        """Build the contact for a chat, preferring the human who wrote."""
        name = _full_name(user) or chat.get("title") or chat.get("first_name") or ""
        username = (user or {}).get("username") or chat.get("username")
        return NormalizedContact(
            source_id=str(chat.get("id")),
            name=name or f"Telegram {chat.get('id')}",
            username=username,
            language=(user or {}).get("language_code"),
            meta={
                "telegram_user_id": (user or {}).get("id"),
                "chat_type": chat.get("type"),
                "username": username,
                "is_premium": bool((user or {}).get("is_premium")),
            },
        )

    def _message_events(
        self, update: dict[str, Any], message: dict[str, Any], *, kind: str
    ) -> list[InboundEvent]:
        chat = message.get("chat") or {}
        if chat.get("type") == "channel":
            return []

        content = message.get("text") or message.get("caption")
        content_type = ContentType.TEXT.value
        attachments: list[NormalizedAttachment] = []

        media_content, media_type, attachments = self._extract_media(message)
        if media_type:
            content_type = media_type
        if media_content and not content:
            content = media_content

        attributes: dict[str, Any] = {
            "telegram_chat_id": chat.get("id"),
            "telegram_chat_type": chat.get("type"),
        }
        reply_to = (message.get("reply_to_message") or {}).get("message_id")
        if reply_to:
            attributes["reply_to_source_id"] = str(reply_to)
        forwarded = self._forward_origin(message)
        if forwarded:
            attributes["forwarded_from"] = forwarded
        if message.get("entities") or message.get("caption_entities"):
            attributes["entities"] = message.get("entities") or message["caption_entities"]
        if message.get("is_topic_message"):
            attributes["is_topic_message"] = True
        if message.get("message_thread_id"):
            attributes["message_thread_id"] = message["message_thread_id"]
        if message.get("via_bot"):
            attributes["via_bot"] = (message["via_bot"] or {}).get("username")
        if message.get("business_connection_id"):
            attributes["business_connection_id"] = message["business_connection_id"]

        normalized = NormalizedMessage(
            source_id=str(message.get("message_id")),
            content=content,
            content_type=content_type,
            attachments=attachments,
            sent_at=_ts(message.get("edit_date") or message.get("date")),
            attributes=attributes,
        )
        return [
            InboundEvent(
                kind=kind,  # type: ignore[arg-type]
                chat_source_id=str(chat.get("id")),
                contact=self._contact(chat, message.get("from")),
                message=normalized,
                raw=update,
            )
        ]

    @staticmethod
    def _forward_origin(message: dict[str, Any]) -> str | None:
        origin = message.get("forward_origin") or {}
        if not origin:
            return None
        return (
            origin.get("sender_user_name")
            or _full_name(origin.get("sender_user"))
            or (origin.get("chat") or {}).get("title")
            or (origin.get("sender_chat") or {}).get("title")
            or None
        )

    def _extract_media(
        self, message: dict[str, Any]
    ) -> tuple[str | None, str | None, list[NormalizedAttachment]]:
        """Return ``(fallback_content, content_type, attachments)`` for a message."""
        keep = self.download_media

        if photos := message.get("photo"):
            sizes = sorted(photos, key=lambda p: p.get("file_size") or p.get("width") or 0)
            largest, smallest = sizes[-1], sizes[0]
            return None, None, [
                NormalizedAttachment(
                    file_type=AttachmentType.IMAGE.value,
                    mime_type="image/jpeg",
                    file_size=largest.get("file_size"),
                    external_id=largest.get("file_id"),
                    thumb_external_id=(
                        smallest.get("file_id") if smallest is not largest and keep else None
                    ),
                    meta={"width": largest.get("width"), "height": largest.get("height")},
                )
            ]

        if voice := message.get("voice"):
            return None, None, [
                self._media(
                    voice,
                    AttachmentType.VOICE.value,
                    meta={"duration": voice.get("duration")},
                )
            ]

        if audio := message.get("audio"):
            return None, None, [
                self._media(
                    audio,
                    AttachmentType.AUDIO.value,
                    file_name=audio.get("file_name"),
                    meta={
                        "duration": audio.get("duration"),
                        "title": audio.get("title"),
                        "performer": audio.get("performer"),
                    },
                )
            ]

        if video := message.get("video"):
            return None, None, [
                self._media(
                    video,
                    AttachmentType.VIDEO.value,
                    file_name=video.get("file_name"),
                    thumb=(video.get("thumbnail") or {}).get("file_id"),
                    meta={
                        "duration": video.get("duration"),
                        "width": video.get("width"),
                        "height": video.get("height"),
                    },
                )
            ]

        if note := message.get("video_note"):
            return None, None, [
                self._media(
                    note,
                    AttachmentType.VIDEO_NOTE.value,
                    thumb=(note.get("thumbnail") or {}).get("file_id"),
                    meta={"duration": note.get("duration"), "length": note.get("length")},
                )
            ]

        if animation := message.get("animation"):
            return None, None, [
                self._media(
                    animation,
                    AttachmentType.ANIMATION.value,
                    file_name=animation.get("file_name"),
                    thumb=(animation.get("thumbnail") or {}).get("file_id"),
                    meta={
                        "duration": animation.get("duration"),
                        "width": animation.get("width"),
                        "height": animation.get("height"),
                    },
                )
            ]

        if sticker := message.get("sticker"):
            attachment = self._media(
                sticker,
                AttachmentType.STICKER.value,
                thumb=(sticker.get("thumbnail") or {}).get("file_id"),
                meta={
                    "emoji": sticker.get("emoji"),
                    "set_name": sticker.get("set_name"),
                    "is_animated": bool(sticker.get("is_animated")),
                    "is_video": bool(sticker.get("is_video")),
                },
            )
            return sticker.get("emoji"), ContentType.STICKER.value, [attachment]

        if document := message.get("document"):
            return None, None, [
                self._media(
                    document,
                    AttachmentType.FILE.value,
                    file_name=document.get("file_name"),
                    thumb=(document.get("thumbnail") or {}).get("file_id"),
                )
            ]

        if location := (message.get("venue") or {}).get("location") or message.get("location"):
            venue = message.get("venue") or {}
            meta = {
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "title": venue.get("title"),
                "address": venue.get("address"),
            }
            attachment = NormalizedAttachment(
                file_type=AttachmentType.LOCATION.value,
                file_name=venue.get("title") or "location",
                meta=meta,
            )
            label = venue.get("title") or (
                f"{location.get('latitude')}, {location.get('longitude')}"
            )
            return label, ContentType.LOCATION.value, [attachment]

        if contact := message.get("contact"):
            meta = {
                "phone_number": contact.get("phone_number"),
                "first_name": contact.get("first_name"),
                "last_name": contact.get("last_name"),
                "user_id": contact.get("user_id"),
            }
            attachment = NormalizedAttachment(
                file_type=AttachmentType.CONTACT_CARD.value,
                file_name=_full_name(contact) or "contact",
                meta=meta,
            )
            label = " ".join(
                p for p in [_full_name(contact), contact.get("phone_number")] if p
            )
            return label or None, ContentType.CONTACT_CARD.value, [attachment]

        if poll := message.get("poll"):
            meta = {
                "options": [o.get("text") for o in poll.get("options") or []],
                "is_anonymous": poll.get("is_anonymous"),
                "type": poll.get("type"),
            }
            return (
                poll.get("question"),
                ContentType.POLL.value,
                [
                    NormalizedAttachment(
                        file_type=AttachmentType.FILE.value,
                        file_name="poll",
                        meta=meta,
                    )
                ],
            )

        return None, None, []

    @staticmethod
    def _media(
        payload: dict[str, Any],
        file_type: str,
        *,
        file_name: str | None = None,
        thumb: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> NormalizedAttachment:
        """Build a :class:`NormalizedAttachment` from a Telegram media object."""
        return NormalizedAttachment(
            file_type=file_type,
            file_name=file_name,
            mime_type=payload.get("mime_type"),
            file_size=payload.get("file_size"),
            external_id=payload.get("file_id"),
            thumb_external_id=thumb,
            meta={k: v for k, v in (meta or {}).items() if v is not None},
        )

    def _reaction_events(self, update: dict[str, Any]) -> list[InboundEvent]:
        payload = update["message_reaction"]
        chat = payload.get("chat") or {}
        return [
            InboundEvent(
                kind="reaction",
                chat_source_id=str(chat.get("id")),
                contact=self._contact(chat, payload.get("user")),
                target_source_id=str(payload.get("message_id")),
                reactions=_reaction_emojis(payload.get("new_reaction")),
                raw=update,
            )
        ]

    def _callback_events(self, update: dict[str, Any]) -> list[InboundEvent]:
        query = update["callback_query"]
        message = query.get("message") or {}
        chat = message.get("chat") or {}
        if not chat:
            return []
        return [
            InboundEvent(
                kind="message",
                chat_source_id=str(chat.get("id")),
                contact=self._contact(chat, query.get("from")),
                message=NormalizedMessage(
                    source_id=f"cb:{query.get('id')}",
                    content=f"🔘 {query.get('data') or ''}".strip(),
                    content_type=ContentType.TEXT.value,
                    sent_at=_ts(message.get("date")),
                    attributes={
                        "callback_query_id": query.get("id"),
                        "callback_data": query.get("data"),
                        "reply_to_source_id": str(message.get("message_id"))
                        if message.get("message_id")
                        else None,
                        "telegram_chat_id": chat.get("id"),
                    },
                ),
                raw=update,
            )
        ]

    # -- outbound --------------------------------------------------------
    async def send_message(
        self, chat_source_id: str, message: OutboundMessage
    ) -> SendResult:
        """Deliver an agent reply, splitting text and uploading media as needed."""
        attachments = list(message.attachments or [])
        if not attachments:
            return await self._send_text(chat_source_id, message)
        if len(attachments) == 1:
            return await self._send_single_media(chat_source_id, message, attachments[0])
        return await self._send_many_media(chat_source_id, message, attachments)

    def _text_options(self, message: OutboundMessage) -> dict[str, Any]:
        attributes = message.attributes or {}
        options: dict[str, Any] = {}
        if attributes.get("format") == "html":
            options["parse_mode"] = "HTML"
        if message.reply_to_source_id:
            try:
                options["reply_parameters"] = {
                    "message_id": int(str(message.reply_to_source_id))
                }
            except ValueError:
                logger.debug("non numeric reply target %s", message.reply_to_source_id)
        if attributes.get("disable_link_preview") or attributes.get("link_preview") is False:
            options["link_preview_options"] = {"is_disabled": True}
        if attributes.get("message_thread_id"):
            options["message_thread_id"] = attributes["message_thread_id"]
        return options

    async def _send_text(
        self, chat_source_id: str, message: OutboundMessage
    ) -> SendResult:
        chunks = chunk_text(message.content or "")
        if not chunks:
            raise ChannelError("Cannot send an empty Telegram message")

        options = self._text_options(message)
        results: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            payload = dict(options) if index == 0 else {
                k: v for k, v in options.items() if k != "reply_parameters"
            }
            results.append(
                await self.api.call(
                    "sendMessage", chat_id=chat_source_id, text=chunk, **payload
                )
            )
        return self._result(results)

    async def _send_single_media(
        self, chat_source_id: str, message: OutboundMessage, attachment: Any
    ) -> SendResult:
        method, field = _SEND_METHODS.get(
            attachment.file_type, ("sendDocument", "document")
        )
        options = self._text_options(message)
        options.pop("link_preview_options", None)

        caption = message.content or ""
        overflow = ""
        if attachment.file_type in _CAPTIONLESS:
            overflow, caption = caption, ""
        elif len(caption) > MAX_CAPTION_LENGTH:
            # Too long for a caption: send the media bare, then the text.
            overflow, caption = caption, ""

        params: dict[str, Any] = {"chat_id": chat_source_id, **options}
        if caption:
            params["caption"] = caption
        elif "parse_mode" in params:
            params.pop("parse_mode")

        files = None
        if attachment.data is not None:
            files = {
                field: (
                    attachment.file_name or "file",
                    attachment.data,
                    attachment.mime_type or storage.guess_mime(attachment.file_name),
                )
            }
        elif attachment.external_id:
            params[field] = attachment.external_id
        else:
            raise ChannelError("Attachment has neither bytes nor a Telegram file id")

        results = [await self.api.call(method, files=files, **params)]

        if overflow:
            follow_up = OutboundMessage(
                content=overflow, attributes=message.attributes or {}
            )
            for chunk in chunk_text(overflow):
                results.append(
                    await self.api.call(
                        "sendMessage",
                        chat_id=chat_source_id,
                        text=chunk,
                        **{
                            k: v
                            for k, v in self._text_options(follow_up).items()
                            if k != "reply_parameters"
                        },
                    )
                )
        return self._result(results)

    async def _send_many_media(
        self, chat_source_id: str, message: OutboundMessage, attachments: list[Any]
    ) -> SendResult:
        if all(a.file_type in _ALBUM_TYPES for a in attachments):
            return await self._send_album(chat_source_id, message, attachments)

        results: list[dict[str, Any]] = []
        for index, attachment in enumerate(attachments):
            part = OutboundMessage(
                content=message.content if index == 0 else None,
                attachments=[attachment],
                reply_to_source_id=message.reply_to_source_id if index == 0 else None,
                attributes=message.attributes or {},
            )
            sent = await self._send_single_media(chat_source_id, part, attachment)
            results.append({"message_id": sent.source_id})
            results.extend(
                {"message_id": mid}
                for mid in sent.attributes.get("extra_source_ids", [])
            )
        return self._result(results)

    async def _send_album(
        self, chat_source_id: str, message: OutboundMessage, attachments: list[Any]
    ) -> SendResult:
        media: list[dict[str, Any]] = []
        files: dict[str, tuple[str, bytes, str | None]] = {}
        caption = (message.content or "")[:MAX_CAPTION_LENGTH]

        for index, attachment in enumerate(attachments):
            entry: dict[str, Any] = {"type": _ALBUM_TYPES[attachment.file_type]}
            if attachment.data is not None:
                handle = f"file{index}"
                files[handle] = (
                    attachment.file_name or handle,
                    attachment.data,
                    attachment.mime_type or storage.guess_mime(attachment.file_name),
                )
                entry["media"] = f"attach://{handle}"
            elif attachment.external_id:
                entry["media"] = attachment.external_id
            else:
                raise ChannelError("Attachment has neither bytes nor a Telegram file id")
            if index == 0 and caption:
                entry["caption"] = caption
                if (message.attributes or {}).get("format") == "html":
                    entry["parse_mode"] = "HTML"
            media.append(entry)

        results = await self.api.call(
            "sendMediaGroup",
            files=files or None,
            chat_id=chat_source_id,
            media=media,
        )
        return self._result(list(results or []))

    @staticmethod
    def _result(results: list[dict[str, Any]]) -> SendResult:
        """Wrap Bot API ``Message`` results into a :class:`SendResult`."""
        ids = [str(r.get("message_id")) for r in results if r and r.get("message_id")]
        if not ids:
            raise ChannelError("Telegram did not return a message id")
        attributes: dict[str, Any] = {"telegram": {"message_ids": ids}}
        if len(ids) > 1:
            attributes["extra_source_ids"] = ids[1:]
        return SendResult(source_id=ids[0], attributes=attributes)

    async def send_reaction(
        self, chat_source_id: str, message_source_id: str, emojis: list[str]
    ) -> None:
        """Set the bot reaction on a message (Telegram allows a single emoji)."""
        reaction = []
        for emoji in emojis[:1]:
            if emoji not in SUPPORTED_REACTIONS:
                logger.info("emoji %s unsupported by Telegram, sending %s", emoji, FALLBACK_REACTION)
                emoji = FALLBACK_REACTION
            reaction.append({"type": "emoji", "emoji": emoji})
        await self.api.call(
            "setMessageReaction",
            chat_id=chat_source_id,
            message_id=int(message_source_id),
            reaction=reaction,
            is_big=False,
        )

    async def send_typing(self, chat_source_id: str) -> None:
        await self.api.call("sendChatAction", chat_id=chat_source_id, action="typing")

    async def edit_message(
        self, chat_source_id: str, message_source_id: str, content: str
    ) -> None:
        await self.api.call(
            "editMessageText",
            chat_id=chat_source_id,
            message_id=int(message_source_id),
            text=content[:MAX_TEXT_LENGTH],
        )

    async def delete_message(self, chat_source_id: str, message_source_id: str) -> None:
        await self.api.call(
            "deleteMessage",
            chat_id=chat_source_id,
            message_id=int(message_source_id),
        )

    # -- media -----------------------------------------------------------
    async def download_file(self, external_id: str) -> tuple[bytes, str | None, str | None]:
        """Resolve a ``file_id`` and download its bytes."""
        if not self.download_media:
            raise ChannelError("Media download is disabled for this inbox")

        info = await self.api.get_file(external_id)
        size = info.get("file_size") or 0
        if size and size > MAX_DOWNLOAD_BYTES:
            raise ChannelError(
                f"File is too large for the Bot API ({size} bytes, max {MAX_DOWNLOAD_BYTES})"
            )
        file_path = info.get("file_path")
        if not file_path:
            raise ChannelError("Telegram returned no file path")

        data = await self.api.download(file_path)
        file_name = file_path.rsplit("/", 1)[-1]
        return data, file_name, storage.guess_mime(file_name)
