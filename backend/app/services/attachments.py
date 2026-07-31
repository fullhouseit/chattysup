"""Persisting inbound/outbound media."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.base import (
    BaseChannel,
    NormalizedAttachment,
    OutboundAttachment,
)
from ..core import storage
from ..models import Attachment, AttachmentType, Inbox

logger = logging.getLogger(__name__)

_EXTENSION_BY_TYPE = {
    AttachmentType.IMAGE.value: ".jpg",
    AttachmentType.VOICE.value: ".ogg",
    AttachmentType.AUDIO.value: ".mp3",
    AttachmentType.VIDEO.value: ".mp4",
    AttachmentType.VIDEO_NOTE.value: ".mp4",
    AttachmentType.ANIMATION.value: ".mp4",
    AttachmentType.STICKER.value: ".webp",
}


async def persist_inbound_attachment(
    db: AsyncSession,
    inbox: Inbox,
    channel: BaseChannel,
    norm: NormalizedAttachment,
) -> Attachment:
    """Store a normalised attachment, downloading it from the provider if needed."""
    data = norm.data
    file_name = norm.file_name
    mime_type = norm.mime_type

    if data is None and norm.external_id:
        try:
            data, remote_name, remote_mime = await channel.download_file(norm.external_id)
            file_name = file_name or remote_name
            mime_type = mime_type or remote_mime
        except Exception as exc:  # keep the message even if the media failed
            logger.warning("attachment download failed (%s): %s", norm.external_id, exc)
            data = None

    if not file_name:
        file_name = f"{norm.file_type}{_EXTENSION_BY_TYPE.get(norm.file_type, '')}"

    attachment = Attachment(
        file_type=norm.file_type,
        file_name=file_name,
        mime_type=mime_type or storage.guess_mime(file_name),
        file_size=norm.file_size,
        external_id=norm.external_id,
        external_url=norm.external_url,
        meta=norm.meta or {},
    )

    if data:
        key = storage.build_key(inbox.id, file_name)
        storage.save_bytes(key, data)
        attachment.storage_key = key
        attachment.file_size = len(data)

    if norm.thumb_external_id:
        try:
            thumb, thumb_name, _ = await channel.download_file(norm.thumb_external_id)
            thumb_key = storage.build_key(inbox.id, f"thumb-{thumb_name or 'preview.jpg'}")
            storage.save_bytes(thumb_key, thumb)
            attachment.thumb_key = thumb_key
        except Exception:  # pragma: no cover - thumbnails are best effort
            logger.debug("thumbnail download failed for %s", norm.thumb_external_id)

    db.add(attachment)
    return attachment


def to_outbound(attachment: Attachment) -> OutboundAttachment:
    """Convert a stored attachment into something a channel can send."""
    data = None
    if attachment.storage_key:
        path = storage.path_for(attachment.storage_key)
        if path.is_file():
            data = path.read_bytes()
    return OutboundAttachment(
        file_type=attachment.file_type,
        file_name=attachment.file_name or "file",
        mime_type=attachment.mime_type,
        data=data,
        external_id=attachment.external_id,
        meta=attachment.meta or {},
    )
