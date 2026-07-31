"""ChattySup ASGI application.

Wires the REST API, the realtime WebSocket, the background workers and the
compiled single page application into one process.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.chatwoot import application_router as chatwoot_application_router
from .api.chatwoot import client_router as chatwoot_client_router
from .api.v1 import api_router
from .channels.base import ChannelError
from .config import settings
from .db import init_db
from .services import webhooks as webhook_service

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepare the database, the event listeners and the channel workers."""
    await init_db()
    webhook_service.install()

    try:
        from . import channels  # noqa: F401  (registers the built-in channels)
    except Exception:  # pragma: no cover - a broken channel must not block boot
        logger.exception("channel registry could not be imported")

    supervisor = scheduler = None
    if settings.run_workers:
        try:
            # Imported lazily so the API still boots without the worker package.
            from .workers import scheduler as scheduler_singleton
            from .workers import supervisor as supervisor_singleton

            supervisor, scheduler = supervisor_singleton, scheduler_singleton
            await supervisor.start()
            await scheduler.start()
        except Exception:  # pragma: no cover - workers are optional at boot
            logger.exception("background workers could not be started")

    try:
        yield
    finally:
        for worker in (scheduler, supervisor):
            if worker is None:
                continue
            try:
                await worker.stop()
            except Exception:  # pragma: no cover - shutdown must not raise
                logger.exception("worker shutdown failed")


app = FastAPI(
    title="ChattySup API",
    version=__version__,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ChannelError)
async def channel_error_handler(request: Request, exc: ChannelError) -> JSONResponse:
    """Surface upstream provider failures as a clean 502."""
    logger.warning("channel error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


app.include_router(api_router, prefix=API_PREFIX)

# Chatwoot compatibility surface — additive, and mounted *after* the native
# routers so it can never shadow them. The Application API only claims
# ``/api/v1/accounts/…``, which is not a native resource; the Client API lives
# under its own ``/public/api/v1`` root. Both carry their own prefix.
app.include_router(chatwoot_client_router)
app.include_router(chatwoot_application_router)


# ---------------------------------------------------------------------------
# Single page application
# ---------------------------------------------------------------------------
if INDEX_FILE.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve static files and hand every other path to the client router."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        # The Chatwoot Client API is a JSON-only surface: an unknown or
        # mistyped path there must answer Chatwoot's 404 body, not index.html.
        if full_path == "public" or full_path.startswith("public/"):
            return JSONResponse(
                status_code=404, content={"error": "Resource could not be found"}
            )
        candidate = (STATIC_DIR / full_path).resolve()
        if (
            full_path
            and STATIC_DIR in candidate.parents
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        return FileResponse(INDEX_FILE)

else:

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        """Friendly landing payload while the frontend has not been built."""
        return {
            "name": "ChattySup",
            "version": __version__,
            "message": (
                "The frontend bundle is not built yet. Run `npm run build` in "
                "frontend/ (the output lands in backend/app/static) or use the "
                "Vite dev server."
            ),
            "api": f"{API_PREFIX}/health",
            "docs": "/api/docs",
        }
