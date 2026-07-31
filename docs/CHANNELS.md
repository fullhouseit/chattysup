# Adding a new source (channel)

ChattySup keeps every provider integration behind one small interface, so a new
source never touches the conversation logic, the API or the UI.

## The contract

Everything lives in `backend/app/channels/base.py`:

| Piece | Purpose |
| --- | --- |
| `BaseChannel` | The interface each provider implements |
| `FieldSpec` | Declares one configuration input — the admin UI renders the form from these |
| `NormalizedContact` / `NormalizedMessage` / `NormalizedAttachment` | Provider payload → core payload |
| `InboundEvent` | One normalised thing that happened upstream (`message`, `message_edited`, `message_deleted`, `reaction`, `read`, `typing`) |
| `OutboundMessage` / `OutboundAttachment` / `SendResult` | What the core hands to the provider and gets back |
| `register()` | Adds the class to the registry |

## Minimal example

```python
# backend/app/channels/acme/channel.py
from __future__ import annotations

from ..base import (
    BaseChannel, FieldSpec, InboundEvent, NormalizedContact, NormalizedMessage,
    OutboundMessage, SendResult, register,
)


@register
class AcmeChannel(BaseChannel):
    key = "acme"
    display_name = "Acme Chat"
    description = "Acme customer messaging"
    icon = "message-square"
    color = "#7C3AED"

    supports_polling = True
    supports_webhook = True
    supports_proxy = True
    capabilities = {"media", "reply", "typing"}

    config_fields = [
        FieldSpec("api_key", "API key", kind="password", required=True, secret=True),
        FieldSpec("workspace", "Workspace", required=True),
    ]

    @classmethod
    async def validate_config(cls, config):
        config = await super().validate_config(config)
        # ping the provider here; raise ChannelConfigError when it fails
        return config

    async def fetch_updates(self, cursor):
        payload = await self._get("/updates", since=cursor)
        events = [self._to_event(item) for item in payload["items"]]
        return events, payload.get("cursor")

    async def parse_webhook(self, payload, headers):
        return [self._to_event(payload)]

    async def send_message(self, chat_source_id, message: OutboundMessage) -> SendResult:
        result = await self._post("/messages", chat=chat_source_id, text=message.content)
        return SendResult(source_id=str(result["id"]))

    def _to_event(self, item) -> InboundEvent:
        return InboundEvent(
            kind="message",
            chat_source_id=str(item["chat_id"]),
            contact=NormalizedContact(source_id=str(item["chat_id"]), name=item["user"]["name"]),
            message=NormalizedMessage(source_id=str(item["id"]), content=item["text"]),
        )
```

Then import it once so the decorator runs:

```python
# backend/app/channels/__init__.py
from .acme import AcmeChannel  # noqa: F401
```

That is the whole integration. You now get, for free:

* the channel in `GET /api/v1/channels` and in the "Add inbox" wizard,
* a generated settings form built from `config_fields`,
* polling supervision with backoff (`supports_polling`) and/or a public webhook
  endpoint at `/api/v1/webhooks/acme/{token}` (`supports_webhook`),
* an optional per-inbox proxy (`supports_proxy`),
* contact/conversation routing, media storage, automations, outgoing webhooks,
  realtime updates and the full agent UI.

## Optional capabilities

Override only what the provider supports; the core degrades gracefully when a
method raises `NotImplementedError`:

```python
async def send_reaction(self, chat_source_id, message_source_id, emojis): ...
async def send_typing(self, chat_source_id): ...
async def edit_message(self, chat_source_id, message_source_id, content): ...
async def delete_message(self, chat_source_id, message_source_id): ...
async def mark_read(self, chat_source_id, message_source_id): ...
async def download_file(self, external_id) -> tuple[bytes, str | None, str | None]: ...
async def health_check(self) -> dict: ...
async def setup(self) -> dict: ...     # e.g. register the webhook upstream
async def teardown(self) -> None: ...  # e.g. remove it again
```

Advertise them in `capabilities` so the UI can hide controls the provider cannot
honour (`reactions`, `typing`, `edit`, `delete`, `voice`, `stickers`, `media`,
`reply`, `read_receipts`).

## Where the pieces plug in

```
provider  ──fetch_updates()/parse_webhook()──▶  InboundEvent
                                                    │
                        services.conversations.process_inbound_event()
                                                    │
              contact ▸ conversation ▸ message ▸ attachments ▸ automations
                                                    │
                              event bus ──▶ WebSocket + outgoing webhooks

agent UI ──▶ POST /conversations/{id}/messages ──▶ create_outgoing_message()
                                                    │
                                     deliver_message() ──▶ send_message()
```
