from __future__ import annotations

from decimal import Decimal

import pytest

from src.brokers.paper.paper_broker import PaperBrokerAdapter
from src.core.entities import Order, OrderType, ProductType, TransactionType
from src.core.exceptions import OrderRejectedError


def _order(transaction_type: TransactionType, quantity: int = 10) -> Order:
    return Order(
        instrument_id="NSE:RELIANCE",
        transaction_type=transaction_type,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        quantity=quantity,
    )


def test_place_order_fills_immediately_at_last_price():
    broker = PaperBrokerAdapter()
    broker.connect()
    broker.set_last_price("NSE:RELIANCE", Decimal("2500"))

    order = broker.place_order(_order(TransactionType.BUY))

    assert order.status.value == "FILLED"
    assert order.filled_quantity == 10
    assert order.average_price == Decimal("2500")


def test_place_order_without_price_or_reference_is_rejected():
    broker = PaperBrokerAdapter()
    broker.connect()
    with pytest.raises(OrderRejectedError):
        broker.place_order(_order(TransactionType.BUY))


def test_position_tracked_after_fill():
    broker = PaperBrokerAdapter()
    broker.connect()
    broker.set_last_price("NSE:RELIANCE", Decimal("2500"))
    broker.place_order(_order(TransactionType.BUY, quantity=10))

    positions = broker.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == 10
    assert positions[0].average_price == Decimal("2500")


def test_buy_then_sell_flattens_position_and_realizes_pnl():
    broker = PaperBrokerAdapter()
    broker.connect()
    broker.set_last_price("NSE:RELIANCE", Decimal("2500"))
    broker.place_order(_order(TransactionType.BUY, quantity=10))

    broker.set_last_price("NSE:RELIANCE", Decimal("2600"))
    broker.place_order(_order(TransactionType.SELL, quantity=10))

    positions = broker.get_positions()
    assert positions[0].quantity == 0
    assert positions[0].realized_pnl == Decimal("1000")  # (2600-2500) * 10


def test_cancel_filled_order_is_rejected():
    broker = PaperBrokerAdapter()
    broker.connect()
    broker.set_last_price("NSE:RELIANCE", Decimal("2500"))
    order = broker.place_order(_order(TransactionType.BUY))

    with pytest.raises(OrderRejectedError):
        broker.cancel_order(order.client_order_id)
