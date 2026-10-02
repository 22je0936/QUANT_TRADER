from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter
from src.core.entities import Exchange, Order, OrderStatus, OrderType, ProductType, TransactionType
from src.core.exceptions import OrderRejectedError


class FakeSmartConnect:
    def __init__(self) -> None:
        self.placed_params: dict[str, Any] | None = None
        self.cancelled: tuple[str, str] | None = None
        self.order_status = "open"
        self.filled_shares = 0
        self.average_price = "0"

    def placeOrderFullResponse(self, params: dict[str, Any]) -> dict[str, Any]:
        self.placed_params = params
        return {"status": True, "data": {"orderid": "BROKER-123"}}

    def orderBook(self) -> dict[str, Any]:
        return {
            "status": True,
            "data": [
                {
                    "orderid": "BROKER-123",
                    "orderstatus": self.order_status,
                    "filledshares": str(self.filled_shares),
                    "averageprice": self.average_price,
                }
            ],
        }

    def cancelOrder(self, order_id: str, variety: str) -> dict[str, Any]:
        self.cancelled = (order_id, variety)
        self.order_status = "cancelled"
        return {"status": True}

    def modifyOrder(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": True, "data": {"orderid": params["orderid"]}}


def _order(exchange: Exchange = Exchange.BSE) -> Order:
    return Order(
        instrument_id=f"{exchange.value}:TEST",
        transaction_type=TransactionType.BUY,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        quantity=2,
        price=Decimal("100.00"),
        exchange=exchange,
        trading_symbol="TEST-EQ",
        symbol_token="12345",
    )


def _adapter(client: FakeSmartConnect) -> AngelOneBrokerAdapter:
    adapter = AngelOneBrokerAdapter("api", "client", "password", "totp")
    adapter._client = client
    return adapter


def test_place_order_sends_explicit_bse_exchange_and_instrument_details():
    client = FakeSmartConnect()
    adapter = _adapter(client)
    order = _order()

    result = adapter.place_order(order)

    assert client.placed_params is not None
    assert client.placed_params["exchange"] == "BSE"
    assert client.placed_params["tradingsymbol"] == "TEST-EQ"
    assert client.placed_params["symboltoken"] == "12345"
    assert result.broker_order_id == "BROKER-123"
    assert result.status == OrderStatus.OPEN


def test_order_book_updates_partial_fill_and_average_price():
    client = FakeSmartConnect()
    client.order_status = "partially filled"
    client.filled_shares = 1
    client.average_price = "99.95"
    adapter = _adapter(client)
    order = adapter.place_order(_order())

    result = adapter.get_order_status(order.client_order_id)

    assert result.status == OrderStatus.PARTIALLY_FILLED
    assert result.filled_quantity == 1
    assert result.average_price == Decimal("99.95")


def test_cancel_uses_broker_order_id_and_reconciles_final_status():
    client = FakeSmartConnect()
    adapter = _adapter(client)
    order = adapter.place_order(_order())

    result = adapter.cancel_order(order.client_order_id)

    assert client.cancelled == ("BROKER-123", "NORMAL")
    assert result.status == OrderStatus.CANCELLED


def test_angel_one_rejects_orders_without_exchange_metadata():
    adapter = _adapter(FakeSmartConnect())
    order = _order()
    order.exchange = None

    with pytest.raises(OrderRejectedError, match="require exchange"):
        adapter.place_order(order)
