"""Broker factory: constructs the configured IBrokerGateway/IMarketDataFeed pair.
This is the ONLY place that should branch on `settings.broker_provider`.
"""
from __future__ import annotations

from src.config.settings import Settings
from src.core.interfaces import IBrokerGateway, IMarketDataFeed


def build_broker_gateway(settings: Settings) -> IBrokerGateway:
    if settings.broker_provider == "paper":
        from src.brokers.paper.paper_broker import PaperBrokerAdapter

        return PaperBrokerAdapter()

    if settings.broker_provider == "angel_one":
        from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter

        return AngelOneBrokerAdapter(
            api_key=settings.angel_one_api_key,
            client_id=settings.angel_one_client_id,
            password=settings.angel_one_password,
            totp_secret=settings.angel_one_totp_secret,
        )

    if settings.broker_provider == "kite":
        from src.brokers.kite.kite_broker import KiteBrokerAdapter

        return KiteBrokerAdapter(
            api_key=settings.kite_api_key,
            api_secret=settings.kite_api_secret,
            access_token=settings.kite_access_token,
        )

    raise ValueError(f"Unknown BROKER_PROVIDER: {settings.broker_provider}")


def build_market_data_feed(settings: Settings) -> IMarketDataFeed:
    if settings.broker_provider == "paper":
        from src.brokers.paper.paper_broker import PaperMarketDataFeed

        return PaperMarketDataFeed()

    if settings.broker_provider == "angel_one":
        from src.brokers.angel_one.angel_one_broker import AngelOneMarketDataFeed

        return AngelOneMarketDataFeed(
            api_key=settings.angel_one_api_key,
            client_id=settings.angel_one_client_id,
            feed_token="",  # populate after SmartConnect session login
        )

    if settings.broker_provider == "kite":
        from src.brokers.kite.kite_broker import KiteMarketDataFeed

        return KiteMarketDataFeed(
            api_key=settings.kite_api_key,
            access_token=settings.kite_access_token,
        )

    raise ValueError(f"Unknown BROKER_PROVIDER: {settings.broker_provider}")
