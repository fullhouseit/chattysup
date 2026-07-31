"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- General -------------------------------------------------------
    app_name: str = "ChattySup"
    environment: str = "development"
    debug: bool = False
    # Public base URL of this installation. Used to build webhook callbacks
    # and absolute attachment links.
    base_url: str = "http://localhost:8000"

    # --- Security ------------------------------------------------------
    secret_key: str = secrets.token_urlsafe(48)
    access_token_expire_minutes: int = 60 * 24 * 7
    # Feature flag: allow self-service signup. The very first user is always
    # allowed to register (bootstrap of the super admin) regardless of it.
    enable_registration: bool = False
    cors_origins: str = "*"

    # --- Database ------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./chattysup.db"

    # --- Storage -------------------------------------------------------
    storage_path: str = str(BASE_DIR / "storage")
    max_upload_size: int = 50 * 1024 * 1024

    # --- Networking ----------------------------------------------------
    # Global default proxy used by channels when they do not define their own.
    http_proxy: str | None = None

    # --- Workers -------------------------------------------------------
    # Run channel pollers inside the API process. Set to false when running a
    # dedicated worker process (`python -m app.workers.runner`).
    run_workers: bool = True
    automation_tick_seconds: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def storage_dir(self) -> Path:
        p = Path(self.storage_path)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
