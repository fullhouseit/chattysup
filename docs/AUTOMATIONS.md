# Automations, greetings and webhooks

## Auto-greeting

Per inbox (Settings → Inboxes → *inbox* → Behaviour):

* **Greeting enabled** — sends `greeting_message` on the first inbound message
  of a conversation, once (`Conversation.greeting_sent` guards it).
* **Out of office message** — replaces the greeting when the current time falls
  outside the inbox working hours.
* **Working hours** — stored as JSON:

```json
{
  "enabled": true,
  "days": {
    "0": {"enabled": true, "start": "09:00", "end": "18:00"},
    "5": {"enabled": false},
    "6": {"enabled": false}
  }
}
```

Keys are `datetime.weekday()` values (`0` = Monday), times are UTC `HH:MM`.

## Rules

A rule is `event` + `conditions` + `actions`, evaluated in
`backend/app/services/automation.py`. `GET /api/v1/automations/catalogue`
returns the full vocabulary the UI builds its form from.

**Events** — `conversation_created`, `message_created`, `conversation_updated`,
`conversation_resolved`.

**Condition attributes** — `message_content`, `message_type`, `inbox_id`,
`status`, `priority`, `assignee_id`, `team_id`, `label`, `contact_name`,
`contact_email`, `is_first_message`, `business_hours`.

**Operators** — `equal_to`, `not_equal_to`, `contains`, `does_not_contain`,
`starts_with`, `matches_regex`, `is_present`, `is_not_present`,
`is_greater_than`, `is_less_than`.

**Actions** — `send_message`, `send_private_note`, `assign_agent`,
`assign_team`, `add_label`, `remove_label`, `set_priority`, `set_status`,
`mute_conversation`, `snooze_conversation`.

Conditions are joined by `condition_logic` (`and` / `or`). Enable
*run once per conversation* to make a rule fire at most once per thread.

Message bodies support placeholders: `{{contact.name}}`,
`{{contact.first_name}}`, `{{contact.email}}`, `{{conversation.id}}`,
`{{inbox.name}}`.

### Example — triage refund requests

```json
{
  "name": "Refund requests to billing",
  "event_name": "message_created",
  "condition_logic": "and",
  "conditions": [
    {"attribute": "message_content", "operator": "contains", "values": ["refund", "возврат"]},
    {"attribute": "message_type", "operator": "equal_to", "values": ["incoming"]}
  ],
  "actions": [
    {"action": "add_label", "params": {"label": "billing"}},
    {"action": "set_priority", "params": {"priority": "high"}},
    {"action": "assign_team", "params": {"team_id": 2}},
    {"action": "send_message", "params": {"content": "Hi {{contact.first_name}}, our billing team is on it."}}
  ],
  "run_once_per_conversation": true,
  "active": true
}
```

## Outgoing webhooks

Configure under Settings → Webhooks. Every subscribed event is POSTed as:

```json
{
  "event": "message.created",
  "timestamp": "2026-07-31T10:00:00+00:00",
  "data": { "message": { ... }, "conversation_id": 42 }
}
```

Available events: `conversation.created`, `conversation.updated`,
`message.created`, `message.updated`, `message.deleted`, `contact.updated`,
`inbox.updated`, `presence.updated`.

When a secret is set, the raw body is signed with HMAC-SHA256 and sent as
`X-ChattySup-Signature`. Verify it like this:

```python
import hmac, hashlib
expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
assert hmac.compare_digest(expected, request.headers["X-ChattySup-Signature"])
```

Delivery retries three times with exponential backoff; the last status and error
are shown in the UI.

## Public API

Create a token under Settings → API tokens and call any endpoint with
`Authorization: Bearer cs_…`. The token inherits the role of the user that
created it. Interactive documentation lives at `/api/docs`.
