"""Automation engine: auto-greetings and condition/action rules.

A rule is ``event_name`` + a list of ``conditions`` + a list of ``actions``.
Conditions are ``{attribute, operator, values}``; actions are ``{action, params}``.
The catalogue below is exposed over the API so the UI can build the form
without hard-coding anything.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import utcnow
from ..models import (
    Automation,
    AutomationRun,
    Conversation,
    ConversationLabel,
    Inbox,
    Label,
    Message,
    MessageType,
    SenderType,
    Team,
    TeamMember,
    User,
)

logger = logging.getLogger(__name__)

OPERATORS = [
    {"key": "equal_to", "label": "is"},
    {"key": "not_equal_to", "label": "is not"},
    {"key": "contains", "label": "contains"},
    {"key": "does_not_contain", "label": "does not contain"},
    {"key": "starts_with", "label": "starts with"},
    {"key": "matches_regex", "label": "matches regex"},
    {"key": "is_present", "label": "is present"},
    {"key": "is_not_present", "label": "is empty"},
    {"key": "is_greater_than", "label": "is greater than"},
    {"key": "is_less_than", "label": "is less than"},
]

ATTRIBUTES = [
    {"key": "message_content", "label": "Message content", "type": "text"},
    {"key": "message_type", "label": "Message type", "type": "select",
     "options": ["incoming", "outgoing"]},
    {"key": "inbox_id", "label": "Inbox", "type": "inbox"},
    {"key": "status", "label": "Conversation status", "type": "select",
     "options": ["open", "pending", "snoozed", "resolved"]},
    {"key": "priority", "label": "Priority", "type": "select",
     "options": ["none", "low", "medium", "high", "urgent"]},
    {"key": "assignee_id", "label": "Assignee", "type": "agent"},
    {"key": "team_id", "label": "Team", "type": "team"},
    {"key": "label", "label": "Label", "type": "label"},
    {"key": "contact_name", "label": "Contact name", "type": "text"},
    {"key": "contact_email", "label": "Contact email", "type": "text"},
    {"key": "is_first_message", "label": "Is first message", "type": "boolean"},
    {"key": "business_hours", "label": "Within business hours", "type": "boolean"},
]

ACTIONS = [
    {"key": "send_message", "label": "Send a reply", "params": ["content"]},
    {"key": "send_private_note", "label": "Add a private note", "params": ["content"]},
    {"key": "assign_agent", "label": "Assign to agent", "params": ["user_id"]},
    {"key": "assign_team", "label": "Assign to team", "params": ["team_id"]},
    {"key": "add_label", "label": "Add label", "params": ["label"]},
    {"key": "remove_label", "label": "Remove label", "params": ["label"]},
    {"key": "set_priority", "label": "Set priority", "params": ["priority"]},
    {"key": "set_status", "label": "Change status", "params": ["status"]},
    {"key": "mute_conversation", "label": "Mute conversation", "params": []},
    {"key": "snooze_conversation", "label": "Snooze for N minutes", "params": ["minutes"]},
]


def catalogue() -> dict[str, Any]:
    return {
        "events": [
            "conversation_created",
            "conversation_updated",
            "message_created",
            "conversation_resolved",
        ],
        "attributes": ATTRIBUTES,
        "operators": OPERATORS,
        "actions": ACTIONS,
    }


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------
def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def _match(operator: str, actual: Any, expected: list[Any]) -> bool:
    first = expected[0] if expected else None
    actual_text = _as_text(actual).lower()
    expected_texts = [_as_text(v).lower() for v in expected]

    match operator:
        case "is_present":
            return actual not in (None, "", [], {})
        case "is_not_present":
            return actual in (None, "", [], {})
        case "equal_to":
            if isinstance(actual, list):
                return any(_as_text(a).lower() in expected_texts for a in actual)
            return actual_text in expected_texts
        case "not_equal_to":
            if isinstance(actual, list):
                return not any(_as_text(a).lower() in expected_texts for a in actual)
            return actual_text not in expected_texts
        case "contains":
            return any(t and t in actual_text for t in expected_texts)
        case "does_not_contain":
            return not any(t and t in actual_text for t in expected_texts)
        case "starts_with":
            return any(t and actual_text.startswith(t) for t in expected_texts)
        case "matches_regex":
            try:
                return bool(re.search(_as_text(first), _as_text(actual), re.I))
            except re.error:
                return False
        case "is_greater_than":
            try:
                return float(actual) > float(first)
            except (TypeError, ValueError):
                return False
        case "is_less_than":
            try:
                return float(actual) < float(first)
            except (TypeError, ValueError):
                return False
    return False


def _within_business_hours(inbox: Inbox | None) -> bool:
    hours = (inbox.working_hours if inbox else None) or {}
    if not hours.get("enabled"):
        return True
    now = datetime.now(timezone.utc)
    day = hours.get("days", {}).get(str(now.weekday()))
    if not day or not day.get("enabled"):
        return False
    start = day.get("start", "00:00")
    end = day.get("end", "23:59")
    current = now.strftime("%H:%M")
    return start <= current <= end


async def _build_context(
    db: AsyncSession,
    conversation: Conversation,
    message: Message | None,
) -> dict[str, Any]:
    inbox = conversation.inbox or await db.get(Inbox, conversation.inbox_id)
    contact = conversation.contact
    label_titles = [link.label.title for link in conversation.labels if link.label]
    incoming_count = await db.scalar(
        select(Message.id)
        .where(
            Message.conversation_id == conversation.id,
            Message.message_type == MessageType.INCOMING.value,
        )
        .limit(2)
        .offset(1)
    )
    return {
        "message_content": message.content if message else None,
        "message_type": message.message_type if message else None,
        "inbox_id": conversation.inbox_id,
        "status": conversation.status,
        "priority": conversation.priority,
        "assignee_id": conversation.assignee_id,
        "team_id": conversation.team_id,
        "label": label_titles,
        "contact_name": contact.name if contact else None,
        "contact_email": contact.email if contact else None,
        "is_first_message": incoming_count is None,
        "business_hours": _within_business_hours(inbox),
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
async def run_automations(
    db: AsyncSession,
    event_name: str,
    *,
    conversation: Conversation,
    message: Message | None = None,
) -> None:
    """Evaluate every active rule for ``event_name`` and apply matching actions."""
    try:
        if event_name == "conversation_created" or (
            event_name == "message_created" and not conversation.greeting_sent
        ):
            await _maybe_greet(db, conversation)

        rules = (
            await db.scalars(
                select(Automation).where(
                    Automation.event_name == event_name, Automation.active.is_(True)
                )
            )
        ).all()
        if not rules:
            return

        context = await _build_context(db, conversation, message)
        for rule in rules:
            if rule.inbox_id and rule.inbox_id != conversation.inbox_id:
                continue
            if not _rule_matches(rule, context):
                continue
            if rule.run_once_per_conversation and await _already_ran(db, rule, conversation):
                continue
            await _apply_actions(db, rule, conversation)
            db.add(
                AutomationRun(
                    automation_id=rule.id,
                    conversation_id=conversation.id,
                    created_at=utcnow(),
                )
            )
            rule.execution_count += 1
            rule.last_executed_at = utcnow()
            await db.flush()
    except Exception:  # pragma: no cover - never let a rule break message intake
        logger.exception("automation run failed for event %s", event_name)


def _rule_matches(rule: Automation, context: dict[str, Any]) -> bool:
    conditions = rule.conditions or []
    if not conditions:
        return True
    results = [
        _match(
            cond.get("operator", "equal_to"),
            context.get(cond.get("attribute", "")),
            cond.get("values", []),
        )
        for cond in conditions
    ]
    return all(results) if (rule.condition_logic or "and") == "and" else any(results)


async def _already_ran(
    db: AsyncSession, rule: Automation, conversation: Conversation
) -> bool:
    return (
        await db.scalar(
            select(AutomationRun.id).where(
                AutomationRun.automation_id == rule.id,
                AutomationRun.conversation_id == conversation.id,
            )
        )
    ) is not None


async def _apply_actions(
    db: AsyncSession, rule: Automation, conversation: Conversation
) -> None:
    from . import conversations as conv_service

    for action in rule.actions or []:
        kind = action.get("action")
        params = action.get("params") or {}
        try:
            match kind:
                case "send_message":
                    await conv_service.create_outgoing_message(
                        db,
                        conversation,
                        content=_render(params.get("content", ""), conversation),
                        sender_type=SenderType.BOT.value,
                        content_attributes={"automation_id": rule.id},
                    )
                case "send_private_note":
                    await conv_service.create_outgoing_message(
                        db,
                        conversation,
                        content=_render(params.get("content", ""), conversation),
                        private=True,
                        sender_type=SenderType.BOT.value,
                        content_attributes={"automation_id": rule.id},
                    )
                case "assign_agent":
                    user = await db.get(User, int(params["user_id"]))
                    await conv_service.assign(db, conversation, user)
                case "assign_team":
                    team = await db.get(Team, int(params["team_id"]))
                    if team:
                        conversation.team_id = team.id
                        if team.allow_auto_assign:
                            member = await db.scalar(
                                select(TeamMember).where(TeamMember.team_id == team.id)
                            )
                            if member:
                                user = await db.get(User, member.user_id)
                                await conv_service.assign(db, conversation, user)
                        await db.flush()
                case "add_label":
                    await _add_label(db, conversation, params.get("label", ""))
                case "remove_label":
                    await _remove_label(db, conversation, params.get("label", ""))
                case "set_priority":
                    conversation.priority = params.get("priority", "none")
                    await db.flush()
                case "set_status":
                    await conv_service.set_status(
                        db, conversation, params.get("status", "open")
                    )
                case "mute_conversation":
                    conversation.muted = True
                    await db.flush()
                case "snooze_conversation":
                    await conv_service.set_status(
                        db,
                        conversation,
                        "snoozed",
                        snoozed_until=utcnow()
                        + timedelta(minutes=int(params.get("minutes", 60))),
                    )
                case _:
                    logger.warning("unknown automation action %s", kind)
        except Exception:
            logger.exception("automation action %s failed (rule %s)", kind, rule.id)


def _render(template: str, conversation: Conversation) -> str:
    contact = conversation.contact
    values = {
        "contact.name": contact.name if contact else "",
        "contact.first_name": (contact.name.split(" ")[0] if contact and contact.name else ""),
        "contact.email": (contact.email or "") if contact else "",
        "conversation.id": str(conversation.id),
        "inbox.name": conversation.inbox.name if conversation.inbox else "",
    }
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


async def _add_label(db: AsyncSession, conversation: Conversation, title: str) -> None:
    title = (title or "").strip()
    if not title:
        return
    label = await db.scalar(select(Label).where(Label.title == title))
    if not label:
        label = Label(title=title)
        db.add(label)
        await db.flush()
    exists = await db.scalar(
        select(ConversationLabel).where(
            ConversationLabel.conversation_id == conversation.id,
            ConversationLabel.label_id == label.id,
        )
    )
    if not exists:
        db.add(ConversationLabel(conversation_id=conversation.id, label_id=label.id))
        await db.flush()
        await db.refresh(conversation)


async def _remove_label(db: AsyncSession, conversation: Conversation, title: str) -> None:
    label = await db.scalar(select(Label).where(Label.title == (title or "").strip()))
    if not label:
        return
    link = await db.scalar(
        select(ConversationLabel).where(
            ConversationLabel.conversation_id == conversation.id,
            ConversationLabel.label_id == label.id,
        )
    )
    if link:
        await db.delete(link)
        await db.flush()
        await db.refresh(conversation)


# ---------------------------------------------------------------------------
# Greeting
# ---------------------------------------------------------------------------
async def _maybe_greet(db: AsyncSession, conversation: Conversation) -> None:
    from . import conversations as conv_service

    inbox = conversation.inbox or await db.get(Inbox, conversation.inbox_id)
    if not inbox or not inbox.greeting_enabled or conversation.greeting_sent:
        return
    body = inbox.greeting_message
    if not _within_business_hours(inbox) and inbox.out_of_office_message:
        body = inbox.out_of_office_message
    if not body:
        return
    conversation.greeting_sent = True
    await db.flush()
    await conv_service.create_outgoing_message(
        db,
        conversation,
        content=_render(body, conversation),
        sender_type=SenderType.BOT.value,
        content_attributes={"greeting": True},
    )
