# Chatwoot compatibility

ChattySup can present the same data in Chatwoot's shapes, so tooling written
against Chatwoot works unmodified. The compatibility layer is **additive**: the
native API and the native webhook format are unchanged.

Everything below was reproduced from the Chatwoot source
(`chatwoot/chatwoot@develop`) rather than from prose docs — the jbuilder views,
`app/listeners/webhook_listener.rb`, `app/models/*.rb` and `lib/webhooks/trigger.rb`.

## Outgoing webhooks

Set a webhook's `payload_format` to `chatwoot` (Settings → Webhooks, or
`POST /api/v1/webhooks`) and it is delivered exactly as Chatwoot delivers it.

```json
{
  "url": "https://example.com/hook",
  "payload_format": "chatwoot",
  "secret": "…",
  "subscriptions": ["message_created", "conversation_status_changed"]
}
```

`GET /api/v1/webhooks/events?payload_format=chatwoot` lists the twelve events:
`conversation_created`, `conversation_updated`, `conversation_status_changed`,
`message_created`, `message_updated`, `contact_created`, `contact_updated`,
`inbox_created`, `inbox_updated`, `webwidget_triggered`,
`conversation_typing_on`, `conversation_typing_off`.

Things that surprise people, all reproduced faithfully:

* **There is no envelope.** The body *is* the resource hash with `event` merged
  in as one more sibling key. Only the two typing events have their own nested
  `{event, user, conversation, is_private}` shape.
* **`message_type` is a string at the top level** (`"incoming"`) but an
  **integer** inside `conversation.messages[]` (`0`) — webhooks use
  `webhook_data`, the nested array uses `push_event_data`.
* **`created_at` is ISO-8601 at the top level** and **epoch seconds** in the
  nested message — same reason.
* `attachments` is **omitted** when there are none, never `[]` or `null`.
* `changed_attributes` is an array of single-key objects
  (`[{"status": {"previous_value": "open", "current_value": "resolved"}}]`),
  and `contact_updated` / `inbox_updated` are **not delivered at all** when the
  diff is empty.
* The signature covers `"{timestamp}.{body}"` — not the body alone:

```python
expected = "sha256=" + hmac.new(
    secret.encode(), f"{headers['X-Chatwoot-Timestamp']}.".encode() + raw_body,
    hashlib.sha256,
).hexdigest()
assert hmac.compare_digest(expected, headers["X-Chatwoot-Signature"])
```

Chatwoot sends one attempt with a 5s timeout and does not retry; so do we for
this format. Native-format hooks keep their three attempts and
`X-ChattySup-Signature`.

## The API channel

An inbox whose source is any HTTP client. Settings → Inboxes → **Add inbox** →
API, or `POST /api/v1/accounts/{account_id}/inboxes`.

* **Outbound** — every agent reply is POSTed to the inbox's `webhook_url` as a
  `message_created` body, signed with the inbox `hmac_token`.
* **Inbound** — clients use Chatwoot's Client API, mounted at the same paths:

```
POST   /public/api/v1/inboxes/{inbox_identifier}/contacts
GET    /public/api/v1/inboxes/{inbox_identifier}/contacts/{contact_identifier}
PATCH  /public/api/v1/inboxes/{inbox_identifier}/contacts/{contact_identifier}
POST   /public/api/v1/inboxes/{inbox_identifier}/contacts/{contact_identifier}/conversations
GET    …/conversations
POST   …/conversations/{conversation_id}/messages
GET    …/conversations/{conversation_id}/messages
POST   …/conversations/{conversation_id}/toggle_status
POST   …/conversations/{conversation_id}/toggle_typing
POST   …/conversations/{conversation_id}/update_last_seen
```

The `inbox_identifier` is stable: it survives editing the inbox, including a
mode change, so client URLs never rotate.

Inbound messages go through the normal pipeline, so conversations, automations,
realtime updates and native webhooks all behave as if the message had arrived
over Telegram.

## Application API

A subset of `/api/v1/accounts/{account_id}/…`, authenticated with the
`api_access_token` header (our own `Authorization: Bearer` also works):

```
GET|POST   /conversations            GET /conversations/{id}
POST       /conversations/{id}/toggle_status
POST       /conversations/{id}/assignments
GET|POST   /conversations/{id}/messages
PATCH      /conversations/{id}/messages/{message_id}   (API inboxes only)
GET|POST   /contacts                 GET /contacts/search
GET|PATCH  /contacts/{id}
GET|POST   /inboxes                  POST /inboxes/{id}/reset_secret
GET|POST|PATCH|DELETE /webhooks
```

REST responses use Chatwoot's REST encoding — integer `message_type`, epoch
`created_at` — which is deliberately *different* from the webhook encoding.

The native `/api/v1/…` routes are untouched; `/api/v1/accounts/…` does not
shadow them.

## Known gaps

* Attachments in the Client API are accepted as URLs, not multipart uploads.
* `webwidget_triggered` is implemented but never fired — there is no web widget.
* Conversation `display_id` equals our conversation id (single account).
* Four cosmetic divergences remain in attachment serialization for
  external-URL-only attachments and for location/contact cards.
