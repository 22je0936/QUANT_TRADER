"""Construct the project's Angel One broker and market-data adapters."""
from __future__ import annotations

from src.config.settings import Settings
from src.core.interfaces import IBrokerGateway, IMarketDataFeed
from src.brokers.angel_one.angel_one_broker import (
    AngelOneBrokerAdapter,
    AngelOneMarketDataFeed,
)


def build_broker_gateway(settings: Settings) -> IBrokerGateway:
    return AngelOneBrokerAdapter(
        api_key=settings.angel_one_api_key,
        client_id=settings.angel_one_client_id,
        password=settings.angel_one_password,
        totp_secret=settings.angel_one_totp_secret,
    )


def build_market_data_feed(settings: Settings) -> IMarketDataFeed:
    return AngelOneMarketDataFeed(
        api_key=settings.angel_one_api_key,
        client_id=settings.angel_one_client_id,
        feed_token="",  # populated after SmartConnect session login
    )
