"""Centralized application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from decimal import Decimal
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    # Angel One
    angel_one_api_key: str = ""
    angel_one_client_id: str = ""
    angel_one_password: str = ""
    angel_one_totp_secret: str = ""

    # Live arbitrage guardrails.
    live_trading_enabled: bool = False
    live_trading_acknowledgement: str = ""
    arbitrage_max_exposure_inr: Decimal = Decimal("300")
    arbitrage_max_daily_loss_inr: Decimal = Decimal("60")
    arbitrage_max_fallback_loss_inr: Decimal = Decimal("30")

    # FUTURE-ONLY INFRASTRUCTURE
    # Postgres / ClickHouse are intentionally not active in the default arbitrage runtime.
    # These values are kept only as placeholders for possible future analytics or storage layers.
    # Do not treat them as required services for the current live arbitrage workflow.

    # Redis (optional cache/state placeholder; not required for current arbitrage flow)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Security
    jwt_secret_key: str = "change_me_dev_only"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    credential_encryption_key: str = ""

    # Risk defaults
    max_daily_loss: float = 25000
    max_position_size: float = 100000
    max_order_quantity: int = 1000

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
