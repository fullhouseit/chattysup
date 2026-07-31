"""Single message operations and authenticated attachment downloads."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from ...channels.base import ChannelError, build_channel
from ...core import events as bus
from ...core import storage
from ...core.deps import CurrentUser, DbSession, get_current_user
from ...db import utcnow
from ...models import Attachment, Conversation, Inbox, Message
from ...schemas import MessageUpdate, ReactionRequest
from ...serializers import serialize_message
from ...services import conversations as conv_service

router = APIRouter(
    prefix="/messages", tags=["messages"], dependencies=[Depends(get_current_user)]
)
attachments_router = APIRouter(
    prefix="/attachments", tags=["attachments"], dependencies=[Depends(get_current_user)]
)


async def _get_message(db: DbSession, message_id: int) -> Message:
    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


@router.patch("/{message_id}")
async def update_message(
    message_id: int, payload: MessageUpdate, db: DbSession
) -> dict:
    """Edit an outgoing message locally and upstream when the channel allows it."""
    message = await _get_message(db, message_id)
    conversation = await db.get(Conversation, message.conversation_id)
    message.content = payload.content
    message.edited_at = utcnow()
    await db.flush()

    inbox = await db.get(Inbox, message.inbox_id)
    if inbox and message.source_id and not message.private and conversation:
        channel = build_channel(inbox)
        try:
            await channel.edit_message(
                conversation.source_id or "", message.source_id, payload.content
            )
        except (NotImplementedError, ChannelError):
            pass  # local edit still stands
        finally:
            await channel.close()

    await db.refresh(message)
    await bus.publish(
        bus.EVENT_MESSAGE_UPDATED,
        {"message": serialize_message(message), "conversation_id": message.conversation_id},
    )
    return serialize_message(message)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(message_id: int, db: DbSession) -> None:
    """Soft-delete a message and try to retract it upstream."""
    message = await _get_message(db, message_id)
    conversation = await db.get(Conversation, message.conversation_id)
    inbox = await db.get(Inbox, message.inbox_id)
    if inbox and message.source_id and not message.private and conversation:
        channel = build_channel(inbox)
        try:
            await channel.delete_message(conversation.source_id or "", message.source_id)
        except (NotImplementedError, ChannelError):
            pass
        finally:
            await channel.close()

    message.deleted_at = utcnow()
    await db.flush()
    await bus.publish(
        bus.EVENT_MESSAGE_DELETED,
        {"message_id": message.id, "conversation_id": message.conversation_id},
    )


@router.post("/{message_id}/reactions")
async def toggle_reaction(
    message_id: int, payload: ReactionRequest, db: DbSession, user: CurrentUser
) -> dict:
    message = await _get_message(db, message_id)
    await conv_service.toggle_reaction(db, message, user, payload.emoji)
    return serialize_message(message)


@router.post("/{message_id}/retry")
async def retry(message_id: int, db: DbSession) -> dict:
    message = await _get_message(db, message_id)
    await conv_service.retry_message(db, message)
    return serialize_message(message)


@attachments_router.get("/{attachment_id}/file")
async def download_attachment(
    attachment_id: int,
    db: DbSession,
    variant: str | None = Query(default=None),
) -> FileResponse:
    """Stream a stored attachment (or its thumbnail) to an authenticated agent."""
    attachment = await db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    key = attachment.thumb_key if variant == "thumb" else attachment.storage_key
    key = key or attachment.storage_key
    if not key:
        raise HTTPException(status_code=404, detail="Attachment has no stored file")

    path = storage.path_for(key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file is missing")

    return FileResponse(
        path,
        media_type=attachment.mime_type or storage.guess_mime(attachment.file_name),
        filename=attachment.file_name or path.name,
    )
