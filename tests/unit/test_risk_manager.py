from __future__ import annotations

from decimal import Decimal

import pytest

from src.core.entities import Order, OrderType, ProductType, TransactionType
from src.core.exceptions import RiskLimitBreachedError
from src.risk.risk_manager import RiskLimits, RiskManager


def _order(quantity: int = 10, price: Decimal | None = Decimal("100")) -> Order:
    return Order(
        instrument_id="NSE:RELIANCE",
        transaction_type=TransactionType.BUY,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        quantity=quantity,
        price=price,
    )


def test_order_within_limits_passes():
    manager = RiskManager(limits=RiskLimits(max_order_quantity=50, max_exposure_per_symbol=Decimal("10000")))
    manager.validate_order(_order(quantity=10, price=Decimal("100")))  # should not raise


def test_order_exceeding_max_quantity_is_blocked():
    manager = RiskManager(limits=RiskLimits(max_order_quantity=5))
    with pytest.raises(RiskLimitBreachedError):
        manager.validate_order(_order(quantity=10))


def test_order_exceeding_exposure_limit_is_blocked():
    manager = RiskManager(limits=RiskLimits(max_exposure_per_symbol=Decimal("500")))
    with pytest.raises(RiskLimitBreachedError):
        manager.validate_order(_order(quantity=10, price=Decimal("100")))  # 1000 exposure > 500 limit


def test_daily_loss_breach_engages_kill_switch_and_blocks_further_orders():
    manager = RiskManager(limits=RiskLimits(max_daily_loss=Decimal("1000")))
    manager.record_fill_pnl(Decimal("-1200"))

    assert manager.state.kill_switch_engaged is True
    with pytest.raises(RiskLimitBreachedError):
        manager.validate_order(_order())


def test_reset_daily_state_clears_kill_switch():
    manager = RiskManager(limits=RiskLimits(max_daily_loss=Decimal("1000")))
    manager.record_fill_pnl(Decimal("-1200"))
    manager.reset_daily_state()

    assert manager.state.kill_switch_engaged is False
    manager.validate_order(_order())  # should not raise
