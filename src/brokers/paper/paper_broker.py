"""Simulated broker: fills orders instantly at the last known price. Used for every
strategy before it is allowed to touch a live broker, and as the execution engine
inside the backtester (same code path as live/paper trading).
"""
from __future__ import annotations

from decimal import Decimal

from src.core.entities import Order, OrderStatus, Position, TransactionType
from src.core.exceptions import OrderRejectedError
from src.core.interfaces import IBrokerGateway, IMarketDataFeed, TickCallback
from src.infra.logging import get_logger

logger = get_logger(__name__)


class PaperBrokerAdapter(IBrokerGateway):
    """In-memory paper trading broker. Deterministic, no network calls."""

    def __init__(self, starting_cash: Decimal = Decimal("1000000")) -> None:
        self._connected = False
        self._orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}
        self._cash = starting_cash
        self._last_price: dict[str, Decimal] = {}

    def connect(self) -> None:
        self._connected = True
        logger.info("paper_broker_connected")

    def disconnect(self) -> None:
        self._connected = False
        logger.info("paper_broker_disconnected")

    def set_last_price(self, instrument_id: str, price: Decimal) -> None:
        """Test/backtest hook: feed the price the paper broker will fill orders at."""
        self._last_price[instrument_id] = price

    def place_order(self, order: Order) -> Order:
        if not self._connected:
            raise OrderRejectedError("Paper broker is not connected")
        if order.quantity <= 0:
            raise OrderRejectedError("Order quantity must be positive")

        fill_price = order.price or self._last_price.get(order.instrument_id)
        if fill_price is None:
            raise OrderRejectedError(f"No reference price available for {order.instrument_id}")

        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.average_price = fill_price
        order.broker_order_id = f"PAPER-{order.client_order_id}"

        self._orders[order.client_order_id] = order
        self._apply_fill(order, fill_price)
        logger.info("paper_order_filled", client_order_id=order.client_order_id)
        return order

    def modify_order(self, client_order_id: str, **changes: object) -> Order:
        order = self._require_order(client_order_id)
        for key, value in changes.items():
            setattr(order, key, value)
        return order

    def cancel_order(self, client_order_id: str) -> Order:
        order = self._require_order(client_order_id)
        if order.status == OrderStatus.FILLED:
            raise OrderRejectedError("Cannot cancel a filled order")
        order.status = OrderStatus.CANCELLED
        return order

    def get_order_status(self, client_order_id: str) -> Order:
        return self._require_order(client_order_id)

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_holdings(self) -> list[Position]:
        return []

    def get_margins(self) -> dict:
        return {"cash": float(self._cash)}

    def _require_order(self, client_order_id: str) -> Order:
        order = self._orders.get(client_order_id)
        if order is None:
            raise OrderRejectedError(f"Unknown client_order_id: {client_order_id}")
        return order

    def _apply_fill(self, order: Order, fill_price: Decimal) -> None:
        signed_qty = order.quantity if order.transaction_type == TransactionType.BUY else -order.quantity
        position = self._positions.get(order.instrument_id)
        cost = fill_price * abs(signed_qty)
        self._cash += -cost if signed_qty > 0 else cost

        if position is None:
            self._positions[order.instrument_id] = Position(
                instrument_id=order.instrument_id,
                quantity=signed_qty,
                average_price=fill_price,
                strategy_id=order.strategy_id,
            )
            return

        new_quantity = position.quantity + signed_qty
        if new_quantity == 0:
            realized = (fill_price - position.average_price) * signed_qty * -1
            position.realized_pnl += realized
            position.quantity = 0
        elif (position.quantity > 0) == (signed_qty > 0):
            total_cost = position.average_price * abs(position.quantity) + fill_price * abs(signed_qty)
            position.average_price = total_cost / abs(new_quantity)
            position.quantity = new_quantity
        else:
            position.quantity = new_quantity
        self._positions[order.instrument_id] = position


class PaperMarketDataFeed(IMarketDataFeed):
    """Simulated tick feed — replays ticks pushed via `push_tick` (used by backtester)."""

    def __init__(self) -> None:
        self._subscribed: set[str] = set()
        self._callbacks: list[TickCallback] = []

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def subscribe(self, instrument_ids: list[str]) -> None:
        self._subscribed.update(instrument_ids)

    def unsubscribe(self, instrument_ids: list[str]) -> None:
        self._subscribed.difference_update(instrument_ids)

    def on_tick(self, callback: TickCallback) -> None:
        self._callbacks.append(callback)

    def push_tick(self, tick) -> None:  # noqa: ANN001 - Tick, avoids circular import at module load
        if tick.instrument_id in self._subscribed:
            for callback in self._callbacks:
                callback(tick)
