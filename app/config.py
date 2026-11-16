from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_path: Path
    token_secret: str
    token_ttl_minutes: int
    environment: str


def get_settings() -> Settings:
    database_path = Path(os.getenv("APP_DATABASE_PATH", ROOT / "data" / "inventory.db"))
    environment = os.getenv("APP_ENV", "development")
    token_secret = os.getenv("APP_TOKEN_SECRET", "local-development-secret-change-me")
    if environment == "production" and token_secret == "local-development-secret-change-me":
        raise RuntimeError("APP_TOKEN_SECRET phải được cấu hình riêng trong môi trường production")
    return Settings(
        database_path=database_path,
        token_secret=token_secret,
        token_ttl_minutes=int(os.getenv("APP_TOKEN_TTL_MINUTES", "480")),
        environment=environment,
    )
