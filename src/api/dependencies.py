"""FastAPI dependency wiring — thin composition root. This is one of the few
places allowed to construct concrete broker/risk instances; everything else
(services, strategies) receives them via constructor injection.
"""
from __future__ import annotations

from functools import lru_cache

from src.brokers.factory import build_broker_gateway
from src.config.settings import Settings, get_settings
from src.core.interfaces import IBrokerGateway
from src.risk.risk_manager import RiskLimits, RiskManager


@lru_cache
def get_risk_manager() -> RiskManager:
    settings = get_settings()
    limits = RiskLimits(
        max_daily_loss=settings.max_daily_loss,
        max_position_size=settings.max_position_size,
        max_order_quantity=settings.max_order_quantity,
    )
    return RiskManager(limits=limits)


_broker_singleton: IBrokerGateway | None = None


def get_broker_gateway(settings: Settings | None = None) -> IBrokerGateway:
    global _broker_singleton
    if _broker_singleton is None:
        settings = settings or get_settings()
        _broker_singleton = build_broker_gateway(settings)
        _broker_singleton.connect()
    return _broker_singleton
