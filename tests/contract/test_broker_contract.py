"""Contract test suite: every IBrokerGateway implementation MUST pass these
tests unmodified. This is what proves Angel One <-> Kite <-> Paper are truly
interchangeable. Add a new adapter to `_broker_factories` once it's ready.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.brokers.paper.paper_broker import PaperBrokerAdapter
from src.core.entities import Order, OrderType, ProductType, TransactionType
from src.core.interfaces import IBrokerGateway


def _make_paper_broker() -> IBrokerGateway:
    broker = PaperBrokerAdapter()
    broker.connect()
    broker.set_last_price("NSE:RELIANCE", Decimal("2500"))
    return broker


# Register additional adapters here once credentials/sandboxes are available,
# e.g. ("angel_one", _make_angel_one_broker), ("kite", _make_kite_broker).
_broker_factories = [
    ("paper", _make_paper_broker),
]


@pytest.fixture(params=_broker_factories, ids=[name for name, _ in _broker_factories])
def broker(request) -> IBrokerGateway:  # noqa: ANN001
    _, factory = request.param
    return factory()


def test_place_order_returns_broker_order_id(broker: IBrokerGateway):
    order = Order(
        instrument_id="NSE:RELIANCE",
        transaction_type=TransactionType.BUY,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        quantity=1,
    )
    result = broker.place_order(order)
    assert result.broker_order_id is not None


def test_get_positions_returns_a_list(broker: IBrokerGateway):
    assert isinstance(broker.get_positions(), list)


def test_get_margins_returns_a_dict(broker: IBrokerGateway):
    assert isinstance(broker.get_margins(), dict)
