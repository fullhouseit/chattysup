"""Compatibility layers that expose ChattySup data in foreign shapes.

Everything in this package is **additive**: it never replaces our native API or
our native webhook payloads, it only offers a second representation of exactly
the same data.

Currently implemented:

* :mod:`app.compat.chatwoot` — Chatwoot's ``webhook_data`` payload shapes and
  the Chatwoot outgoing-webhook event envelopes.
"""
from __future__ import annotations

from . import chatwoot

__all__ = ["chatwoot"]
