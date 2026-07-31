"""Thin asynchronous client for the Telegram Bot API (9.x).

The client is deliberately dumb: it knows how to authenticate, how to shape a
request (JSON or multipart), how to unwrap the ``{"ok": true, "result": …}``
envelope and how to survive a ``429 Too Many Requests``. Every bit of Telegram
semantics lives in :mod:`app.channels.telegram.channel`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from ..base import ChannelError

logger = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"
#: Bot API hard limit for files a bot may download through ``getFile``.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
#: Telegram may ask us to wait; never sleep longer than this on a 429.
MAX_RETRY_AFTER = 30

#: A multipart part: ``(filename, bytes, mime_type)``.
FilePart = tuple[str, bytes, str | None]


class TelegramApi:
    """One authenticated HTTP session against ``api.telegram.org``.

    :param token: the bot token issued by @BotFather.
    :param proxy: optional ``http(s)://`` or ``socks5://`` proxy URL.
    :param timeout: default per-request timeout in seconds.
    """

    def __init__(
        self,
        token: str,
        *,
        proxy: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.token = token
        self.proxy = proxy or None
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    # -- plumbing --------------------------------------------------------
    @property
    def client(self) -> httpx.AsyncClient:
        """Lazily built ``httpx.AsyncClient`` bound to this bot."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=f"{API_ROOT}/bot{self.token}",
                proxy=self.proxy,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        """Release the underlying connection pool."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    # -- diagnostics -----------------------------------------------------
    def _transport_error(self, method: str, exc: Exception) -> str:
        """Describe a network failure in terms an operator can act on.

        ``httpx`` transport exceptions frequently carry an empty ``str()`` (a
        bare ``ConnectError('')`` for a refused socket, for instance), so the
        exception class and the current proxy have to be spelled out or the
        message degrades to "failed: " and tells nobody anything.
        """
        detail = str(exc).strip() or exc.__class__.__name__
        via = f" via proxy {self._safe_proxy()}" if self.proxy else " (no proxy configured)"

        if isinstance(exc, httpx.ProxyError):
            return (
                f"Telegram {method} failed: could not reach api.telegram.org through "
                f"the proxy {self._safe_proxy()} — {detail}"
            )
        if isinstance(exc, httpx.ConnectTimeout | httpx.ReadTimeout | httpx.WriteTimeout):
            return f"Telegram {method} timed out after {self.timeout:g}s{via} — {detail}"
        if isinstance(exc, httpx.ConnectError):
            return (
                f"Telegram {method} failed: cannot connect to api.telegram.org{via} — "
                f"{detail}. Check outbound network access, or configure a proxy for "
                f"this inbox if Telegram is blocked from this host."
            )
        return f"Telegram {method} failed{via}: {detail}"

    def _safe_proxy(self) -> str:
        """The proxy URL with any password redacted, safe to show in the UI."""
        if not self.proxy:
            return ""
        try:
            url = httpx.URL(self.proxy)
        except Exception:  # pragma: no cover - malformed URL, show the scheme only
            return "(configured)"
        if url.password:
            # `copy_with(password=…)` alone rewrites the whole userinfo and
            # would drop the username, so pass both.
            url = url.copy_with(username=url.username, password="***")
        return str(url)

    # -- requests --------------------------------------------------------
    async def call(
        self,
        method: str,
        *,
        files: dict[str, FilePart] | None = None,
        http_timeout: float | None = None,
        _retry: bool = True,
        **params: Any,
    ) -> Any:
        """Invoke a Bot API ``method`` and return its ``result`` payload.

        ``http_timeout`` overrides the socket timeout for this call only (long
        polling needs a window wider than the Telegram side ``timeout``).
        ``None`` parameters are dropped. When ``files`` is given the request is
        sent as ``multipart/form-data`` and complex parameters are JSON encoded,
        as the Bot API requires.

        :raises ChannelError: on transport failures or ``ok: false`` responses.
        """
        payload = {k: v for k, v in params.items() if v is not None}
        request_timeout = httpx.Timeout(
            http_timeout if http_timeout is not None else self.timeout
        )

        try:
            if files:
                data = {
                    k: (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
                    for k, v in payload.items()
                }
                response = await self.client.post(
                    f"/{method}", data=data, files=files, timeout=request_timeout
                )
            else:
                response = await self.client.post(
                    f"/{method}", json=payload, timeout=request_timeout
                )
        except httpx.HTTPError as exc:
            raise ChannelError(self._transport_error(method, exc)) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise ChannelError(
                f"Telegram {method} returned a non-JSON response "
                f"(HTTP {response.status_code})"
            ) from exc

        if body.get("ok"):
            return body.get("result")

        description = body.get("description") or "unknown error"
        code = body.get("error_code", response.status_code)
        retry_after = int((body.get("parameters") or {}).get("retry_after") or 0)

        if code == 429 and _retry:
            delay = min(retry_after or 1, MAX_RETRY_AFTER)
            logger.warning(
                "Telegram rate limited %s, retrying in %ss (%s)", method, delay, description
            )
            await asyncio.sleep(delay)
            return await self.call(
                method, files=files, http_timeout=http_timeout, _retry=False, **params
            )

        raise ChannelError(f"Telegram {method} failed [{code}]: {description}")

    # -- files -----------------------------------------------------------
    async def get_file(self, file_id: str) -> dict[str, Any]:
        """Return the ``File`` object describing ``file_id``."""
        return await self.call("getFile", file_id=file_id)

    def file_url(self, file_path: str) -> str:
        """Absolute download URL for a ``File.file_path``."""
        return f"{API_ROOT}/file/bot{self.token}/{file_path}"

    async def download(self, file_path: str) -> bytes:
        """Download a file previously resolved through :meth:`get_file`."""
        try:
            response = await self.client.get(self.file_url(file_path))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ChannelError(self._transport_error("file download", exc)) from exc
        return response.content
