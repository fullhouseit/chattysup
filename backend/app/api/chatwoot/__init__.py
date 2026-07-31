"""Chatwoot-compatible REST surface.

Two routers, mounted next to (never instead of) our native API:

``client_router``
    Chatwoot's **Client / Public API**, ``/public/api/v1/inboxes/…``. No token:
    the ``inbox_identifier`` and the contact's ``source_id`` in the path *are*
    the credentials, exactly as in Chatwoot.

``application_router``
    A subset of Chatwoot's **Application API**, ``/api/v1/accounts/{id}/…``,
    authenticated with the ``api_access_token`` header (our ``Bearer`` scheme is
    accepted too).

Both render responses through :mod:`app.compat.chatwoot`, and both mutate state
only through :mod:`app.services.conversations`, so realtime events, automations
and our native webhooks fire exactly as they do for the native API.

Error bodies follow ``RequestExceptionHandler``: ``404``/``ParameterMissing``
use the key ``error``, ``RecordInvalid`` uses ``message``. FastAPI's default
``{"detail": …}`` envelope is therefore bypassed with a custom route class
rather than an app-level handler, so nothing about the native API changes.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

#: Namespace for the synthetic conversation ``uuid`` Chatwoot clients expect.
#: ChattySup has no uuid column, so it is derived from the conversation id and
#: is therefore stable for the lifetime of the row.
_UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


class ChatwootError(Exception):
    """An error rendered in Chatwoot's body shape instead of FastAPI's."""

    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        super().__init__(body)
        self.status_code = status_code
        self.body = body


def not_found(message: str = "Resource could not be found") -> ChatwootError:
    return ChatwootError(404, {"error": message})


def unauthorized(message: str = "Invalid Access Token") -> ChatwootError:
    return ChatwootError(401, {"error": message})


def forbidden(message: str) -> ChatwootError:
    """``render json: {error: …}, status: :forbidden``."""
    return ChatwootError(403, {"error": message})


def invalid(message: str, attributes: list[str] | None = None) -> ChatwootError:
    """``render_record_invalid`` — note the key is ``message``, not ``error``."""
    body: dict[str, Any] = {"message": message}
    if attributes is not None:
        body["attributes"] = attributes
    return ChatwootError(422, body)


def parameter_missing(message: str) -> ChatwootError:
    return ChatwootError(422, {"error": message})


class ChatwootRoute(APIRoute):
    """Route class translating :class:`ChatwootError` into a Chatwoot body."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except ChatwootError as exc:
                return JSONResponse(status_code=exc.status_code, content=exc.body)

        return handler


def conversation_uuid(conversation_id: int) -> str:
    return str(uuid.uuid5(_UUID_NAMESPACE, f"chattysup-conversation-{conversation_id}"))


async def read_params(request: Request) -> dict[str, Any]:
    """Chatwoot accepts JSON and form encoded bodies interchangeably."""
    content_type = (request.headers.get("content-type") or "").lower()
    if content_type.startswith("multipart/") or content_type.startswith(
        "application/x-www-form-urlencoded"
    ):
        form = await request.form()
        params: dict[str, Any] = {}
        for key in form.keys():  # noqa: SIM118 - multi-dict needs getlist
            values = form.getlist(key)
            params[key.removesuffix("[]")] = values if len(values) > 1 else values[0]
        return params
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


from .application import router as application_router  # noqa: E402
from .client import router as client_router  # noqa: E402

__all__ = [
    "ChatwootError",
    "ChatwootRoute",
    "application_router",
    "client_router",
    "conversation_uuid",
    "forbidden",
    "invalid",
    "not_found",
    "parameter_missing",
    "read_params",
    "unauthorized",
]
