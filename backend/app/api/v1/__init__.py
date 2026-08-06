"""Version 1 of the REST API — aggregates every feature router."""
from __future__ import annotations

from fastapi import APIRouter

from ... import __version__
from ...channels.base import available_channels
from . import (
    admin,
    api_tokens,
    auth,
    automations,
    canned_responses,
    contacts,
    conversations,
    inboxes,
    labels,
    messages,
    notifications,
    settings,
    sso,
    teams,
    users,
    webhooks,
    ws,
)

api_router = APIRouter()


@api_router.get("/health", tags=["health"])
async def health() -> dict:
    """Liveness probe; also reports which channels are registered."""
    return {
        "status": "ok",
        "version": __version__,
        "channels": [c["key"] for c in available_channels()],
    }


api_router.include_router(auth.router)
api_router.include_router(sso.router)
api_router.include_router(sso.admin_router)
api_router.include_router(users.router)
api_router.include_router(teams.router)
api_router.include_router(inboxes.channels_router)
api_router.include_router(inboxes.router)
api_router.include_router(conversations.router)
api_router.include_router(messages.router)
api_router.include_router(messages.attachments_router)
api_router.include_router(notifications.router)
api_router.include_router(contacts.router)
api_router.include_router(labels.router)
api_router.include_router(canned_responses.router)
api_router.include_router(automations.router)
api_router.include_router(webhooks.router)
api_router.include_router(webhooks.inbound_router)
api_router.include_router(api_tokens.router)
api_router.include_router(settings.router)
api_router.include_router(admin.router)
api_router.include_router(ws.router)

__all__ = ["api_router"]
