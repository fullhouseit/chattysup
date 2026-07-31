"""Standalone worker process: ``python -m app.workers.runner``.

Runs the polling supervisor and the conversation scheduler without the HTTP
API. Use it when ``RUN_WORKERS=false`` so the web tier can be scaled
independently of the channel pollers.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from ..db import init_db
from . import scheduler as scheduler_module
from . import supervisor as supervisor_module

logger = logging.getLogger(__name__)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Ask the loop to set ``stop_event`` on SIGINT/SIGTERM when supported."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, AttributeError):
            loop.add_signal_handler(sig, stop_event.set)


async def run() -> None:
    """Start both workers and block until the process is asked to stop."""
    await init_db()

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    await supervisor_module.start()
    await scheduler_module.start()
    logger.info("ChattySup workers running — press Ctrl+C to stop")

    try:
        await stop_event.wait()
    except asyncio.CancelledError:  # pragma: no cover - propagated by the loop
        pass
    finally:
        await scheduler_module.stop()
        await supervisor_module.stop()


def main() -> None:
    """Console entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    main()
