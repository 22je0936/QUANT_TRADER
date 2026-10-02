"""Centralized application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from decimal import Decimal
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    broker_provider: Literal["paper", "angel_one", "kite"] = "paper"

    # Angel One
    angel_one_api_key: str = ""
    angel_one_client_id: str = ""
    angel_one_password: str = ""
    angel_one_totp_secret: str = ""

    # Arbitrage guardrails. Live execution is intentionally unsupported for now.
    live_trading_enabled: bool = False
    live_trading_acknowledgement: str = ""
    arbitrage_max_exposure_inr: Decimal = Decimal("300")
    arbitrage_max_daily_loss_inr: Decimal = Decimal("60")
    arbitrage_max_fallback_loss_inr: Decimal = Decimal("30")

    # Kite
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_access_token: str = ""

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "quant_trader"
    postgres_user: str = "quant_trader"
    postgres_password: str = "change_me"

    # ClickHouse
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_db: str = "quant_trader"
    clickhouse_user: str = "default"
    clickhouse_password: str = "change_me"

    # Redis
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
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
