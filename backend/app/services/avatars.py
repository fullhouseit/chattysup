"""Mirroring contact profile pictures from a channel into local storage.

Most providers (Telegram among them) expose avatars only through an
authenticated file API, so the picture has to be downloaded once and served
from here. It is stored as a message-less :class:`~app.models.message.Attachment`,
which reuses the existing authenticated ``/attachments/{id}/file`` route.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.base import BaseChannel, NormalizedContact
from ..core import storage
from ..db import utcnow
from ..models import Attachment, AttachmentType, Contact, ContactInbox, Inbox

logger = logging.getLogger(__name__)

#: Don't ask the provider again for a while — plenty of contacts simply have no
#: photo, or hide it, and a lookup per inbound message would be wasteful.
RECHECK_AFTER = timedelta(days=7)
#: Guard against a provider handing back something absurd for an avatar.
MAX_AVATAR_BYTES = 5 * 1024 * 1024

_CHECKED_AT = "avatar_checked_at"


def _due(link: ContactInbox) -> bool:
    stamp = (link.meta or {}).get(_CHECKED_AT)
    if not stamp:
        return True
    try:
        from datetime import datetime

        return datetime.fromisoformat(stamp) + RECHECK_AFTER < utcnow()
    except ValueError:
        return True


def _mark_checked(link: ContactInbox) -> None:
    link.meta = {**(link.meta or {}), _CHECKED_AT: utcnow().isoformat()}


async def ensure_contact_avatar(
    db: AsyncSession,
    inbox: Inbox,
    channel: BaseChannel | None,
    contact: Contact,
    link: ContactInbox,
    payload: NormalizedContact,
) -> bool:
    """Fetch and store the contact's avatar when one is missing.

    Returns ``True`` when a new picture was stored. Never raises: a missing
    avatar must not interfere with receiving the message it came with.
    """
    if channel is None or "avatars" not in channel.capabilities:
        return False
    if contact.avatar_url or not _due(link):
        return False

    _mark_checked(link)
    try:
        result = await channel.fetch_avatar(payload)
    except NotImplementedError:
        return False
    except Exception as exc:
        logger.info("avatar lookup failed for contact %s: %s", contact.id, exc)
        return False

    if not result:
        return False
    data, file_name, mime_type = result
    if not data or len(data) > MAX_AVATAR_BYTES:
        return False

    key = storage.build_key(inbox.id, file_name or f"avatar-{contact.id}.jpg")
    storage.save_bytes(key, data)

    attachment = Attachment(
        file_type=AttachmentType.IMAGE.value,
        file_name=file_name or f"avatar-{contact.id}.jpg",
        mime_type=mime_type or "image/jpeg",
        file_size=len(data),
        storage_key=key,
        meta={"kind": "avatar", "contact_id": contact.id},
    )
    db.add(attachment)
    await db.flush()

    contact.avatar_url = storage.url_for(attachment.id)
    await db.flush()
    logger.info("stored avatar for contact %s (%d bytes)", contact.id, len(data))
    return True
