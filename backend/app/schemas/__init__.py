"""Pydantic request models used by the REST API.

Responses are plain dicts produced by :mod:`app.serializers`; only the *input*
side is modelled here so the wire format stays defined in a single place.
"""
from .api_tokens import ApiTokenCreate
from .auth import LoginRequest, ProfileUpdate, RegisterRequest
from .automations import AutomationCreate, AutomationUpdate
from .canned_responses import CannedResponseCreate, CannedResponseUpdate
from .common import IdList, Schema, clamp_page, page_meta
from .contacts import (
    BlockRequest,
    ContactCreate,
    ContactNoteCreate,
    ContactUpdate,
)
from .conversations import ConversationUpdate, LabelAssignment, ParticipantCreate
from .inboxes import InboxCreate, InboxUpdate
from .notifications import NotificationPreferences
from .labels import LabelCreate, LabelUpdate
from .messages import MessageUpdate, ReactionRequest
from .settings import SettingsUpdate
from .sso import SsoProviderCreate, SsoProviderUpdate
from .teams import TeamCreate, TeamUpdate
from .users import UserCreate, UserUpdate
from .webhooks import WebhookCreate, WebhookUpdate

__all__ = [
    "NotificationPreferences",
    "ApiTokenCreate",
    "AutomationCreate",
    "AutomationUpdate",
    "BlockRequest",
    "CannedResponseCreate",
    "CannedResponseUpdate",
    "ContactCreate",
    "ContactNoteCreate",
    "ContactUpdate",
    "ConversationUpdate",
    "IdList",
    "InboxCreate",
    "InboxUpdate",
    "LabelAssignment",
    "LabelCreate",
    "LabelUpdate",
    "LoginRequest",
    "MessageUpdate",
    "ParticipantCreate",
    "ProfileUpdate",
    "ReactionRequest",
    "RegisterRequest",
    "Schema",
    "SettingsUpdate",
    "SsoProviderCreate",
    "SsoProviderUpdate",
    "TeamCreate",
    "TeamUpdate",
    "UserCreate",
    "UserUpdate",
    "WebhookCreate",
    "WebhookUpdate",
    "clamp_page",
    "page_meta",
]
